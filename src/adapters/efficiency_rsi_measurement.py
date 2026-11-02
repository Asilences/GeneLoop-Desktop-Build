"""Frozen efficiency/capability study validation and measurement, never publication.

The caller must supply the runner's complete independent registry and ledger
export. Hashes detect changes; they do not authenticate a fabricated inventory.
No LLM calls, retry loop, privilege changes, or existing policy changes occur here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator
from .rsi_quality import quality_status, verify_quality_files

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / 'schemas/efficiency-rsi-study-v1.schema.json').read_text(encoding='utf-8'))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _validate(value, kind):
    def finite(v):
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError('efficiency_nonfinite_number')
        if isinstance(v, dict):
            for x in v.values(): finite(x)
        elif isinstance(v, list):
            for x in v: finite(x)
    finite(value)
    validator = Draft202012Validator({'$defs': SCHEMA['$defs'], '$ref': '#/$defs/' + kind})
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        raise ValueError('efficiency_schema_invalid:' + '/'.join(map(str, errors[0].path)))
    return deepcopy(value)


def _index(rows, key, error):
    result = {}
    for row in rows:
        if row[key] in result: raise ValueError(error)
        result[row[key]] = row
    return result


def _refs(values):
    if len({x['id'] for x in values}) != len(values):
        raise ValueError('efficiency_duplicate_capability')
    for x in values:
        if x['id'] != 'cap_' + x['sha256'][:24]:
            raise ValueError('efficiency_capability_identity_changed')
    return sorted(values, key=lambda x: x['id'])


def validate_study(plan):
    """Return a defensive copy after schema and cross-field checks."""
    plan = _validate(plan, 'study')
    tasks = _index(plan['tasks'], 'id', 'efficiency_duplicate_task')
    arms = _index(plan['arms'], 'id', 'efficiency_duplicate_arm')
    _index(plan['cells'], 'id', 'efficiency_duplicate_cell')
    if 'study_only' in arms or plan['baseline_arm'] not in arms:
        raise ValueError('efficiency_baseline_or_reserved_arm')
    if len({t['sha256'] for t in tasks.values()}) != len(tasks):
        raise ValueError('efficiency_duplicate_or_leaked_task_bytes')
    for arm in arms.values():
        for prefix in ('execution', 'build'):
            refs = _refs(arm[prefix + '_capabilities'])
            if refs and arm[prefix + '_snapshot_sha256'] is None:
                raise ValueError('efficiency_capability_snapshot_required')
    allocations = _index(plan['overhead_allocations'], 'category', 'efficiency_duplicate_allocation_policy')
    for row in allocations.values():
        if set(row['weights']) - (set(arms) | {'study_only'}) or not math.isclose(sum(row['weights'].values()), 1., rel_tol=0., abs_tol=1e-9):
            raise ValueError('efficiency_invalid_allocation_policy')
    blocks = {}
    seen = set()
    for cell in plan['cells']:
        if cell['task_id'] not in tasks or cell['arm_id'] not in arms:
            raise ValueError('efficiency_unknown_cell_reference')
        if tasks[cell['task_id']]['split'] == 'training':
            raise ValueError('efficiency_training_in_evaluation')
        key = cell['task_id'], cell['replicate'], cell['phase']
        pair = key + (cell['arm_id'],)
        if pair in seen: raise ValueError('efficiency_duplicate_cell_assignment')
        seen.add(pair)
        blocks.setdefault(key, []).append(cell)
    for cells in blocks.values():
        if {c['arm_id'] for c in cells} != set(arms):
            raise ValueError('efficiency_unpaired_frozen_matrix')
        if len({(c['budget_usd'], c['max_attempts']) for c in cells}) != 1:
            raise ValueError('efficiency_unequal_research_budget')
    return plan


def _file(root, ref, expected):
    path = (root / ref).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('efficiency_evidence_missing_or_outside_root')
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('efficiency_evidence_changed')


def _key(row):
    return row['ledger_ref'], row['id']


def _providers(rows, arms):
    providers = {}
    for row in rows:
        if set(row['allocations']) - (set(arms) | {'study_only'}):
            raise ValueError('efficiency_unknown_allocation_arm')
        if not math.isclose(sum(row['allocations'].values()), 1., rel_tol=0., abs_tol=1e-9):
            raise ValueError('efficiency_allocation_not_conserved')
        if row['phase'] == 'booked' and row['observed_peak_usd'] is not None:
            raise ValueError('efficiency_booking_cannot_claim_cost')
        key = _key(row)
        old = providers.get(key)
        if old is None or old == row:
            providers[key] = row
            continue
        if old['allocations'] != row['allocations']:
            raise ValueError('efficiency_request_allocation_changed')
        if old['phase'] == 'booked' and row['phase'] != 'booked':
            providers[key] = row
        elif old['phase'] != 'booked' and row['phase'] == 'booked':
            pass
        else:
            raise ValueError('efficiency_conflicting_request_records')
    return providers


def _cost(keys, providers, arm=None):
    known = 0.
    unknown, upper = [], 0.
    for key in sorted(set(keys)):
        row = providers[key]
        weight = 1. if arm is None else row['allocations'].get(arm, 0.)
        if not weight: continue
        amount = row['observed_peak_usd'] if row['phase'] != 'booked' else None
        if amount is None:
            unknown.append({'ledger_ref': key[0], 'id': key[1]})
            if row['reserved_upper_usd'] is None: upper = None
            elif upper is not None: upper += row['reserved_upper_usd'] * weight
        else:
            known += amount * weight
            if upper is not None: upper += amount * weight
    return {'model_usd': None if unknown else known, 'known_model_usd': known,
            'unknown_requests': unknown, 'accounted_upper_usd': upper}


def measure_study(plan, observations, *, registry, evidence_root):
    """Measure every frozen cell, including unobserved and unsuccessful cells.

    `registry` is an independently exported runner registry. The caller must not
    reconstruct it from the successful runs in `observations`.
    """
    plan = validate_study(plan)
    obs, registry = _validate(observations, 'observations'), _validate(registry, 'registry')
    plan_sha = digest(plan)
    if obs['plan_sha256'] != plan_sha or registry['plan_sha256'] != plan_sha:
        raise ValueError('efficiency_frozen_plan_changed')
    if obs['registry_sha256'] != digest(registry):
        raise ValueError('efficiency_runner_registry_changed')
    root = Path(evidence_root).resolve()
    _file(root, plan['evaluator']['ref'], plan['evaluator']['sha256'])
    tasks = {t['id']: t for t in plan['tasks']}
    arms = {a['id']: a for a in plan['arms']}
    cells = {c['id']: c for c in plan['cells']}
    reg = _index(registry['cells'], 'cell_id', 'efficiency_duplicate_registry_cell')
    if set(reg) != set(cells): raise ValueError('efficiency_registry_cell_inventory_incomplete')
    expected = [a for c in reg.values() for a in c['attempt_ids']]
    if len(set(expected)) != len(expected): raise ValueError('efficiency_attempt_registered_twice')
    attempts = _index(obs['attempts'], 'id', 'efficiency_duplicate_attempt')
    if set(expected) != set(attempts): raise ValueError('efficiency_attempt_inventory_incomplete')
    providers = _providers(obs['providers'], arms)
    registered_requests = {_key(r) for r in registry['request_refs']}
    if set(providers) != registered_requests:
        raise ValueError('efficiency_request_inventory_incomplete')
    owners, qualities = {}, {}
    def assign(refs, owner):
        keys = [_key(r) for r in refs]
        if len(set(keys)) != len(keys): raise ValueError('efficiency_duplicate_request_reference')
        for key in keys:
            if key not in providers: raise ValueError('efficiency_missing_request_ledger')
            if key in owners: raise ValueError('efficiency_request_attributed_twice')
            owners[key] = owner
        return keys
    for cell_id, entry in reg.items():
        cell, previous = cells[cell_id], None
        if len(entry['attempt_ids']) > cell['max_attempts']:
            raise ValueError('efficiency_attempt_limit_exceeded')
        for ordinal, aid in enumerate(entry['attempt_ids'], 1):
            a = attempts[aid]
            if a['cell_id'] != cell_id or a['ordinal'] != ordinal or a['parent_attempt_id'] != previous:
                raise ValueError('efficiency_retry_chain_changed')
            previous = aid
            if a['conditions_sha256'] != plan['conditions_sha256']:
                raise ValueError('efficiency_conditions_changed')
            for prefix in ('execution', 'build'):
                arm = arms[cell['arm_id']]
                if (a[prefix + '_snapshot_sha256'] != arm[prefix + '_snapshot_sha256'] or
                        _refs(a[prefix + '_capabilities']) != _refs(arm[prefix + '_capabilities'])):
                    raise ValueError('efficiency_visible_capability_set_changed')
            if entry['closed'] and a['status'] == 'running':
                raise ValueError('efficiency_closed_cell_has_running_attempt')
            assigned = assign(a['request_refs'], aid)
            if any(providers[key]['allocations'] != {cell['arm_id']: 1} for key in assigned):
                raise ValueError('efficiency_attempt_cost_shifted_to_other_arm')
            q = 'unknown'
            if a['quality'] is not None:
                if a['artifact_ref'] is None or a['artifact_sha256'] is None:
                    raise ValueError('efficiency_quality_artifact_required')
                _file(root, a['artifact_ref'], a['artifact_sha256'])
                payload = a['quality'].get('payload', {})
                if payload.get('evaluator') != plan['evaluator']['id'] or payload.get('task_id') != cell['task_id']:
                    raise ValueError('efficiency_independent_evaluator_changed')
                q = quality_status(a['quality'], task_sha256=tasks[cell['task_id']]['sha256'],
                                   artifact_sha256=a['artifact_sha256'], rubric_sha256=plan['rubric_sha256'],
                                   required_checks=plan['required_checks'])
                verify_quality_files(a['quality'], root)
            if a['status'] == 'quality_failed' and q != 'failed':
                raise ValueError('efficiency_quality_failure_without_evidence')
            if q == 'passed' and a['status'] != 'completed':
                raise ValueError('efficiency_pass_without_completed_attempt')
            qualities[aid] = q
    overheads = _index(obs['overheads'], 'id', 'efficiency_duplicate_overhead')
    if set(overheads) != set(registry['overhead_ids']):
        raise ValueError('efficiency_overhead_inventory_incomplete')
    if set(overheads) & set(attempts): raise ValueError('efficiency_owner_id_collision')
    allocation_policy = {x['category']: x['weights'] for x in plan['overhead_allocations']}
    for overhead in overheads.values():
        if overhead['category'] not in allocation_policy:
            raise ValueError('efficiency_unplanned_overhead_category')
        assigned = assign(overhead['request_refs'], overhead['id'])
        if any(providers[key]['allocations'] != allocation_policy[overhead['category']] for key in assigned):
            raise ValueError('efficiency_overhead_allocation_changed')
    if set(owners) != set(providers): raise ValueError('efficiency_unallocated_ledger_requests')
    results = []
    for cell_id, cell in cells.items():
        entry, keys, first = reg[cell_id], [], None
        for aid in entry['attempt_ids']:
            a = attempts[aid]
            keys.extend(map(_key, a['request_refs']))
            if first is None and a['status'] == 'completed' and qualities[aid] == 'passed':
                first = {'attempt_id': aid, **_cost(keys, providers)}
        total = _cost(keys, providers)
        statuses = [attempts[a]['status'] for a in entry['attempt_ids']]
        last = statuses[-1] if statuses else None
        outcome = ('success' if first else 'not_observed' if not statuses else
                   'pending' if not entry['closed'] or last == 'running' else
                   'unreviewed' if last == 'completed' and qualities[entry['attempt_ids'][-1]] == 'unknown' else
                   'budget_exhausted' if last == 'budget_exhausted' else
                   'infrastructure_error' if last in ('provider_error', 'environment_error') else
                   'cancelled' if last == 'cancelled' else 'failed')
        budget = cell['budget_usd']
        within = None if first is None or first['model_usd'] is None or budget is None else first['model_usd'] <= budget
        if first and within is False: outcome = 'success_over_budget'
        if first and budget is not None and first['model_usd'] is None: outcome = 'success_budget_unknown'
        results.append({**cell, 'split': tasks[cell['task_id']]['split'], 'outcome': outcome, 'closed': entry['closed'], 'attempt_ids': entry['attempt_ids'],
                        'attempt_count': len(statuses), 'quality_statuses': [qualities[a] for a in entry['attempt_ids']],
                        'cost': total, 'first_success': first, 'within_research_budget': within,
                        'success_acquisition_cost_usd': first['model_usd'] if first else None,
                        'right_censored': outcome == 'budget_exhausted',
                        'censoring_spend_usd': total['model_usd'] if outcome == 'budget_exhausted' else None})
    blocks = {}
    for row in results:
        blocks.setdefault((row['task_id'], row['replicate'], row['phase']), {})[row['arm_id']] = row
    comparisons = []
    negative = {'failed', 'budget_exhausted'}
    for (task, replicate, phase), block in blocks.items():
        b = block[plan['baseline_arm']]
        for arm, c in block.items():
            if arm == plan['baseline_arm']: continue
            bo, co = b['outcome'], c['outcome']
            comparable = bo in negative | {'success'} and co in negative | {'success'}
            category = ('both_success' if bo == co == 'success' else
                        'capability_unlock' if bo in negative and co == 'success' else
                        'capability_regression' if bo == 'success' and co in negative else
                        'both_unsuccessful' if bo in negative and co in negative else 'unresolved')
            bc, cc = b['cost']['model_usd'], c['cost']['model_usd']
            saving = bc - cc if category == 'both_success' and bc is not None and cc is not None else None
            comparisons.append({'task_id': task, 'split': tasks[task]['split'], 'replicate': replicate, 'phase': phase, 'candidate_arm': arm,
                                'category': category, 'resolved': comparable,
                                'baseline_outcome': bo, 'candidate_outcome': co,
                                'conditional_cost_saving_usd': saving,
                                'conditional_cost_reduction': saving / bc if saving is not None and bc else None})
    by_arm = {}
    for arm in arms:
        rows = [r for r in results if r['arm_id'] == arm]
        by_arm[arm] = {'planned_cells': len(rows), 'observed_cells': sum(r['attempt_count'] > 0 for r in rows),
                       'successful_cells': sum(r['outcome'] == 'success' for r in rows),
                       'success_rate_all_planned': sum(r['outcome'] == 'success' for r in rows) / len(rows),
                       'outcomes': {status: sum(r['outcome'] == status for r in rows) for status in sorted({r['outcome'] for r in results})},
                       'allocated_cost': _cost(providers, providers, arm),
                       'by_split': {split: {
                           'planned_cells': sum(r['split'] == split for r in rows),
                           'successful_cells': sum(r['split'] == split and r['outcome'] == 'success' for r in rows)}
                           for split in sorted({r['split'] for r in rows})}}
    return {'format': 'efficiency_rsi_measurement_v1', 'study_id': plan['id'], 'objective': plan['objective'],
            'plan_sha256': plan_sha, 'registry_sha256': digest(registry), 'observations_sha256': digest(obs),
            'measurement_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'budget_scope': plan['budget_scope'],
            'success_rate_scope': 'attempt_execution_excludes_shared_overheads',
            'complete': all(r['closed'] and r['attempt_count'] > 0 for r in results),
            'planned_cells': len(cells), 'attempts': len(attempts), 'physical_model_requests': len(providers),
            'physical_study_cost': _cost(providers, providers), 'arms': by_arm,
            'study_only_cost': _cost(providers, providers, 'study_only'),
            'cells': results, 'comparisons': comparisons, 'amortization': None,
            'billing_usd': None, 'non_model_costs': None, 'total_economic_cost_usd': None,
            'cost_basis': 'proxy_estimate_not_provider_bill',
            'evidence_scope': 'trusted_runner_and_reviewer_exports_not_self_authenticating',
            'publication_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', '--study', dest='plan', type=Path, required=True)
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--evidence-root', type=Path)
    args = parser.parse_args()
    plan = validate_study(json.loads(args.plan.read_text(encoding='utf-8')))
    if args.observations:
        if args.registry is None or args.evidence_root is None:
            parser.error('measurement requires --registry and --evidence-root')
        result = measure_study(plan, json.loads(args.observations.read_text(encoding='utf-8')),
                               registry=json.loads(args.registry.read_text(encoding='utf-8')), evidence_root=args.evidence_root)
    else:
        result = {'valid': True, 'plan_sha256': digest(plan), 'paid_requests': 0, 'publication_authorized': False}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
