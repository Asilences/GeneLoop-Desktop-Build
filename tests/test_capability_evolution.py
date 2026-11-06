"""RAE feedback mechanism diagnostics; fixtures do not prove empirical gains."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.capability_contract import capability_ref
from src.adapters.capability_evolution import (
    evolve_abstraction, propose_evolution_boundary, record_measured_effect, record_relation, value_context,
)
from src.adapters.capability_feedback import CapabilityFeedback, file_ref
from tests.test_capability_feedback import fixture
from tests.test_efficiency_rsi_measurement import example, refresh


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


def test_disabled_evolution_does_not_read_or_create_evidence(tmp_path):
    result = evolve_abstraction([], [], {}, feedback=None, prior_candidate=None,
                                proposal=None, directory=tmp_path / 'unused')
    assert result['status'] == 'disabled' and result['budget_credit'] is None
    assert not (tmp_path / 'unused').exists()


@pytest.mark.parametrize('failure,message', [
    ('malformed', 'evolution_training_proposal_invalid'),
    ('irrelevant', 'evolution_relevant_feedback_required'),
    ('prior_changed', 'evidence_changed'),
    ('feedback_changed', 'evolution_feedback_changed'),
])
def test_boundary_response_validation_preserves_failure(tmp_path, failure, message):
    manager, library, source, _ = fixture(tmp_path)
    cap = library['snapshot']['capabilities'][0]
    subject = capability_ref(cap)
    prior = put(tmp_path / 'prior.json', {'capability': cap})
    def proposer(request):
        if failure == 'prior_changed':
            Path(prior['path']).write_text('{}', encoding='utf-8')
        if failure == 'feedback_changed':
            manager.observe(stage='execution', subject=subject, scope='diagnostic',
                            status='failed', cost=None, evidence=[source])
        return {} if failure == 'malformed' else {'feedback_ids': ['absent'], 'regions': {}}
    directory = tmp_path / 'boundary'
    with pytest.raises(ValueError, match=message):
        propose_evolution_boundary([], feedback=manager, prior_candidate=prior, scope='diagnostic',
                                   proposer=proposer, directory=directory, enabled=True)
    saved = json.loads((directory / 'failure.json').read_bytes())
    assert saved['status'] == 'failed' and message in saved['error']
    assert (directory / 'request.json').is_file() and (directory / 'response.json').is_file()
    assert not (directory / 'result.json').exists()


@pytest.mark.parametrize('relation', ['proposed_parent', 'material_read'])
def test_proposed_or_read_material_is_not_successful_construction_credit(tmp_path, relation):
    manager, library, source, _ = fixture(tmp_path)
    a, b = sorted(library['snapshot']['roots'], key=lambda row: row['id'])
    witness = put(tmp_path / 'witness.json', {'owner': 'owner', 'relation': relation,
        'subject': b, 'beneficiary': a, 'scope': 'study', 'status': 'passed', 'sources': [source]})
    identity = record_relation(manager, relation=relation, subject=b, beneficiary=a,
                               scope='study', evidence=witness)
    assert manager.order([a, b], 'construction')[0] == a
    assert manager.read()['facts'][identity]['relation'] == relation
    context = value_context(manager, b, 'study')
    assert identity in context['creation'] and context['execution'] == {}
    assert context['budget_credit'] is None and context['total_economic_benefit'] is None


def test_relation_requires_original_compile_or_runtime_witness(tmp_path):
    manager, library, source, proposal = fixture(tmp_path)
    a, b = library['snapshot']['roots']
    for relation, message in [('compile_ref', 'compile_dependency_not_observed'),
                              ('runtime_call', 'runtime_call_not_observed')]:
        witness = put(tmp_path / (relation + '.json'), {'owner': 'owner', 'relation': relation,
            'subject': a, 'beneficiary': b, 'scope': 'study', 'status': 'passed', 'sources': [source]})
        with pytest.raises(ValueError, match=message):
            record_relation(manager, relation=relation, subject=a, beneficiary=b, scope='study', evidence=witness)
    from src.adapters.capability_builder import compile_proposal
    candidate = compile_proposal(proposal, library['snapshot'], 'owner')
    compiled = put(tmp_path / 'compiled.json', candidate)
    beneficiary = capability_ref(candidate['capability'])
    witness = put(tmp_path / 'compile-witness.json', {'owner': 'owner', 'relation': 'compile_ref',
        'subject': a, 'beneficiary': beneficiary, 'scope': 'study', 'status': 'passed', 'sources': [compiled]})
    identity = record_relation(manager, relation='compile_ref', subject=a, beneficiary=beneficiary,
                               scope='study', evidence=witness)
    assert manager.read()['facts'][identity]['benefit'] is None
    with pytest.raises(ValueError, match='binding_changed'):
        record_relation(manager, relation='compile_ref', subject=b, beneficiary=beneficiary,
                        scope='study', evidence=witness)


def measured_fixture(tmp_path, dimension='creation'):
    manager, library, _, _ = fixture(tmp_path)
    subject = library['snapshot']['roots'][0]
    x = list(example(tmp_path))
    key = 'build' if dimension == 'creation' else 'execution'
    phase = 'construction' if dimension == 'creation' else 'execution'
    x[0]['arms'][1][key + '_capabilities'] = [subject]
    x[0]['arms'][1][key + '_snapshot_sha256'] = library['snapshot']['digest']
    for cell in x[0]['cells']:
        cell['phase'] = phase
    x[1]['attempts'][1][key + '_capabilities'] = [subject]
    x[1]['attempts'][1][key + '_snapshot_sha256'] = library['snapshot']['digest']
    refresh(x)
    return manager, subject, x


def record_measurement(tmp_path, manager, subject, x, dimension='creation'):
    refs = [put(tmp_path / (name + '.json'), value) for name, value in zip(('plan', 'observations', 'registry'), x)]
    return record_measured_effect(manager, subject=subject, scope='matched-study', dimension=dimension,
        candidate_arm='candidate', plan_ref=refs[0], observations_ref=refs[1], registry_ref=refs[2],
        evidence_root=tmp_path, directory=tmp_path / 'measurement')


@pytest.mark.parametrize('dimension', ['execution', 'creation'])
def test_measured_value_uses_original_full_accounting_and_separate_dimension(tmp_path, dimension):
    manager, subject, x = measured_fixture(tmp_path, dimension)
    identity = record_measurement(tmp_path, manager, subject, x, dimension)
    row = manager.read()['facts'][identity]
    assert row['relation'] == 'measured_causal_effect' and row['value_dimension'] == dimension
    assert row['comparisons'][0]['conditional_cost_saving_usd'] == pytest.approx(.2)
    assert row['budget_credit'] is None and row['benefit'] is None and row['total_economic_benefit'] is None
    # Changed independent quality data cannot keep an old apparently valid fact.
    (tmp_path / 'candidate.txt').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence_changed'):
        manager.read()


def test_unknown_cost_preserves_unresolved_effect_and_no_budget(tmp_path):
    manager, subject, x = measured_fixture(tmp_path)
    x[1]['providers'][1]['observed_peak_usd'] = None
    identity = record_measurement(tmp_path, manager, subject, x)
    row = manager.read()['facts'][identity]
    assert row['status'] == 'unknown' and row['cost'] is None
    assert row['comparisons'][0]['category'] == 'unresolved'
    assert row['comparisons'][0]['conditional_cost_saving_usd'] is None
    assert row['budget_credit'] is None


def test_unrelated_arms_or_missing_failed_requests_cannot_claim_measured_effect(tmp_path):
    manager, subject, x = measured_fixture(tmp_path)
    changed = copy.deepcopy(x)
    changed[0]['arms'][0]['execution_snapshot_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='single_capability_contrast_required'):
        record_measurement(tmp_path, manager, subject, changed)
    x[1]['attempts'].pop()
    with pytest.raises(ValueError, match='attempt_inventory_incomplete'):
        record_measurement(tmp_path, manager, subject, x)


def test_model_label_cannot_award_measured_effect(tmp_path):
    manager, library, evidence, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match='requires_witness_or_measurement'):
        manager.observe(stage='construction', relation='measured_causal_effect',
                        subject=library['snapshot']['roots'][0], scope='study', status='passed', evidence=[evidence])
    with pytest.raises(ValueError, match='requires_independent_measurement'):
        record_relation(manager, relation='measured_causal_effect', subject=library['snapshot']['roots'][0],
                        beneficiary=None, scope='study', evidence=evidence)


def test_known_foreign_owner_cannot_be_imported_as_local_relation(tmp_path):
    manager, library, _, _ = fixture(tmp_path)
    a, b = library['snapshot']['roots']
    foreign = put(tmp_path / 'foreign.json', {'owner': 'someone-else', 'materials': [a]})
    witness = put(tmp_path / 'read.json', {'owner': 'owner', 'relation': 'material_read',
        'subject': a, 'beneficiary': b, 'scope': 'study', 'status': 'passed', 'sources': [foreign]})
    with pytest.raises(ValueError, match='owner_changed'):
        record_relation(manager, relation='material_read', subject=a, beneficiary=b, scope='study', evidence=witness)
