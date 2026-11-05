"""Input projection and original Store catalog diagnostics, no model requests.

Injected material execution here checks dispatch only. No fabricated backend
certificate is passed to Store.publish. Native publication needs real Script
libraries and original task call receipts supplied by the research host.
"""
import copy
import json

import pytest

from src.adapters.benchmark_capability_publication import (
    learning_dependency_snapshot, original_store_catalog, prepare_recursive_publication,
    prepare_witnessed_case, publish_recursive_candidate,
)
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import capability_ref, create_capability_snapshot
from src.adapters.capability_feedback import verify
from tests.test_benchmark_script_materials import data, acquire
from tests.test_capability_motif_learning import corpus, call_trace, put


def projected():
    one = {'id': 'first', 'sha256': 'a' * 64}
    two = {'id': 'second', 'sha256': 'b' * 64}
    candidate = {'proposal': {
        'contract': {'input_schema': {'type': 'object', 'properties': {
            'p0_value': {'type': 'integer'}, 'p1_extra': {'type': 'string'}},
            'required': ['p0_value', 'p1_extra'], 'additionalProperties': False}},
        'steps': [{'id': 'call0', 'capability': one, 'arguments': {'kind': 'object', 'fields': {
            'value': {'kind': 'input', 'path': ['p0_value']}}}},
            {'id': 'call1', 'capability': two, 'arguments': {'kind': 'object', 'fields': {
                'value': {'kind': 'step', 'step_id': 'call0', 'path': ['value']},
                'extra': {'kind': 'input', 'path': ['p1_extra']}}}}],
        'output': {'kind': 'step', 'step_id': 'call1', 'path': []}},
        'provenance': {'source_input_bindings': [
            {'input_name': 'p0_value', 'step_index': 0, 'capability': one, 'argument_path': ['value']},
            {'input_name': 'p1_extra', 'step_index': 1, 'capability': two, 'argument_path': ['extra']}]}}
    trace = {'task_id': 'heldout', 'task_fingerprint': 'original-input', 'digest': 'c' * 64,
        'steps': [{'capability': one, 'arguments': {'value': 4}, 'result': {'value': 5},
                   'receipt_ref': {'path': '/original/one.json', 'sha256': 'd' * 64}},
                  {'capability': two, 'arguments': {'value': 5, 'extra': 'current'},
                   'result': {'answer': 'current-5'},
                   'receipt_ref': {'path': '/original/two.json', 'sha256': 'e' * 64}}]}
    return candidate, trace


def test_heldout_arguments_and_expected_result_come_from_explicit_original_bindings():
    candidate, trace = projected()
    result = prepare_witnessed_case(candidate, trace)
    assert result['input'] == {'p0_value': 4, 'p1_extra': 'current'}
    assert result['expected_result'] == {'answer': 'current-5'}
    assert result['source_executions'] == [step['receipt_ref'] for step in trace['steps']]
    result['expected_result']['answer'] = 'changed copy'
    assert trace['steps'][-1]['result']['answer'] == 'current-5'


def test_changed_parameter_flow_is_rejected_before_store():
    candidate, trace = projected()
    trace['steps'][1]['arguments']['value'] = 7
    with pytest.raises(ValueError, match='observed_arguments_changed'):
        prepare_witnessed_case(candidate, trace)


def test_repeated_matching_call_region_requires_explicit_disambiguation():
    candidate, trace = projected()
    trace['steps'] += copy.deepcopy(trace['steps'])
    with pytest.raises(ValueError, match='unique_observed_occurrence'):
        prepare_witnessed_case(candidate, trace)


def test_projection_cannot_change_referenced_capability():
    candidate, trace = projected()
    candidate = copy.deepcopy(candidate)
    candidate['provenance']['source_input_bindings'][0]['capability']['id'] = 'foreign'
    with pytest.raises(ValueError):
        prepare_witnessed_case(candidate, trace)


def test_absent_store_keeps_empty_seed_without_materializing_another_registry(tmp_path):
    seed = create_capability_snapshot('owner', [], [])
    directory = tmp_path / 'store'
    result = original_store_catalog(seed, directory)
    assert result['snapshot'] == seed and result['head'] is None
    assert not directory.exists()


def test_existing_empty_original_store_is_readable_with_empty_seed(tmp_path):
    seed = create_capability_snapshot('owner', [], [])
    directory = tmp_path / 'store'
    directory.mkdir()
    result = original_store_catalog(seed, directory)
    assert result['snapshot'] == seed
    assert result['head'] is None and result['catalog'] == []


def test_bad_learning_evidence_stays_pending_and_retains_request(tmp_path):
    class Materials:
        owner = 'owner'
        def catalog(self):
            return {'snapshot': create_capability_snapshot('owner', [], []), 'libraries': []}
    result = publish_recursive_candidate({}, [{'path': str(tmp_path / 'missing'), 'sha256': 'a' * 64}],
        materials=Materials(), output=tmp_path / 'publication')
    assert result['status'] == 'pending'
    assert result['model_requests'] == 0
    assert result['followup'] == 'pending_independent_task_consumption'
    assert (tmp_path / 'publication/request.json').exists()
    assert json.loads((tmp_path / 'publication/result.json').read_text())['reason']


