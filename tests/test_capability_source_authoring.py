"""Single-source syntax/IR diagnostics; no model or effectiveness evidence."""
import copy
import hashlib

import pytest

from src.adapters.capability_authoring import aliases, expand_draft
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability, create_capability_snapshot, capability_ref
from src.adapters.capability_source_authoring import (
    SourceAuthoringError, compile_capability_source, source_callable_interfaces,
)
from tests.test_capability_contract import leaf


INTEGER = {'type': 'integer'}
RECORD = {'type': 'object', 'properties': {'score': INTEGER}, 'required': ['score'], 'additionalProperties': False}
PROJECT = {'type': 'object', 'properties': {'project': {'type': 'string'}}, 'required': ['project'], 'additionalProperties': False}
PAIR = {'type': 'object', 'properties': {'before': {'type': 'string'}, 'after': {'type': 'string'}},
        'required': ['before', 'after'], 'additionalProperties': False}
DELTA = {'type': 'object', 'properties': {'delta': INTEGER}, 'required': ['delta'], 'additionalProperties': False}


def native(name, inputs, outputs, backend='script_motif'):
    old = leaf(name)
    definition = {key: copy.deepcopy(old[key]) for key in ('owner', 'contract', 'implementation', 'dependencies')}
    definition['contract'] = {'input_schema': inputs, 'output_schema': outputs, 'effects': ['read']}
    definition['implementation']['legacy_ref']['backend'] = backend
    return create_capability(definition, {'lifecycle': 'active', 'certification': 'certified', 'migration': 'legacy'})


def envelope(schema):
    return {'type': 'object', 'properties': {'stdout': {'type': 'string'}, 'value': schema},
            'required': ['stdout', 'value'], 'additionalProperties': False}


def fixture():
    parser = native('raw-parser', PROJECT, RECORD, 'source_program')
    audit = create_capability({'owner': 'owner', 'contract': parser['contract'],
        'implementation': {'kind': 'composition', 'steps': [{'id': 'extract', 'capability': capability_ref(parser),
            'arguments': {'kind': 'input', 'path': []}}], 'output': {'kind': 'step', 'step_id': 'extract', 'path': []}},
        'dependencies': [capability_ref(parser)]}, {'lifecycle': 'active', 'certification': 'certified', 'migration': 'testing'})
    operation = native('native-value', {'type': 'object', 'properties': {'value': RECORD},
        'required': ['value'], 'additionalProperties': False}, envelope(RECORD))
    snapshot = create_capability_snapshot('owner', [capability_ref(audit), capability_ref(operation)], [parser, audit, operation])
    table = aliases(snapshot)
    names = {cap['id']: key for key, ref in table.items() for cap in snapshot['capabilities'] if ref['id'] == cap['id']}
    task = {'id': 'single-source-diagnostic', 'contract': {'input_schema': PAIR, 'output_schema': DELTA, 'effects': ['read']}}
    return snapshot, task, audit, operation, names


def test_two_parameter_helper_keeps_algorithm_and_model_chosen_calls():
    snapshot, task, audit, _, names = fixture(); frozen = copy.deepcopy(snapshot)
    algorithm = "def compare_versions(previous, current):\n    # Keep this exact algorithm and its spacing.\n    return {'delta':current['score'] - previous['score']}"
    source = "import json\n\n" + algorithm + "\n\ndef build(value):\n    previous = capability." + names[audit['id']] + "(project=value['before'])\n    current = capability." + names[audit['id']] + "(project=value['after'])\n    return compare_versions(previous, current)\n"
    result = compile_capability_source(source, task, snapshot)
    assert algorithm in result['program']['source']
    assert result['program']['mode'] == 'json' and result['program']['interface'] == 'function_v1'
    assert "return compare_versions(value['previous'], value['current'])" in result['program']['source']
    assert [s['use'] for s in result['composition']['steps']] == [names[audit['id']], names[audit['id']], '$program']
    assert result['composition']['steps'][-1]['args'] == {'value': {
        'previous': {'$step': ['previous']}, 'current': {'$step': ['current']}}}
    assert result['composition']['output'] == {'$step': ['source_return', 'value']}
    assert result['new_program_step_id'] == 'source_return'
    assert result['provenance']['build_executed'] is False
    assert result['provenance']['helper_algorithm_changed'] is False
    assert result['provenance']['helper']['sha256'] == hashlib.sha256(algorithm.encode()).hexdigest()
    assert snapshot == frozen
    # Native certification is external. A diagnostic certified material proves
    # the emitted draft still passes the unchanged existing IR type checker.
    program_input = {'type': 'object', 'properties': {'previous': RECORD, 'current': RECORD},
                     'required': ['previous', 'current'], 'additionalProperties': False}
    material = native('new-comparison', {'type': 'object', 'properties': {'value': program_input},
        'required': ['value'], 'additionalProperties': False}, envelope(DELTA))
    current = create_capability_snapshot('owner', [*snapshot['roots'], capability_ref(material)], [*snapshot['capabilities'], material])
    material_alias = next(key for key, ref in aliases(current).items() if ref == capability_ref(material))
    current_audit = next(key for key, ref in aliases(current).items() if ref == capability_ref(audit))
    composition = copy.deepcopy(result['composition'])
    for step in composition['steps']: step['use'] = material_alias if step['use'] == '$program' else current_audit
    candidate = compile_proposal(expand_draft(composition, task, current), current, 'owner')
    assert candidate['capability']['dependencies'] == sorted([capability_ref(audit), capability_ref(material)], key=lambda r: r['id'])


