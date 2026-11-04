"""Synthetic read-only accounting diagnostics, with no model/provider calls."""
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.adapters.capability_feedback import file_ref


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/summarize-evolution-benchmark.py'
spec = importlib.util.spec_from_file_location('benchmark_summary_diagnostics', SCRIPT)
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def test_source_snapshot_list_digest_ignores_session_location_and_order():
    first = [{'path': '/session-one/source-snapshot/runner.py', 'sha256': 'a' * 64},
             {'path': '/session-one/source-snapshot/scope.mjs', 'sha256': 'b' * 64}]
    second = [{'path': '/session-two/source-snapshot/scope.mjs', 'sha256': 'b' * 64},
              {'path': '/session-two/source-snapshot/runner.py', 'sha256': 'a' * 64}]
    assert summary._code_digest(first) == summary._code_digest(second)
    second[1]['sha256'] = 'c' * 64
    assert summary._code_digest(first) != summary._code_digest(second)
    assert summary._code_digest({'sha256': 'legacy'}) == 'legacy'
    assert summary._code_digest(None) is None


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    return path


def trial(root, ledger, *, name='one', task='task-a', source='source-a', ids=(1,), reward=1, status='evaluated'):
    output = root / 'host/trials' / name
    session = root / 'host/model-sessions' / name
    put(session / 'effective.json', {'mode': 'benchmark_task', 'model': 'diagnostic',
        'reasoning_effort': 'off', 'max_tokens': 100, 'code': {'sha256': 'same-code'}})
    put(session / 'result.json', {'status': 'completed', 'provider_requests': len(ids), 'elapsed_seconds': 3})
    lines(session / 'requests.jsonl', [{'phase': 'booked', 'request_id': value,
        'ledger_ref': str(ledger), 'reserved_upper_usd': 5} for value in ids])
    put(output / 'manifest.json', {'source_identity': source, 'source_version': 'fixed-data',
        'source_files': {'instruction.md': 'same-input', 'tests/test.sh': 'fixed-verifier'},
        'effective_verifier_environment': {}})
    put(output / 'result.json', {'task_id': task, 'split': 'test', 'label': 'final',
        'score': str(reward) if status == 'evaluated' else None,
        'status': status, 'elapsed_seconds': 5, 'evaluation': {'status': 'evaluated', 'reward': reward,
        'passed': reward > 0}, 'model': {'directory': str(session), 'status': 'completed'}})
    return output, session


@pytest.mark.parametrize('model_status', ['failed', 'incomplete', 'timeout'])
def test_full_verifier_reward_does_not_override_unscoreable_model(model_status):
    value = {'score': None, 'model_scoreable': False,
             'model': {'status': model_status, 'provider_requests': 0},
             'evaluation': {'status': 'evaluated', 'reward': 1}}
    quality = summary._quality(value, Decimal('1'))
    assert quality['raw_reward'] == 1 and quality['verifier_status'] == 'evaluated'
    assert quality['trial_scoreable'] is False
    assert quality['full_quality'] is None and quality['paper_positive_reward_pass'] is None


def test_timeout_quality_requires_original_host_cancellation_evidence(tmp_path):
    value = {'score': '1', 'model_scoreable': True,
             'model': {'status': 'timeout', 'timed_out': True, 'provider_requests': 1},
             'evaluation': {'status': 'evaluated', 'reward': 1}}
    assert summary._quality(value, Decimal('1'))['full_quality'] is None
    evidence = put(tmp_path / 'cancel.json', {'runtime_closed': True})
    value['model']['cancel_evidence'] = file_ref(evidence)
    assert summary._quality(value, Decimal('1'))['full_quality'] is True
    evidence.write_text('{"runtime_closed":false}')
    assert summary._quality(value, Decimal('1'))['full_quality'] is None


def test_failed_model_cannot_make_matching_group_comparable(tmp_path):
    ledger = lines(tmp_path / 'ledger.jsonl', [])
    left = root(tmp_path, name='left', mode='geneloop')
    right = root(tmp_path, name='right', mode='skill-infinity')
    left_output, left_session = trial(left, ledger)
    _right_output, right_session = trial(right, ledger, ids=(2,))
    result = json.loads((left_output / 'result.json').read_text())
    result.update(score=None, model_scoreable=False)
    result['model']['status'] = 'failed'
    put(left_output / 'result.json', result)
    lines(ledger, [settled(left_session, 1), settled(right_session, 2)])
    value = summary.summarize([left, right], ledger)
    assert value['matching_groups'][0]['full_quality_comparable'] is False


