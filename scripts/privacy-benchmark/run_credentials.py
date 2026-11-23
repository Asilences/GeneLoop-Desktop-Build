"""CredData Gitleaks comparison at explicitly labeled line/file granularity.

Uses the original metadata and upstream Result formulas. The current legacy
Gitleaks wrapper is run as an audit, NOT silently repaired into a headline score.
Full module refusals are not counted as entity detections.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import run_pii as pii


def read_annotations(root):
    from meta_row import read_meta
    return [vars(row) for row in read_meta(root / 'meta')]


def truth_status(rows):
    labels = {row['GroundTruth'] for row in rows}
    if 'T' in labels:
        return 'positive'
    if labels == {'F'}:
        return 'negative'
    return 'uncertain'


def matrix(items):
    from benchmark.common.result import Result
    positives = [row for row in items if row['truth'] == 'positive']
    negatives = [row for row in items if row['truth'] == 'negative']
    tp = sum(row['flagged'] for row in positives)
    fp = sum(row['flagged'] for row in negatives)
    score = Result(tp, fp, len(positives), len(negatives))
    names = ('true_positive', 'false_positive', 'true_negative', 'false_negative',
             'false_positive_rate', 'false_negative_rate', 'precision', 'recall', 'f1')
    return {**{name: getattr(score, name) for name in names},
            'uncertain_excluded': sum(row['truth'] == 'uncertain' for row in items)}


def extract_positive_values(text, rows):
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    values = []
    unsupported = 0
    for row in rows:
        if row['GroundTruth'] != 'T':
            continue
        start, end = row['LineStart'] - 1, row['LineEnd']
        a, b = row['ValueStart'], row['ValueEnd']
        if not (0 <= start < end <= len(lines)):
            unsupported += 1
            continue
        if end == start + 1 and 0 <= a < b <= len(lines[start]):
            value = lines[start][a:b]
        elif end > start + 1 and a >= 0 and b >= 0:
            value = '\n'.join([lines[start][a:], *lines[start + 1:end - 1], lines[end - 1][:b]])
        else:
            unsupported += 1
            continue
        if value:
            values.append(value)
        else:
            unsupported += 1
    return values, unsupported


def evaluate_file(item):
    path, annotations, flagged = item
    text = Path(path).read_text(encoding='utf-8')
    result = pii.module_result(text)
    result['file'] = annotations[0]['FilePath']
    result['truth'] = truth_status(annotations)
    result['gitleaks_flagged'] = flagged
    result['chars'] = len(text)
    values, unsupported = extract_positive_values(text, annotations)
    result['positive_annotation_rows'] = len(values) + unsupported
    result['unextractable_positive_rows'] = unsupported
    if result['accepted']:
        output = result.pop('text')
        result['extractable_positive_rows'] = len(values)
        result['literal_residual_rows'] = sum(value in output for value in values)
        result['any_literal_residual'] = result['literal_residual_rows'] > 0
    return result


def prepare_subset(root, preparation):
    """No deletion/renaming of gold CSVs. Exclusions are reported by repo ID."""
    import shutil
    import zlib
    sys.path.insert(0, str(root))
    from download_data import move_files
    from obfuscate_creds import obfuscate_creds
    snapshot = json.loads((root / 'snapshot.json').read_text())
    complete = {r['repo'] for r in preparation['results'] if r['status'] == 'complete'}
    available = {key: value for key, value in snapshot.items()
                 if f'{zlib.crc32(bytes.fromhex(key)):08x}' in complete}
    scoring = root.parent / 'CredData-scoring'
    (scoring / 'meta').mkdir(parents=True, exist_ok=True)
    for repo8 in complete:
        shutil.copyfile(root / 'meta' / f'{repo8}.csv', scoring / 'meta' / f'{repo8}.csv')
    os.chdir(root)
    assert not move_files(available, 'data')
    obfuscate_creds(str(scoring / 'meta'), 'data', 0)
    (scoring / 'data').symlink_to(root / 'data', target_is_directory=True)
    return scoring


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--method', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--prior-output', type=Path)
    args = parser.parse_args()
    args.root = args.root.resolve()
    sys.path.insert(0, str(args.root))
    method = json.loads(args.method.read_text())
    assert args.workers == method['workers']
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    preparation = json.loads((args.root.parent / 'creddata-preparation.json').read_text())
    original_meta = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.root / 'meta').glob('*.csv')}
    assert original_meta == preparation['meta_sha256']
    all_annotations = read_annotations(args.root)
    sys.path.insert(0, str(args.root))
    prior = None
    if args.prior_output:
        prior = json.loads((args.prior_output / 'credential-frozen-snapshot.json').read_text())
        assert prior['config_sha256'] == hashlib.sha256(args.config.read_bytes()).hexdigest()
        assert prior['method_sha256'] == hashlib.sha256(args.method.read_bytes()).hexdigest()
        scoring = args.root.parent / 'CredData-scoring'
    elif preparation.get('prepared_files'):
        scoring = args.root
    else:
        scoring = prepare_subset(args.root, preparation)
    annotations = read_annotations(scoring)
    excluded = [row for row in all_annotations if row['RepoName'] not in {p.stem for p in (scoring / 'meta').glob('*.csv')}]
    grouped = defaultdict(list)
    cells = defaultdict(list)
    for row in annotations:
        grouped[row['FilePath']].append(row)
        cells[(row['FilePath'], row['LineStart'], row['LineEnd'])].append(row)
    for relative in grouped:
        assert (scoring / relative).is_file()
    snapshot = {'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
                'method_sha256': hashlib.sha256(args.method.read_bytes()).hexdigest(), 'method': method,
                'workers': args.workers,
                'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'available_repositories': len({r['RepoName'] for r in annotations}),
                'full_annotation_labels': dict(Counter(r['GroundTruth'] for r in all_annotations)),
                'evaluated_annotation_labels': dict(Counter(r['GroundTruth'] for r in annotations)),
                'excluded_annotation_labels': dict(Counter(r['GroundTruth'] for r in excluded)),
                'unavailable_repositories': [r for r in preparation['results'] if r['status'] != 'complete'],
                'scope': 'available pinned sources; never silently remove unavailable gold labels',
                'line_scope': 'exact file + StartLine + EndLine; T-containing cells positive, F-only negative, X-only or F/X uncertain excluded',
                'file_scope': 'T-containing file positive, F-only negative, F/X or X-only uncertain excluded',
                'legacy_wrapper_status': 'audit only: current wrapper supplies no Category, but official checker requires Category equality',
                'data_digest': hashlib.sha256(json.dumps({relative: hashlib.sha256((scoring / relative).read_bytes()).hexdigest() for relative in sorted(grouped)}, sort_keys=True).encode()).hexdigest(),
                'cloud_requests': 0, 'cloud_api_cost': 0}
    if prior:
        assert prior['data_digest'] == snapshot['data_digest']
        snapshot['prior_preparation_and_scan'] = prior
        snapshot['execution_id'] = 'r1-credentials-execution2-legacy-audit-guard'
    (args.output / 'credential-frozen-snapshot.json').write_text(json.dumps(snapshot, indent=2))
    report = args.output / 'gitleaks-modern-private.json'
    binary = os.environ['SSS_RSI_GITLEAKS']
    env = {key: os.environ[key] for key in ('PATH', 'HOME') if key in os.environ}
    scan_started = time.perf_counter()
    if prior:
        report = args.prior_output / 'gitleaks-modern-private.json'
        scan_wall_seconds = None
    else:
        with (args.output / 'gitleaks-private.log').open('w') as log:
            completed = subprocess.run([binary, 'dir', str((scoring / 'data').resolve()), '--no-banner', '--redact=100',
                '--ignore-gitleaks-allow', '--max-decode-depth', '2', '--report-format', 'json', '--report-path', str(report)],
                cwd=args.output, env=env, stdout=log, stderr=log, check=False)
        assert completed.returncode in (0, 1), 'Gitleaks failed; do not score errors as clean'
        scan_wall_seconds = time.perf_counter() - scan_started
    findings = json.loads(report.read_text())
    flagged_files = set()
    flagged_cells = set()
    legacy = []
    for item in findings:
        file = Path(item['File'])
        relative = 'data/' + str(file.relative_to((scoring / 'data').resolve())) if file.is_absolute() and file.is_relative_to((scoring / 'data').resolve()) else None
        if relative is None:
            # Modern Gitleaks can preserve the symlink path spelling.
            relative = 'data/' + str(file.relative_to(scoring / 'data')) if file.is_absolute() else 'data/' + str(file).removeprefix('data/')
        flagged_files.add(relative)
        flagged_cells.add((relative, item['StartLine'], item['EndLine']))
        legacy.append({'file': relative, 'lineNumber': item['StartLine']})
    legacy_path = args.output / 'gitleaks-legacy-private.json'
    legacy_path.write_text(json.dumps(legacy))
    from benchmark.scanner.gitleaks import Gitleaks
    os.chdir(scoring)
    with (args.output / 'official-wrapper-audit-private.log').open('w') as log, redirect_stdout(log):
        scanner = Gitleaks(str(args.output), str(scoring), True, False)
        scanner.output_dir = str(legacy_path)
        legacy_error = None
        try:
            scanner.parse_result()
            scanner.analyze_result()
        except Exception as exc:
            legacy_error = type(exc).__name__
    snapshot['legacy_wrapper_audit'] = {'true_count': scanner.true_cnt, 'false_count': scanner.false_cnt,
                                        'unmatched': scanner.lost_cnt, 'findings': len(findings),
                                        'error_type': legacy_error, 'valid_detector_score': False}
    cell_items = [{'truth': truth_status(rows), 'flagged': key in flagged_cells} for key, rows in cells.items()]
    snapshot['gitleaks'] = {'exact_line_cells': matrix(cell_items), 'findings': len(findings),
                            'findings_outside_exact_labeled_cells': len(flagged_cells - set(cells)),
                            'scan_wall_seconds': scan_wall_seconds,
                            'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(), 'reused_completed_scan': bool(prior)}
    items = [(str(scoring / relative), rows, relative in flagged_files) for relative, rows in sorted(grouped.items())]
    records = []
    private_records = args.output / 'module-file-records-private.jsonl'
    assert not private_records.exists(), 'Preserve completed/failed runs'
    with private_records.open('w') as stream:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=pii.initialize, initargs=(str(args.config.resolve()),)) as pool:
            for record in pool.map(evaluate_file, items, chunksize=4):
                records.append(record)
                stream.write(json.dumps(record) + '\n')
                if len(records) % 250 == 0:
                    stream.flush()
                    print(json.dumps({'credential_files_completed': len(records), 'total': len(items)}), flush=True)
    snapshot['files'] = len(records)
    snapshot['gitleaks']['files'] = matrix([{'truth': r['truth'], 'flagged': r['gitleaks_flagged']} for r in records])
    snapshot['module'] = {'files': matrix([{'truth': r['truth'], 'flagged': not r['accepted']} for r in records]),
                         'accepted': sum(r['accepted'] for r in records), 'rejected': sum(not r['accepted'] for r in records),
                         'rejection_reasons': dict(Counter(r['reason'] for r in records if not r['accepted'])),
                         'accepted_extractable_positive_rows': sum(r.get('extractable_positive_rows', 0) for r in records),
                         'accepted_literal_residual_rows': sum(r.get('literal_residual_rows', 0) for r in records),
                         'accepted_files_with_literal_residual': sum(r.get('any_literal_residual', False) for r in records),
                         'unextractable_positive_rows': sum(r['unextractable_positive_rows'] for r in records),
                         'timing': pii.timing([r['seconds'] for r in records])}
    snapshot['wall_seconds'] = time.perf_counter() - started
    assert original_meta == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.root / 'meta').glob('*.csv')}
    (args.output / 'credential-summary.json').write_text(json.dumps(snapshot, indent=2))
    print(json.dumps({'credential_files': len(records), 'completed': True}), flush=True)


if __name__ == '__main__':
    main()
