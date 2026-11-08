#!/usr/bin/env python3
"""Rebind unchanged products to the read-only Runtime catalog and main integration.

The exact old/current differences are reviewed explicitly. Reuses the original
exporter's immutable artifact, staging, admission and final hash checks. No model.
"""
import importlib.util
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('catalog_compat',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(spec);spec.loader.exec_module(compat)
COMMON={
    'scripts/harless_gateway.mjs','scripts/harness-web.py','scripts/learn-web-ppt-tasks.py',
    'scripts/prepare-native-host.mjs','scripts/serve-web-budget.py',
    'src/adapters/capability_proposal.py','src/adapters/deepseek_cost_gate.py',
    'src/adapters/dsh_web_tasks.ts','src/adapters/harless_reasoning.ts','src/adapters/harless_rsi_bundle.py',
    'src/adapters/motif_evidence_projection.ts',
}
compat.RELEASES=[
    ('paper-web-v85','paper-web-v86','paper-proofreading','scenarios/paper_proofreading/document-read-contracts.json',
     COMMON|{'scripts/compile-witnessed-read-chains.py','scripts/learn-web-paper-document-motif.py',
             'scripts/learn-web-paper-tasks.py','src/adapters/task_identity.py','src/motif_core/offline/edge_compiler.py'}),
    ('ppt-master-v83','ppt-master-v84','ppt','scenarios/ppt_master/contracts.json',
     COMMON|{'scenarios/research_ppt/motif_v6.py','scripts/learn-ppt-master-motif.py'}),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS={
    'scripts/reexport-motif-catalog-compat.py','src/adapters/harless_motif_catalog.ts',
    'config/motif-evidence-v2.schema.json',
}

def prepare(candidate,directory,validation_record):
    shutil.copytree(candidate['old'],directory,dirs_exist_ok=True)
    record=compat.compatibility_record(candidate,validation_record)
    record.update(repairs=['runtime_owned_read_only_catalog','main_privacy_and_model_compatibility'],
                  runtime_delta='Projects only host-admitted libraries, reuses the existing availability and account learning resolvers. No tool registration, source mutation, model call or execution authorization.')
    report=compat.read(directory/'learning-report.json')
    report['runtime_catalog_compatibility']=record
    compat.write(directory/'learning-report.json',report)
    (directory/'README.md').write_text(
        '# '+candidate['release']+'\n\n从 '+candidate['previous']+' 重导出的只读运行库目录兼容版本。'
        '精确锁定当前 main 的已审阅隐私/模型接线，以及本次只读目录和协议；'
        '原 library、online manifest、task、工具 Schema、来源证据逐字节保留。'
        '零训练、零模型请求，不新增能力或质量/收益认证。旧库保持。\n\n验证：['+validation_record+'](../../'+validation_record+')。\n',encoding='utf-8')
    cert=dict(candidate['cert'])
    cert.update(code_locks=candidate['locks'],learning_report_sha256=compat.sha(directory/'learning-report.json'),
                file_locks={name:compat.sha(directory/name) for name in cert['file_locks']})
    compat.write(directory/'certification.json',cert)
    entry=dict(candidate['entry']);entry['files']={name:compat.sha(directory/name) for name in entry['files']}
    compat.write(directory/'entry.json',entry)
    for name,expected in candidate['locked_artifact_hashes'].items():
        if compat.sha(directory/name)!=expected:raise ValueError('Immutable artifact changed: '+name)
    from src.adapters.harless_rsi_bundle import load_product_bundle
    if load_product_bundle(ROOT,directory,candidate['scene'])['runtime_kind']!=entry['runtime_kind']:
        raise ValueError('Runtime kind changed')

compat.prepare=prepare
if __name__=='__main__':compat.main()
