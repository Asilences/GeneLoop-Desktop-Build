"""Synthetic measurement diagnostics, not evidence of Agent quality or savings."""
from copy import deepcopy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.adapters.efficiency_rsi_measurement import digest, validate_study, measure_study
from src.adapters.rsi_protocol import envelope


def sha(raw): return hashlib.sha256(raw).hexdigest()


def example(tmp_path):
    evaluator = b'independent frozen checker fixture'
    (tmp_path / 'checker.py').write_bytes(evaluator)
    arm = lambda name: {'id': name, 'execution_snapshot_sha256': None, 'build_snapshot_sha256': None,
                        'execution_capabilities': [], 'build_capabilities': []}
    plan = {'format': 'efficiency_rsi_study_v1', 'id': 'diagnostic',
            'objective': 'efficiency_and_capability', 'conditions_sha256': 'c'*64,
            'rubric_sha256': 'd'*64, 'evaluator': {'id': 'fixture-checker', 'sha256': sha(evaluator), 'ref': 'checker.py'},
            'required_checks': ['correct'], 'tasks': [{'id': 'task', 'sha256': 'a'*64, 'family': 'one', 'split': 'final_test'}],
            'arms': [arm('baseline'), arm('candidate')], 'baseline_arm': 'baseline',
            'cells': [{'id': a, 'task_id': 'task', 'arm_id': a, 'replicate': 0, 'phase': 'construction',
                       'budget_usd': 1., 'max_attempts': 3} for a in ('baseline', 'candidate')],
            'allocation_policy': 'explicit_conserved_weights_v1',
            'overhead_allocations': [{'category': 'seed_learning', 'weights': {'baseline': .5, 'candidate': .5}}],
            'budget_policy': 'research_comparison_not_platform_authorization', 'budget_scope': 'attempt_execution'}
    registry = {'format': 'efficiency_rsi_registry_v1', 'plan_sha256': digest(plan),
                'overhead_ids': [], 'request_refs': [{'ledger_ref': 'ledger-one', 'id': str(i)} for i in (1, 2)],
                'cells': [{'cell_id': a, 'attempt_ids': [a+'-1'], 'closed': True} for a in ('baseline', 'candidate')]}
    obs = {'format': 'efficiency_rsi_observations_v1', 'plan_sha256': digest(plan), 'registry_sha256': digest(registry),
           'attempts': [], 'overheads': [], 'providers': []}
    for i, arm in enumerate(('baseline', 'candidate'), 1):
        filename = arm+'.txt'; raw = (arm+' output').encode(); (tmp_path / filename).write_bytes(raw)
        quality = envelope('quality_evaluation', {'id': 'q-'+arm, 'task_id': 'task', 'task_sha256': 'a'*64,
            'artifact_sha256': sha(raw), 'rubric_sha256': 'd'*64, 'evaluator': 'fixture-checker',
            'scope': 'synthetic diagnostic', 'limitations': ['not real quality'],
            'checks': [{'id': 'correct', 'status': 'passed', 'observation': 'Fixture matches.',
                        'evidence': [{'ref': filename, 'sha256': sha(raw)}]}]})
        obs['attempts'].append({'id': arm+'-1', 'cell_id': arm, 'ordinal': 1, 'parent_attempt_id': None,
            'conditions_sha256': 'c'*64, 'execution_snapshot_sha256': None, 'build_snapshot_sha256': None,
            'execution_capabilities': [], 'build_capabilities': [], 'status': 'completed',
            'request_refs': [{'ledger_ref': 'ledger-one', 'id': str(i)}], 'artifact_ref': filename,
            'artifact_sha256': sha(raw), 'quality': quality, 'wall_seconds': 1.})
        obs['providers'].append({'ledger_ref': 'ledger-one', 'id': str(i), 'phase': 'completed',
            'observed_peak_usd': .4 if arm == 'baseline' else .2, 'reserved_upper_usd': .5,
            'allocations': {arm: 1.}})
    return plan, obs, registry


