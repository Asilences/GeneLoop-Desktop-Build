"""Seeded CPU inference witness; emits aggregate facts for synthetic inputs only."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    import torch
    torch.manual_seed(1729)
    torch.set_num_threads(4)
    x = torch.randn(8, 8)
    witness = float((x @ x.T).sum())
    assert x.device.type == 'cpu' and witness > 0
    result = {'versions': {name: importlib.metadata.version(name) for name in
                          ('torch', 'opf', 'tiktoken', 'credsweeper', 'onnxruntime', 'numpy')},
              'kernel': {'shape': [8, 8], 'device': 'cpu', 'seed': 1729, 'value': witness},
              'cloud_requests': 0, 'input_scope': 'two synthetic identity examples and three scanner controls including a real ML path'}
    from opf import OPF
    start = time.perf_counter()
    detector = OPF(model=args.checkpoint, device='cpu', context_window_length=4096)
    detector.get_runtime()
    result['opf_load_seconds'] = time.perf_counter() - start
    result['opf'] = []
    for name, text in [('en', 'My name is Alice Morgan. My home address is 123 Oak Street, Seattle. Contact me at alice@example.com.'),
                       ('zh', '我叫张晓明，家庭住址是北京市朝阳区建国路88号。请将报告发给我。')]:
        start = time.perf_counter()
        prediction = detector.redact(text)
        assert not prediction.warning and prediction.text == text
        assert all(0 <= s.start < s.end <= len(text) and text[s.start:s.end] == s.text for s in prediction.detected_spans)
        result['opf'].append({'language': name, 'labels': [s.label for s in prediction.detected_spans],
                              'spans': len(prediction.detected_spans), 'seconds': time.perf_counter() - start,
                              'roundtrip_exact': True})
    from credsweeper import CredSweeper
    args.output.with_suffix('.opf.json').write_text(json.dumps(result, indent=2))
    print('OPF_FORWARD_WITNESS', json.dumps(result), flush=True)
    from credsweeper.file_handler.string_content_provider import StringContentProvider
    scanner = CredSweeper(pool_count=1, stdout=False, color=False, hashed=True,
                          ml_threads_limit=1, ml_providers='CPUExecutionProvider', log_level='CRITICAL')
    result['credsweeper'] = []
    for name, text in [('plain', 'Compare linear regression and random forests using mean ± SD.'),
                       ('synthetic_secret', 'password = "FictionalTrainingPassword_7391!"'),
                       ('random_synthetic_secret', 'password = "C7r8@zB6dM3fQ9nJ5kW2!vR4"')]:
        scanner.credential_manager.clear_credentials()
        start = time.perf_counter()
        provider = StringContentProvider(lines=text.splitlines(), file_path='memory.txt', file_type='.txt')
        scanner.scan([provider], None)
        before = scanner.credential_manager.len_credentials()
        requires_ml = any(c.use_ml for c in scanner.credential_manager.get_credentials())
        scanner.post_processing(None)
        result['credsweeper'].append({'case': name, 'before_ml': before, 'requires_ml': requires_ml,
                                      'findings': scanner.credential_manager.len_credentials(),
                                      'seconds': time.perf_counter() - start})
        scanner.credential_manager.clear_credentials()
        provider.free()
    result['credsweeper_ml_forward_exercised'] = any(row['requires_ml'] for row in result['credsweeper'])
    assert result['credsweeper_ml_forward_exercised'], 'witness_did_not_exercise_real_ml_path'
    result['driver_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2))
    print('CPU_KERNEL_WITNESS', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
