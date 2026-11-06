#!/usr/bin/env python3
"""只读汇总实际benchmark记录与原费用账本，不创建分配或收益结论。"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.efficiency_rsi_measurement import _cost
from src.adapters.evolution_benchmark import _model_scoreable, benchmark_evaluation_role


IGNORED_DIRECTORIES = {'artifacts', 'environment', 'verifier', 'node_modules', '.git',
                       'deps', 'data', 'data-clean', 'data-test-clean', 'dsh', 'skill-bundles', 'skill', 'skills'}
TOKEN_FIELDS = ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens')


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _code_digest(code):
    if isinstance(code, dict):
        return code.get('sha256')
    if isinstance(code, list) and code and all(isinstance(row, dict)
            and isinstance(row.get('path'), str) and isinstance(row.get('sha256'), str)
            for row in code):
        files = sorted((Path(row['path']).name, row['sha256']) for row in code)
        return hashlib.sha256(json.dumps(files, separators=(',', ':')).encode()).hexdigest()
    return None


def _number(value, *, allow_negative=False):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and (allow_negative or number >= 0) else None


def _lines(path, warnings, raw=None):
    raw = Path(path).read_bytes() if raw is None else raw
    rows = []
    for index, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('object_required')
            rows.append(value)
        except (ValueError, UnicodeError):
            warnings.append({'issue': 'invalid_jsonl_row', 'path': str(path), 'line': index})
    return rows, {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}


def _directories(root):
    for current, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name not in IGNORED_DIRECTORIES
                          and not (Path(current) / name).is_symlink())
        yield Path(current), set(files)


def _reference(value, warnings):
    if not isinstance(value, dict) or set(value) != {'path', 'sha256'}:
        return None
    try:
        return json.loads(verify(value))
    except (OSError, ValueError, TypeError):
        warnings.append({'issue': 'unavailable_or_changed_reference', 'reference': value})
        return None


def _dependency_conditions(enabled, result, warnings):
    if enabled is False:
        return {'status': 'disabled'} if result.get('dependency_preparation') is None else None
    if enabled is not True:
        return None
    preparation = _reference(result.get('dependency_preparation'), warnings)
    if not isinstance(preparation, dict):
        return None
    profile = preparation.get('profile')
    if preparation.get('status') == 'not_applicable' and profile is None:
        return {'status': 'not_applicable'}
    if preparation.get('status') != 'prepared' or not isinstance(profile, dict):
        return None
    reference = profile.get('profile')
    if not isinstance(_reference(reference, warnings), dict):
        return None
    selected = {name: profile.get(name) for name in ('id', 'versions', 'steps', 'environment_keys')}
    return {'status': 'prepared', 'profile_sha256': reference['sha256'],
            'selection_sha256': hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()}


def _method(effective, result):
    if isinstance(result.get('method'), str):
        return result['method']
    return {'trial': 'vanilla', 'geneloop': 'geneloop',
            'skill-infinity': 'skill_infinity_paper_reproduction'}.get(effective.get('mode'), 'unknown')


def _source_count(trials):
    groups = []
    for trial in trials:
        if not trial['source_identity']:
            continue
        keys = {'identity:' + trial['source_identity']}
        files = trial['matching_conditions']['source_files']
        if files is not None:
            keys.add('files:' + hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest())
        separate = []
        for group in groups:
            if group & keys:
                keys.update(group)
            else:
                separate.append(group)
        groups = separate + [keys]
    return len(groups)


def _account(request_ids, providers, *, inventory_complete=True):
    keys = sorted(set(request_ids))
    cost = _cost(keys, providers)
    if not inventory_complete:
        cost['model_usd'] = cost['model_usd_decimal'] = None
    tokens = {}
    for field in TOKEN_FIELDS:
        known = 0
        unknown = []
        for key in keys:
            usage = providers[key].get('response_usage')
            value = usage.get(field) if isinstance(usage, dict) else None
            if type(value) is int and value >= 0:
                known += value
            else:
                unknown.append({'ledger_ref': key[0], 'id': key[1]})
        tokens[field] = {'value': known if not unknown and inventory_complete else None,
                         'known_value': known, 'unknown_requests': unknown}
    elapsed = [_number(providers[key].get('elapsed_seconds')) for key in keys]
    return {'requests': len(keys), 'request_refs': [{'ledger_ref': key[0], 'id': key[1]} for key in keys],
            'booked_only_requests': sum(providers[key]['phase'] == 'booked' for key in keys),
            'settled_requests': sum(providers[key]['phase'] != 'booked' for key in keys),
            'inventory_complete': inventory_complete, **cost, 'tokens': tokens,
            'provider_elapsed_seconds_sum': str(sum(elapsed, Decimal(0)))
                if all(value is not None for value in elapsed) else None,
            'billing_usd': None, 'non_model_costs_usd': {'machine': None, 'human_revision': None, 'external_services': None},
            'cost_source': 'original_ledger_observed_peak_usd_estimate'}


def _quality(result, threshold):
    evaluation = result.get('evaluation', {})
    reward = _number(evaluation.get('reward'), allow_negative=True)
    verified = evaluation.get('status') == 'evaluated'
    scoreable = (result.get('score') is not None and result.get('model_scoreable') is not False
                 and _model_scoreable(result.get('model', {})))
    return {'raw_reward': evaluation.get('reward'), 'quality_threshold': str(threshold),
            'verifier_status': evaluation.get('status'),
            'trial_scoreable': scoreable,
            'full_quality': reward >= threshold if verified and reward is not None and scoreable else None,
            'paper_positive_reward_pass': reward > 0 if verified and reward is not None and scoreable else None}


def summarize(run_directories, ledger_ref, *, ledger_id=None, quality_threshold='1'):
    """Read booking ownership and settlement once, with no ledger mutations."""
    threshold = _number(quality_threshold)
    if threshold is None or threshold <= 0:
        raise ValueError('benchmark_summary_quality_threshold_invalid')
    warnings = []
    requested = sorted({Path(root).resolve() for root in run_directories}, key=lambda p: len(p.parts))
    roots, ignored = [], []
    for root in requested:
        if not root.is_dir():
            raise ValueError('benchmark_summary_run_missing:' + str(root))
        if any(root.is_relative_to(parent) for parent in roots):
            ignored.append(str(root))
        else:
            roots.append(root)
    if not roots:
        raise ValueError('benchmark_summary_runs_required')
    path = Path(ledger_ref['path'] if isinstance(ledger_ref, dict) else ledger_ref).resolve()
    ledger_bytes = verify(ledger_ref) if isinstance(ledger_ref, dict) else None
    ledger_rows, ledger_snapshot = _lines(path, warnings, ledger_bytes)
    identity = str(ledger_id or path)
    providers, conflicted = {}, set()
    for row in ledger_rows:
        if row.get('request_id') is None:
            continue
        key = identity, str(row['request_id'])
        fields = {name: row.get(name) for name in ('observed_peak_usd', 'reserved_upper_usd',
                   'response_status', 'response_usage', 'elapsed_seconds', 'attempt_path', 'model')}
        phase = 'booked' if row.get('phase') == 'booked' or row.get('event') == 'request_booked' else 'settled'
        for name in ('observed_peak_usd', 'reserved_upper_usd'):
            if fields[name] is not None:
                amount = _number(fields[name])
                if amount is None:
                    warnings.append({'issue': 'invalid_ledger_cost', 'request_id': key[1], 'field': name})
                fields[name] = str(amount) if amount is not None else None
        old = providers.get(key)
        if old and old['phase'] == phase == 'settled' and any(old.get(name) != value for name, value in fields.items()):
            conflicted.add(key)
        if old and old['phase'] == 'settled' and phase == 'booked':
            continue
        providers[key] = {**fields, 'phase': phase}
    for key in conflicted:
        providers[key].update(observed_peak_usd=None, response_usage=None)
        warnings.append({'issue': 'conflicting_ledger_settlements', 'request_id': key[1]})
    bookings = defaultdict(set)
    sessions, trials, records, run_info = {}, {}, {}, {}
    failures, generations, materials, activation_events, skill_reads, capability_calls = [], [], [], [], [], []
    for root in roots:
        effective = _json(root / 'effective.json') if (root / 'effective.json').is_file() else {}
        result = _json(root / 'result.json') if (root / 'result.json').is_file() else {}
        run_info[root] = {'directory': str(root), 'method': _method(effective, result),
                          'status': result.get('status', 'incomplete'),
                          'self_improvement': result.get('self_improvement'),
                          'elapsed_seconds': result.get('elapsed_seconds')}
        for directory, files in _directories(root):
            local_effective = _json(directory / 'effective.json') if 'effective.json' in files else {}
            local_result = _json(directory / 'result.json') if 'result.json' in files else {}
            if local_result:
                records[directory] = local_result
                if local_result.get('status') in ('failed', 'rejected', 'incomplete', 'timeout'):
                    failures.append({'directory': str(directory), 'status': local_result['status'],
                                     'error': local_result.get('error'), 'record': file_ref(directory / 'result.json')})
                if directory.parent.name == 'acquisitions' and local_result.get('origin') == 'model_construction':
                    materials.append({'directory': str(directory), 'status': local_result.get('status'),
                        'library': local_result.get('library'), 'error': local_result.get('error'),
                        'record': file_ref(directory / 'result.json')})
            if 'requests.jsonl' in files and local_effective:
                rows, _ = _lines(directory / 'requests.jsonl', warnings)
                for row in rows:
                    if row.get('phase') != 'booked' and row.get('event') != 'request_booked':
                        continue
                    if row.get('ledger_ref') != identity or row.get('request_id') is None:
                        warnings.append({'issue': 'booking_ledger_unmatched', 'directory': str(directory)})
                        continue
                    key = identity, str(row['request_id'])
                    owner = str(Path(row.get('attempt_path') or directory).resolve())
                    bookings[key].add(owner)
                    if key not in providers:
                        providers[key] = {'phase': 'booked', 'observed_peak_usd': None,
                                          'reserved_upper_usd': row.get('reserved_upper_usd')}
                sessions[str(directory)] = {'directory': str(directory), 'mode': local_effective.get('mode'),
                                           'effective': local_effective, 'result': local_result}
            if ('task_id' in local_result and local_result.get('split') in ('training', 'test')
                    and ('manifest.json' in files or directory.parent.name == 'trials')):
                manifest = _json(directory / 'manifest.json') if 'manifest.json' in files else {}
                model = local_result.get('model', {})
                model_directory = str(Path(model['directory']).resolve()) if model.get('directory') else None
                source_id = manifest.get('source_identity')
                source_hashes = manifest.get('source_files')
                config = _json(Path(model_directory) / 'effective.json') if model_directory and (
                    Path(model_directory) / 'effective.json').is_file() else {}
                common = {'source_files': source_hashes, 'source_version': manifest.get('source_version'),
                          'verifier_environment': manifest.get('effective_verifier_environment'),
                          'prewarm_dependencies': effective.get('prewarm_dependencies')
                              if type(effective.get('prewarm_dependencies')) is bool else None,
                          'dependency_preparation': _dependency_conditions(
                              effective.get('prewarm_dependencies'), local_result, warnings),
                          'model': config.get('model'), 'reasoning_effort': config.get('reasoning_effort'),
                          'max_tokens': config.get('max_tokens'),
                          'harness_code_sha256': _code_digest(config.get('code'))}
                state = local_result.get('decision_context', {}).get('state', {})
                explicit_role = local_result.get('evaluation_role') or (
                    state.get('evaluation_role') if isinstance(state, dict) else None)
                trials[str(directory)] = {'directory': str(directory), 'run': str(root),
                    'method': run_info[root]['method'], 'task_id': local_result['task_id'],
                    'split': local_result['split'], 'label': local_result.get('label'),
                    'evaluation_role': benchmark_evaluation_role(local_result),
                    'evaluation_role_inferred': explicit_role is None,
                    'status': local_result.get('status'), 'source_identity': source_id,
                    'elapsed_seconds': local_result.get('elapsed_seconds'), 'model_directory': model_directory,
                    'artifact_collection_phase': local_result.get('artifacts', {}).get('collection_phase')
                        or local_result.get('artifacts', {}).get('phase'),
                    'model_status': model.get('status'), **_quality(local_result, threshold),
                    'matching_conditions': common, 'record': file_ref(directory / 'result.json')}
            if 'skill-activations.jsonl' in files and local_effective:
                rows, reference = _lines(directory / 'skill-activations.jsonl', warnings)
                activation_events.extend({'directory': str(directory), 'event': index,
                                          'name': row.get('name'), 'evidence': reference}
                                         for index, row in enumerate(rows) if row.get('status') == 'loaded')
            if 'tool-calls.jsonl' in files and local_effective:
                rows, reference = _lines(directory / 'tool-calls.jsonl', warnings)
                skill_reads.extend({'directory': str(directory), 'event': index, 'evidence': reference}
                    for index, row in enumerate(rows) if row.get('phase') == 'finished'
                    and row.get('name') == 'read_skill' and row.get('status') == 'completed'
                    and row.get('arguments', {}).get('resource') == 'SKILL.md'
                    and isinstance(row.get('result'), dict) and row['result'].get('status') != 'error')
            if 'capability-call-records.json' in files:
                for row in _json(directory / 'capability-call-records.json'):
                    trace = _reference(row.get('execution_ref'), warnings)
                    verified = bool(row.get('status') == 'succeeded' and trace and trace.get('status') == 'succeeded'
                        and trace.get('task_id') == row.get('task_id') and trace.get('root') == row.get('capability'))
                    capability_calls.append({'directory': str(directory), 'id': row.get('id'),
                        'capability': row.get('capability'), 'status': row.get('status'), 'verified_success': verified})
            if local_result.get('format') == 'gene_benchmark_generation_v1' and 'development_tasks' in local_effective:
                recursive = local_result.get('recursive_learning', {})
                learned = _reference(recursive.get('result'), warnings)
                generations.append({'directory': str(directory), 'status': local_result.get('status'),
                    'strategy_selected': local_result.get('selection') is not None,
                    'native_acquisitions': [{key: item.get(key) for key in ('status', 'origin', 'library', 'error')}
                                            for item in local_result.get('capability_acquisitions', [])],
                    'recursive_status': recursive.get('status'), 'recursive_reason': recursive.get('reason'),
                    'recursive_candidates': len(learned['candidates']) if learned and 'candidates' in learned else None,
                    'publication': recursive.get('publication')})
    trial_by_session = {row['model_directory']: row for row in trials.values() if row['model_directory']}
    assignments = {}
    for key, provider in providers.items():
        claims = bookings.get(key, set())
        owner = next(iter(claims)) if len(claims) == 1 else provider.get('attempt_path')
        relevant = any(Path(claim).is_relative_to(root) for claim in claims for root in roots)
        if len(claims) > 1:
            warnings.append({'issue': 'conflicting_booked_owners', 'request_id': key[1], 'owners': sorted(claims)})
            owner = None
        if owner is not None:
            owner = str(Path(owner).resolve())
        matched = [root for root in roots if owner and Path(owner).is_relative_to(root)]
        if not matched:
            if relevant:
                assignments[key] = {'run': None, 'method': 'attribution_unknown', 'phase': 'attribution_unknown',
                                    'task_id': None, 'split': None, 'label': None, 'evaluation_role': None}
            continue
        root = max(matched, key=lambda value: len(value.parts))
        if len(claims) == 1 and provider.get('attempt_path') not in (None, owner):
            warnings.append({'issue': 'settlement_owner_differs_from_booking', 'request_id': key[1],
                             'booked_owner': owner, 'settled_owner': provider['attempt_path']})
        trial = trial_by_session.get(owner)
        session = sessions.get(owner, {})
        assignments[key] = {'run': str(root), 'method': run_info[root]['method'],
            'owner_path': owner,
            'phase': 'task_execution' if trial else session.get('mode') or 'recorded_request',
            'task_id': trial['task_id'] if trial else None, 'split': trial['split'] if trial else None,
            'evaluation_role': trial['evaluation_role'] if trial else None,
            'label': trial['label'] if trial else None}
    for directory, session in sessions.items():
        expected = session['result'].get('provider_requests')
        found = sum(owner.get('owner_path') == directory for owner in assignments.values())
        if type(expected) is int and expected > found:
            warnings.append({'issue': 'reported_requests_without_inventory', 'directory': directory,
                             'reported_requests': expected, 'verified_inventory_requests': found})
    complete = not any(row['issue'] in ('invalid_jsonl_row', 'reported_requests_without_inventory') for row in warnings)
    def accounting(keys):
        return _account(keys, providers, inventory_complete=complete)
    for trial in trials.values():
        keys = [key for key, owner in assignments.items() if owner.get('owner_path') == trial['model_directory']]
        trial['accounting'] = accounting(keys)
    groups = defaultdict(list)
    for key, owner in assignments.items():
        groups[(owner['method'], owner['phase'], owner['task_id'], owner['split'], owner['label'],
                owner['evaluation_role'])].append(key)
    for trial in trials.values():
        groups.setdefault((trial['method'], 'task_execution', trial['task_id'], trial['split'], trial['label'],
                           trial['evaluation_role']), [])
    phases = [{'method': group[0], 'phase': group[1], 'task_id': group[2], 'split': group[3],
               'label': group[4], 'evaluation_role': group[5], 'accounting': accounting(keys),
               'trial_elapsed_seconds': {trial['directory']: trial['elapsed_seconds'] for trial in trials.values()
                    if (trial['method'], 'task_execution', trial['task_id'], trial['split'], trial['label'],
                        trial['evaluation_role']) == group},
               'session_elapsed_seconds': {owner: sessions[owner]['result'].get('elapsed_seconds')
                    for owner in {assignments[key].get('owner_path') for key in keys} if owner in sessions}}
              for group, keys in groups.items()]
    methods = []
    names = {info['method'] for info in run_info.values()} | {row['method'] for row in assignments.values()}
    for method in sorted(names):
        method_trials = [row for row in trials.values() if row['method'] == method]
        method_roots = [root for root, info in run_info.items() if info['method'] == method]
        keys = [key for key, owner in assignments.items() if owner['method'] == method]
        belongs = lambda directory: any(Path(directory).is_relative_to(root) for root in method_roots)
        calls = [row for row in capability_calls if belongs(row['directory'])]
        methods.append({'method': method, 'accounting': accounting(keys), 'trials': method_trials,
            'unique_task_ids': sorted({row['task_id'] for row in method_trials}),
            'known_independent_sources': _source_count(method_trials),
            'trials_with_unknown_source': sum(row['source_identity'] is None for row in method_trials),
            'native_skill_loads': sum(belongs(row['directory']) for row in activation_events),
            'explicit_skill_body_reads': sum(belongs(row['directory']) for row in skill_reads),
            'capability_call_attempts': len(calls),
            'verified_capability_calls': sum(row['verified_success'] for row in calls),
            'native_material_outcomes': [row for row in materials if belongs(row['directory'])],
            'generations': [row for row in generations if belongs(row['directory'])],
            'known_recorded_trial_elapsed_seconds_sum': str(sum((_number(row['elapsed_seconds']) or Decimal(0)
                                                          for row in method_trials), Decimal(0))),
            'trials_with_unknown_elapsed': sum(_number(row['elapsed_seconds']) is None for row in method_trials)})
    matching = defaultdict(list)
    for trial in trials.values():
        trial['reuses_observed_validation_dataset'] = trial['evaluation_role'] == 'final' and any(
            other['evaluation_role'] == 'validation' and other['method'] == trial['method']
            and other['task_id'] == trial['task_id'] and other['split'] == trial['split']
            and trial['matching_conditions']['source_files'] is not None
            and other['matching_conditions']['source_files'] == trial['matching_conditions']['source_files']
            for other in trials.values())
        value = [trial['task_id'], trial['split'], trial['evaluation_role'], trial['matching_conditions']]
        signature = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        matching[signature].append(trial)
    matched = []
    for signature, rows in matching.items():
        missing = any(row['matching_conditions'][name] is None for row in rows
                      for name in ('source_files', 'source_version', 'verifier_environment',
                                   'model', 'reasoning_effort', 'max_tokens', 'harness_code_sha256',
                                   'prewarm_dependencies', 'dependency_preparation'))
        matched.append({'signature': signature, 'task_id': rows[0]['task_id'], 'split': rows[0]['split'],
            'evaluation_role': rows[0]['evaluation_role'],
            'comparison_scope': ('canonical_' if rows[0]['split'] == 'test' else 'training_')
                + rows[0]['evaluation_role'],
            'reuses_observed_validation_dataset': any(row['reuses_observed_validation_dataset'] for row in rows),
            'heldout_status': ('observed_validation_reuse' if any(
                row['reuses_observed_validation_dataset'] for row in rows) else 'prior_exposure_unverified')
                if rows[0]['evaluation_role'] == 'final' else None,
            'methods': sorted({row['method'] for row in rows}), 'trials': [row['directory'] for row in rows],
            'full_quality_comparable': len({row['method'] for row in rows}) > 1 and not missing
                and all(row['full_quality'] is True for row in rows),
            'missing_matching_conditions': missing})
    return {'format': 'evolution_benchmark_summary_v1', 'ledger': {**ledger_snapshot, 'ledger_id': identity},
            'ledger_access': 'read_only', 'ledger_write_operations': 0, 'ignored_nested_run_roots': ignored,
            'runs': list(run_info.values()), 'methods': methods, 'phases': phases,
            'overall_accounting': accounting(assignments), 'failures': failures,
            'matching_groups': matched, 'savings_estimates': [], 'warnings': warnings,
            'source_count_scope': 'Original identities coalesced with identical source-file inventories.',
            'elapsed_scope': 'Per-trial and provider duration sums are recorded work, not overall wall time.',
            'evaluation_scope': 'Dataset split records input provenance. Evaluation role records development, '
                'validation or final use. Final-role records alone do not establish new heldout data.',
            'adoption_scope': 'Native skill loads and verified Runtime calls do not establish causal benefit.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', required=True, type=Path)
    parser.add_argument('--ledger-ref', required=True, type=Path)
    parser.add_argument('--ledger-id')
    parser.add_argument('--quality-threshold', default='1')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = summarize(args.run, args.ledger_ref, ledger_id=args.ledger_id,
                       quality_threshold=args.quality_threshold)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
