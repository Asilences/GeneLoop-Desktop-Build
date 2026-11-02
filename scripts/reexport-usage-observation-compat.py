#!/usr/bin/env python3
"""Re-export unchanged Paper/PPT programs for read-only usage timeout recovery.

Preview is read-only. --write uses fresh immutable release directories. The
existing exporter verifies exact reviewed source deltas and identical programs;
this does not train, replay private traces, or promote quality/cost claims.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('usage_compat', ROOT / 'scripts/reexport-native-capabilities-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)
REVIEWED = {'src/adapters/dsh_web_tasks.ts'}
compat.RELEASES = [
    ('paper-web-v31', 'paper-web-v32', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json', REVIEWED),
    ('ppt-master-v28', 'ppt-master-v29', 'ppt',
     'scenarios/ppt_master/contracts.json', REVIEWED),
]
compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-usage-observation-compat.py'}
original_record, original_prepare = compat.compatibility_record, compat.prepare


def compatibility_record(candidate, validation_record):
    value = original_record(candidate, validation_record)
    value['repairs'] = ['usage_transport_timeout_does_not_fail_live_task',
                        'retain_last_usage_and_mark_incomplete_until_next_successful_read']
    value['runtime_delta'] = ('Read-only usage polling tolerates temporary transport failure. '
        'Model admission, cancellation, authentication/HTTP errors, permissions and all '
        'Motif matching/learning/version guards remain unchanged.')
    return value


def prepare(candidate, directory, validation_record):
    original_prepare(candidate, directory, validation_record)
    (directory / 'README.md').write_text(
        '# ' + candidate['release'] + '\n\n'
        '基于 ' + candidate['previous'] + ' 的用量查询兼容版本。只修复统计查询临时超时导致对照任务误报失败：'
        '保留已有计数、标记统计未同步，并在后续查询恢复。模型准入、权限、取消及 Motif 匹配、学习、版本守卫不变。\n\n'
        '原 library、manifest、task、tool schema、source evidence 字节保持一致。零新训练、零模型调用；'
        '不代表质量或成本效果晋级。验证记录：' + validation_record + '。\n', encoding='utf-8')
    cert = compat.read(directory / 'certification.json')
    cert['file_locks'] = {name: compat.sha(directory / name) for name in cert['file_locks']}
    compat.write(directory / 'certification.json', cert)
    entry = compat.read(directory / 'entry.json')
    entry['files'] = {name: compat.sha(directory / name) for name in entry['files']}
    compat.write(directory / 'entry.json', entry)
    from src.adapters.harless_rsi_bundle import load_product_bundle
    assert load_product_bundle(ROOT, directory, candidate['scene'])['runtime_kind'] == entry['runtime_kind']


compat.compatibility_record, compat.prepare = compatibility_record, prepare
if __name__ == '__main__':
    compat.main()
