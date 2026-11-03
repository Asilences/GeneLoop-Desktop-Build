"""Single-source syntax/IR diagnostics; no model or effectiveness evidence."""
import copy
import hashlib

import pytest

from src.adapters.capability_authoring import aliases, expand_draft
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability, create_capability_snapshot, capability_ref, capability_digest
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
    source = 'def build(value):\n    calculated = capability.' + names[operation['id']] + "(score=value['score'])\n    return calculated['score']\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['program'] is None and result['new_program_step_id'] is None
    assert result['composition']['output'] == {'$step': ['calculated', 'value', 'score']}
    interface = next(row for row in source_callable_interfaces(snapshot) if row['capability'] == capability_ref(operation))
    assert interface['output_schema'] == RECORD and interface['result_path'] == ['value']
    assert interface['input_schema'] == RECORD and interface['input_projection'] == ['value']
    assert result['composition']['steps'][0]['args'] == {'value': {'score': {'$input': ['score']}}}
    compile_proposal(expand_draft(result['composition'], task, snapshot), snapshot, 'owner')


def test_json_relation_semantic_keywords_lower_to_one_exact_native_envelope():
    pair = {'type': 'object', 'properties': {'bibliography': RECORD, 'latex': RECORD},
            'required': ['bibliography', 'latex'], 'additionalProperties': False}
    native_input = {'type': 'object', 'properties': {'value': pair}, 'required': ['value'], 'additionalProperties': False}
    relation = native('relation-J', native_input, envelope(RECORD))
    snapshot = create_capability_snapshot('owner', [capability_ref(relation)], [relation])
    task = {'contract': {'input_schema': pair, 'output_schema': INTEGER, 'effects': ['read']}}
    source = "def build(value):\n    joined = capability.c1(bibliography=value['bibliography'], latex=value['latex'])\n    return joined['score']\n"
    result = compile_capability_source(source, task, snapshot)
    original_arguments = {'bibliography': {'$input': ['bibliography']}, 'latex': {'$input': ['latex']}}
    assert result['composition']['steps'][0]['args'] == {'value': original_arguments}
    assert result['composition']['output'] == {'$step': ['joined', 'value', 'score']}
    assert result['provenance']['calls'][0]['input_projection'] == ['value']
    assert result['provenance']['calls'][0]['host_input_envelope'] == 'script_json_value'
    interface = source_callable_interfaces(snapshot)[0]
    assert interface['input_schema'] == pair and interface['input_projection'] == ['value']
    assert interface['native_input_schema_ref'] == {'capability': capability_ref(relation),
        'schema_path': ['contract', 'input_schema'], 'sha256': capability_digest(native_input)}
    compile_proposal(expand_draft(result['composition'], task, snapshot), snapshot, 'owner')
    # This unpublished single-source API has one declared semantic signature;
    # the old raw wrapper spelling is not guessed from a supplied value.
    old = "def build(value):\n    return capability.c1(value={'bibliography':value['bibliography'], 'latex':value['latex']})\n"
    with pytest.raises(SourceAuthoringError): compile_capability_source(old, task, snapshot)


@pytest.mark.parametrize('payload', [INTEGER, {'type': 'array', 'items': INTEGER}])
def test_scalar_and_array_native_value_parameters_are_not_expanded(payload):
    inputs = {'type': 'object', 'properties': {'value': payload}, 'required': ['value'], 'additionalProperties': False}
    cap = native('scalar-or-array', inputs, envelope(RECORD))
    snapshot = create_capability_snapshot('owner', [capability_ref(cap)], [cap])
    task = {'contract': {'input_schema': {'type': 'object', 'properties': {'payload': payload},
        'required': ['payload'], 'additionalProperties': False}, 'output_schema': INTEGER, 'effects': ['read']}}
    source = "def build(value):\n    result = capability.c1(value=value['payload'])\n    return result['score']\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['composition']['steps'][0]['args'] == {'value': {'$input': ['payload']}}
    assert result['provenance']['calls'][0]['input_projection'] == []
    interface = source_callable_interfaces(snapshot)[0]
    assert interface['input_schema'] == inputs and interface['input_projection'] == []
    compile_proposal(expand_draft(result['composition'], task, snapshot), snapshot, 'owner')


