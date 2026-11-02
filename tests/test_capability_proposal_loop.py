"""Proposal orchestration diagnostics only; fake Harness never establishes real RSI."""
from contextlib import AbstractContextManager
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scenarios.remotion_edit.structured import run_capability_loop as pilot
from tests.test_capability_builder import setup


def inputs():
    snapshot, proposal = setup()
    task = {'id': 'two-stage-diagnostic', 'instruction': 'Build a reusable pipeline using current inputs.',
            'contract': copy.deepcopy(proposal['contract'])}
    catalog = {'programs': [{'description': 'Synthetic primitive, no task execution evidence'}]}
    return task, catalog, snapshot, proposal


class DiagnosticGate:
    current = None
    root = Path('/synthetic-private-ledger')
    def environment(self): return {'DIAGNOSTIC_ONLY': '1'}
    def costs(self, attempt):
        return {'request_ids': [123], 'provider_requests': 1, 'observed_model_usd': None,
                'billing_usd': None, 'ledger_ref': 'synthetic',
                'cumulative_requests': 123, 'cumulative_accounted_usd': 2.0}


def fake_harness(monkeypatch, answer, *, complete=True, during=None, notifications=False):
    captured = {}
    class Harness(AbstractContextManager):
        def __exit__(self, *args): return False
        def run(self, prompt, session_id, on_notification):
            captured['prompt'] = prompt
            if during: during()
            if notifications:
                for event in [
                    {'type': 'assistant/message', 'data': {'content': [{'type': 'text', 'text': answer}]}},
                    {'type': 'turn/end', 'data': {'reason': {'kind': 'completed'}}},
                ]:
                    on_notification(SimpleNamespace(method='session.event', payload={'sessionId': session_id, 'event': event}))
            return SimpleNamespace(final_response=answer, finish_reason='completed' if complete else 'failed')
    def factory(**kwargs): captured.update(kwargs); return Harness()
    monkeypatch.setattr(pilot, 'create_harness', factory)
    return captured


def test_preview_freezes_context_without_model_or_new_ledger(tmp_path, monkeypatch):
    task, catalog, snapshot, _ = inputs()
    monkeypatch.setattr(pilot, 'create_harness', lambda **kwargs: pytest.fail('preview called model'))
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'preview')
    assert result['status'] == 'preview' and not result['model_called']
    effective = pilot.read_json(tmp_path/'preview/effective.json')
    assert effective['max_tokens'] == 393216 and effective['reasoning_effort'] == 'off'
    assert effective['cap_usd'] is None and effective['max_requests'] is None and not effective['reset_history']
    assert not (tmp_path/'budget-checkpoint.json').exists()
    assert pilot.read_json(tmp_path/'preview/snapshot.json') == snapshot
    with pytest.raises(FileExistsError):
        pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'preview')


def test_one_harness_turn_compiles_candidate_but_does_not_certify(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal = inputs()
    observed = fake_harness(monkeypatch, json.dumps(proposal))
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'first', gate=DiagnosticGate())
    assert result['status'] == 'compiled_candidate'
    assert result['observed_model_usd'] is None and result['billing_usd'] is None
    assert observed['max_tokens'] == 393216 and observed['model'] == 'deepseek-flash'
    assert observed['patches'] == (str(pilot.PATCH),)
    candidate = pilot.read_json(tmp_path/'first/candidate.json')['capability']
    assert candidate['certification'] == 'candidate' and candidate['lifecycle'] == 'build_only'
    assert not result['publication_authorized'] and not result['reusability_verified']


def test_partial_and_malformed_answers_preserve_failed_attempts(tmp_path, monkeypatch):
    task, catalog, snapshot, _ = inputs()
    for name, complete in [('invalid-json', True), ('incomplete-turn', False)]:
        fake_harness(monkeypatch, 'private unfinished source text', complete=complete)
        result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/name, gate=DiagnosticGate())
        assert result['status'] == 'failed' and result['request_ids'] == [123]
        assert (tmp_path/name/'answer.txt').read_text() == 'private unfinished source text'
        assert 'private unfinished' not in result['error']
        assert not (tmp_path/name/'candidate.json').exists()
    rows = [json.loads(x) for x in (tmp_path/'attempt-registry.jsonl').read_text().splitlines()]
    assert [r['phase'] for r in rows] == ['registered', 'failed', 'registered', 'failed']


def test_compile_failure_then_explicit_repair_keeps_both_proposals(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal = inputs(); bad = copy.deepcopy(proposal)
    bad['steps'][0]['capability']['sha256'] = 'f'*64
    fake_harness(monkeypatch, json.dumps(bad))
    first = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'failed', gate=DiagnosticGate())
    assert first['status'] == 'failed' and (tmp_path/'failed/proposal.json').exists()
    observed = fake_harness(monkeypatch, json.dumps(proposal))
    second = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'repair',
        gate=DiagnosticGate(), repair_from=tmp_path/'failed', feedback={'scope': 'validation', 'reason': 'reference changed'})
    assert second['status'] == 'compiled_candidate' and second['parent_attempt_id'] == 'failed'
    assert 'reference changed' in observed['prompt']
    assert pilot.read_json(tmp_path/'failed/proposal.json') == bad
    changed = copy.deepcopy(task); changed['instruction'] += ' different task'
    with pytest.raises(ValueError, match='repair_context_changed'):
        pilot.propose_once(task=changed, catalog=catalog, snapshot=snapshot, output=tmp_path/'wrong-repair', repair_from=tmp_path/'failed')


