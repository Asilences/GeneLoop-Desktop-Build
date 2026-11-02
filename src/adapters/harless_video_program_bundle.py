"""Admit the existing published video program form without changing its rules.

The original TypeScript resolver checks publication, validation gates, source
witnesses and program digests. This module only freezes the web deployment and
exposes the same learned tools alongside the existing video tools.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

from scenarios.remotion_edit.web_programs import PublishedPrograms
from src.adapters.source_program_mcp import learned_tool_definitions

# Product deployment snapshot only; no learning/publication rule is altered.
VIDEO_RUNTIME_CODE=(
    'scenarios/remotion_edit/web_server.py','scenarios/remotion_edit/web_programs.py',
    'scenarios/remotion_edit/web-tool-schemas.json','scenarios/remotion_edit/web-scenario.json',
    'scenarios/remotion_edit/structured/server.py','scenarios/remotion_edit/server.py',
    'scripts/materialize-source-program.mjs','src/adapters/source_program_runtime.ts',
    'src/adapters/source_program_mcp.py','src/adapters/rsi_protocol.ts',
    'schemas/rsi-protocol-v1.schema.json','src/adapters/harless_video_program_bundle.py',
    'src/adapters/harless_video_program.ts','src/adapters/dsh_web_tasks.ts',
    'src/adapters/harless_scenarios.py','src/adapters/harless_settings.ts',
    'src/adapters/geneloop_video.ts','src/adapters/geneloop_command_broker.ts',
    'src/adapters/session_files.py','src/motif_core/online_skill_runtime.mjs','package-lock.json',
)

def runtime_code_locks(root):
    result={}
    for name in VIDEO_RUNTIME_CODE:
        path=root/name
        if path.is_symlink() or not path.is_file() or path.resolve(strict=True)!=path:
            raise ValueError('video runtime code is redirected or missing')
        result[str(path)]=sha(path)
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixed_store(store):
    root=Path(store)
    if (not root.is_absolute() or root.is_symlink() or root.resolve(strict=True)!=root
            or not root.is_dir() or root==root.parent):
        raise ValueError('video program store is not a fixed directory')
    def read(path):
        stat=path.lstat()
        if path.is_symlink() or not path.is_file() or stat.st_nlink!=1 or stat.st_size>4_000_000:
            raise ValueError('video program runtime file is redirected or oversized')
        return json.loads(path.read_text(encoding='utf-8'))
    pointer=read(root/'latest.json')
    pattern=r'round-[a-f0-9]{24}/(?:policy|source-library)\.json'
    if (not isinstance(pointer,dict) or any(not isinstance(pointer.get(k),str) or
            not re.fullmatch(pattern,pointer[k]) for k in ('policy','library')) or
            pointer['policy'].split('/')[0]!=pointer['library'].split('/')[0]):
        raise ValueError('video program pointer must select one complete published round')
    directory=root/pointer['policy'].split('/')[0]
    if (directory.is_symlink() or directory.resolve(strict=True)!=directory or not directory.is_dir()
            or {p.name for p in root.iterdir()}!={'latest.json',directory.name}):
        raise ValueError('video program deployment contains non-runtime evidence')
    names={'policy.json','source-library.json','rsi-update.json','rsi-publication.json'}
    if {p.name for p in directory.iterdir()}!=names:
        raise ValueError('video program publication receipt set changed')
    for name in names:read(directory/name)
    files=[root/'latest.json',*(directory/name for name in sorted(names))]
    return root,{str(path):sha(path) for path in files}


def load_video_program_bundle(root:Path,store:str,owner:str):
    if not isinstance(owner,str) or not re.fullmatch(r'[a-zA-Z0-9._-]{1,128}',owner):
        raise ValueError('video program owner is invalid')
    directory,locks=fixed_store(store)
    published=PublishedPrograms(str(directory),owner)
    policy=published.policy
    # This is admission of a published form, never a new promotion. The
    # original TS loader has already checked the complete RSI publication.
    if policy['verdict'].get('accepted') is not True:
        raise ValueError('video program policy is not published')
    schema_path=root/'scenarios/remotion_edit/web-tool-schemas.json'
    baseline=json.loads(schema_path.read_text(encoding='utf-8'))
    names=json.loads((root/'scenarios/remotion_edit/web-scenario.json').read_text())['allowed_tools']
    if (not isinstance(baseline,list) or len(baseline)!=11 or
            [r.get('name') for r in baseline]!=names or
            any(not isinstance(r.get('description'),str) or not isinstance(r.get('parameters'),dict) for r in baseline)):
        raise ValueError('current complete native video schemas are missing')
    learned=learned_tool_definitions(published.catalog['programs'],published.naming,published.binding)
    schemas=[{'name':'mcp__remotion__'+tool.name,'description':tool.description,'parameters':tool.input_schema} for tool in learned]
    all_names=[r['name'] for r in baseline+schemas]
    if not schemas or len(set(all_names))!=len(all_names):
        raise ValueError('published video tools are empty or overlap native tools')
    published.check()
    if fixed_store(store)[1]!=locks:raise ValueError('video program store changed during admission')
    library=Path(published.library_path)
    return {'runtime_kind':'video_program_v1','runtime_mode':'execute',
        'runtime_library':str(library),'runtime_library_sha256':sha(library),
        'video_program_store':str(directory),'video_program_owner':owner,
        'video_program_file_locks':locks,'video_program_policy_digest':policy['digest'],
        'video_program_library_digest':policy['library_digest'],
        'video_program_tools':[r['name'] for r in schemas],
        'video_program_agent_instruction':policy['form'].get('agent_instruction',''),
        'certified_tool_schemas':sorted(baseline+schemas,key=lambda row:row['name']),
        'certified_code_locks':runtime_code_locks(root),
        'certification_scope':'published_source_program_form',
        'quality_cost_promoted':True}


def configure_video_programs(root:Path,scene:dict,store:str|None,owner:str|None):
    if not store and not owner:
        scene['rsi_unavailable_reason']='video_program_not_deployed'
        return
    if not store or not owner:
        raise ValueError('video program deployment requires store and owner')
    info=load_video_program_bundle(root,store,owner)
    scene.update(info)
    scene['allowed_tools']=[*scene['allowed_tools'],*info['video_program_tools']]
    for row in scene['mcp_rows']:
        if row['config']['serverName']=='remotion':
            row['config'].setdefault('env',{}).update(GENELOOP_VIDEO_MOTIF_STORE=info['video_program_store'],
                GENELOOP_VIDEO_MOTIF_OWNER=owner)
    scene['config_sha256']=hashlib.sha256(json.dumps({'parent':scene['config_sha256'],
        'policy':info['video_program_policy_digest'],'library':info['video_program_library_digest'],
        'files':info['video_program_file_locks'],'tools':info['video_program_tools'],
        'instruction':info['video_program_agent_instruction']},sort_keys=True).encode()).hexdigest()