def run(x, root):
    return measure_study(x[0], x[1], registry=x[2], evidence_root=root)


def refresh(x):
    x[1]['plan_sha256'] = x[2]['plan_sha256'] = digest(x[0])
    x[1]['registry_sha256'] = digest(x[2])


def fail(attempt, status='budget_exhausted'):
    attempt['status'] = status
    attempt['quality'] = None


def test_both_success_costs_and_no_publication(tmp_path):
    x = example(tmp_path); report = run(x, tmp_path)
    assert report['physical_study_cost']['model_usd'] == pytest.approx(.6)
    assert report['comparisons'][0]['category'] == 'both_success'
    assert report['comparisons'][0]['conditional_cost_saving_usd'] == pytest.approx(.2)
    assert report['cells'][0]['success_acquisition_cost_usd'] == .4
    assert report['amortization'] is None and report['publication_authorized'] is False


@pytest.mark.parametrize('baseline,candidate,category', [
    (False, True, 'capability_unlock'), (True, False, 'capability_regression'),
    (False, False, 'both_unsuccessful')])
def test_failed_baseline_cannot_generate_savings(tmp_path, baseline, candidate, category):
    x = example(tmp_path)
    for success, attempt in zip((baseline, candidate), x[1]['attempts']):
        if not success: fail(attempt)
    report = run(x, tmp_path)
    assert report['comparisons'][0]['category'] == category
    assert report['comparisons'][0]['conditional_cost_saving_usd'] is None
    for cell, success in zip(report['cells'], (baseline, candidate)):
        assert cell['right_censored'] is (not success)
        if not success: assert cell['success_acquisition_cost_usd'] is None


def test_missing_attempt_rejected_against_independent_registry(tmp_path):
    x = example(tmp_path); x[1]['attempts'].pop()
    with pytest.raises(ValueError, match='attempt_inventory_incomplete'): run(x, tmp_path)


def test_unobserved_cell_stays_in_denominator(tmp_path):
    x = example(tmp_path)
    x[2]['cells'][1].update(attempt_ids=[], closed=False)
    x[1]['attempts'].pop(); x[1]['providers'].pop(); x[2]['request_refs'].pop(); refresh(x)
    report = run(x, tmp_path)
    assert report['planned_cells'] == 2 and not report['complete']
    assert report['cells'][1]['outcome'] == 'not_observed'
    assert report['arms']['candidate']['planned_cells'] == 1
    assert report['arms']['candidate']['success_rate_all_planned'] == 0
    assert report['comparisons'][0]['category'] == 'unresolved'


def test_unknown_cost_is_null_and_not_budget_success(tmp_path):
    x = example(tmp_path); x[1]['providers'][1]['observed_peak_usd'] = None
    report = run(x, tmp_path)
    assert report['physical_study_cost']['model_usd'] is None
    assert report['physical_study_cost']['known_model_usd'] == .4
    assert report['physical_study_cost']['accounted_upper_usd'] == pytest.approx(.9)
    assert report['cells'][1]['outcome'] == 'success_budget_unknown'
    assert report['comparisons'][0]['conditional_cost_saving_usd'] is None


def test_booking_terminal_and_exact_duplicates_count_once(tmp_path):
    x = example(tmp_path); row = deepcopy(x[1]['providers'][0]); row.update(phase='booked', observed_peak_usd=None)
    x[1]['providers'] = [row, *x[1]['providers'], deepcopy(x[1]['providers'][0])]
    report = run(x, tmp_path)
    assert report['physical_model_requests'] == 2
    assert report['physical_study_cost']['model_usd'] == pytest.approx(.6)


def test_conflicting_terminal_request_rejected(tmp_path):
    x = example(tmp_path); row = deepcopy(x[1]['providers'][0]); row['observed_peak_usd'] = .001
    x[1]['providers'].append(row)
    with pytest.raises(ValueError, match='conflicting_request'): run(x, tmp_path)