def test_composition_domain_value_argument_keeps_its_original_signature():
    inputs = {'type': 'object', 'properties': {'value': RECORD}, 'required': ['value'], 'additionalProperties': False}
    old = native('domain-value', inputs, RECORD, 'source_program')
    cap = create_capability({'owner': 'owner', 'contract': old['contract'],
        'implementation': {'kind': 'composition', 'steps': [{'id': 'domain', 'capability': capability_ref(old),
            'arguments': {'kind': 'input', 'path': []}}], 'output': {'kind': 'step', 'step_id': 'domain', 'path': []}},
        'dependencies': [capability_ref(old)]}, {'lifecycle': 'active', 'certification': 'certified', 'migration': 'testing'})
    snapshot = create_capability_snapshot('owner', [capability_ref(cap)], [old, cap])
    task = {'contract': {'input_schema': {'type': 'object', 'properties': {'report': RECORD},
        'required': ['report'], 'additionalProperties': False}, 'output_schema': INTEGER, 'effects': ['read']}}
    source = "def build(value):\n    report = capability.c1(value=value['report'])\n    return report['score']\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['composition']['steps'][0]['args'] == {'value': {'$input': ['report']}}
    assert result['composition']['output'] == {'$step': ['report', 'score']}
    interface = source_callable_interfaces(snapshot)[0]
    assert interface['input_schema'] == inputs and interface['input_projection'] == []
    compile_proposal(expand_draft(result['composition'], task, snapshot), snapshot, 'owner')


def test_inner_domain_field_named_value_is_not_confused_with_native_wrapper():
    inner = {'type': 'object', 'properties': {'value': RECORD}, 'required': ['value'], 'additionalProperties': False}
    inputs = {'type': 'object', 'properties': {'value': inner}, 'required': ['value'], 'additionalProperties': False}
    cap = native('nested-domain-value', inputs, envelope(RECORD))
    snapshot = create_capability_snapshot('owner', [capability_ref(cap)], [cap])
    task = {'contract': {'input_schema': {'type': 'object', 'properties': {'report': RECORD},
        'required': ['report'], 'additionalProperties': False}, 'output_schema': INTEGER, 'effects': ['read']}}
    source = "def build(value):\n    report = capability.c1(value=value['report'])\n    return report['score']\n"
    result = compile_capability_source(source, task, snapshot)
    assert result['composition']['steps'][0]['args'] == {'value': {'value': {'$input': ['report']}}}
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


def graph_fixture():
    files = {'type': 'object', 'properties': {'paths': {'type': 'array', 'items': {'type': 'string'}}},
             'required': ['paths'], 'additionalProperties': False}
    pair = {'type': 'object', 'properties': {'bibliography': RECORD, 'latex': RECORD},
            'required': ['bibliography', 'latex'], 'additionalProperties': False}
    bib = native('bib-leaf', files, envelope(RECORD))
    tex = native('tex-leaf', files, envelope(RECORD))
    join = native('join-leaf', {'type': 'object', 'properties': {'value': pair},
        'required': ['value'], 'additionalProperties': False}, envelope(RECORD))
    caps = [bib, tex, join]
    snapshot = create_capability_snapshot('owner', [capability_ref(c) for c in caps], caps)
    names = {ref['id']: alias for alias, ref in aliases(snapshot).items()}
    graph = ("def audit(project):\n"
             f"    bib = capability.{names[bib['id']]}(paths=[project])\n"
             f"    tex = capability.{names[tex['id']]}(paths=[project])\n"
             f"    return capability.{names[join['id']]}(bibliography=bib, latex=tex)")
    task = {'contract': {'input_schema': PAIR, 'output_schema': DELTA, 'effects': ['read']}}
    return snapshot, task, caps, names, graph