def settled(session, request_id, cost='0.10000001'):
    return {'request_id': request_id, 'attempt_path': str(session), 'observed_peak_usd': cost,
            'reserved_upper_usd': 5, 'model': 'diagnostic', 'response_status': 200,
            'elapsed_seconds': 1, 'response_usage': {'prompt_cache_hit_tokens': 10,
            'prompt_cache_miss_tokens': 20, 'prompt_tokens': 30, 'completion_tokens': 5, 'total_tokens': 35}}


def root(tmp_path, name='run', mode='trial'):
    directory = tmp_path / name
    put(directory / 'effective.json', {'mode': mode, 'prewarm_dependencies': False})
    return directory


def test_deduplicates_nested_roots_sessions_and_decimal_costs(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    output, session = trial(run, ledger)
    child = session / 'nested'
    put(child / 'effective.json', {'mode': 'review'})
    put(child / 'result.json', {'status': 'completed', 'provider_requests': 1})
    lines(child / 'requests.jsonl', [{'phase': 'booked', 'request_id': 2,
                                     'ledger_ref': str(ledger), 'reserved_upper_usd': 5}])
    put(run / 'result.json', json.loads((output / 'result.json').read_text()))
    lines(ledger, [settled(session, 1), settled(child, 2, '0.20000002'), settled(tmp_path / 'other', 99)])
    before = ledger.read_bytes()
    value = summary.summarize([run, output, session, run], file_ref(ledger))
    assert value['overall_accounting']['requests'] == 2
    assert value['overall_accounting']['model_usd_decimal'] == '0.30000003'
    method = value['methods'][0]
    assert len(method['trials']) == 1 and method['known_independent_sources'] == 1
    assert method['trials'][0]['accounting']['requests'] == 1
    assert len(value['ignored_nested_run_roots']) == 2
    assert value['overall_accounting']['tokens']['prompt_cache_hit_tokens']['value'] == 20
    assert ledger.read_bytes() == before


def test_booking_keeps_ownership_when_settlement_path_changes(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    one, session_one = trial(run, ledger, name='one')
    two, session_two = trial(run, ledger, name='two', ids=())
    row = settled(session_two, 1)
    lines(ledger, [row])
    value = summary.summarize([run], ledger)
    trials = {Path(row['directory']).name: row for row in value['methods'][0]['trials']}
    assert trials['one']['accounting']['requests'] == 1
    assert trials['two']['accounting']['requests'] == 0
    assert any(row['issue'] == 'settlement_owner_differs_from_booking' for row in value['warnings'])


def test_missing_settlement_and_unknown_usage_remain_unknown(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    _, session = trial(run, ledger, ids=(1, 2, 3))
    unknown = settled(session, 2)
    unknown.update(observed_peak_usd=None, response_usage={})
    lines(ledger, [settled(session, 1), unknown])
    value = summary.summarize([run], ledger)['overall_accounting']
    assert value['requests'] == 3 and value['model_usd_decimal'] is None
    assert value['known_model_usd_decimal'] == '0.10000001'
    assert len(value['unknown_requests']) == 2
    assert value['tokens']['completion_tokens']['value'] is None
    assert value['tokens']['completion_tokens']['known_value'] == 5


def test_partial_quality_and_repeated_tasks_do_not_create_savings_or_independence(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    _, first = trial(run, ledger, name='one', reward=0.4)
    _, second = trial(run, ledger, name='two', reward=1, ids=(2,))
    lines(ledger, [settled(first, 1), settled(second, 2)])
    value = summary.summarize([run], ledger)
    method = value['methods'][0]
    assert method['known_independent_sources'] == 1 and len(method['trials']) == 2
    partial = next(row for row in method['trials'] if row['raw_reward'] == 0.4)
    assert partial['paper_positive_reward_pass'] is True and partial['full_quality'] is False
    assert value['savings_estimates'] == []
    assert not value['matching_groups'][0]['full_quality_comparable']


def test_renamed_identical_inputs_still_count_as_one_source(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    _, first = trial(run, ledger, name='one', source='source-a')
    _, second = trial(run, ledger, name='two', task='renamed-task', source='source-b', ids=(2,))
    lines(ledger, [settled(first, 1), settled(second, 2)])
    method = summary.summarize([run], ledger)['methods'][0]
    assert len(method['unique_task_ids']) == 2
    assert method['known_independent_sources'] == 1


def test_same_full_quality_inputs_are_marked_comparable_without_inventing_delta(tmp_path):
    vanilla = root(tmp_path, 'vanilla')
    gene = root(tmp_path, 'gene', 'geneloop')
    ledger = tmp_path / 'ledger.jsonl'
    _, one = trial(vanilla, ledger)
    _, two = trial(gene, ledger, ids=(2,))
    lines(ledger, [settled(one, 1), settled(two, 2)])
    value = summary.summarize([vanilla, gene], ledger)
    assert len(value['matching_groups']) == 1
    assert value['matching_groups'][0]['full_quality_comparable'] is True
    assert value['savings_estimates'] == []


def test_canonical_validation_and_final_roles_do_not_form_a_pair(tmp_path):
    vanilla = root(tmp_path, 'vanilla')
    gene = root(tmp_path, 'gene', 'geneloop')
    ledger = tmp_path / 'ledger.jsonl'
    one, first = trial(vanilla, ledger)
    two, second = trial(gene, ledger, ids=(2,))
    record = json.loads((one / 'result.json').read_text())
    record['evaluation_role'] = 'validation'
    put(one / 'result.json', record)
    record = json.loads((two / 'result.json').read_text())
    record['evaluation_role'] = 'final'
    put(two / 'result.json', record)
    lines(ledger, [settled(first, 1), settled(second, 2)])
    value = summary.summarize([vanilla, gene], ledger)
    assert {group['comparison_scope'] for group in value['matching_groups']} == {'canonical_validation', 'canonical_final'}
    assert all(group['full_quality_comparable'] is False for group in value['matching_groups'])
    assert all(row['evaluation_role_inferred'] is False for method in value['methods'] for row in method['trials'])
    assert value['overall_accounting']['requests'] == 2


def test_all_role_costs_remain_and_final_reuse_is_disclosed(tmp_path):
    run = root(tmp_path, 'gene', 'geneloop')
    ledger = tmp_path / 'ledger.jsonl'
    providers = []
    for index, role in enumerate(('development', 'validation', 'final'), 1):
        output, session = trial(run, ledger, name=role, ids=(index,))
        record = json.loads((output / 'result.json').read_text())
        record.update(evaluation_role=role, label='same-label')
        put(output / 'result.json', record)
        providers.append(settled(session, index))
    lines(ledger, providers)
    value = summary.summarize([run], ledger)
    assert value['overall_accounting']['requests'] == 3
    assert value['overall_accounting']['model_usd_decimal'] == '0.30000003'
    assert {phase['evaluation_role'] for phase in value['phases']} == {'development', 'validation', 'final'}
    assert sum(phase['accounting']['requests'] for phase in value['phases']) == 3
    final = next(group for group in value['matching_groups'] if group['evaluation_role'] == 'final')
    assert final['reuses_observed_validation_dataset'] is True
    assert final['heldout_status'] == 'observed_validation_reuse'
    assert value['savings_estimates'] == []


@pytest.mark.parametrize('label,split,expected', [
    ('gene-frozen-test', 'test', 'final'), ('final', 'test', 'final'),
    ('gene-independent-validation', 'test', 'validation'), ('validation', 'training', 'validation'),
    ('gene-development', 'training', 'development'),
])
def test_legacy_role_inference_preserves_original_records(tmp_path, label, split, expected):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    output, session = trial(run, ledger)
    record = json.loads((output / 'result.json').read_text())
    record.update(label=label, split=split)
    original = put(output / 'result.json', record).read_bytes()
    lines(ledger, [settled(session, 1)])
    value = summary.summarize([run], ledger)
    row = value['methods'][0]['trials'][0]
    assert row['evaluation_role'] == expected
    assert row['evaluation_role_inferred'] is True
    assert row['split'] == split
    assert (output / 'result.json').read_bytes() == original


@pytest.mark.parametrize('left_flag,right_flag,left_profile,right_profile,comparable', [
    (False, False, None, None, True),
    (True, True, 'same', 'same', True),
    (True, True, 'one', 'two', False),
    (False, True, None, 'profile', False),
    (None, None, None, None, False),
    (True, True, None, None, False),
])
def test_dependency_preparation_is_part_of_matching_conditions(
        tmp_path, left_flag, right_flag, left_profile, right_profile, comparable):
    ledger = tmp_path / 'ledger.jsonl'
    sessions = []
    roots = []
    for index, (flag, profile_id) in enumerate(((left_flag, left_profile), (right_flag, right_profile))):
        run = root(tmp_path, str(index), 'geneloop' if index else 'trial')
        roots.append(run)
        config = json.loads((run / 'effective.json').read_text())
        if flag is None:
            config.pop('prewarm_dependencies')
        else:
            config['prewarm_dependencies'] = flag
        put(run / 'effective.json', config)
        output, session = trial(run, ledger, ids=(index + 1,))
        sessions.append(session)
        if profile_id is not None:
            profile_path = put(run / 'public-profile.json', {'id': profile_id})
            prep_path = put(output / 'dependency-preparation.json', {
                'status': 'prepared', 'profile': {'id': 'fixed-selection', 'profile': file_ref(profile_path)}})
            result = json.loads((output / 'result.json').read_text())
            result['dependency_preparation'] = file_ref(prep_path)
            put(output / 'result.json', result)
    lines(ledger, [settled(session, index + 1) for index, session in enumerate(sessions)])
    value = summary.summarize(roots, ledger)
    assert any(group['full_quality_comparable'] for group in value['matching_groups']) is comparable
    if left_flag is None or left_flag is True and left_profile is None:
        assert all(group['missing_matching_conditions'] for group in value['matching_groups'])


def test_partial_reward_in_one_arm_is_not_a_full_quality_pair(tmp_path):
    vanilla = root(tmp_path, 'vanilla')
    gene = root(tmp_path, 'gene', 'geneloop')
    ledger = tmp_path / 'ledger.jsonl'
    _, one = trial(vanilla, ledger, reward=0.25)
    _, two = trial(gene, ledger, ids=(2,))
    lines(ledger, [settled(one, 1), settled(two, 2)])
    value = summary.summarize([vanilla, gene], ledger)
    assert value['matching_groups'][0]['full_quality_comparable'] is False
    assert value['savings_estimates'] == []


def test_conflicting_settlements_keep_request_cost_unknown(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    _, session = trial(run, ledger)
    lines(ledger, [settled(session, 1), settled(session, 1), settled(session, 1, '0.2')])
    value = summary.summarize([run], ledger)
    assert value['overall_accounting']['requests'] == 1
    assert value['overall_accounting']['model_usd_decimal'] is None
    assert any(row['issue'] == 'conflicting_ledger_settlements' for row in value['warnings'])


def test_booked_then_settled_global_rows_are_one_request(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    _, session = trial(run, ledger)
    lines(ledger, [{'phase': 'booked', 'request_id': 1, 'reserved_upper_usd': 5,
                    'attempt_path': str(session)}, settled(session, 1)])
    value = summary.summarize([run], ledger)
    assert value['overall_accounting']['requests'] == 1
    assert value['overall_accounting']['model_usd_decimal'] == '0.10000001'


def test_generated_skill_resources_are_not_booking_or_usage_authority(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    _, session = trial(run, ledger)
    lines(ledger, [settled(session, 1)])
    package = run / 'candidate' / 'skill'
    put(package / 'effective.json', {'mode': 'benchmark_task'})
    lines(package / 'requests.jsonl', [{'phase': 'booked', 'request_id': 99,
        'ledger_ref': str(ledger), 'reserved_upper_usd': 5}])
    lines(package / 'skill-activations.jsonl', [{'status': 'loaded', 'name': 'invented'}])
    value = summary.summarize([run], ledger)
    assert value['overall_accounting']['requests'] == 1
    assert value['methods'][0]['native_skill_loads'] == 0


def test_actual_native_loads_and_verified_runtime_receipts_are_separate(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    output, session = trial(run, ledger)
    lines(ledger, [settled(session, 1)])
    lines(session / 'skill-activations.jsonl', [{'name': 'policy', 'status': 'loaded'}] * 2)
    lines(session / 'tool-calls.jsonl', [{'phase': 'finished', 'name': 'read_skill',
        'status': 'completed', 'arguments': {'resource': 'SKILL.md'}, 'result': {'status': 'read'}}])
    cap = {'id': 'cap-diagnostic', 'sha256': 'diagnostic'}
    trace = put(output / 'trace.json', {'status': 'succeeded', 'task_id': 'task-a', 'root': cap})
    put(output / 'capability-call-records.json', [{'id': 'call0', 'task_id': 'task-a',
         'capability': cap, 'status': 'succeeded', 'execution_ref': file_ref(trace)}])
    value = summary.summarize([run], ledger)['methods'][0]
    assert value['native_skill_loads'] == 2
    assert value['explicit_skill_body_reads'] == 1
    assert value['capability_call_attempts'] == value['verified_capability_calls'] == 1


def test_recursive_candidates_are_kept_distinct_from_pending_publication(tmp_path):
    run = root(tmp_path, mode='geneloop')
    ledger = lines(tmp_path / 'ledger.jsonl', [])
    generation = run / 'generation'
    put(generation / 'effective.json', {'development_tasks': ['a', 'b']})
    learned = put(generation / 'recursive-learning.json', {'candidates': [{'id': 'diagnostic'}]})
    value = {'format': 'gene_benchmark_generation_v1', 'status': 'completed',
        'recursive_learning': {'status': 'candidates', 'result': file_ref(learned),
                               'publication': 'pending_independent_original_store_publication'},
        'selection': None, 'capability_acquisitions': [{'status': 'registered'}]}
    put(generation / 'result.json', value)
    put(run / 'result.json', value)
    rows = summary.summarize([run], ledger)['methods'][0]['generations']
    assert len(rows) == 1 and rows[0]['recursive_candidates'] == 1
    assert rows[0]['publication'].startswith('pending_')


def test_native_registration_survives_failed_outer_generation(tmp_path):
    run = root(tmp_path, mode='geneloop')
    ledger = lines(tmp_path / 'ledger.jsonl', [])
    put(run / 'result.json', {'status': 'failed', 'error': 'later_step_failed'})
    put(run / 'materials/acquisitions/id/result.json', {'origin': 'model_construction',
        'status': 'registered', 'library': {'path': '/diagnostic/library', 'sha256': 'diagnostic'}})
    result = summary.summarize([run], ledger)
    assert result['methods'][0]['native_material_outcomes'][0]['status'] == 'registered'
    assert result['failures'][0]['status'] == 'failed'


def test_broken_journal_reports_partial_inventory_without_mutating_input(tmp_path):
    run = root(tmp_path)
    ledger = tmp_path / 'ledger.jsonl'
    _, session = trial(run, ledger)
    lines(ledger, [settled(session, 1)])
    ledger.write_text(ledger.read_text() + '{"request_id":')
    before = ledger.read_bytes()
    value = summary.summarize([run], ledger)
    assert value['overall_accounting']['model_usd_decimal'] is None
    assert value['overall_accounting']['known_model_usd_decimal'] == '0.10000001'
    assert value['warnings'][0]['issue'] == 'invalid_jsonl_row'
    assert ledger.read_bytes() == before


def test_reported_request_count_with_missing_inventory_is_unknown(tmp_path):
    run = root(tmp_path)
    ledger = lines(tmp_path / 'ledger.jsonl', [])
    _, session = trial(run, ledger)
    (session / 'requests.jsonl').write_text('')
    value = summary.summarize([run], ledger)
    assert value['overall_accounting']['model_usd_decimal'] is None
    assert any(row['issue'] == 'reported_requests_without_inventory' for row in value['warnings'])


def test_failed_zero_request_trial_remains_in_phase_table(tmp_path):
    run = root(tmp_path)
    ledger = lines(tmp_path / 'ledger.jsonl', [])
    output, session = trial(run, ledger, ids=(), reward=0, status='failed')
    value = summary.summarize([run], ledger)
    assert len(value['methods'][0]['trials']) == 1
    assert value['phases'][0]['accounting']['requests'] == 0
    assert value['failures'][0]['directory'] == str(output)


@pytest.mark.parametrize('threshold', ['0', '-1', 'NaN'])
def test_invalid_quality_threshold_rejected_without_ledger_changes(tmp_path, threshold):
    ledger = lines(tmp_path / 'ledger.jsonl', [])
    with pytest.raises(ValueError, match='quality_threshold_invalid'):
        summary.summarize([root(tmp_path)], ledger, quality_threshold=threshold)
