"""Synthetic host-call diagnostics; no model behavior or benefit is inferred."""
import json

import pytest
from jsonschema import Draft202012Validator

from src.adapters.capability_evolution_investigation import run_investigation
from src.adapters.capability_feedback import file_ref, verify
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


def test_real_host_feedback_is_readable_without_echoing_all_references(tmp_path, data):
    diagnostic = tmp_path / 'host-validation.txt'
    diagnostic.write_text('Independent validation failed its quality check.\n')
    reference = file_ref(diagnostic)

    def handler(*_args):
        return {'status': 'rejected', 'checks': [{'id': 'quality', 'status': 'failed'}],
                'evidence_refs': [reference]}

    def agent(request, dispatch):
        identifiers = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        reply = dispatch('evolution_submit', {'candidate': candidate(identifiers), 'observation_ids': identifiers})
        assert reply['outcome']['status'] == 'rejected'
        assert reply['outcome']['available_evidence_count'] == 1
        assert 'evidence_refs' not in reply['outcome']
        original = dispatch('evolution_read', {'kind': 'evidence', 'id': 'evidence_' + reference['sha256']})
        assert original['content'] == diagnostic.read_bytes().decode('utf-8')
        dispatch('evolution_finish', {'reason': 'Actual independent feedback is available for revision'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert result['submissions'][0]['outcome']['evidence_refs'] == [reference]


def test_local_candidate_limit_bounds_real_evaluations_without_limiting_reads(tmp_path, data):
    handled = []
    def handler(*args):
        handled.append(args)
        return {'status': 'rejected', 'reason': 'Independent evaluation failed'}
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        for expected in (1, 0):
            reply = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
            assert reply['remaining_candidate_evaluations'] == expected
        rejected = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        assert 'evaluation_limit_reached' in rejected['reason']
        assert dispatch('evolution_overview', {})['scope'] == 'study'
        dispatch('evolution_finish', {'reason': 'Retain two actual rejected candidates for the next investigation'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(handled) == 2 and len(result['submissions']) == 3


def test_missing_verification_reports_the_real_field_and_can_be_repaired(tmp_path, data):
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        proposed = candidate(ids)
        verification = proposed.pop('verification')
        failed = dispatch('evolution_submit', {'candidate': proposed, 'observation_ids': ids})
        assert failed['diagnostic']['missing_fields'] == ['verification']
        assert failed['diagnostic']['unexpected_fields'] == []
        assert 'missing candidate fields' in failed['diagnostic']['message']
        proposed['verification'] = verification
        repaired = dispatch('evolution_submit', {'candidate': proposed, 'observation_ids': ids})
        assert repaired['status'] == 'pending'
        dispatch('evolution_finish', {'reason': 'Repaired the actual missing field without changing the hypothesis'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    assert len(result['submissions']) == 2


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


def test_host_preflight_failures_do_not_spend_native_evaluation_slots(tmp_path, data):
    called = []
    def handler(proposal, context, directory):
        called.append(proposal)
        return {'status': 'evaluated'}
    def preflight(proposal, context):
        if proposal['proposal']['decision_policy'] == 'invalid contract':
            error = ValueError('host_contract_invalid')
            error.evolution_diagnostic = {'message': 'Choose a supported host input contract.', 'lookup_tool': 'host_inputs'}
            raise error
    handler.preflight = preflight
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        invalid = candidate(ids)
        invalid['proposal']['decision_policy'] = 'invalid contract'
        for _ in range(3):
            result = dispatch('evolution_submit', {'candidate': invalid, 'observation_ids': ids})
            assert result['remaining_candidate_evaluations'] == 2
            assert result['diagnostic']['lookup_tool'] == 'host_inputs'
        for expected in (1, 0):
            result = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
            assert result['remaining_candidate_evaluations'] == expected
        dispatch('evolution_finish', {'reason': 'Preserve three preflight failures and two actual evaluations'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(called) == 2 and len(result['submissions']) == 5


def test_native_exception_records_are_readable_for_revision_in_the_same_session(tmp_path, data):
    calls = []
    native = {'kind': 'script_admission', 'error': 'unbound_path_literal',
              'source_space': 'parameterized_template', 'line': 4, 'column': 10,
              'source_line': 'literal = "// header"'}
    path = tmp_path / 'native/admission-error.json'
    path.parent.mkdir()
    path.write_text(json.dumps(native))
    reference = file_ref(path)
    def handler(proposal, context, directory):
        calls.append(proposal)
        if len(calls) == 1:
            error = ValueError('unbound_path_literal')
            error.evolution_diagnostic = {'message': 'Original native source admission rejected this candidate.',
                'native_diagnostics': [{**native, 'evidence_id': 'evidence_' + reference['sha256']}]}
            error.evolution_evidence_refs = [reference]
            raise error
        return {'status': 'evaluated'}
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        first = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        assert first['status'] == 'rejected' and first['remaining_candidate_evaluations'] == 1
        assert first['diagnostic']['message'].startswith('Original native')
        assert first['diagnostic']['native_diagnostics'][0]['line'] == 4
        assert first['diagnostic']['available_evidence_count'] == 1
        diagnostic_id = first['diagnostic']['native_diagnostics'][0]['evidence_id']
        record = dispatch('evolution_read', {'kind': 'evidence', 'id': diagnostic_id,
                                           'section': 'content', 'json_path': ['source_line']})
        assert json.loads(record['content']) == native['source_line']
        revised = candidate(ids)
        revised['proposal']['decision_policy'] = 'Diagnostic revised proposal after reading original host evidence'
        second = dispatch('evolution_submit', {'candidate': revised, 'observation_ids': ids})
        assert second['outcome']['status'] == 'evaluated' and second['remaining_candidate_evaluations'] == 0
        dispatch('evolution_finish', {'reason': 'Keep actual rejection and subsequent host evaluation'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
                              handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert result['submissions'][0]['evidence_refs'] == [reference]
    assert len(calls) == 2 and json.loads(path.read_text()) == native


def test_changed_native_exception_evidence_is_reported_without_hiding_original_rejection(tmp_path, data):
    path = tmp_path / 'native.json'
    path.write_text('{"diagnostic":true}')
    reference = file_ref(path)
    path.write_text('{}')
    def handler(*args):
        error = ValueError('original_native_rejection')
        error.evolution_evidence_refs = [reference]
        raise error
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        reply = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        assert reply['status'] == 'rejected' and 'original_native_rejection' in reply['reason']
        assert 'evidence_changed' in reply['diagnostic']['evidence_error']
        dispatch('evolution_finish', {'reason': 'Native record integrity is unresolved'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert result['submissions'][0]['evidence_refs'] == [reference]


def test_failed_root_can_be_repaired_twice_without_consuming_other_root(tmp_path, data):
    calls = []
    def handler(*args):
        calls.append(args)
        if len(calls) == 1:
            raise ValueError('native_source_rejection')
        return {'status': 'rejected', 'reason': 'independent_check_failed'}
    def agent(request, dispatch):
        assert request['initial_context']['candidate_repair_limit_per_root'] == 2
        assert 'Never encode or concatenate rejected literals' in request['prompt']
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        first = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        assert first['root_index'] == 0 and first['repair_attempt'] == 0
        for expected in (1, 0):
            revised = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids, 'repair_of': 0})
            assert revised['remaining_candidate_evaluations'] == 1
            assert revised['remaining_candidate_repairs'] == {'0': expected}
        # Referencing a different failed revision cannot reset the root allowance.
        failed = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids, 'repair_of': 1})
        assert 'repair_limit_reached' in failed['reason']
        second = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        assert second['remaining_candidate_evaluations'] == 0
        repaired = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids, 'repair_of': second['index']})
        assert repaired['remaining_candidate_evaluations'] == 0
        assert repaired['remaining_candidate_repairs'] == {'0': 0, '4': 1}
        dispatch('evolution_finish', {'reason': 'Root and repair allowances are separate'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(calls) == 5
    assert [row.get('repair_attempt') for row in result['submissions']] == [0, 1, 2, None, 0, 1]
    assert result['submissions'][1]['repair_of'] == 0
    assert result['submissions'][0]['reason'] == 'ValueError:native_source_rejection'


@pytest.mark.parametrize('prior_status', ['evaluated', 'deferred'])
def test_repair_requires_failed_actual_evaluation(tmp_path, data, prior_status):
    calls = []
    def handler(*args):
        calls.append(args)
        return {'status': prior_status}
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        original = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        failed = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids, 'repair_of': original['index']})
        assert 'requires_failed_host_evaluation' in failed['reason']
        assert failed['remaining_candidate_repairs'] == {'0': 2}
        dispatch('evolution_finish', {'reason': 'No repair for accepted or deferred host results'})
        return {}
    run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(calls) == 1


@pytest.mark.parametrize('repair_of', [-1, True, None, 1, '0'])
def test_invalid_repair_reference_retains_original_allowance(tmp_path, data, repair_of):
    calls = []
    def handler(*args):
        calls.append(args)
        return {'status': 'failed'}
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        failed = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids, 'repair_of': repair_of})
        assert 'repair_reference_invalid' in failed['reason']
        assert failed['remaining_candidate_repairs'] == {'0': 2}
        dispatch('evolution_finish', {'reason': 'Invalid references do not allocate actual evaluations'})
        return {}
    run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(calls) == 1


def test_format_failure_cannot_be_relabelled_as_actual_repair(tmp_path, data):
    calls = []
    def agent(request, dispatch):
        ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        invalid = candidate(ids)
        invalid.pop('verification')
        dispatch('evolution_submit', {'candidate': invalid, 'observation_ids': ids})
        failed = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids, 'repair_of': 0})
        assert 'requires_failed_host_evaluation' in failed['reason']
        assert failed['remaining_candidate_evaluations'] == 2
        dispatch('evolution_finish', {'reason': 'Format correction can be resubmitted without repair_of'})
        return {}
    run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': lambda *args: calls.append(args)}, output=tmp_path / 'run')
    assert calls == []


@pytest.mark.parametrize('change', ['observations', 'scope', 'preflight'])
def test_repair_keeps_context_and_preflight_failures_do_not_spend_revision(tmp_path, data, change):
    calls = []
    def handler(*args):
        calls.append(args)
        return {'status': 'failed'}
    def preflight(proposal, context):
        if proposal['burden'] == 'invalid native shape':
            raise ValueError('original_native_preflight_rejected')
    handler.preflight = preflight
    def agent(request, dispatch):
        all_ids = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items']]
        ids = all_ids[:2]
        dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids})
        selected = all_ids[1:] if change == 'observations' else ids
        proposed = candidate(selected)
        if change == 'scope':
            proposed['scope'] = 'another-scope'
        if change == 'preflight':
            proposed['burden'] = 'invalid native shape'
        reply = dispatch('evolution_submit', {'candidate': proposed, 'observation_ids': selected, 'repair_of': 0})
        assert reply['status'] == 'rejected'
        expected = {'observations': 'evolution_repair_context_changed', 'scope': 'scope_conflict',
                    'preflight': 'original_native_preflight_rejected'}[change]
        assert expected in reply['reason']
        assert reply['remaining_candidate_evaluations'] == 1
        assert reply['remaining_candidate_repairs'] == {'0': 2}
        repaired = dispatch('evolution_submit', {'candidate': candidate(ids), 'observation_ids': ids, 'repair_of': 0})
        assert repaired['remaining_candidate_repairs'] == {'0': 1}
        dispatch('evolution_finish', {'reason': 'Original context and host preflight remain authoritative'})
        return {}
    run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'run')
    assert len(calls) == 2
