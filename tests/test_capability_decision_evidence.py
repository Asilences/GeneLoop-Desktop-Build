"""Synthetic event diagnostics; no provider invocation or strategy benefit claim."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.capability_decision_evidence import (
    CONTEXT_FORMAT, inspect_decision, record_web_decision, record_construction_decision,
)
from src.adapters.capability_trajectory import project_web_task
from src.adapters.capability_feedback import file_ref
from src.adapters.capability_construction_history import capture


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


def context(path, refs, *, interactions=None):
    return put(path, {'format': CONTEXT_FORMAT, 'owner': 'owner', 'source_evidence': refs,
                      'objective': 'Generate a requested deliverable', 'state': 'Target needs confirmation',
                      'remaining_judgments': ['Choose whether clarification is useful'],
                      'interactions': interactions or [], 'outcome': 'Task finished; quality unknown'})


def source_refs(task):
    refs = project_web_task(task, 'owner')['evidence']
    for path in (task.parent.parent / 'comparisons.json', task / 'ppt-learning-delivery.json'):
        if path.exists():
            refs.append(file_ref(path))
    return refs


def web_task(root, identity='task', source='decision'):
    task = root / 'tasks' / identity
    task.mkdir(parents=True)
    common = {'task_id': identity, 'user_id': 'owner', 'source_task_id': source,
              'status': 'completed', 'scene': 'example', 'session_id': source}
    put(task / 'task-state.json', common)
    put(task / 'effective-config.json', {**common, 'provider_mode': 'real', 'tools': [], 'trace_start_index': 0})
    put(task / 'task.json', {**common, 'content': [{'type': 'text', 'text': 'PRIVATE ORIGINAL'}]})
    events = [
        {'type': 'tool/call', 'data': {'callId': 'q', 'name': 'ask_user_question',
                                     'arguments': {'questions': [{'id': 'target', 'question': 'PRIVATE QUESTION'}]}}},
        {'type': 'tool/result', 'data': {'message': {'content': [{'type': 'tool-result', 'toolCallId': 'q',
             'isError': False, 'content': json.dumps({'answers': [{'id': 'target', 'custom': 'PRIVATE ANSWER'}]})}]}}},
        {'type': 'user/message', 'data': {'source': {'kind': 'user'}, 'content': [{'type': 'text', 'text': 'PRIVATE FOLLOWUP'}]}},
    ]
    (task / 'events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in events), encoding='utf-8')
    return task


def test_web_decision_preserves_questions_answers_and_user_messages_as_evidence(tmp_path):
    task = web_task(tmp_path)
    refs = source_refs(task)
    approved = context(tmp_path / 'approved.json', refs, interactions=[
        {'event_index': 0, 'kind': 'clarification', 'summary': 'Asked user to choose the target'},
        {'event_index': 2, 'kind': 'user_message', 'summary': 'User provided further information'},
    ])
    ref = record_web_decision(task, 'owner', relation='target-ambiguity', approved_context=approved,
                              output=tmp_path / 'decision.json')
    row = inspect_decision(ref, 'owner')
    assert row['status'] == 'passed' and row['counterexample'] is False
    assert row['quality'] == 'unreviewed' and row['observed_cost_usd'] is None
    assert row['interaction_evidence'][0]['result_event_index'] == 1
    assert row['interaction_evidence'][1] == {'kind': 'user_message', 'event_index': 2}
    assert 'PRIVATE' not in json.dumps(row['decision_context'])
    assert any(Path(r['path']).name == 'events.jsonl' for r in row['evidence'])


def test_retry_identity_is_original_task_metadata_and_raw_mutation_is_rejected(tmp_path):
    identities = []
    for identity in ('attempt-one', 'attempt-two'):
        task = web_task(tmp_path, identity=identity)
        approved = context(tmp_path / (identity + '-approval.json'), source_refs(task))
        ref = record_web_decision(task, 'owner', relation='shared', approved_context=approved,
                                  output=tmp_path / (identity + '.json'))
        identities.append(inspect_decision(ref, 'owner')['source_identity'])
    assert identities[0] == identities[1]
    (task / 'events.jsonl').write_text('', encoding='utf-8')
    with pytest.raises(ValueError, match='source_evidence_changed'):
        inspect_decision(ref, 'owner')


@pytest.mark.parametrize('change', ['owner', 'source', 'invented_event', 'oversized'])
def test_approval_must_match_current_evidence_and_observed_event_indices(tmp_path, change):
    task = web_task(tmp_path)
    approved = context(tmp_path / 'approved.json', source_refs(task))
    value = json.loads(Path(approved['path']).read_text())
    if change == 'owner': value['owner'] = 'foreign'
    if change == 'source': value['source_evidence'] = []
    if change == 'invented_event':
        value['interactions'] = [{'event_index': 99, 'kind': 'clarification', 'summary': 'Invented'}]
    if change == 'oversized': value['objective'] = 'x' * 2001
    approved = put(tmp_path / 'changed.json', value)
    with pytest.raises(ValueError, match='decision_context'):
        record_web_decision(task, 'owner', relation='shared', approved_context=approved,
                            output=tmp_path / 'decision.json')


def test_missing_approval_and_foreign_inspection_are_rejected(tmp_path):
    task = web_task(tmp_path)
    approved = context(tmp_path / 'approved.json', source_refs(task))
    ref = record_web_decision(task, 'owner', relation='shared', approved_context=approved,
                              output=tmp_path / 'decision.json')
    with pytest.raises(ValueError, match='owner_changed'):
        inspect_decision(ref, 'foreign')
    Path(approved['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence_changed'):
        inspect_decision(ref, 'owner')


def test_construction_reuses_original_attempt_and_unknown_all_stage_cost(tmp_path):
    task = put(tmp_path / 'task.json', {'id': 'goal', 'instruction': 'Construct a reusable checker'})
    attempt = tmp_path / 'attempt'; attempt.mkdir()
    result = put(attempt / 'result.json', {'status': 'failed', 'model_called': False,
        'provider_requests': 0, 'request_ids': [], 'error': 'interface_incompatible'})
    record = capture({'id': 'goal', 'task': task}, attempt, {'digest': 'snapshot'})
    refs = [task, record, result]
    approved = context(tmp_path / 'approved.json', refs)
    ref = record_construction_decision([record], task, 'owner', relation='interface-repair',
        approved_context=approved, output=tmp_path / 'decision.json')
    row = inspect_decision(ref, 'owner')
    assert row['stage'] == 'construction' and row['status'] == 'unknown'
    assert row['observed_cost_usd'] == '0'
    assert row['construction_outcomes'][0]['error'] == 'interface_incompatible'
    assert row['cost_attribution'].startswith('construction_requests_only')
    assert row['quality'] == 'unreviewed'



def test_fresh_child_sessions_in_same_comparison_parent_are_one_source(tmp_path):
    first = web_task(tmp_path, identity='first', source='child-one')
    second = web_task(tmp_path, identity='second', source='child-two')
    put(tmp_path / 'comparisons.json', {'principal': 'owner', 'turns': [
        {'id': 'comparison-one', 'session_id': 'main-conversation', 'lanes': {'baseline': {'task_id': 'first'}}},
        {'id': 'comparison-two', 'session_id': 'main-conversation', 'lanes': {'motif': {'task_id': 'second'}}},
    ]})
    identities = []
    for index, task in enumerate((first, second)):
        approval = context(tmp_path / f'approved-{index}.json', source_refs(task))
        ref = record_web_decision(task, 'owner', relation='shared', approved_context=approval,
                                  output=tmp_path / f'decision-{index}.json')
        identities.append(inspect_decision(ref, 'owner')['source_identity'])
    assert identities[0] == identities[1]


def test_missing_lineage_is_rejected_instead_of_using_a_fresh_task_name(tmp_path):
    task = web_task(tmp_path)
    for name in ('task-state.json', 'task.json'):
        data = json.loads((task / name).read_text())
        data.pop('session_id'); data.pop('source_task_id')
        put(task / name, data)
    approval = context(tmp_path / 'approved.json', source_refs(task))
    with pytest.raises(ValueError, match='independent_lineage_required'):
        record_web_decision(task, 'owner', relation='shared', approved_context=approval,
                            output=tmp_path / 'decision.json')


def test_foreign_comparison_journal_is_rejected(tmp_path):
    task = web_task(tmp_path)
    put(tmp_path / 'comparisons.json', {'principal': 'foreign', 'turns': []})
    approval = context(tmp_path / 'approved.json', source_refs(task))
    with pytest.raises(ValueError, match='foreign comparison lineage'):
        record_web_decision(task, 'owner', relation='shared', approved_context=approval,
                            output=tmp_path / 'decision.json')
