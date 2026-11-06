#!/usr/bin/env python3
"""Re-export unchanged Paper/PPT IR for the account-scoped read-only Motif view.

Use the existing compatibility export, including exact changed-file review,
immutable artifact checks, staged admission and a final source hash check.
Preview by default; --write --update-registry selects fresh releases locally.
No certificate is relaxed, no old release is overwritten, no model is called.
"""
import importlib.util
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('motif_view_compat', ROOT / 'scripts/reexport-native-capabilities-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)
compat.RELEASES = [
    ('paper-web-v84', 'paper-web-v85', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json', {'scripts/harless_gateway.mjs'}),
    ('ppt-master-v82', 'ppt-master-v83', 'ppt',
     'scenarios/ppt_master/contracts.json', {'scripts/harless_gateway.mjs'}),
]
compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS = {
    'scripts/reexport-motif-view-compat.py', 'scripts/harless_motif_view.ts',
    'src/adapters/motif_evidence_projection.ts', 'config/motif-evidence-v1.schema.json',
}


def prepare(candidate, directory, validation_record):
    shutil.copytree(candidate['old'], directory, dirs_exist_ok=True)
    record = compat.compatibility_record(candidate, validation_record)
    record.update(
        repairs=['account_scoped_read_only_motif_evidence_view'],
        runtime_delta='A GET-only display route reads host-bound deidentified evidence after existing account authentication. '
                      'It cannot register executable tools, authorize models, submit tasks or mutate a library. '
                      'The Agent, MCP schemas and learned programs are unchanged.')
    report = compat.read(directory / 'learning-report.json')
    report['motif_view_compatibility'] = record
    compat.write(directory / 'learning-report.json', report)
    (directory / 'README.md').write_text(
        '# ' + candidate['release'] + '\n\n'
        '从 ' + candidate['previous'] + ' 重导出的只读 Motif 展示兼容版本。'
        '仅审阅账号网关新增的只读入口，并锁定展示适配器和协议；'
        '原 IR、online manifest、task、完整工具 schema 与来源证据逐字节保留。\n\n'
        '旧库和证书保留，代码漂移继续拒绝。没有新训练、原始轨迹重放或模型调用，'
        '不代表质量、成本或新能力认证。原有 new_training 字段只描述历史来源。\n\n'
        '验证记录：[' + validation_record + '](../../' + validation_record + ')。\n', encoding='utf-8')
    cert = dict(candidate['cert'])
    cert.update(code_locks=candidate['locks'], learning_report_sha256=compat.sha(directory / 'learning-report.json'),
                file_locks={name: compat.sha(directory / name) for name in cert['file_locks']})
    compat.write(directory / 'certification.json', cert)
    entry = dict(candidate['entry'])
    entry['files'] = {name: compat.sha(directory / name) for name in entry['files']}
    compat.write(directory / 'entry.json', entry)
    for name, expected in candidate['locked_artifact_hashes'].items():
        if compat.sha(directory / name) != expected:
            raise ValueError('Compatibility export altered immutable artifact: ' + name)
    from src.adapters.harless_rsi_bundle import load_product_bundle
    if load_product_bundle(ROOT, directory, candidate['scene'])['runtime_kind'] != entry['runtime_kind']:
        raise ValueError('Runtime kind changed')


compat.prepare = prepare
if __name__ == '__main__':
    compat.main()
