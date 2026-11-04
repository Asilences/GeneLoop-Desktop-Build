"""Deterministic Builder policy exposure and revocation, zero real model calls."""
import copy
import json

import pytest

from src.adapters import capability_proposal as pilot
from src.adapters.capability_construction_history import capture, build_history
from src.adapters.capability_feedback import file_ref
from src.adapters.capability_strategy import create_strategy, admit_strategy, strategy_ref
from tests.test_capability_feedback import fixture
from tests.test_capability_proposal_loop import DiagnosticGate, fake_harness


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


def configured(tmp_path):
    feedback, library, evidence, proposal = fixture(tmp_path)
    snapshot = library['snapshot']
    task = {'id': 'policy-diagnostic', 'instruction': 'Construct the requested pipeline.',
            'contract': copy.deepcopy(proposal['contract'])}
    strategy = create_strategy({'owner': 'owner', 'target': 'construction', 'scope': 'paper',
        'applicability': 'When a task needs two established operations.',
        'decision_policy': 'Check compatible existing interfaces before choosing an implementation.',
        'capability_refs': [snapshot['roots'][0]], 'evidence': [evidence], 'parent': None}, snapshot)
    reference = put(tmp_path / 'strategy.json', strategy)
    train = put(tmp_path / 'train.json', {'input': 'diagnostic training'})
    heldout = put(tmp_path / 'heldout.json', {'input': 'independent diagnostic'})
    selection = admit_strategy(reference, snapshot, target='construction', scope='paper',
        evaluate=lambda candidate: {'passed': True, 'checks': [{'id': 'host-quality', 'status': 'passed'}],
            'training_sources': [train], 'heldout_sources': [heldout], 'evidence': [heldout]},
        directory=tmp_path / 'admission', feedback=feedback)
    catalog = {'source_catalog': {'inherited_strategy': {'enabled': True, 'selection': selection,
        'scope': 'paper', 'feedback_directory': str(tmp_path / 'feedback')}}}
    return task, catalog, snapshot, proposal, feedback, strategy, selection


def test_disabled_policy_does_not_read_selection_or_change_prompt(tmp_path):
    task, catalog, snapshot, *_ = configured(tmp_path)
    catalog['source_catalog']['inherited_strategy'] = {'enabled': False, 'selection': {'path': '/missing'}}
    disabled, prompt = pilot.prepare_attempt(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'disabled')
    plain, ordinary = pilot.prepare_attempt(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'plain')
    assert disabled['inherited_strategy'] is None and plain['inherited_strategy'] is None
    assert prompt == ordinary


def test_actual_builder_prompt_records_admitted_policy_with_current_aliases(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal, _, strategy, selection = configured(tmp_path)
    observed = fake_harness(monkeypatch, json.dumps(proposal))
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot,
                               output=tmp_path/'attempt', gate=DiagnosticGate())
    assert result['status'] == 'compiled_candidate'
    assert strategy['decision_policy'] in observed['prompt']
    visible = json.loads(observed['prompt'].split('Frozen task and construction evidence:\n', 1)[1])
    assert visible['inherited_strategy']['capability_aliases']
    effective = pilot.read_json(tmp_path/'attempt/effective.json')
    assert effective['inherited_strategy']['selection'] == selection
    assert result['strategy_observation'] == 'prompt_exposure_only'
    assert result['inherited_strategy']['strategy'] == strategy_ref(strategy)
    compiled = pilot.read_json(tmp_path/'attempt/candidate.json')
    assert sorted(compiled['capability']['dependencies'], key=lambda ref: ref['id']) == sorted(
        [step['capability'] for step in proposal['steps']], key=lambda ref: ref['id'])
    assert not result['publication_authorized']


def test_policy_reference_is_retained_in_existing_construction_history(tmp_path):
    task, catalog, snapshot, *_ = configured(tmp_path)
    output = tmp_path/'preview'
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=output)
    task_ref = put(tmp_path/'task.json', task)
    evidence = capture({'id': task['id'], 'task': task_ref}, output, snapshot)
    history = build_history([evidence], task_ref)
    assert history['attempts'][0]['inherited_strategy'] == result['inherited_strategy']
    assert history['attempts'][0]['strategy_observation'] == 'prompt_prepared_only'
    assert history['attempts'][0]['actual_dependencies'] is None


def test_repair_freezes_policy_selection_and_disabled_state(tmp_path):
    task, catalog, snapshot, *_ = configured(tmp_path)
    pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'first')
    changed = copy.deepcopy(catalog)
    changed['source_catalog']['inherited_strategy']['enabled'] = False
    with pytest.raises(ValueError, match='repair_inherited_strategy_changed'):
        pilot.prepare_attempt(task=task, catalog=changed, snapshot=snapshot, output=tmp_path/'repair',
                              repair_from=tmp_path/'first')


def test_wrong_scope_is_rejected_before_model_dispatch(tmp_path, monkeypatch):
    task, catalog, snapshot, *_ = configured(tmp_path)
    catalog['source_catalog']['inherited_strategy']['scope'] = 'other'
    monkeypatch.setattr(pilot, 'create_harness', lambda **kwargs: pytest.fail('model called'))
    with pytest.raises(ValueError, match='scope_changed'):
        pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot, output=tmp_path/'attempt', gate=DiagnosticGate())


def test_withdrawal_during_turn_prevents_candidate_compilation(tmp_path, monkeypatch):
    task, catalog, snapshot, proposal, feedback, strategy, selection = configured(tmp_path)
    fake_harness(monkeypatch, json.dumps(proposal), during=lambda: feedback.withdraw(
        strategy_ref(strategy), 'diagnostic counterexample', selection['strategy']))
    result = pilot.propose_once(task=task, catalog=catalog, snapshot=snapshot,
                               output=tmp_path/'attempt', gate=DiagnosticGate())
    assert result['status'] == 'failed' and 'strategy_withdrawn' in result['error']
    assert not (tmp_path/'attempt/candidate.json').exists()
    assert (tmp_path/'attempt/answer.txt').exists()
    assert result['request_ids'] == [123]
