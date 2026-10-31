#!/usr/bin/env python3
"""Re-export unchanged Paper/PPT programs for explicit output formats and delegated design preferences.

Preview is read-only. --write uses fresh immutable release directories. The
existing exporter verifies exact reviewed source deltas and identical programs;
this does not train, replay private traces, or promote quality/cost claims.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('readiness_compat', ROOT / 'scripts/reexport-native-capabilities-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)
REVIEWED = {'config/geneloop-capabilities.md'}
compat.RELEASES = [
    ('paper-web-v32', 'paper-web-v33', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json', REVIEWED),
    ('ppt-master-v29', 'ppt-master-v30', 'ppt',
     'scenarios/ppt_master/contracts.json', REVIEWED | {'scenarios/ppt_master/prompt.md'}),
]
compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-release-readiness-compat.py'}
original_record, original_prepare = compat.compatibility_record, compat.prepare


def compatibility_record(candidate, validation_record):
    value = original_record(candidate, validation_record)
    value['repairs'] = ['respect_explicit_output_format_over_progress_prose',
                        'honor_user_delegated_reversible_design_choices']
    value['runtime_delta'] = ('Both lanes receive clarified user interaction guidance. '
        'Explicit machine-readable output excludes progress prose; delegated reversible '
        'design choices do not require duplicate questions. Necessary information and '
        'permission questions, all tool guards and Motif algorithms remain unchanged.')
    return value


def prepare(candidate, directory, validation_record):
    original_prepare(candidate, directory, validation_record)
    (directory / 'README.md').write_text(
        '# ' + candidate['release'] + '\n\n'
        '基于 ' + candidate['previous'] + ' 的交互提示兼容版本。明确本轮机器可读输出格式优先于通用进度汇报，'
        '自主设计授权覆盖其范围内可逆的版式、配色、可选归一化和导出选择。必要信息与权限仍须确认。'
        'Baseline/Motif 同样使用此提示；不改 Motif 匹配、学习、认证或版本守卫。\n\n'
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
