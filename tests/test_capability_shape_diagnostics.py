"""Shape diagnostics preserve weak contracts instead of inventing constraints."""
import copy

import pytest

from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability, create_capability_snapshot, capability_ref
from src.adapters.capability_shape_diagnostics import composition_shape_advisories, diagnose_step_argument_shapes


def obj(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


def example(*, wrapped=True, items=None):
    array = {'type': 'array', **({'items': items} if items is not None else {})}
    source_schema = obj({'rows': array})
    def native(name, inputs, outputs):
        return create_capability({'owner': 'owner', 'contract': {'input_schema': inputs,
            'output_schema': outputs, 'effects': ['read']}, 'dependencies': [],
            'implementation': {'kind': 'legacy', 'legacy_ref': {'backend': 'script_motif',
                'library_sha256': 'a' * 64, 'library_digest': 'b' * 64, 'object_id': name,
                'object_sha256': 'c' * 64, 'certificate_sha256': 'd' * 64}}},
            {'lifecycle': 'active', 'certification': 'certified', 'migration': 'legacy'})
    first = native('producer', source_schema, source_schema)
    last = native('consumer', source_schema, obj({'ok': {'type': 'boolean'}}))
    seed = create_capability_snapshot('owner', [capability_ref(first), capability_ref(last)], [first, last])
    selected = {'kind': 'step', 'step_id': 'producer', 'path': ['rows']}
    if wrapped:
        selected = {'kind': 'array', 'items': [selected]}
    proposal = {'format': 'capability_compose_proposal_v1', 'owner': 'owner',
        'contract': {'input_schema': source_schema, 'output_schema': last['contract']['output_schema'], 'effects': ['read']},
        'steps': [{'id': 'producer', 'capability': capability_ref(first),
                   'arguments': {'kind': 'input', 'path': []}},
                  {'id': 'consumer', 'capability': capability_ref(last),
                   'arguments': {'kind': 'object', 'fields': {'rows': selected}}}],
        'output': {'kind': 'step', 'step_id': 'consumer', 'path': []}}
    return compile_proposal(proposal, seed, 'owner')


def test_wrapped_unknown_array_is_advisory_and_not_a_contract_violation():
    candidate = example();original = copy.deepcopy(candidate)
    result = diagnose_step_argument_shapes(candidate, 'consumer', {'rows': [[{'private': 'not emitted'}]]})
    assert result['declared_contract_passed'] and result['issues'] == []
    assert len(result['advisories']) == 1
    note = result['advisories'][0]
    assert note['binding_path'] == ['steps', 1, 'arguments', 'fields', 'rows', 'items', 0]
    assert note['argument_path'] == ['rows', 0]
    assert note['contract_violation'] is False and note['target_items_declared'] is False
    assert 'not emitted' not in repr(result) and 'private' not in repr(result)
    assert candidate == original


def test_existing_declared_items_reject_bad_actual_arguments_at_binding():
    candidate = example(wrapped=False, items=obj({'path': {'type': 'string'}}))
    result = diagnose_step_argument_shapes(candidate, 'consumer', {'rows': [[{'path': 'x'}]]})
    assert not result['declared_contract_passed'] and not result['advisories']
    issue = result['issues'][0]
    assert issue['validator'] == 'type' and issue['actual_type'] == 'array'
    assert issue['argument_path'] == ['rows', 0]
    assert issue['binding_path'] == ['steps', 1, 'arguments', 'fields', 'rows']
    assert issue['expected_constraint'] == 'object' and issue['contract_violation']


def test_correct_flat_array_produces_no_nesting_advisory():
    candidate = example(wrapped=False)
    result = diagnose_step_argument_shapes(candidate, 'consumer', {'rows': [{'path': 'x'}]})
    assert result['declared_contract_passed'] and not result['issues'] and not result['advisories']


def test_legitimate_nested_array_is_not_rejected_or_repaired():
    candidate = example(items={'type': 'array'})
    arguments = {'rows': [[['x']]]}
    original = copy.deepcopy(arguments)
    result = diagnose_step_argument_shapes(candidate, 'consumer', arguments)
    assert result['declared_contract_passed'] and result['issues'] == []
    assert result['advisories'][0]['target_items_declared']
    assert result['advisories'][0]['contract_violation'] is False
    assert arguments == original


def test_missing_required_argument_maps_to_call_not_to_guessed_binding():
    candidate = example(wrapped=False)
    result = diagnose_step_argument_shapes(candidate, 'consumer', {})
    assert result['issues'][0]['validator'] == 'required'
    assert result['issues'][0]['binding_path'] == ['steps', 1, 'arguments']


def test_many_bad_items_have_bounded_diagnostics_and_stay_a_failure():
    candidate = example(wrapped=False, items={'type': 'object'})
    result = diagnose_step_argument_shapes(candidate, 'consumer', {'rows': list(range(100))})
    assert not result['declared_contract_passed']
    assert result['issues_truncated'] and len(result['issues']) == 64


def test_missing_step_or_changed_candidate_cannot_produce_a_false_diagnosis():
    candidate = example()
    with pytest.raises(ValueError, match='step_missing'):
        diagnose_step_argument_shapes(candidate, 'not-selected', {})
    candidate['capability']['contract']['input_schema']['description'] = 'unfrozen'
    with pytest.raises(ValueError, match='changed'):
        composition_shape_advisories(candidate)
