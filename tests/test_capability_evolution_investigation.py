"""Synthetic host-call diagnostics; no model behavior or benefit is inferred."""
import json

import pytest
from jsonschema import Draft202012Validator

from src.adapters.capability_evolution_investigation import run_investigation
from src.adapters.capability_feedback import verify
from tests.test_capability_investigation import data, make


def candidate(identifiers):
    return {'kind': 'construction_strategy', 'burden': 'Repeated interface conversion',
            'evidence_ids': identifiers, 'scope': 'study',
            'expected_behavior': 'Reuse a stable representation before composition',
            'verification': 'Original independent checks', 'failure_conditions': 'Keep old method',
            'proposal': {'applicability': 'Shared object input',
                         'decision_policy': 'Inspect interface compatibility before composing',
                         'capability_refs': [], 'parent': None}}


def test_one_existing_session_can_investigate_submit_and_revise(tmp_path, data):
    investigation = make(tmp_path, data)
    calls = []
    def handler(proposal, context, directory):
        calls.append((proposal, context, directory))
        return {'status': 'failed' if len(calls) == 1 else 'evaluated',
                'reason': 'heldout_quality_failure' if len(calls) == 1 else None,
                'actual_adoption': None, 'measured_net_benefit': None}
    agent_calls = []
    def agent(request, dispatch):
        agent_calls.append(request)
        assert 'relation checker' not in json.dumps(request['initial_context'])
        assert {tool['name'] for tool in request['tools']} == {
            'evolution_overview', 'evolution_search', 'evolution_read', 'evolution_note',
            'evolution_submit', 'evolution_finish'}
        for tool in request['tools']:
            Draft202012Validator.check_schema(tool['parameters'])
        rows = dispatch('evolution_search', {'kind': 'experience'})['items']
        identifiers = [row['id'] for row in rows[:2]]
        local = dispatch('evolution_read', {'kind': 'experience', 'id': identifiers[0], 'section': 'context'})
        assert local['cost_attribution'] == 'construction_requests_only'
        first = dispatch('evolution_submit', {'candidate': candidate(identifiers), 'observation_ids': identifiers})
        assert first['outcome']['reason'] == 'heldout_quality_failure'
        revised = candidate(identifiers)
        revised['proposal']['decision_policy'] = 'Project only fields accepted by the child interface'
        second = dispatch('evolution_submit', {'candidate': revised, 'observation_ids': identifiers})
        assert second['outcome']['status'] == 'evaluated'
        dispatch('evolution_finish', {'reason': 'Retain evaluated candidate for future use'})
        return {'status': 'completed', 'model_requests': 0, 'diagnostic': True}
    result = run_investigation(investigation, call_agent=agent,
                              handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(agent_calls) == 1
    assert len(calls) == len(result['submissions']) == 2
    assert calls[0][2] != calls[1][2]
    assert result['status'] == 'completed'
    assert result['actual_adoption'] is None and result['measured_net_benefit'] is None
    assert (tmp_path / 'run/submission-0.json').exists()
    assert len(result['tool_calls']) == 5


def test_boundary_aliases_return_to_original_handler_identity(tmp_path, data):
    investigation = make(tmp_path, data)
    seen = []
    def agent(request, dispatch):
        rows = dispatch('evolution_search', {'kind': 'experience'})['items'][:2]
        identifiers = [row['id'] for row in rows]
        proposal = candidate(identifiers)
        proposal.update(kind='boundary', proposal={'regions': {row['task_id']: ['prepare'] for row in rows}})
        result = dispatch('evolution_submit', {'candidate': proposal, 'observation_ids': identifiers})
        assert result['status'] == 'submitted'
        dispatch('evolution_finish', {'reason': 'Submitted an observed region'})
        return {}
    def handler(value, context, directory):
        seen.append(value)
        assert set(value['proposal']['regions']) == {row['task_id'] for row in context['observations']}
        return {'status': 'deferred'}
    run_investigation(investigation, call_agent=agent, handlers={'boundary': handler}, output=tmp_path / 'run')
    assert len(seen) == 1


def test_no_change_is_an_explicit_agent_decision(tmp_path, data):
    def agent(request, dispatch):
        dispatch('evolution_search', {'kind': 'experience', 'status': 'failed'})
        dispatch('evolution_finish', {'reason': 'Evidence does not support a general improvement'})
        return {'diagnostic': True}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    assert result['status'] == 'no_change'
    assert result['submissions'] == []
    assert result['finish']['reason'].startswith('Evidence')


def test_ending_without_finish_preserves_incomplete_state(tmp_path, data):
    result = run_investigation(make(tmp_path, data), call_agent=lambda request, dispatch: {'answer': 'done'},
                              handlers={}, output=tmp_path / 'run')
    assert result['status'] == 'incomplete'
    assert result['finish'] is None


def test_submission_rejection_is_returned_and_retained_without_retry(tmp_path, data):
    handled = []
    def agent(request, dispatch):
        identifier = dispatch('evolution_search', {'kind': 'experience'})['items'][0]['id']
        result = dispatch('evolution_submit', {'candidate': candidate([identifier]), 'observation_ids': [identifier]})
        assert result['status'] == 'rejected'
        assert 'cross_task_support_required' in result['reason']
        dispatch('evolution_finish', {'reason': 'Need independent evidence'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': lambda *args: handled.append(args)}, output=tmp_path / 'run')
    assert handled == []
    assert len(result['submissions']) == 1
    assert result['submissions'][0]['status'] == 'rejected'


def test_missing_handler_remains_pending(tmp_path, data):
    def agent(request, dispatch):
        identifiers = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        result = dispatch('evolution_submit', {'candidate': candidate(identifiers), 'observation_ids': identifiers})
        assert result['status'] == 'pending'
        dispatch('evolution_finish', {'reason': 'Existing host does not support this candidate yet'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    assert result['submissions'][0]['reason'] == 'existing_host_admission_unavailable'


def test_submission_reply_avoids_echoing_model_source_and_retains_original(tmp_path, data):
    def agent(request, dispatch):
        identifiers = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        proposed = candidate(identifiers)
        reply = dispatch('evolution_submit', {'candidate': proposed, 'observation_ids': identifiers})
        assert 'candidate' not in reply and 'validated_candidate' not in reply
        full = dispatch('evolution_read', {'kind': 'evidence', 'id': reply['evidence_id'], 'limit': 100})
        assert json.loads(full['content'])['candidate'] == proposed
        assert json.loads(verify(reply['record']))['candidate'] == proposed
        dispatch('evolution_finish', {'reason': 'Original proposal remains available on demand'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    assert result['submissions'][0]['status'] == 'pending'


def test_tool_error_can_be_corrected_in_same_session(tmp_path, data):
    def agent(request, dispatch):
        error = dispatch('evolution_read', {'kind': 'experience', 'id': 'unknown'})
        assert error['status'] == 'error'
        assert dispatch('evolution_overview', {})['scope'] == 'study'
        dispatch('evolution_finish', {'reason': 'End after checking overview'})
        later = dispatch('evolution_overview', {})
        assert 'already_finished' in later['error']
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    assert len(result['tool_calls']) == 4
    assert json.loads((tmp_path / 'run/tool-0.json').read_text())['status'] == 'failed'


def test_host_failure_keeps_partial_submission_and_does_not_create_certification(tmp_path, data):
    def handler(*args):
        raise ValueError('independent_check_failed')
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        result = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        assert result['status'] == 'rejected' and 'independent_check_failed' in result['reason']
        dispatch('evolution_finish', {'reason': 'Keep failed candidate for diagnosis'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
                              handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert result['production_enabled'] is False
    assert result['submissions'][0]['status'] == 'rejected'


def test_model_transport_failure_keeps_existing_tool_records(tmp_path, data):
    def agent(request, dispatch):
        dispatch('evolution_overview', {})
        raise RuntimeError('diagnostic_transport_failure')
    with pytest.raises(RuntimeError, match='transport_failure'):
        run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    record = json.loads((tmp_path / 'run/result.json').read_text())
    assert record['status'] == 'failed'
    assert len(record['tool_calls']) == 1
    assert record['submissions'] == []


@pytest.mark.parametrize('omitted', [('scope',), ('evidence_ids',), ('scope', 'evidence_ids')])
def test_host_binds_omitted_redundant_candidate_fields(tmp_path, data, omitted):
    received = []
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        proposal = candidate(ids)
        for key in omitted:
            proposal.pop(key)
        tool = next(tool for tool in request['tools'] if tool['name'] == 'evolution_submit')
        arguments = {'candidate': proposal, 'observation_ids': ids}
        Draft202012Validator(tool['parameters']).validate(arguments)
        result = dispatch('evolution_submit', arguments)
        assert result['status'] == 'submitted'
        recorded = json.loads(verify(result['record']))
        assert recorded['candidate'] == proposal
        assert recorded['validated_candidate']['scope'] == 'study'
        assert recorded['validated_candidate']['evidence_ids'] == ids
        assert all(key not in proposal for key in omitted)
        dispatch('evolution_finish', {'reason': 'Host bound only omitted context fields'})
        return {}
    def handler(proposal, context, directory):
        received.append((proposal, context))
        return {'status': 'pending'}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(received) == 1
    assert result['submissions'][0]['validated_candidate']['scope'] == 'study'


@pytest.mark.parametrize('field,value,error', [
    ('scope', 'foreign-scope', 'scope_conflict'),
    ('evidence_ids', ['evidence_file_sha'], 'cross_task_support_required'),
    ('evidence_ids', None, 'cross_task_support_required')])
def test_explicit_conflicts_are_rejected_with_usable_observation_ids(tmp_path, data, field, value, error):
    received = []
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        proposal = candidate(ids)
        proposal[field] = value
        result = dispatch('evolution_submit', {'candidate': proposal, 'observation_ids': ids})
        assert result['status'] == 'rejected' and error in result['reason']
        assert json.loads(verify(result['record']))['candidate'][field] == value
        assert set(ids) <= set(result['diagnostic']['available_observation_ids'])
        assert result['diagnostic']['expected_scope'] == 'study'
        assert 'evidence_*' in result['diagnostic']['message']
        dispatch('evolution_finish', {'reason': 'Preserve the explicit invalid value'})
        return {}
    run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': lambda *args: received.append(args)}, output=tmp_path / 'run')
    assert received == []


def test_file_ids_in_observation_selection_return_recoverable_feedback(tmp_path, data):
    def agent(request, dispatch):
        error = dispatch('evolution_submit', {'candidate': candidate([]), 'observation_ids': ['evidence_raw_file']})
        assert error['status'] == 'rejected'
        assert error['diagnostic']['available_observation_ids']
        ids = error['diagnostic']['available_observation_ids'][:2]
        proposal = candidate(ids)
        proposal.pop('scope')
        proposal.pop('evidence_ids')
        corrected = dispatch('evolution_submit', {'candidate': proposal, 'observation_ids': ids})
        assert corrected['status'] == 'pending'
        dispatch('evolution_finish', {'reason': 'Corrected IDs in the same original session'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    assert [row['status'] for row in result['submissions']] == ['rejected', 'pending']


def test_host_binding_preserves_cross_task_independence_check(tmp_path, data):
    def agent(request, dispatch):
        ids = [dispatch('evolution_search', {'kind': 'experience'})['items'][0]['id']]
        proposal = candidate(ids)
        proposal.pop('scope')
        proposal.pop('evidence_ids')
        result = dispatch('evolution_submit', {'candidate': proposal, 'observation_ids': ids})
        assert result['status'] == 'rejected'
        assert 'cross_task_support_required' in result['reason']
        dispatch('evolution_finish', {'reason': 'One experience is insufficient for generalization'})
        return {}
    run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
