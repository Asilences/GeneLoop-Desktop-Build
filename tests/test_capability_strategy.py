"""Deterministic policy admission checks; no empirical strategy gains implied."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.capability_contract import create_capability_snapshot
from src.adapters.capability_feedback import file_ref, CapabilityFeedback
from src.adapters.capability_strategy import (
    create_strategy, validate_strategy, strategy_ref, admit_strategy, strategy_context,
)
from tests.test_capability_feedback import fixture


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


@pytest.fixture
def policy(tmp_path):
    feedback, library, evidence, _ = fixture(tmp_path)
    snapshot = library['snapshot']
    definition = {'owner': 'owner', 'target': 'construction', 'scope': 'paper',
                  'applicability': 'When independent tasks repeat the same conversion.',
                  'decision_policy': 'Compare existing interfaces before proposing a new conversion.',
                  'capability_refs': [snapshot['roots'][0]], 'evidence': [evidence], 'parent': None}
    strategy = create_strategy(definition, snapshot)
    reference = put(tmp_path / 'strategy.json', strategy)
    training = put(tmp_path / 'training.json', {'source': 'training'})
    heldout = put(tmp_path / 'heldout.json', {'source': 'heldout'})
    verdict = {'passed': True, 'checks': [{'id': 'independent-quality', 'status': 'passed'}],
               'training_sources': [training], 'heldout_sources': [heldout], 'evidence': [heldout]}
    return feedback, snapshot, strategy, reference, verdict


def admit(tmp_path, policy, verdict=None):
    feedback, snapshot, _, reference, default = policy
    return admit_strategy(reference, snapshot, target='construction', scope='paper',
                          evaluate=lambda candidate: copy.deepcopy(default if verdict is None else verdict),
                          directory=tmp_path / 'admission', feedback=feedback)


def test_admitted_context_keeps_policy_and_certified_references_bounded(tmp_path, policy):
    feedback, snapshot, strategy, reference, _ = policy
    selection = admit(tmp_path, policy)
    context = strategy_context(selection, snapshot, target='construction', scope='paper', feedback=feedback)
    assert context['strategy'] == strategy_ref(strategy)
    assert context['decision_policy'] == strategy['decision_policy']
    assert context['capability_refs'] == strategy['capability_refs']
    assert context['selection']['strategy'] == reference
    assert 'implementation' not in json.dumps(context)
    assert all(fact['cost'] is None and fact['benefit'] is None for fact in feedback.read()['facts'].values())


def test_actual_feedback_withdrawal_blocks_inheritance(tmp_path, policy):
    feedback, snapshot, strategy, reference, _ = policy
    selection = admit(tmp_path, policy)
    feedback.withdraw(strategy_ref(strategy), 'counterexample', reference)
    with pytest.raises(ValueError, match='strategy_withdrawn'):
        strategy_context(selection, snapshot, target='construction', scope='paper', feedback=feedback)


@pytest.mark.parametrize('field,value,error', [
    ('scope', 'other', 'scope_changed'), ('target', 'task', 'target_changed'),
    ('owner', 'foreign', 'owner_changed'), ('decision_policy', 'tampered', 'identity_changed'),
])
def test_policy_identity_and_scope_are_rechecked(tmp_path, policy, field, value, error):
    feedback, snapshot, strategy, _, _ = policy
    if field in ('target', 'scope', 'owner'):
        kwargs = {field: value}
        if field == 'owner':
            with pytest.raises(ValueError, match='foreign_owner'):
                validate_strategy(strategy, snapshot, **kwargs)
            return
        with pytest.raises(ValueError, match=error):
            validate_strategy(strategy, snapshot, **kwargs)
    else:
        strategy[field] = value
        with pytest.raises(ValueError, match=error):
            validate_strategy(strategy, snapshot)


def test_unverified_selection_and_candidate_self_certification_rejected(tmp_path, policy):
    feedback, snapshot, strategy, reference, _ = policy
    selection = admit(tmp_path, policy)
    other_feedback = CapabilityFeedback(tmp_path / 'other-feedback', 'owner')
    with pytest.raises(ValueError, match='host_admission_required'):
        strategy_context(selection, snapshot, target='construction', scope='paper', feedback=other_feedback)
    strategy['certification'] = 'certified'
    with pytest.raises(ValueError, match='shape_invalid'):
        validate_strategy(strategy, snapshot)


def test_changed_source_or_receipt_rejected(tmp_path, policy):
    feedback, snapshot, _, reference, _ = policy
    selection = admit(tmp_path, policy)
    Path(selection['evaluation']['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='feedback_evidence_changed'):
        strategy_context(selection, snapshot, target='construction', scope='paper', feedback=feedback)
    Path(reference['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='feedback_evidence_changed'):
        strategy_context(selection, snapshot, target='construction', scope='paper', feedback=feedback)


def test_independent_evaluation_rejects_same_bytes_with_different_path(tmp_path, policy):
    verdict = copy.deepcopy(policy[-1])
    reference = verdict['training_sources'][0]
    alias = tmp_path / 'renamed-input.json'
    alias.write_bytes(Path(reference['path']).read_bytes())
    verdict['heldout_sources'] = [file_ref(alias)]
    with pytest.raises(ValueError, match='heldout_overlap'):
        admit(tmp_path, policy, verdict)
    assert not policy[0].read()['facts']


def test_dependency_rejection_and_lifecycle_change_block_inheritance(tmp_path, policy):
    feedback, snapshot, _, _, _ = policy
    selection = admit(tmp_path, policy)
    for state in ('candidate', 'rejected'):
        changed = copy.deepcopy(snapshot['capabilities'])
        changed[0]['certification'] = state
        current = create_capability_snapshot('owner', snapshot['roots'], changed)
        with pytest.raises(ValueError, match='dependency_unavailable'):
            strategy_context(selection, current, target='construction', scope='paper', feedback=feedback)


@pytest.mark.parametrize('change', ['failed', 'empty', 'unknown'])
def test_failed_or_unknown_evaluation_never_admits(tmp_path, policy, change):
    verdict = copy.deepcopy(policy[-1])
    if change == 'failed': verdict['passed'] = False
    if change == 'empty': verdict['checks'] = []
    if change == 'unknown': verdict['checks'][0]['status'] = 'unknown'
    with pytest.raises(ValueError, match='evaluation_failed'):
        admit(tmp_path, policy, verdict)
    assert not policy[0].read()['facts']


def test_parent_version_is_bound_and_current_scope_matches(tmp_path, policy):
    _, snapshot, original, reference, _ = policy
    definition = {key: copy.deepcopy(original[key]) for key in
                  ('owner', 'target', 'scope', 'applicability', 'decision_policy', 'capability_refs', 'evidence', 'parent')}
    definition['parent'] = reference
    definition['decision_policy'] += ' Keep counterexamples in the next proposal.'
    child = create_strategy(definition, snapshot)
    assert child['id'] != original['id']
    Path(reference['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='feedback_evidence_changed'):
        validate_strategy(child, snapshot)


def test_dependency_feedback_withdrawal_blocks_context(tmp_path, policy):
    feedback, snapshot, strategy, reference, _ = policy
    selection = admit(tmp_path, policy)
    feedback.withdraw(strategy['capability_refs'][0], 'native_certificate_revoked', reference)
    with pytest.raises(ValueError, match='dependency_withdrawn'):
        strategy_context(selection, snapshot, target='construction', scope='paper', feedback=feedback)


def test_discovery_evidence_cannot_be_an_independent_heldout(tmp_path, policy):
    verdict = copy.deepcopy(policy[-1])
    verdict['heldout_sources'] = policy[2]['evidence']
    with pytest.raises(ValueError, match='discovery_heldout_overlap'):
        admit(tmp_path, policy, verdict)
