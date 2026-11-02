#!/usr/bin/env python3
"""Re-export unchanged Paper/PPT programs for read-only native access to exported artifacts.

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
REVIEWED = {'src/adapters/geneloop_shell.ts', 'src/adapters/geneloop_fs.ts', 'src/adapters/session_report.py'}
compat.RELEASES = [
    ('paper-web-v33', 'paper-web-v36', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json', REVIEWED),
    ('ppt-master-v30', 'ppt-master-v33', 'ppt',
     'scenarios/ppt_master/contracts.json', REVIEWED - {'src/adapters/session_report.py'}),
]
compat.REGISTRY_SELECTED = {'paper-web-v33':'paper-web-v35','ppt-master-v30':'ppt-master-v32'}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-artifact-view-compat.py'}
original_record, original_prepare = compat.compatibility_record, compat.prepare


def compatibility_record(candidate, validation_record):
    value = original_record(candidate, validation_record)
    value['repairs'] = ['read_only_current_session_artifact_view']
    value['runtime_delta'] = ('Native read/read_image and Bash gain a read-only /artifacts view of this Session outputs. '
        'Report export adds a logical read_path; receipt names, hashes, source guards and permissions remain unchanged. '
        'No Motif matching, learning or execution algorithm changes.')
    return value


def prepare(candidate, directory, validation_record):
    original_prepare(candidate, directory, validation_record)
    (directory / 'README.md').write_text(
        '# ' + candidate['release'] + '\n\n'
        '基于 ' + candidate['previous'] + ' 的只读交付文件访问兼容版本。原生文件工具与 Bash 可通过 /artifacts 读取本会话导出文件。'
        '保留原交付收据、哈希和来源校验；禁止写入及跨会话访问。不改 Motif 算法。\n\n'
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