def test_request_identity_contains_ledger(tmp_path):
    x = example(tmp_path)
    x[1]['providers'][1].update(ledger_ref='ledger-two', id='1')
    x[1]['attempts'][1]['request_refs'] = [{'ledger_ref': 'ledger-two', 'id': '1'}]
    x[2]['request_refs'][1] = {'ledger_ref': 'ledger-two', 'id': '1'}; refresh(x)
    assert run(x, tmp_path)['physical_model_requests'] == 2


def test_retry_failure_cost_in_first_success_and_total(tmp_path):
    x = example(tmp_path); first = x[1]['attempts'][1]; retry = deepcopy(first)
    fail(first, 'provider_error')
    retry.update(id='candidate-2', ordinal=2, parent_attempt_id='candidate-1', request_refs=[{'ledger_ref': 'ledger-one', 'id': '3'}])
    x[1]['attempts'].append(retry); x[2]['cells'][1]['attempt_ids'].append('candidate-2')
    row = deepcopy(x[1]['providers'][1]); row.update(id='3', observed_peak_usd=.1)
    x[1]['providers'].append(row); x[2]['request_refs'].append({'ledger_ref': 'ledger-one', 'id': '3'}); refresh(x)
    report = run(x, tmp_path)
    assert report['cells'][1]['success_acquisition_cost_usd'] == pytest.approx(.3)
    assert report['cells'][1]['attempt_count'] == 2
    assert report['physical_study_cost']['model_usd'] == pytest.approx(.7)


def test_shared_seed_physically_once_and_allocated_conservatively(tmp_path):
    x = example(tmp_path)
    x[1]['providers'].append({'ledger_ref': 'ledger-one', 'id': '3', 'phase': 'failed',
        'observed_peak_usd': .3, 'reserved_upper_usd': .4, 'allocations': {'baseline': .5, 'candidate': .5}})
    x[1]['overheads'] = [{'id': 'seed', 'category': 'seed_learning', 'request_refs': [{'ledger_ref': 'ledger-one', 'id': '3'}]}]
    x[2]['overhead_ids'] = ['seed']; x[2]['request_refs'].append({'ledger_ref': 'ledger-one', 'id': '3'}); refresh(x)
    report = run(x, tmp_path)
    assert report['physical_study_cost']['model_usd'] == pytest.approx(.9)
    assert report['arms']['baseline']['allocated_cost']['model_usd'] == pytest.approx(.55)
    assert report['arms']['candidate']['allocated_cost']['model_usd'] == pytest.approx(.35)


@pytest.mark.parametrize('mutate,error', [
    (lambda x: x[1]['attempts'][0].update(conditions_sha256='e'*64), 'conditions_changed'),
    (lambda x: x[1]['attempts'][0].update(ordinal=2), 'retry_chain_changed'),
    (lambda x: x[1]['attempts'][0]['quality']['payload'].update(rubric_sha256='e'*64), 'quality_artifact_binding_changed'),
    (lambda x: x[1]['attempts'][0]['quality']['payload'].update(evaluator='builder'), 'independent_evaluator_changed'),
    (lambda x: x[1]['providers'][0].update(allocations={'candidate': 1.}), 'cost_shifted'),
    (lambda x: x[1]['providers'][0].update(allocations={'baseline': .5}), 'allocation_not_conserved'),
    (lambda x: x[1]['attempts'][0]['request_refs'].append(x[1]['attempts'][0]['request_refs'][0]), 'duplicate_request_reference'),
    (lambda x: x[1]['providers'].append({**x[1]['providers'][0], 'id': 'orphan'}), 'request_inventory_incomplete'),
])
def test_changed_or_incomplete_evidence_fails_closed(tmp_path, mutate, error):
    x = example(tmp_path); mutate(x)
    with pytest.raises(ValueError, match=error): run(x, tmp_path)


