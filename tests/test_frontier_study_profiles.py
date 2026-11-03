"""Creation-value exposures and execution order are frozen before any results."""
import copy
from collections import Counter

import pytest

from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability, create_capability_snapshot, capability_ref
from scenarios.paper_proofreading.frontier.study_profiles import balanced_order, creation_value_profile
from tests.test_capability_builder import RECORD, setup


def material():
    seed, _ = setup()
    a, b = seed['capabilities']
    definition = {key: copy.deepcopy(a[key]) for key in ('owner', 'contract', 'implementation', 'dependencies')}
    definition['implementation']['legacy_ref']['object_id'] = 'relation-J'
    j = create_capability(definition, {'certification': 'certified', 'lifecycle': 'active'})
    base = [capability_ref(a), capability_ref(b)]
    jref = capability_ref(j)
    flat = create_capability_snapshot(seed['owner'], [*base, jref], [a, b, j])
    proposal = {'format': 'capability_compose_proposal_v1', 'owner': seed['owner'],
        'contract': {'input_schema': RECORD, 'output_schema': RECORD, 'effects': ['read']},
        'steps': [{'id': 'PRIVATE_IMPLEMENTATION_STEP', 'capability': jref, 'arguments': {'kind': 'input', 'path': []}}],
        'output': {'kind': 'step', 'step_id': 'PRIVATE_IMPLEMENTATION_STEP', 'path': []}}
    c = compile_proposal(proposal, flat, seed['owner'])['capability']
    c = {**c, 'lifecycle': 'active', 'certification': 'certified'}
    cref = capability_ref(c)
    hierarchical = create_capability_snapshot(seed['owner'], [*base, jref, cref], [a, b, j, c])
    return hierarchical, cref, base, jref


def test_description_is_information_only_and_lower_materials_match():
    args = material();original = copy.deepcopy(args)
    result = creation_value_profile(*args, 'Public callable behavior and validation scope')
    snapshots = result['snapshots'];cards = result['reference_interfaces']
    assert snapshots['flat_without_C'] == snapshots['description_only_C']
    assert snapshots['flat_without_C'] is not snapshots['description_only_C']
    assert cards['description_only_C'] == cards['hierarchical_with_C']
    assert cards['description_only_C'] is not cards['hierarchical_with_C']
    assert cards['flat_without_C'] == []
    c = args[1]
    assert c not in snapshots['description_only_C']['roots']
    assert c not in snapshots['flat_without_C']['roots']
    assert c in snapshots['hierarchical_with_C']['roots']
    assert not any(row['id'] == c['id'] for row in snapshots['description_only_C']['capabilities'])
    card = cards['description_only_C'][0]
    assert set(card) == {'format', 'reference', 'contract', 'description', 'scope'}
    assert 'alias' not in card and 'implementation' not in card and 'dependencies' not in card
    assert 'PRIVATE_IMPLEMENTATION_STEP' not in repr(card)
    assert args == original


def test_description_cannot_authorize_the_omitted_C_reference():
    snapshot, cref, base, jref = material()
    profile = creation_value_profile(snapshot, cref, base, jref, 'Public C interface')
    proposal = {'format': 'capability_compose_proposal_v1', 'owner': snapshot['owner'],
        'contract': {'input_schema': RECORD, 'output_schema': RECORD, 'effects': ['read']},
        'steps': [{'id': 'call', 'capability': cref, 'arguments': {'kind': 'input', 'path': []}}],
        'output': {'kind': 'step', 'step_id': 'call', 'path': []}}
    with pytest.raises(ValueError, match='reference_not_visible'):
        compile_proposal(proposal, profile['snapshots']['description_only_C'], snapshot['owner'])
    assert compile_proposal(proposal, profile['snapshots']['hierarchical_with_C'], snapshot['owner'])


@pytest.mark.parametrize('which', ['C', 'base', 'J'])
def test_wrong_version_reference_is_rejected(which):
    snapshot, cref, base, jref = material()
    target = {'C': cref, 'base': base[0], 'J': jref}[which]
    target['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='reference_not_visible'):
        creation_value_profile(snapshot, cref, base, jref, 'C interface')


def test_duplicates_or_uncertified_C_are_rejected():
    snapshot, cref, base, jref = material()
    with pytest.raises(ValueError, match='not_distinct'):
        creation_value_profile(snapshot, cref, [*base, jref], jref, 'C interface')
    for row in snapshot['capabilities']:
        if row['id'] == cref['id']:
            row['certification'] = 'candidate'
    # Lifecycle metadata is part of snapshot identity, so re-freeze after the deliberate change.
    changed = create_capability_snapshot(snapshot['owner'], snapshot['roots'], snapshot['capabilities'])
    with pytest.raises(ValueError, match='not_active_certified'):
        creation_value_profile(changed, cref, base, jref, 'C interface')


def test_C_cannot_add_unmatched_hidden_material_to_the_treatment():
    snapshot, cref, base, jref = material()
    lower = [row for row in snapshot['capabilities'] if row['id'] != cref['id']]
    definition = {key: copy.deepcopy(lower[0][key]) for key in ('owner', 'contract', 'implementation', 'dependencies')}
    definition['implementation']['legacy_ref']['object_id'] = 'unshared-hidden-material'
    hidden = create_capability(definition, {'certification': 'certified', 'lifecycle': 'active'})
    construction = create_capability_snapshot(snapshot['owner'], [*base, jref, capability_ref(hidden)], [*lower, hidden])
    proposal = {'format': 'capability_compose_proposal_v1', 'owner': snapshot['owner'],
        'contract': {'input_schema': RECORD, 'output_schema': RECORD, 'effects': ['read']},
        'steps': [{'id': 'hidden', 'capability': capability_ref(hidden), 'arguments': {'kind': 'input', 'path': []}}],
        'output': {'kind': 'step', 'step_id': 'hidden', 'path': []}}
    c = {**compile_proposal(proposal, construction, snapshot['owner'])['capability'],
         'lifecycle': 'active', 'certification': 'certified'}
    full = create_capability_snapshot(snapshot['owner'], [*base, jref, capability_ref(c)], [*lower, hidden, c])
    with pytest.raises(ValueError, match='unmatched_C_dependencies'):
        creation_value_profile(full, capability_ref(c), base, jref, 'Public interface only')


def test_six_replicates_are_position_balanced_and_have_no_missing_cells():
    arms = ['flat_without_C', 'description_only_C', 'hierarchical_with_C']
    order = balanced_order(arms)
    assert len(order) == 18 and len(set(order)) == 18
    assert set(order) == {(arm, replicate) for replicate in range(6) for arm in arms}
    positions = {arm: Counter() for arm in arms}
    for replicate in range(6):
        row = order[replicate * 3:(replicate + 1) * 3]
        assert {pair[1] for pair in row} == {replicate}
        for position, (arm, _) in enumerate(row):
            positions[arm][position] += 1
    assert all(dict(counts) == {0: 2, 1: 2, 2: 2} for counts in positions.values())
    assert [arm for arm, _ in order[9:12]] == list(reversed(arms))
    assert order == balanced_order(arms, 6)


@pytest.mark.parametrize('arms,reps', [(['a', 'a'], 6), (['a'], 6), ('abc', 6),
    (['a', 'b'], True), (['a', 'b'], 0), (['a', 'b'], -1), (['a', 'bad/name'], 6)])
def test_order_rejects_ambiguous_or_invalid_configuration(arms, reps):
    with pytest.raises(ValueError, match='profile_'):
        balanced_order(arms, reps)
