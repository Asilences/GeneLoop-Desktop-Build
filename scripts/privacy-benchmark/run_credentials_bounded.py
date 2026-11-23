"""Finish CredData with a declared evaluation deadline, not a redaction rule.

Unknown results are neither privacy rejections nor safe detections. Completed
same-rule records below a conservative reuse margin are retained as observations.
Pebble owns timeout termination/restart; no custom process killer or scanner.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, TimeoutError, wait
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

from pebble import ProcessPool
import run_credentials as legacy
import run_pii as pii


def transform(text):
    return pii.module_result(text)


def finish_record(base, result, text, annotations):
    values, unsupported = legacy.extract_positive_values(text, annotations)
    record = {**base, **result, 'status': 'accepted' if result['accepted'] else 'rejected',
              'positive_annotation_rows': len(values) + unsupported,
              'unextractable_positive_rows': unsupported}
    if result['accepted']:
        output = record.pop('text')
        record['extractable_positive_rows'] = len(values)
        record['literal_residual_rows'] = sum(value in output for value in values)
        record['any_literal_residual'] = record['literal_residual_rows'] > 0
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--method', type=Path, required=True)
    parser.add_argument('--prior-output', type=Path, required=True)
    parser.add_argument('--scan-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(); sys.path.insert(0, str(root))
    method = json.loads(args.method.read_text()); started = time.perf_counter()
    assert importlib.metadata.version('Pebble') == method['controller_version']
    assert not args.output.exists(), 'Use a new experiment output directory'
    args.output.mkdir(parents=True)
    annotations = legacy.read_annotations(root)
    grouped, cells = defaultdict(list), defaultdict(list)
    for row in annotations:
        grouped[row['FilePath']].append(row)
        cells[(row['FilePath'], row['LineStart'], row['LineEnd'])].append(row)
    assert len(grouped) == 11030 and len(annotations) == 67896
    scoring = root.parent / 'CredData-scoring'
    initial = json.loads((args.scan_output / 'credential-frozen-snapshot.json').read_text())
    data_digest = hashlib.sha256(json.dumps({p: hashlib.sha256((scoring / p).read_bytes()).hexdigest() for p in sorted(grouped)}, sort_keys=True).encode()).hexdigest()
    assert data_digest == initial['data_digest']
    report = args.scan_output / 'gitleaks-modern-private.json'
    findings = json.loads(report.read_text()); flagged_files, flagged_cells = set(), set()
    for item in findings:
        file = Path(item['File']); assert file.is_absolute() and file.is_relative_to((scoring / 'data').resolve())
        relative = 'data/' + str(file.relative_to((scoring / 'data').resolve()))
        flagged_files.add(relative); flagged_cells.add((relative, item['StartLine'], item['EndLine']))
    raw_prior = args.prior_output / 'module-file-records-private.jsonl'
    prior, tail_incomplete = {}, 0
    lines = raw_prior.read_text().splitlines()
    for index, line in enumerate(lines):
        try: row = json.loads(line)
        except json.JSONDecodeError:
            assert index == len(lines) - 1
            tail_incomplete += 1; continue
        assert row['file'] in grouped and row['file'] not in prior
        prior[row['file']] = row
    cache = {name: row for name, row in prior.items() if row['seconds'] <= method['reuse_max_seconds']}
    assert all(row['gitleaks_flagged'] == (name in flagged_files) for name, row in cache.items())
    snapshot = {'run_id': method['run_id'], 'rule_commit': method['rule_commit'], 'method': method,
                'method_sha256': hashlib.sha256(args.method.read_bytes()).hexdigest(),
                'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
                'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'data_digest': data_digest, 'records_from_unbounded_attempt': len(prior),
                'reused_completed_records': len(cache), 'prior_over_margin_rerun': len(prior) - len(cache),
                'prior_trailing_incomplete_lines': tail_incomplete,
                'prior_record_file_sha256': hashlib.sha256(raw_prior.read_bytes()).hexdigest(),
                'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'controller': {'name': 'Pebble', 'version': importlib.metadata.version('Pebble'), 'license': 'LGPL', 'scope': 'evaluation only'},
                'cloud_requests': 0, 'cloud_api_cost': 0}
    (args.output / 'credential-frozen-snapshot.json').write_text(json.dumps(snapshot, indent=2))
    todo = iter(name for name in sorted(grouped) if name not in cache)
    records = []; pending = {}; timeout_seconds = method['per_call_timeout_seconds']
    with (args.output / 'module-file-records-private.jsonl').open('w') as stream:
        for name, old in sorted(cache.items()):
            record = {**old, 'status': 'accepted' if old['accepted'] else 'rejected', 'observation_origin': 'completed_unbounded_attempt'}
            records.append(record); stream.write(json.dumps(record) + '\n')
        stream.flush()
        with ProcessPool(max_workers=method['workers'], initializer=pii.initialize, initargs=(str(args.config.resolve()),)) as pool:
            def submit():
                try: name = next(todo)
                except StopIteration: return False
                text = (scoring / name).read_text(encoding='utf-8')
                future = pool.schedule(transform, args=(text,), timeout=timeout_seconds)
                pending[future] = (name, text)
                return True
            for _ in range(method['workers'] * 2):
                if not submit(): break
            print(json.dumps({'reused': len(cache), 'to_evaluate': len(grouped) - len(cache), 'deadline_seconds': timeout_seconds}), flush=True)
            while pending:
                done, _ = wait(pending, timeout=5, return_when=FIRST_COMPLETED)
                for future in done:
                    name, text = pending.pop(future)
                    base = {'file': name, 'truth': legacy.truth_status(grouped[name]),
                            'gitleaks_flagged': name in flagged_files, 'chars': len(text),
                            'observation_origin': 'budgeted_attempt'}
                    try:
                        record = finish_record(base, future.result(), text, grouped[name])
                    except TimeoutError:
                        record = {**base, 'status': 'evaluation_timeout', 'accepted': None,
                                  'seconds': None, 'censored_lower_bound_seconds': timeout_seconds}
                    except Exception as exc:
                        record = {**base, 'status': 'evaluation_error', 'accepted': None,
                                  'seconds': None, 'error_type': type(exc).__name__}
                    records.append(record); stream.write(json.dumps(record) + '\n'); stream.flush()
                    if len(records) % 100 == 0:
                        print(json.dumps({'recorded': len(records), 'total': len(grouped), 'statuses': dict(Counter(r['status'] for r in records))}), flush=True)
                    submit()
    assert len(records) == len(grouped) and len({r['file'] for r in records}) == len(grouped)
    completed = [r for r in records if r['accepted'] is not None]
    accepted = [r for r in completed if r['accepted']]
    rejected = [r for r in completed if not r['accepted']]
    unknown = [r for r in records if r['accepted'] is None]
    snapshot.update(files=len(records), available_repositories=len({r['RepoName'] for r in annotations}),
                    full_annotation_labels=dict(Counter(r['GroundTruth'] for r in annotations)),
                    evaluated_annotation_labels=dict(Counter(r['GroundTruth'] for r in annotations)),
                    excluded_annotation_labels={}, unavailable_repositories=[],
                    statuses=dict(Counter(r['status'] for r in records)), wall_seconds=time.perf_counter()-started)
    snapshot['gitleaks'] = {'findings': len(findings), 'files': legacy.matrix([{'truth': r['truth'], 'flagged': r['gitleaks_flagged']} for r in records]),
                           'exact_line_cells': legacy.matrix([{'truth': legacy.truth_status(rows), 'flagged': key in flagged_cells} for key, rows in cells.items()]),
                           'findings_outside_exact_labeled_cells': len(flagged_cells - set(cells)),
                           'scan_wall_seconds': None, 'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(), 'reused_completed_scan': True}
    snapshot['module'] = {'accepted': len(accepted), 'rejected': len(rejected), 'evaluation_timeout': sum(r['status']=='evaluation_timeout' for r in records),
                         'evaluation_error': sum(r['status']=='evaluation_error' for r in records),
                         'files': legacy.matrix([{'truth': r['truth'], 'flagged': not r['accepted']} for r in completed]),
                         'file_matrix_scope': 'completed outcomes only; unknown predictions excluded and counted separately',
                         'unknown_truth_counts': dict(Counter(r['truth'] for r in unknown)),
                         'rejection_reasons': dict(Counter(r['reason'] for r in rejected)),
                         'accepted_extractable_positive_rows': sum(r.get('extractable_positive_rows',0) for r in accepted),
                         'accepted_literal_residual_rows': sum(r.get('literal_residual_rows',0) for r in accepted),
                         'accepted_files_with_literal_residual': sum(r.get('any_literal_residual',False) for r in accepted),
                         'unextractable_positive_rows_completed': sum(r['unextractable_positive_rows'] for r in completed),
                         'timing_completed': pii.timing([r['seconds'] for r in completed])}
    snapshot['legacy_wrapper_audit'] = method.get('legacy_audit_reference', {
        'error_type': 'ValueError', 'valid_detector_score': False,
        'details': 'Preserved original wrapper audit in the unbounded attempt; Category is missing'})
    (args.output / 'credential-summary.json').write_text(json.dumps(snapshot, indent=2))
    print(json.dumps({'completed': True, 'files': len(records), 'statuses': snapshot['statuses']}), flush=True)


if __name__ == '__main__':
    main()
