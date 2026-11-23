"""Compare pinned credential scanners on fresh synthetic trajectory packets."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.adapters.geneloop_privacy import PrivacyRejected, _material_scan_text
from src.adapters.rsi_privacy_candidates import OfficialTools, candidate_context
from src.adapters.rsi_text_privacy import _scan, _scan_gitleaks


def cases(split):
    """Independent fixtures; no real accounts, secrets, or CredData fragments."""
    # Different wrappers and synthetic values between the two splits.
    layouts = ('tool_result', 'model') if split == 'pilot' else ('arguments', 'nested_output', 'handoff')
    replicas = 2 if split == 'pilot' else 16
    for layout in layouts:
        for index in range(replicas):
            digest = sha256(f'geneloop-synthetic-r10:{split}:{layout}:{index}'.encode()).hexdigest()
            fake_token = 'ghp_' + digest[:36]
            texts = (
                ('service_key', True, f'export GITHUB_TOKEN="{fake_token}"'),
                ('password', True, f'password = "Yx!{digest[:15]}"'),
                ('session_header', True, f'Authorization: Bearer {digest[:40]}'),
                ('budget', False, f'Keep token count {100 + index}; report RMSE and 24 fps.'),
                ('example', False, 'Set the environment variable API_KEY outside this task.'),
                ('digest', False, f'SHA256 of the input artifact: {digest}'),
            )
            for family, positive, text in texts:
                if layout == 'tool_result':
                    packet = {'content': [{'role': 'tool', 'value': text}]}
                elif layout == 'model':
                    packet = {'content': [{'role': 'model', 'value': '诊断输出\n' + text}]}
                elif layout == 'arguments':
                    packet = {'content': [{'role': 'tool', 'value': {'arguments': json.dumps({'note': text})}}]}
                elif layout == 'nested_output':
                    packet = {'content': [{'role': 'tool', 'value': json.dumps({'stdout': json.dumps({'line': text})})}]}
                else:
                    packet = {'content': [{'role': 'user', 'value': '保留任务约束与统计量。'},
                                          {'role': 'model', 'value': '交接记录\n' + text}]}
                yield f'{layout}-{index}-{family}', positive, packet


def run_scan(mode, text, medium, reviewer):
    if mode == 'gitleaks':
        _scan_gitleaks(text)
    elif mode == 'credsweeper':
        medium.scan(text)
    else:
        with candidate_context(reviewer if mode == 'review' else medium):
            _scan(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=('pilot', 'heldout'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    settings = {'format': 'geneloop.privacy-candidate/v1', 'text_mode': 'r4',
                'checkpoint': '', 'tokenizer_cache': '', 'threads': 1}
    medium = OfficialTools({**settings, 'credential_mode': 'gitleaks+credsweeper'})
    reviewer = OfficialTools({**settings, 'credential_mode': 'gitleaks+credsweeper-review'})
    data = list(cases(args.split))
    dataset = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    result = {'split': args.split, 'dataset_sha256': sha256(dataset).hexdigest(),
              'source_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': len(data), 'synthetic': True, 'modes': {}, 'cloud_requests': 0}
    for mode in ('gitleaks', 'credsweeper', 'union', 'review'):
        counts = Counter()
        durations = []
        rows = []
        for identifier, positive, packet in data:
            text = _material_scan_text(packet)
            start = time.monotonic()
            try:
                run_scan(mode, text, medium, reviewer)
                status = 'clear'
            except PrivacyRejected as error:
                status = 'review' if error.reason == 'credential_review_required' else 'unknown'
            except subprocess.CalledProcessError as error:
                status = 'hit' if error.returncode == 1 else 'unknown'
            except Exception:
                status = 'unknown'
            durations.append(time.monotonic() - start)
            if status == 'unknown':
                counts['unknown'] += 1
            elif status in ('hit', 'review'):
                counts['tp' if positive else 'fp'] += 1
                counts['review'] += status == 'review'
            else:
                counts['fn' if positive else 'tn'] += 1
            rows.append({'id': identifier, 'positive': positive, 'status': status})
        result['modes'][mode] = {'counts': dict(counts), 'seconds': sum(durations), 'rows': rows}
    mode_rows = {mode: {r['id']: r['status'] for r in row['rows']} for mode, row in result['modes'].items()}
    positive = {identifier for identifier, label, _ in data if label}
    controls = set(mode_rows['union']) - positive
    result['gate'] = (
        all(not r['counts'].get('unknown') for r in result['modes'].values())
        and all(any(mode_rows[mode][key] == 'hit' for key in positive) for mode in ('gitleaks', 'credsweeper'))
        and all(
            (mode_rows['union'][key] == 'hit') == any(
                mode_rows[mode][key] == 'hit' for mode in ('gitleaks', 'credsweeper')
            ) for key in mode_rows['union']
        )
        and any(mode_rows['union'][key] == 'clear' for key in controls)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({'cases': result['cases'], 'gate': result['gate'],
                      'counts': {m: row['counts'] for m, row in result['modes'].items()}}))
    if not result['gate']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