def test_native_result_projection_matches_context_and_existing_ir():
    snapshot, task, _, operation, names = fixture()
    task['contract'] = {'input_schema': RECORD, 'output_schema': INTEGER, 'effects': ['read']}
    source = 'def build(value):\n    calculated = capability.' + names[operation['id']] + "(value={'score':value['score']})\n    return calculated['score']\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['program'] is None and result['new_program_step_id'] is None
    assert result['composition']['output'] == {'$step': ['calculated', 'value', 'score']}
    interface = next(row for row in source_callable_interfaces(snapshot) if row['capability'] == capability_ref(operation))
    assert interface['output_schema'] == RECORD and interface['result_path'] == ['value']
    compile_proposal(expand_draft(result['composition'], task, snapshot), snapshot, 'owner')


def test_noncanonical_script_output_is_not_silently_projected():
    snapshot, task, _, operation, _ = fixture()
    output = envelope(RECORD); output['properties']['debug'] = {'type': 'string'}
    other = native('extra-envelope-field', operation['contract']['input_schema'], output)
    snapshot = create_capability_snapshot('owner', [capability_ref(other)], [other])
    interface = source_callable_interfaces(snapshot)[0]
    assert interface['result_path'] == [] and interface['output_schema'] == output


def test_single_argument_run_is_unmodified_direct_entry_with_raw_binding():
    snapshot, task, audit, _, names = fixture(); task['contract']['output_schema'] = RECORD
    algorithm = "def run(report):\n    return {'score':report['score'] + 1}"
    source = algorithm + '\n\ndef build(value):\n    report = capability.' + names[audit['id']] + "(project=value['before'])\n    return run(report=report)\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['program']['source'].strip() == algorithm
    assert result['composition']['steps'][-1]['args'] == {'value': {'$step': ['report']}}
    assert result['provenance']['entrypoint'] == 'direct_model_run'
    assert result['provenance']['generated_wrapper'] == ''


def test_keyword_arguments_and_dependent_helper_source_remain_explicit():
    snapshot, task, audit, _, names = fixture()
    source = "SHIFT = 1\n\ndef difference(a, b):\n    return b['score'] - a['score'] + SHIFT\n\ndef compare(before, *, after):\n    return {'delta':difference(before, after)}\n\ndef build(value):\n    old = capability." + names[audit['id']] + "(project=value['before'])\n    new = capability." + names[audit['id']] + "(project=value['after'])\n    final = compare(after=new, before=old)\n    return final\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['composition']['steps'][-1]['args'] == {'value': {'before': {'$step': ['old']}, 'after': {'$step': ['new']}}}
    assert 'def difference(a, b):' in result['program']['source']
    assert "return compare(value['before'], after=value['after'])" in result['program']['source']
    assert result['composition']['output'] == {'$step': ['final', 'value']}


def test_host_entrypoint_does_not_overwrite_a_model_import_or_constant():
    snapshot, task, *_ = fixture()
    for declaration in ['import json as run', 'run = 3']:
        source = declaration + '\n\ndef transform(x):\n    return x\n\ndef build(value):\n    return transform(value)\n'
        with pytest.raises(SourceAuthoringError, match='capability_source_invalid'):
            compile_capability_source(source, task, snapshot)


def test_direct_run_accepts_array_argument_without_parameter_name_boxing():
    snapshot, task, *_ = fixture()
    source = "def run(items):\n    return {'delta':len(items)}\n\ndef build(value):\n    return run([value['before'], value['after']])\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['composition']['steps'][0]['args'] == {'value': [{'$input': ['before']}, {'$input': ['after']}]}
    assert result['program']['source'].startswith('def run(items):')


@pytest.mark.parametrize('source', [
    "import os\ndef transform(x):\n    return x\ndef build(value):\n    return transform(value)\n",
    "open('/tmp/not-created-by-source-compiler', 'w')\ndef build(value):\n    return capability.c1()\n",
    "def transform(x):\n    return eval(x)\ndef build(value):\n    return transform(value)\n",
    "def transform(x):\n    return capability.c1(value=x)\ndef build(value):\n    return transform(value)\n",
    "def build(value):\n    for item in value:\n        result = capability.c1(value=item)\n    return result\n",
    "def build(value):\n    return getattr(capability, 'c1')(value=value)\n",
    "def build(value):\n    return capability.c999(project=value['before'])\n",
    "def build(value):\n    return capability.c1(project=value[0])\n",
    "def build(value):\n    return capability.c1(project=unknown)\n",
    "@print('not-executed')\ndef build(value):\n    return capability.c1(project=value['before'])\n",
    "def transform(a, b):\n    return a\ndef build(value):\n    return transform(value)\n",
    "def run(a, b):\n    return a\ndef build(value):\n    return run(value, value)\n",
    "def transform(a):\n    return a\ndef build(value):\n    first = transform(value)\n    return transform(first)\n",
])
def test_unsafe_or_ambiguous_authoring_is_rejected_without_execution(source):
    snapshot, task, *_ = fixture()
    with pytest.raises(SourceAuthoringError) as error: compile_capability_source(source, task, snapshot)
    assert error.value.diagnostics['kind'] == 'capability_source_authoring'
    assert error.value.diagnostics['issues'][0]['path'] == ['capability_source']


def test_task_input_paths_and_required_capability_bindings_are_not_invented():
    snapshot, task, audit, _, names = fixture()
    for call in ["(project=value['missing'])", '()']:
        source = 'def build(value):\n    return capability.' + names[audit['id']] + call + '\n'
        with pytest.raises(SourceAuthoringError) as error: compile_capability_source(source, task, snapshot)
        assert error.value.diagnostics['issues'][0]['line'] == 2
