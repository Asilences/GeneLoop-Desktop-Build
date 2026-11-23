"""Retrospective residual attribution; annotation values never reach detection.

Uses the existing frozen extractor and bounded evaluation controller. Private
per-file outcomes stay in the output directory; public output contains counts.
Literal presence is a proxy, not an assertion about the annotated output span.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import TimeoutError
import hashlib
import json
from pathlib import Path
import re
import sys

from pebble import ProcessPool
import run_credentials as cred
import run_pii as bench


def transform(text):
    return bench.module_result(text)


def shape(value):
    if '\n' in value:
        return 'multiline'
    if re.fullmatch(r'[0-9]+', value):
        return 'digits'
    if re.fullmatch(r'[0-9a-fA-F]+', value):
        return 'hexadecimal'
    if re.fullmatch(r'[A-Za-z0-9+/=_-]+', value):
        return 'alphanumeric_or_base64_like'
    return 'other'


def length_bin(value):
    return next(label for limit, label in ((3, '1-3'), (7, '4-7'), (15, '8-15'),
                                          (31, '16-31'), (10**20, '32+')) if len(value) <= limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'baseline', 'config', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--sample', type=int, default=64)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    sys.path.insert(0, str(args.root))
    annotations = cred.read_annotations(args.root)
    groups = defaultdict(list)
    for row in annotations:
        groups[row['FilePath']].append(row)
    baseline_file = args.baseline / 'module-file-records-private.jsonl'
    baseline = [json.loads(line) for line in baseline_file.read_text().splitlines()]
    candidates = [row['file'] for row in baseline if row.get('accepted') and row.get('any_literal_residual')]
    seed = 'privacy-r4-credential-diagnostic-v1'
    selected = sorted(candidates, key=lambda name: hashlib.sha256((seed+':'+name).encode()).hexdigest())[:args.sample]
    assert len(selected) == args.sample
    scoring = args.root.parent / 'CredData-scoring'
    counters = {name: Counter() for name in ('status', 'category', 'length', 'shape', 'source_occurrences',
                                            'predefined_pattern', 'cryptographic_key')}
    rows = Counter()
    with ProcessPool(max_workers=args.workers, initializer=bench.initialize,
                     initargs=(str(args.config.resolve()),)) as pool:
        pending = []
        for name in selected:
            text = (scoring/name).read_text(encoding='utf-8')
            pending.append((name, text, pool.schedule(transform, args=(text,), timeout=120)))
        with (args.output/'outcomes-private.jsonl').open('w') as stream:
            for name, text, future in pending:
                try:
                    outcome = future.result()
                    status = 'accepted' if outcome['accepted'] else 'rejected'
                except TimeoutError:
                    outcome, status = {}, 'evaluation_timeout'
                except Exception as exc:
                    outcome, status = {'error_type': type(exc).__name__}, 'evaluation_error'
                counters['status'][status] += 1
                output = outcome.pop('text', None)
                stream.write(json.dumps(dict(file=name, status=status, **outcome))+'\n')
                if status != 'accepted':
                    continue
                for row in groups[name]:
                    if row['GroundTruth'] != 'T':
                        continue
                    values, unsupported = cred.extract_positive_values(text, [row])
                    rows['unextractable'] += unsupported
                    for value in values:
                        rows['extractable_positive_rows'] += 1
                        if value not in output:
                            continue
                        rows['literal_residual_rows'] += 1
                        counters['category'][str(row['Category'])] += 1
                        counters['length'][length_bin(value)] += 1
                        counters['shape'][shape(value)] += 1
                        counters['source_occurrences']['multiple' if text.count(value)>1 else 'single'] += 1
                        counters['predefined_pattern'][str(row['PredefinedPattern'])] += 1
                        counters['cryptographic_key'][str(row['CryptographyKey'])] += 1
    summary = {'purpose': 'known leaky-file diagnostic, not representative quality or unseen evaluation',
        'selection_seed': seed, 'candidate_files': len(candidates), 'sample_files': len(selected),
        'source_selection_digest': hashlib.sha256(json.dumps(selected).encode()).hexdigest(),
        'baseline_records_sha256': hashlib.sha256(baseline_file.read_bytes()).hexdigest(),
        'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'per_call_timeout_seconds': 120, 'workers': args.workers, 'gold_passed_to_detector': False,
        'literal_presence_is_position_sensitive': False, 'rows': dict(rows),
        'bins': {key: dict(value) for key, value in counters.items()}}
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({'completed': True, 'sample_files': len(selected), 'status': dict(counters['status'])}))


if __name__ == '__main__':
    main()
