#!/usr/bin/env python3
"""Review the paired published-video adapter; preserve existing Paper/PPT IR.

The video program library is an already published, independently stored form.
This export only rebinds the unchanged Paper/PPT libraries to reviewed shared
runtime code. It never retrains, re-promotes or rewrites any learned program.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('video_paired_compat',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(spec);spec.loader.exec_module(compat)
REVIEWED={
    'scenarios/remotion_edit/web_server.py','scripts/harless_member_scenes.mjs',
    'src/adapters/dsh_web_tasks.ts','src/adapters/harless_scenarios.py',
    'src/adapters/harless_task_progress.ts',
}
compat.RELEASES=[
    ('paper-web-v40','paper-web-v41','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',REVIEWED),
    ('ppt-master-v37','ppt-master-v38','ppt',
     'scenarios/ppt_master/contracts.json',REVIEWED|{'src/adapters/harless_settings.ts'}),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS={
    'scripts/reexport-video-paired-compat.py','scripts/geneloop_service.py',
    'scripts/prepare-release-scenes.py','scripts/harless_video_motif_store.mjs',
    'scripts/materialize-source-program.mjs',
    'scenarios/remotion_edit/web_programs.py','scenarios/remotion_edit/web-tool-schemas.json',
    'src/adapters/harless_video_program_bundle.py','src/adapters/harless_video_program.ts',
    'src/adapters/harless_settings.ts','src/adapters/source_program_runtime.ts',
    'src/adapters/source_program_mcp.py','src/adapters/rsi_protocol.ts',
    'schemas/rsi-protocol-v1.schema.json',
}
original_record,original_prepare=compat.compatibility_record,compat.prepare

def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value.update(release_scope='paired video with existing published source-program form',
        repairs=['isolated_baseline_and_program_tool_surfaces','existing_published_form_validation',
                 'task_owned_program_reuse_receipts','readonly_runtime_store_mount'],
        runtime_delta='The shared adapter admits the original published video form and parallel lanes. '
                      'Paper/PPT learned IR, matching, independent evidence and guards are unchanged.',
        video_form_scope='Separate pre-existing published runtime; this compatibility export neither certifies nor promotes video.')
    return value

def prepare(candidate,directory,validation_record):
    original_prepare(candidate,directory,validation_record)
    (directory/'README.md').write_text('# '+candidate['release']+'\n\n'
        '从 '+candidate['previous']+' 生成的视频双栏运行环境兼容版本。旧库保留；'
        'library、online manifest、task、完整工具 schema、来源证据五项逐字节保持一致。\n\n'
        '网页视频另行加载原已发布程序策略，Baseline 和 Motif 使用独立会话与工作区；'
        '本次只绑定共享适配代码版本，没有重新训练、改变 Paper/PPT 原算法，'
        '也没有由本兼容记录赋予视频库新的认证或晋级结论。\n\n'
        '零模型调用、零新训练；验证记录：'+validation_record+'。\n',encoding='utf-8')
    cert=compat.read(directory/'certification.json')
    cert['file_locks']={name:compat.sha(directory/name) for name in cert['file_locks']}
    compat.write(directory/'certification.json',cert)
    entry=compat.read(directory/'entry.json')
    entry['files']={name:compat.sha(directory/name) for name in entry['files']}
    compat.write(directory/'entry.json',entry)
    from src.adapters.harless_rsi_bundle import load_product_bundle
    assert load_product_bundle(ROOT,directory,candidate['scene'])['runtime_kind']==entry['runtime_kind']

compat.compatibility_record,compat.prepare=compatibility_record,prepare
if __name__=='__main__':compat.main()
