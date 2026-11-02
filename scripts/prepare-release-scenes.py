#!/usr/bin/env python3
"""Regenerate immutable release scene snapshots using the deployed app factory.

No account data, budgets, models, trained libraries, or live files are changed.
Only new versioned presets are added to the existing preset root.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

from geneloop_service import load_plan, read, save, same_data, assert_scene_snapshot


def prepare(plan_path, output, public_origin=None):
    old = load_plan(plan_path)
    output = Path(output).absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    gateway = read(old['gateway_config'])
    deployment = gateway['memberSceneDeployment']
    root = Path(deployment['projectRoot']).resolve(strict=True)
    sys.path.insert(0, str(root))
    from src.adapters.scenario import prepare_scenario
    from src.adapters.harless_scenarios import prepare_scene_registry, WORKSPACE
    from src.adapters.harless_product_prompt import product_persona
    registry_path = root / 'config/harless-scenes.json'
    definitions = read(registry_path)['scenes']
    owner = read(old['owner']['env']['SSS_WEB_POLICY'])
    plan = copy.deepcopy(old)
    for key in ('HARLESS_PPT_RUNTIME_BUNDLE','HARLESS_PAPER_RUNTIME_BUNDLE','HARLESS_DATA_RUNTIME_BUNDLE'):
        if os.environ.get(key):
            raise RuntimeError('Private library overrides require a separately reviewed release recipe')
    environment = {'SSS_PYTHON': deployment['pythonExecutable']}
    mapping = {'pptMasterRoot':'GENELOOP_PPT_MASTER_ROOT','pdfToolchainRoot':'HARLESS_PDF_TOOLCHAIN_ROOT',
               'pdfOcrRoot':'GENELOOP_PDF_OCR_ROOT','fontRoot':'HARLESS_PPT_FONT_ROOT',
               'rendererRoot':'HARLESS_PPT_RENDERER_ROOT','paperRendererRoot':'HARLESS_PAPER_RENDERER_ROOT','videoRendererConfig':'GENELOOP_VIDEO_RENDERER_CONFIG',
               'videoMotifStore':'GENELOOP_VIDEO_MOTIF_STORE','videoMotifOwner':'GENELOOP_VIDEO_MOTIF_OWNER'}
    for key, env in mapping.items():
        if deployment.get(key): environment[env] = deployment[key]
    if deployment.get('antiwordRoot'):
        environment['HARLESS_ANTIWORD_BIN'] = str(Path(deployment['antiwordRoot'])/'usr/bin/antiword')
    os.environ.update(environment)
    stamp = 'sss-release-' + old.get('source_sha', 'prepared')[:12] + '-' + uuid4().hex[:8]
    for label, policy in (('owner', owner), ('member', gateway['memberPolicy'])):
        default_id = policy['capability_profile']
        definition = next(row for row in definitions if row['id'] == default_id)
        prepared = prepare_scenario(root/definition['scenario'],case=definition.get('case',''),
                                    session_workspace=WORKSPACE if definition.get('adapter') else None,web_deployment=True)
        generated = output / ('prepared-' + label)
        scenes = prepare_scene_registry(root,registry_path,default_id=default_id,prepared_default=prepared,
                    output=generated,embedding_endpoint=policy['embedding_endpoint'],embedding_model=policy['embedding_model'])
        default_preset = generated/'presets/sss-task'
        default_preset.mkdir(mode=0o700,parents=True)
        rows = [{'id':'sss-persona','name':'@deepseek-ai/dsh-persona','config':product_persona()},
                *([] if definition.get('adapter') else prepared['mcp_rows'])]
        if prepared['environment_references']:
            raise RuntimeError('Release scene requires a separately reviewed credential reference')
        save(default_preset/'agent.cordis.yml',rows)
        save(default_preset/'preset.yml',{'name':'GeneLoop · '+definition['label']})
        for scene in scenes:
            for row in scene.get('mcp_rows',[]):
                env=row['config'].get('env',{})
                if env.get('HARLESS_PRIVATE_ROOT') == str(generated.resolve()):
                    env['HARLESS_PRIVATE_ROOT']=policy['output']
            original=scene['preset']
            scene['preset']=stamp+'-'+label+'-'+scene['id']
            source=generated/'presets'/original
            if source.exists():
                shutil.copytree(source,Path(policy['output'])/'presets'/scene['preset'])
        selected=next(row for row in scenes if row['id']==default_id)
        policy.update(scenes=scenes,allowed_tools=selected['allowed_tools'],
                      scene_registry_sha256=hashlib.sha256(registry_path.read_bytes()).hexdigest())
    if deployment.get('videoRenderer'):gateway['ownerCommandOutput']=owner['output']
    old_patch=old['owner']['argv'][old['owner']['argv'].index('--patch')+1]
    patch=read(old_patch)
    default_preset=next(row['preset'] for row in owner['scenes'] if row['id']==owner['capability_profile'])
    for plugin in patch:
        if 'includeShippedRoot' in plugin.get('config',{}):plugin['config']['default']=default_preset
    if public_origin:
        from urllib.parse import urlparse
        from geneloop_service import valid_public_origin
        if not valid_public_origin(public_origin): raise RuntimeError('Invalid public origin')
        hostname=urlparse(public_origin).hostname
        gateway['publicOrigin']=public_origin
        argv=plan['owner']['argv'];argv[argv.index('--trusted-host')+1]=hostname
        for plugin in patch:
            if 'trustedHosts' in plugin.get('config',{}):plugin['config']['trustedHosts']=[hostname]
    files={old['gateway_config']:str(output/'gateway.json'),old['owner']['env']['SSS_WEB_POLICY']:str(output/'owner-policy.json'),old_patch:str(output/'owner.patch.yml')}
    for role in ('owner','gateway'):
        plan[role]['argv']=[files.get(value,value) for value in plan[role]['argv']]
    plan['gateway_config']=str(output/'gateway.json')
    plan['owner']['env']['SSS_WEB_POLICY']=str(output/'owner-policy.json')
    save(output/'gateway.json',gateway);save(output/'owner-policy.json',owner);save(output/'owner.patch.yml',patch)
    save(output/'service.json',plan)
    same_data(old,plan)
    assert_scene_snapshot(plan)
    save(output/'scene-preparation.json',{'source_sha':old.get('source_sha'),'source_root':str(root),
        'scene_registry_sha256':owner['scene_registry_sha256'],'presets_prefix':stamp,
        'model_calls':0,'training_calls':0,'live_files_modified':False})
    return output/'service.json'

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--public-origin')
    args=parser.parse_args()
    print(prepare(args.plan,args.output,args.public_origin))