def test_flat_two_local_audits_inline_original_refs_then_one_unchanged_algorithm():
    snapshot, task, caps, names, graph = graph_fixture()
    algorithm = "def compare(a, b):\n    # Model algorithm stays verbatim.\n    return {'delta': b['score'] - a['score']}"
    source = graph + '\n\n' + algorithm + "\n\ndef build(value):\n    before = audit(value['before'])\n    after = audit(project=value['after'])\n    return compare(before, after)\n"
    result = compile_capability_source(source, task, snapshot)
    steps = result['composition']['steps']; ids = [step['id'] for step in steps]
    assert len(steps) == 7 and len(set(ids)) == 7
    assert [step['use'] for step in steps] == [names[c['id']] for c in caps] * 2 + ['$program']
    assert steps[0]['args'] == {'paths': [{'$input': ['before']}]}
    assert steps[3]['args'] == {'paths': [{'$input': ['after']}]}
    assert steps[2]['args'] == {'value': {'bibliography': {'$step': [ids[0], 'value']}, 'latex': {'$step': [ids[1], 'value']}}}
    assert steps[-1]['args'] == {'value': {'a': {'$step': [ids[2], 'value']}, 'b': {'$step': [ids[5], 'value']}}}
    assert algorithm in result['program']['source'] and graph not in result['program']['source']
    assert 'capability.' not in result['program']['source'] and 'def audit' not in result['program']['source']
    assert result['provenance']['helper']['sha256'] == hashlib.sha256(algorithm.encode()).hexdigest()
    assert result['provenance']['graph_helpers'] == [{'name': 'audit', 'source_span': {
        'line': 1, 'column': 1, 'end_line': 4, 'end_column': len(graph.splitlines()[-1]) + 1},
        'sha256': hashlib.sha256(graph.encode()).hexdigest()}]
    expansions = result['provenance']['graph_expansions']
    assert [row['parameter_bindings'] for row in expansions] == [{'project': {'$input': ['before']}}, {'project': {'$input': ['after']}}]
    assert [row['step_ids'] for row in expansions] == [ids[:3], ids[3:6]]
    assert all(call['graph_expansion_id'] == expansions[index // 3]['id'] for index, call in enumerate(result['provenance']['calls'][:6]))
    # Independent native certification is outside this encoder. Add a typed
    # diagnostic material and check the unchanged existing IR's exact contracts.
    args = {'type': 'object', 'properties': {'a': RECORD, 'b': RECORD}, 'required': ['a', 'b'], 'additionalProperties': False}
    material = native('diagnostic-comparison', {'type': 'object', 'properties': {'value': args},
        'required': ['value'], 'additionalProperties': False}, envelope(DELTA))
    current = create_capability_snapshot('owner', [*snapshot['roots'], capability_ref(material)], [*caps, material])
    table = {ref['id']: alias for alias, ref in aliases(current).items()}
    reverse = aliases(snapshot); composition = copy.deepcopy(result['composition'])
    for step in composition['steps']:
        step['use'] = table[material['id']] if step['use'] == '$program' else table[reverse[step['use']]['id']]
    compiled = compile_proposal(expand_draft(composition, task, current), current, 'owner')
    assert len(compiled['capability']['dependencies']) == 4  # No invented certified audit capability.


def test_nested_graph_parameter_paths_and_object_returns_preserve_raw_composition_results():
    snapshot, task, audit, _, names = fixture()
    source = ("def inspect(project):\n"
              f"    report = capability.{names[audit['id']]}(project=project['path'])\n"
              "    return {'report': report}\n\n"
              "def audit_local(location):\n"
              "    packet = inspect(project={'path': location['name']})\n"
              "    return packet['report']\n\n"
              "def build(value):\n"
              f"    source_macro_2_report = capability.{names[audit['id']]}(project=value['before'])\n"
              "    before = audit_local(location={'name': value['after']})\n"
              "    return {'delta': before['score']}\n")
    result = compile_capability_source(source, task, snapshot)
    steps = result['composition']['steps']
    assert len(steps) == 2 and steps[0]['id'] != steps[1]['id']
    assert steps[0]['id'] == 'source_macro_2_report'
    assert steps[1]['args'] == {'project': {'$input': ['after']}}
    assert result['composition']['output'] == {'delta': {'$step': [steps[1]['id'], 'score']}}
    assert result['program'] is None
    parent, child = result['provenance']['graph_expansions']
    assert child['parent_expansion'] == parent['id']
    assert parent['step_ids'] == child['step_ids'] == [steps[1]['id']]
    compile_proposal(expand_draft(result['composition'], task, snapshot), snapshot, 'owner')


@pytest.mark.parametrize('body', [
    "    for p in project:\n        report = capability.c1(paths=[p])\n    return report",
    "    report = capability.c1(paths=[project + '/paper'])\n    return report",
    "    report = getattr(capability, 'c1')(paths=[project])\n    return report",
    "    alias = capability\n    return alias.c1(paths=[project])",
    "    report = capability.c1(paths=[later])\n    later = capability.c1(paths=[project])\n    return report",
])
def test_graph_helpers_reject_dynamic_or_nonstatic_operations_with_source_positions(body):
    snapshot, task, *_ = graph_fixture()
    source = 'def audit(project):\n' + body + "\n\ndef build(value):\n    return audit(value['before'])\n"
    with pytest.raises(SourceAuthoringError) as error: compile_capability_source(source, task, snapshot)
    assert error.value.diagnostics['issues'][0]['line'] >= 1
    assert error.value.diagnostics['issues'][0]['column'] >= 1


def test_recursive_graph_helpers_and_excess_depth_are_rejected():
    snapshot, task, *_ = graph_fixture()
    for helpers in [
        "def audit(project):\n    report = capability.c1(paths=[project])\n    return audit(project)\n",
        "def first(project):\n    return second(project)\ndef second(project):\n    report = capability.c1(paths=[project])\n    return first(project)\n",
        ''.join(f"def chain{i}(project):\n    return chain{i + 1}(project)\n" for i in range(8)) + "def chain8(project):\n    return capability.c1(paths=[project])\n",
    ]:
        target = 'audit' if 'def audit' in helpers else 'first' if 'def first' in helpers else 'chain0'
        with pytest.raises(SourceAuthoringError):
            compile_capability_source(helpers + f"def build(value):\n    return {target}(value['before'])\n", task, snapshot)


def test_expansion_limits_and_one_new_algorithm_call_apply_across_macro_instances():
    snapshot, task, _, _, graph = graph_fixture()
    source = graph + '\n\ndef build(value):\n' + ''.join(f"    report{i} = audit(value['before'])\n" for i in range(22)) + '    return report21\n'
    with pytest.raises(SourceAuthoringError) as error: compile_capability_source(source, task, snapshot)
    assert '64' in error.value.diagnostics['issues'][0]['expected']
    source = ("def identity(report):\n    return report\n\n" + graph.replace('    return capability.', '    joined = capability.') +
              '\n    return identity(joined)\n\ndef build(value):\n    before = audit(value[\'before\'])\n    return audit(value[\'after\'])\n')
    with pytest.raises(SourceAuthoringError) as error: compile_capability_source(source, task, snapshot)
    assert 'one explicit new helper call' in error.value.diagnostics['issues'][0]['expected']


def test_graph_helper_cannot_capture_build_input_or_escape_as_a_native_value():
    snapshot, task, _, names, graph = graph_fixture()
    alias = next(iter(names.values()))
    capture = f"def audit(project):\n    return capability.{alias}(paths=[value['before']])\n"
    with pytest.raises(SourceAuthoringError):
        compile_capability_source(capture + "def build(value):\n    return audit(value['after'])\n", task, snapshot)
    source = graph + "\n\ndef choose(x):\n    return audit\n\ndef build(value):\n    return choose(value)\n"
    with pytest.raises(SourceAuthoringError): compile_capability_source(source, task, snapshot)


def test_static_binding_substitution_is_bounded_even_with_few_native_calls():
    snapshot, task, caps, names, _ = graph_fixture()
    source = f"def chain0(project):\n    report = capability.{names[caps[0]['id']]}(paths=[project])\n    return {{'a':report, 'b':report, 'c':report, 'd':report}}\n"
    for index in range(1, 8):
        source += f"def chain{index}(project):\n    child = chain{index - 1}(project)\n    return {{'a':child, 'b':child, 'c':child, 'd':child}}\n"
    source += "def build(value):\n    return chain7(value['before'])\n"
    with pytest.raises(SourceAuthoringError) as error: compile_capability_source(source, task, snapshot)
    assert 'expanded bindings' in error.value.diagnostics['issues'][0]['expected']


def test_wide_helper_arguments_share_one_expanded_binding_budget():
    snapshot, task, audit, _, names = fixture()
    fields = '{' + ', '.join(repr('k' + str(i)) + ':' + str(i) for i in range(600)) + '}'
    parameters = ', '.join('p' + str(i) for i in range(40))
    source = (f"def graph(project):\n    report = capability.{names[audit['id']]}(project=project)\n"
              f"    return {fields}\n\ndef pure({parameters}):\n    return p0\n\n"
              "def build(value):\n    packet = graph(value['before'])\n"
              '    return pure(' + ', '.join('packet' for _ in range(40)) + ')\n')
    with pytest.raises(SourceAuthoringError) as error:
        compile_capability_source(source, task, snapshot)
    assert 'expanded bindings' in error.value.diagnostics['issues'][0]['expected']