def test_task_contract_cannot_be_weakened_by_proposal(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal = inputs(); proposal['contract']['output_schema'] = {}
    fake_harness(monkeypatch, json.dumps(proposal))
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'weak', gate=DiagnosticGate())
    assert result['error'] == 'proposal_task_contract_changed'


def test_context_is_defensively_frozen_during_model_call(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal = inputs()
    fake_harness(monkeypatch, json.dumps(proposal), during=lambda: snapshot.update(owner='mutated-caller'))
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'frozen', gate=DiagnosticGate())
    assert result['status'] == 'compiled_candidate'
    assert pilot.read_json(tmp_path/'frozen/snapshot.json')['owner'] == 'owner'


def test_native_turn_end_collector_retains_events(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal = inputs()
    fake_harness(monkeypatch, json.dumps(proposal), notifications=True)
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'events', gate=DiagnosticGate())
    assert result['status'] == 'compiled_candidate'
    assert len((tmp_path/'events/events.jsonl').read_text().splitlines()) == 2


def test_no_request_evidence_cannot_be_reported_as_real_compiled_candidate(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal = inputs(); fake_harness(monkeypatch, json.dumps(proposal))
    gate = DiagnosticGate()
    gate.costs = lambda attempt: {'request_ids': [], 'provider_requests': 0, 'observed_model_usd': None, 'billing_usd': None}
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'unwitnessed', gate=gate)
    assert result['status'] == 'compiled_without_request_evidence'


def test_duplicate_or_nonfinite_json_is_not_silently_repaired():
    for answer in ['{"a":1,"a":2}', '{"a":NaN}', '```json\n{}\n```']:
        with pytest.raises(ValueError): pilot.parse_proposal(answer)


def test_cumulative_gate_preserves_prior_spend_and_unknown_request(tmp_path, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic-not-a-real-key')
    with pytest.raises(ValueError, match='existing_cumulative_ledger_required'):
        with pilot.CumulativeProposalGate(tmp_path): pass
    pilot.write(tmp_path/'budget-checkpoint.json', {'request_count': 7, 'reserved_usd': 2.0})
    (tmp_path/'cost-ledger.jsonl').write_text('')
    attempt = tmp_path/'attempt'; attempt.mkdir()
    # Accounting test only: avoid opening a listener or sending any request.
    monkeypatch.setattr(pilot, 'create_server', lambda *args: SimpleNamespace(
        serve_forever=lambda: None, shutdown=lambda: None, server_close=lambda: None, server_port=0))
    with pilot.CumulativeProposalGate(tmp_path) as gate:
        gate.current = attempt
        payload = {'model': 'deepseek-flash', 'max_tokens': 393216, 'thinking': {'type': 'disabled'}, 'messages': []}
        booked = gate.state.book(json.dumps(payload).encode())  # No HTTP/upstream request.
        assert booked[0] == 8
        assert gate.state.reserved_usd > 2.0
        costs = gate.costs(attempt)
        assert costs['request_ids'] == [8] and costs['observed_model_usd'] is None
        assert pilot.read_json(attempt/'request-000008.json')['max_tokens'] == 393216
        payload['max_tokens'] = 6000
        with pytest.raises(ValueError, match='configuration_changed'): gate.state.book(json.dumps(payload).encode())
        assert gate.state.request_count == 8
    assert pilot.read_json(tmp_path/'budget-checkpoint.json')['request_count'] == 8


def test_cli_failure_is_nonzero_after_writing_summary(tmp_path, monkeypatch, capsys):
    task, catalog, snapshot, _ = inputs()
    for name, value in [('task',task), ('catalog',catalog), ('snapshot',snapshot)]:
        pilot.write(tmp_path/(name+'.json'), value)
    monkeypatch.setattr(pilot, 'ROOT', tmp_path)
    monkeypatch.setattr(pilot, 'propose_once', lambda **kwargs: {'status':'failed','error':'proposal_incomplete_model_turn'})
    monkeypatch.setattr(pilot.sys, 'argv', ['run_capability_loop.py',
        '--task', str(tmp_path/'task.json'), '--catalog', str(tmp_path/'catalog.json'),
        '--snapshot', str(tmp_path/'snapshot.json'), '--output', str(tmp_path/'.local/attempt'),
        '--ledger-root', str(tmp_path)])
    with pytest.raises(SystemExit) as error: pilot.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'failed'


def test_compile_feedback_points_to_missing_binding_wrapper():
    _,_,snapshot,proposal=inputs()
    proposal['steps'][0]['arguments']={'value':{'kind':'input','path':['value']}}
    with pytest.raises(ValueError) as failure:
        pilot.compile_proposal(proposal,snapshot,snapshot['owner'])
    diagnostic=pilot.proposal_diagnostics(failure.value,proposal)
    assert diagnostic['issues'][0]['path']==['steps',0,'arguments']
    assert 'kind=object' in diagnostic['issues'][0]['expected']


def test_json_feedback_has_location_without_rewriting_candidate():
    import json
    with pytest.raises(json.JSONDecodeError) as failure:pilot.parse_proposal('not JSON')
    diagnostic=pilot.proposal_diagnostics(failure.value,None)
    assert diagnostic['kind']=='json_syntax' and diagnostic['line']==1
