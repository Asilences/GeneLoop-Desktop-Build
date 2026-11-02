#!/usr/bin/env python3
"""Narrow, model-free Paper v40/PPT v37 compatibility re-export.

Only the reviewed optional container-ownership branch in the shared Remotion
server may differ. Default preview is read-only. --write --update-registry uses
fresh v41/v38 directories after original program/evidence and source checks.
No Capability runtime/builder/store code is certified by these product bundles.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capability_container_compat', ROOT/'scripts/reexport-native-capabilities-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)
REVIEWED = {'scenarios/remotion_edit/server.py'}
compat.RELEASES = [
    ('paper-web-v40', 'paper-web-v41', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json', REVIEWED),
    ('ppt-master-v37', 'ppt-master-v38', 'ppt',
     'scenarios/ppt_master/contracts.json', REVIEWED),
]
compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-capability-container-compat.py'}
original_record, original_prepare = compat.compatibility_record, compat.prepare


def compatibility_record(candidate, validation_record):
    value = original_record(candidate, validation_record)
    value['repairs'] = ['optional_explicit_container_name_and_nonce_ownership',
                        'isolate_capability_workers_from_legacy_experiment_cleanup']
    value['runtime_delta'] = ('The existing shared Docker launcher is reused. Without the two explicit '
        'Capability container environment variables the launch is unchanged; with a validated name/nonce '
        'only ownership/name/experiment labels change. Mounts, user, network, capabilities, resource limits, '
        'commands and native renderer remain unchanged. This is product source compatibility only; '
        'it neither certifies new Capability code nor promotes video/task quality or efficiency.')
    value['capability_runtime_certified'] = False
    return value


def prepare(candidate, directory, validation_record):
    original_prepare(candidate, directory, validation_record)
    # Keep all prior report fields and append a separately named compatibility
    # record, rather than replacing the old native-capability integration history.
    report = compat.read(candidate['old']/'learning-report.json')
    report['capability_container_compatibility'] = compatibility_record(candidate, validation_record)
    compat.write(directory/'learning-report.json', report)
    (directory/'README.md').write_text(
        '# ' + candidate['release'] + '\n\n'
        '从 ' + candidate['previous'] + ' 兼容重导出；仅审阅共享 Remotion 启动器新增的可选容器名称/nonce 标签。'
        '未设置这两个专用环境变量时保持原启动行为；设置时只隔离容器归属，避免旧实验清理命中新 worker。\n\n'
        '原 library、online manifest、task、MCP schema 与 source evidence 逐字节保留，旧版本全部保留。'
        '新报告保留全部历史字段并追加兼容记录。零模型调用、零新训练、零原始轨迹重放；'
        '不认证新 Capability 内核，也不宣称任务质量或效率晋级。\n\n'
        '验证记录：' + validation_record + '。\n', encoding='utf-8')
    cert = compat.read(directory/'certification.json')
    cert.update(learning_report_sha256=compat.sha(directory/'learning-report.json'),
                file_locks={name: compat.sha(directory/name) for name in cert['file_locks']})
    compat.write(directory/'certification.json', cert)
    entry = compat.read(directory/'entry.json')
    entry['files'] = {name: compat.sha(directory/name) for name in entry['files']}
    compat.write(directory/'entry.json', entry)
    from src.adapters.harless_rsi_bundle import load_product_bundle
    assert load_product_bundle(ROOT, directory, candidate['scene'])['runtime_kind'] == entry['runtime_kind']


compat.compatibility_record, compat.prepare = compatibility_record, prepare
if __name__ == '__main__':
    compat.main()