def test_changed_artifact_and_evaluator_files_rejected(tmp_path):
    x = example(tmp_path); (tmp_path/'candidate.txt').write_text('mutated')
    with pytest.raises(ValueError, match='evidence_changed'): run(x, tmp_path)
    x = example(tmp_path); (tmp_path/'checker.py').write_text('mutated')
    with pytest.raises(ValueError, match='evidence_changed'): run(x, tmp_path)


def test_unequal_budget_and_train_test_alias_rejected(tmp_path):
    x = example(tmp_path); x[0]['cells'][1]['budget_usd'] = .5
    with pytest.raises(ValueError, match='unequal_research_budget'): validate_study(x[0])
    x = example(tmp_path); x[0]['tasks'].append({**x[0]['tasks'][0], 'id': 'renamed', 'split': 'training'})
    with pytest.raises(ValueError, match='duplicate_or_leaked'): validate_study(x[0])


@pytest.mark.parametrize('status', ['provider_error', 'environment_error', 'cancelled', 'running'])
def test_non_capability_failures_do_not_claim_unlock(tmp_path, status):
    x = example(tmp_path); fail(x[1]['attempts'][0], status)
    if status == 'running': x[2]['cells'][0]['closed'] = False; refresh(x)
    assert run(x, tmp_path)['comparisons'][0]['category'] == 'unresolved'


def test_over_budget_success_not_counted_as_budget_unlock(tmp_path):
    x = example(tmp_path); x[1]['providers'][1]['observed_peak_usd'] = 2.
    report = run(x, tmp_path)
    assert report['cells'][1]['outcome'] == 'success_over_budget'
    assert report['arms']['candidate']['successful_cells'] == 0


def test_cli_validates_without_model_call(tmp_path):
    x = example(tmp_path); path = tmp_path/'plan.json'; path.write_text(json.dumps(x[0]))
    output = subprocess.check_output([sys.executable, str(Path(__file__).resolve().parents[1]/'scripts/measure-efficiency-rsi.py'), '--study', str(path)], text=True)
    assert json.loads(output)['paid_requests'] == 0


def test_missing_whole_failed_overhead_and_ledger_rejected(tmp_path):
    x = example(tmp_path)
    x[2]['overhead_ids'] = ['failed-seed']
    x[2]['request_refs'].append({'ledger_ref': 'seed-ledger', 'id': '1'})
    refresh(x)
    with pytest.raises(ValueError, match='request_inventory_incomplete'): run(x, tmp_path)
    x[1]['providers'].append({'ledger_ref': 'seed-ledger', 'id': '1', 'phase': 'failed',
        'observed_peak_usd': .3, 'reserved_upper_usd': .4, 'allocations': {'baseline': .5, 'candidate': .5}})
    with pytest.raises(ValueError, match='overhead_inventory_incomplete'): run(x, tmp_path)


def test_budget_scope_excludes_overhead_and_is_explicit(tmp_path):
    x = example(tmp_path); report = run(x, tmp_path)
    assert report['budget_scope'] == 'attempt_execution'
    assert report['success_rate_scope'] == 'attempt_execution_excludes_shared_overheads'
    x[0]['budget_scope'] = 'full_lifecycle'
    with pytest.raises(ValueError, match='schema_invalid'): validate_study(x[0])


def test_cli_measures_export_without_execution(tmp_path):
    x = example(tmp_path)
    for name, value in zip(('plan', 'obs', 'registry'), x):
        (tmp_path / (name+'.json')).write_text(json.dumps(value))
    output = subprocess.check_output([sys.executable,
        str(Path(__file__).resolve().parents[1]/'scripts/measure-efficiency-rsi.py'),
        '--study', str(tmp_path/'plan.json'), '--observations', str(tmp_path/'obs.json'),
        '--registry', str(tmp_path/'registry.json'), '--evidence-root', str(tmp_path)], text=True)
    assert json.loads(output)['comparisons'][0]['category'] == 'both_success'