def test_exact_argument_execution_reuses_original_native_route_without_wrapping(tmp_path, data):
    service, _, _, _, calls = data
    learned = acquire(data)
    value = {'value': {'data': {'items': [1, 2]}}}
    result = service.execute_arguments(learned['value_refs'][0], value, tmp_path / 'exact', 'next')
    assert result['arguments'] == value
    assert calls['execute'][0]['args'] == value
    assert calls['execute'][0]['inputs'] == []
    assert json.loads((tmp_path / 'exact/input-provenance.json').read_text())['encoding'] == 'explicit_capability_arguments'


def test_composition_slots_are_not_misclassified_as_leaf_paths(tmp_path, data):
    service, _, _, _, calls = data
    learned = acquire(data)
    seed = learned['snapshot']
    leaf_ref = learned['value_refs'][0]
    leaf = next(cap for cap in seed['capabilities'] if capability_ref(cap) == leaf_ref)
    compiled = compile_proposal({'format': 'capability_compose_proposal_v1', 'owner': service.owner,
        'contract': {'input_schema': {'type': 'object', 'properties': {
            'p0_value': copy.deepcopy(leaf['contract']['input_schema']['properties']['value'])},
            'required': ['p0_value'], 'additionalProperties': False},
            'output_schema': copy.deepcopy(leaf['contract']['output_schema']), 'effects': ['read']},
        'steps': [{'id': 'first', 'capability': leaf_ref, 'arguments': {'kind': 'object', 'fields': {
            'value': {'kind': 'input', 'path': ['p0_value']}}}}],
        'output': {'kind': 'step', 'step_id': 'first', 'path': []}}, seed, service.owner)
    # Dispatch-only injected fixture. No Store publication or certificate claim.
    composition = compiled['capability']
    reference = capability_ref(composition)
    combined = create_capability_snapshot(service.owner, [*seed['roots'], reference],
        [*seed['capabilities'], composition])
    service.catalog = lambda: {'snapshot': combined, 'libraries': [learned['library']]}
    arguments = {'p0_value': {'data': {'items': [3, 4]}}}
    execution = service.execute(reference, arguments, tmp_path / 'composition', 'next')
    assert execution['arguments'] == arguments
    assert calls['execute'][0]['root'] == reference
    assert calls['execute'][0]['args'] == arguments
    assert 'paths' not in calls['execute'][0]['args']


def test_mixed_snapshots_rebuild_original_candidate_before_native_backend_guard(tmp_path, corpus):
    """Synthetic artifact receipts prove validation order, not Script publication."""
    from types import SimpleNamespace
    from src.adapters.capability_motif_learning import learn_capability_motifs
    _, current, _, _, original = corpus
    closure = learning_dependency_snapshot(original, current)
    assert closure['digest'] != current['digest']
    roots = [step['capability'] for step in original[0]['steps']]
    training = [call_trace(tmp_path / 'smaller-library', closure, roots, 'closure-' + str(i), 20 + i)
                for i in range(2)]
    traces = [*training, original[2]]
    references = [put(tmp_path / ('original-' + str(i) + '.json'), trace) for i, trace in enumerate(traces)]
    before = [verify(ref) for ref in references]
    candidate = learn_capability_motifs(training, original[2:], closure)['candidates'][0]
    materials = SimpleNamespace(owner=current['owner'], catalog=lambda: {'snapshot': current, 'libraries': []})
    # Reproduce the candidate across M1/M2, then retain the synthetic-backend rejection.
    with pytest.raises(ValueError, match='benchmark_store_native_script_backend_required'):
        prepare_recursive_publication(candidate, references, materials)
    assert [verify(ref) for ref in references] == before
    changed = copy.deepcopy(candidate)
    changed['provenance']['scope'] = 'invented-quality'
    with pytest.raises(ValueError, match='benchmark_store_original_learner_candidate_required'):
        prepare_recursive_publication(changed, references, materials)


@pytest.mark.parametrize('target', ['root', 'transitive'])
def test_learning_closure_rejects_withdrawn_current_dependencies(corpus, target):
    _, snapshot, c_ref, operations, traces = corpus
    caps = copy.deepcopy(snapshot['capabilities'])
    identifier = c_ref['id'] if target == 'root' else operations['increment']['id']
    next(cap for cap in caps if cap['id'] == identifier)['lifecycle'] = 'archived'
    current = create_capability_snapshot(snapshot['owner'], snapshot['roots'], caps)
    with pytest.raises(ValueError, match='benchmark_learning_dependency_inactive'):
        learning_dependency_snapshot(traces, current)


def test_learning_closure_keeps_original_receipt_and_owner_guards(corpus):
    _, snapshot, _, _, traces = corpus
    changed = copy.deepcopy(traces)
    changed[0]['steps'][0]['result']['value'] = -100
    with pytest.raises(ValueError, match='trace_changed'):
        learning_dependency_snapshot(changed, snapshot)
    foreign = create_capability_snapshot('another-owner', [], [])
    with pytest.raises(ValueError, match='foreign_owner'):
        learning_dependency_snapshot(traces, foreign)
    assert learning_dependency_snapshot(traces)['digest'] == learning_dependency_snapshot(traces, snapshot)['digest']
