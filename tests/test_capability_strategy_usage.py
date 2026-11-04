"""Deterministic host receipt diagnostics; no observed model strategy gain."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.capability_feedback import file_ref
from src.adapters.capability_strategy import create_strategy, admit_strategy, strategy_context, strategy_ref
from src.adapters.capability_strategy_usage import inspect_task_strategy_usage, ingest_task_strategy_usage
from src.adapters.capability_trajectory import project_web_task
from src.adapters.capability_decision_evidence import _web, record_web_decision, inspect_decision
from tests.test_capability_feedback import fixture
from tests.test_capability_decision_evidence import web_task, context


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


@pytest.fixture
def used(tmp_path):
    feedback, library, source, _ = fixture(tmp_path)
    snapshot = library['snapshot']
    task = web_task(tmp_path)
    policy = create_strategy({'owner': 'owner', 'target': 'task', 'scope': 'example',
        'applicability': 'When the requested target is unclear', 'decision_policy': 'Ask a discriminating question',
        'capability_refs': snapshot['roots'][:1], 'evidence': [source], 'parent': None}, snapshot)
    policy_ref = put(tmp_path / 'strategy.json', policy)
    training = put(tmp_path / 'training.json', {'split': 'training'})
    heldout = put(tmp_path / 'heldout.json', {'split': 'heldout'})
    verdict = {'passed': True, 'checks': [{'id': 'host-check', 'status': 'passed'}],
               'training_sources': [training], 'heldout_sources': [heldout], 'evidence': [heldout]}
    selection = admit_strategy(policy_ref, snapshot, target='task', scope='example',
        evaluate=lambda value: verdict, directory=tmp_path / 'admission', feedback=feedback)
    visible = strategy_context(selection, snapshot, target='task', scope='example', feedback=feedback)
    visible.pop('format'); visible.pop('selection')
    ctx = put(task / 'strategy-context.json', visible)
    trace = project_web_task(task, 'owner')
    receipt = {'format': 'harless_task_strategy_use_v1', 'owner': 'owner', 'task_id': task.name,
        'session_id': 'decision', 'scene_id': 'example', 'scope': 'example', 'selection': selection,
        'strategy': strategy_ref(policy), 'snapshot': put(task / 'strategy-snapshot.json', snapshot),
        'context_ref': ctx, 'context_sha256': ctx['sha256'], 'task_status': 'completed',
        'semantic_adoption': None, 'quality_status': 'unreviewed', 'exposure': 'prompt_submitted',
        'events_range': {'start_index': 0, 'end_index': 3},
        'evidence': [next(r for r in trace['evidence'] if Path(r['path']).name == n)
                     for n in ('task.json', 'effective-config.json', 'events.jsonl')]}
    put(task / 'strategy-use.json', receipt)
    return task, feedback, receipt, policy


def test_usage_records_exposure_and_unknown_quality_idempotently(used):
    task, feedback, receipt, policy = used
    row = inspect_task_strategy_usage(task, 'owner')
    assert row['subject'] == strategy_ref(policy)
    assert row['exposure'] == 'prompt_submitted' and row['semantic_adoption'] is None
    first = ingest_task_strategy_usage(task, 'owner', feedback)
    second = ingest_task_strategy_usage(task, 'owner', feedback)
    assert first['fact_id'] == second['fact_id']
    facts = list(feedback.read()['facts'].values())
    assert len(facts) == 2
    usage = next(f for f in facts if f['status'] == 'unknown')
    assert usage['cost'] is None and usage['benefit'] is None


def test_withdrawn_strategy_retains_historical_exposure_without_new_authority(used):
    task, feedback, _, policy = used
    feedback.withdraw(strategy_ref(policy), 'later-counterexample', file_ref(task / 'strategy-use.json'))
    observed = ingest_task_strategy_usage(task, 'owner', feedback)
    assert observed['quality_status'] == 'unreviewed'
    assert feedback.read()['blocked'][policy['id']]['reason'] == 'later-counterexample'


@pytest.mark.parametrize('change', ['passed', 'adoption', 'range', 'owner', 'task', 'context', 'evidence'])
def test_receipt_cannot_self_award_success_or_change_bindings(used, change):
    task, feedback, receipt, _ = used
    value = copy.deepcopy(receipt)
    if change == 'passed': value['quality_status'] = 'passed'
    if change == 'adoption': value['semantic_adoption'] = True
    if change == 'range': value['events_range']['end_index'] += 1
    if change == 'owner': value['owner'] = 'foreign'
    if change == 'task': value['task_id'] = 'another-task'
    if change == 'context': value['context_sha256'] = '0' * 64
    if change == 'evidence': value['evidence'] = []
    put(task / 'strategy-use.json', value)
    with pytest.raises(ValueError, match='strategy_usage'):
        ingest_task_strategy_usage(task, 'owner', feedback)


def test_raw_events_mutation_invalidates_usage(used):
    task, feedback, _, _ = used
    with (task / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps({'type': 'user/message', 'data': {'source': {'kind': 'user'}}}) + '\n')
    with pytest.raises(ValueError, match='task_evidence_changed'):
        ingest_task_strategy_usage(task, 'owner', feedback)


def test_task_decision_carries_verified_usage_in_bounded_context(tmp_path, used):
    task, _, _, policy = used
    approval = context(tmp_path / 'approved-context.json', _web(task, 'owner')['evidence'])
    ref = record_web_decision(task, 'owner', relation='target-selection', approved_context=approval,
        output=tmp_path / 'decision-record.json')
    row = inspect_decision(ref, 'owner')
    assert row['decision_context']['strategy_usage']['subject'] == strategy_ref(policy)
    assert row['decision_context']['strategy_usage']['semantic_adoption'] is None
    assert any(Path(r['path']).name == 'strategy-use.json' for r in row['evidence'])


def test_old_task_without_strategy_receipt_remains_ordinary(tmp_path):
    task = web_task(tmp_path)
    feedback, _, _, _ = fixture(tmp_path)
    assert inspect_task_strategy_usage(task, 'owner') is None
    assert ingest_task_strategy_usage(task, 'owner', feedback) == {'status': 'absent', 'fact_id': None}



def test_mutable_ui_state_does_not_duplicate_the_same_receipt_fact(used):
    task, feedback, _, _ = used
    first = ingest_task_strategy_usage(task, 'owner', feedback)
    state = json.loads((task / 'task-state.json').read_text())
    state['ui_annotation'] = 'review screen opened'
    put(task / 'task-state.json', state)
    second = ingest_task_strategy_usage(task, 'owner', feedback)
    assert first['fact_id'] == second['fact_id']


def test_missing_original_host_admission_cannot_be_recreated_from_exposure(used, tmp_path):
    from src.adapters.capability_feedback import CapabilityFeedback
    task, _, _, _ = used
    with pytest.raises(ValueError, match='host_admission_required'):
        ingest_task_strategy_usage(task, 'owner', CapabilityFeedback(tmp_path / 'empty-feedback', 'owner'))
