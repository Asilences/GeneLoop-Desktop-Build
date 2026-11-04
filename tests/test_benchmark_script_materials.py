"""Native-adapter diagnostics with injected learning/execution, no Docker or API."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.benchmark_script_materials import BenchmarkScriptMaterials
from src.adapters.capability_contract import (
    capability_digest, capability_ref, create_capability, create_capability_snapshot,
)
from src.adapters.capability_feedback import file_ref, verify


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return file_ref(path)


@pytest.fixture
def data(tmp_path):
    program = {'source': "def run(value):\n    return {'count': len(value['data']['items'])}\n",
               'description': 'Count current input items', 'mode': 'json', 'interface': 'function_v1'}
    source = put(tmp_path / 'proposal.json', {'program': program, 'origin': 'diagnostic_model_response'})
    examples = [put(tmp_path / ('example-' + str(index) + '.json'), {'items': list(range(index + 1))})
                for index in range(3)]
    calls = {'learn': [], 'execute': [], 'catalog': []}

    def learn(program, cases, directory, source_evidence, **options):
        calls['learn'].append({'program': program, 'cases': cases, 'directory': directory,
                               'source_evidence': source_evidence, **options})
        directory.mkdir()
        put(directory / 'observations.json', {'diagnostic': True, 'cases': cases})
        put(directory / 'certification.json', {'diagnostic': True})
        return put(directory / 'library.json', {'diagnostic': True, 'source': program['source']})

    def catalog(library, owner):
        calls['catalog'].append(library)
        verify(library)
        caps = []
        record = {'type': 'object', 'properties': {'count': {'type': 'integer'}},
                  'required': ['count'], 'additionalProperties': False}
        inputs = [
            {'type': 'object', 'properties': {'paths': {'type': 'array', 'items': {'type': 'string'}}},
             'required': ['paths'], 'additionalProperties': False},
            {'type': 'object', 'properties': {'value': {'type': 'object'}},
             'required': ['value'], 'additionalProperties': False}]
        for schema in inputs:
            caps.append(create_capability({'owner': owner, 'contract': {
                'input_schema': schema, 'output_schema': {'type': 'object', 'properties': {
                    'stdout': {'type': 'string'}, 'value': record},
                    'required': ['stdout', 'value'], 'additionalProperties': False}, 'effects': ['read']},
                'implementation': {'kind': 'legacy', 'legacy_ref': {'backend': 'script_motif',
                    'object_id': 'diagnostic-program', 'library_sha256': library['sha256'],
                    'library_digest': 'a' * 64, 'object_sha256': 'b' * 64, 'certificate_sha256': 'c' * 64}},
                'dependencies': []}, {'lifecycle': 'active', 'certification': 'certified'}))
        roots = [capability_ref(cap) for cap in caps]
        return {'owner': owner, 'capabilities': caps, 'roots': roots,
                'snapshot': create_capability_snapshot(owner, roots, caps),
                'catalog': [{'capability': capability_ref(cap), 'description': 'Diagnostic native mapping'} for cap in caps]}

    def execute(snapshot, root, libraries, inputs, args, directory, task_id):
        calls['execute'].append({'snapshot': snapshot, 'root': root, 'libraries': libraries,
                                 'inputs': inputs, 'args': args, 'directory': directory, 'task_id': task_id})
        return {'status': 'succeeded', 'owner': snapshot['owner'], 'root': root,
                'task_id': task_id, 'snapshot_sha256': snapshot['digest'],
                'result': {'stdout': '{"count":2}', 'value': {'count': 2}},
                'receipts': [], 'diagnostic': True}

    service = BenchmarkScriptMaterials('owner', tmp_path / 'materials', learn=learn, catalog=catalog, execute=execute)
    return service, program, examples, source, calls


def acquire(data):
    service, program, examples, source, _ = data
    return service.acquire(program, examples, source, 'observed-interface-work')


def test_acquisition_uses_original_material_store_and_mechanical_wrappers(data):
    service, program, examples, source, calls = data
    result = acquire(data)
    assert result['status'] == 'registered'
    assert result['scope'] == 'source_equivalence_not_semantic_quality'
    assert result['origin'] == 'model_construction'
    assert result['model_requests'] == 0 and result['measured_net_benefit'] is None
    assert len(calls['learn']) == 1 and len(calls['learn'][0]['cases']) == 2
    native = calls['learn'][0]
    assert native['origin'] == 'model_construction'
    assert native['source_evidence'] == source
    assert native['program'] == program
    prepared = [json.loads(verify(case['inputs'][0]['source'])) for case in native['cases']]
    assert prepared == [{'data': {'items': [0]}}, {'data': {'items': [0, 1]}}]
    assert all(case['inputs'][0]['path'] == '/work/inputs/value.json' for case in native['cases'])
    records = service.materials.records()
    assert len(records) == 1 and records[0]['backend'] == 'script_motif'
    assert all(ref in records[0]['evidence'] for ref in [source, *examples])
    assert len(result['value_refs']) == 1 and len(result['refs']) == 2
    request = json.loads(verify(result['request']))
    assert request['preparation'] == 'host_file_to_value_wrapper'
    assert request['certification_examples'] == examples[:2]


def test_text_inputs_are_preserved_without_synthetic_task_interpretation(tmp_path, data):
    service, program, _, source, calls = data
    examples = []
    for index in range(2):
        path = tmp_path / ('mesh-' + str(index) + '.obj')
        path.write_text('v 0 0 ' + str(index) + '\n', encoding='utf-8')
        examples.append(file_ref(path))
    service.acquire(program, examples, source, 'actual-obj-files')
    values = [json.loads(verify(case['inputs'][0]['source'])) for case in calls['learn'][0]['cases']]
    assert values == [{'text': 'v 0 0 0\n'}, {'text': 'v 0 0 1\n'}]


def test_wrapper_uses_native_json_wire_for_integral_floats_and_key_order(tmp_path, data):
    service, program, _, source, calls = data
    examples = [put(tmp_path / ('numeric-' + str(i) + '.json'), {'10': 1.0, '2': i + 2.0}) for i in range(2)]
    service.acquire(program, examples, source, 'numeric-data')
    raw = verify(calls['learn'][0]['cases'][0]['inputs'][0]['source']).decode()
    assert raw == '{"data":{"2":2,"10":1}}'


def test_json_escaped_unicode_source_is_bound_to_original_proposal(tmp_path, data):
    service, program, examples, _, _ = data
    program = {**program, 'source': program['source'] + '\n# 原始模型注释\n'}
    path = tmp_path / 'unicode-proposal.json'
    path.write_text(json.dumps({'program': program}, ensure_ascii=True), encoding='utf-8')
    result = service.acquire(program, examples, file_ref(path), 'unicode-source')
    assert result['status'] == 'registered'


def test_acquisition_is_idempotent_and_rebuilds_catalog(data):
    service, _, _, _, calls = data
    first = acquire(data)
    second = acquire(data)
    assert first['library'] == second['library']
    assert len(calls['learn']) == 1
    assert len(service.materials.records()) == 1
    assert second['snapshot'] == service.catalog()['snapshot']


def test_service_restart_reads_original_materials(tmp_path, data):
    service, _, _, _, calls = data
    first = acquire(data)
    restarted = BenchmarkScriptMaterials('owner', service.directory,
        learn=service._learn, catalog=service._catalog, execute=service._execute)
    assert restarted.catalog()['snapshot'] == first['snapshot']
    assert calls['learn']


def test_multiple_libraries_merge_through_original_capability_snapshot(data):
    service, program, examples, _, _ = data
    first = acquire(data)
    revised = {**program, 'source': program['source'] + '\n# Actual second model revision\n'}
    source = put(service.directory / 'second-source.json', revised)
    second = service.acquire(revised, examples, source, 'second-real-candidate')
    assert len(second['snapshot']['roots']) == 4
    assert len(service.materials.records()) == 2
    assert all(ref in second['snapshot']['roots'] for ref in first['refs'])


@pytest.mark.parametrize('change', ['single', 'same_bytes', 'changed_source', 'changed_input', 'wrong_mode'])
def test_invalid_source_or_examples_do_not_reach_native_learning(tmp_path, data, change):
    service, program, examples, source, calls = data
    if change == 'single':
        examples = examples[:1]
    if change == 'same_bytes':
        examples = [examples[0], examples[0]]
    if change == 'changed_source':
        source = put(tmp_path / 'other-proposal.json', {'source': 'different source'})
    if change == 'changed_input':
        Path(examples[0]['path']).write_text('changed', encoding='utf-8')
    if change == 'wrong_mode':
        program = {**program, 'mode': 'paths'}
    with pytest.raises(ValueError):
        service.acquire(program, examples, source, 'invalid')
    assert calls['learn'] == []
    assert service.materials.records() == []


def test_native_failure_is_retained_and_never_registered(tmp_path, data):
    service, program, examples, source, _ = data
    calls = []
    def failed(*args, **kwargs):
        calls.append(args)
        raise ValueError('input_dependency_not_demonstrated')
    service._learn = failed
    with pytest.raises(ValueError, match='input_dependency_not_demonstrated'):
        service.acquire(program, examples, source, 'failed')
    result = next((service.directory / 'acquisitions').glob('*/result.json'))
    assert json.loads(result.read_text())['status'] == 'failed'
    assert service.materials.records() == []
    resumed = service.acquire(program, examples, source, 'failed')
    assert resumed['status'] == 'failed' and len(calls) == 1


def test_value_execution_calls_original_host_with_full_native_arguments(tmp_path, data):
    service, _, _, _, calls = data
    material = acquire(data)
    value = {'data': {'items': [3, 4]}}
    executed = service.execute(material['value_refs'][0], value, tmp_path / 'execution', 'next-task')
    native = calls['execute'][0]
    assert native['args'] == {'value': value}
    assert native['root'] == material['value_refs'][0]
    assert native['task_id'] == 'next-task'
    assert native['libraries'] == [material['library']]
    assert json.loads(verify(executed['execution_ref'])) == executed['trace']
    assert executed['trace']['result']['value'] == {'count': 2}


def test_file_execution_retains_original_file_and_wrapper_provenance(tmp_path, data):
    service, _, examples, _, calls = data
    material = acquire(data)
    executed = service.execute(material['value_refs'][0], examples[1], tmp_path / 'execution', 'next-task')
    assert calls['execute'][0]['args'] == {'value': {'data': {'items': [0, 1]}}}
    assert executed['source'] == examples[1]
    provenance = json.loads((tmp_path / 'execution/input-provenance.json').read_text())
    assert provenance['source'] == examples[1]
    assert provenance['encoding'] == 'json_value'


def test_paths_variant_uses_the_existing_file_input_contract(tmp_path, data):
    service, _, examples, _, calls = data
    material = acquire(data)
    path_ref = next(ref for ref in material['refs'] if ref not in material['value_refs'])
    service.execute(path_ref, examples[0], tmp_path / 'paths-execution', 'paths-task')
    assert calls['execute'][0]['args'] == {'paths': ['/work/inputs/value.json']}
    assert len(calls['execute'][0]['inputs']) == 1


def test_unknown_or_changed_material_cannot_execute(tmp_path, data):
    service, _, _, _, calls = data
    material = acquire(data)
    wrong = {**material['value_refs'][0], 'sha256': 'f' * 64}
    with pytest.raises(ValueError, match='not_registered'):
        service.execute(wrong, {}, tmp_path / 'unknown', 'task')
    assert calls['execute'] == []
    Path(material['library']['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence_changed'):
        service.execute(material['value_refs'][0], {}, tmp_path / 'changed', 'task')


def test_changed_native_trace_is_rejected(tmp_path, data):
    service, _, _, _, calls = data
    material = acquire(data)
    def inconsistent(snapshot, ref, libraries, inputs, args, directory, task_id):
        put(directory / 'trace.json', {'status': 'failed'})
        return {'status': 'succeeded'}
    service._execute = inconsistent
    with pytest.raises(ValueError, match='native_trace_changed'):
        service.execute(material['value_refs'][0], {}, tmp_path / 'changed-trace', 'task')


def test_foreign_catalog_cannot_enter_original_material_store(data):
    service, _, _, _, _ = data
    native = service._catalog
    service._catalog = lambda library, owner: native(library, 'other-owner')
    with pytest.raises(ValueError, match='foreign_owner'):
        acquire(data)
    assert service.materials.records() == []


def test_unsafe_json_number_is_not_silently_rounded(tmp_path, data):
    service, program, _, source, calls = data
    examples = [put(tmp_path / ('large-' + str(i) + '.json'), {'value': 9007199254740992 + i}) for i in range(2)]
    with pytest.raises(ValueError, match='number_out_of_range'):
        service.acquire(program, examples, source, 'large-number')
    assert calls['learn'] == []


def test_original_script_admission_location_is_preserved_and_exposed_compactly(tmp_path, data):
    from src.adapters.capability_script_learning import executable_source
    from src.adapters.script_motif_compiler import compile_script, file_contract
    service, _, examples, _, _ = data
    program = {'source': 'def run(value):\n    return "//' + 'header' * 100 + '" + str(value["data"]["items"])\n',
               'description': 'Synthetic comment-string admission diagnostic', 'mode': 'json', 'interface': 'function_v1'}
    source = put(tmp_path / 'comment-proposal.json', {'program': program})
    calls = []
    def reject(program, cases, directory, source_evidence, **options):
        calls.append(program)
        directory.mkdir()
        text = executable_source(program, cases)
        (directory / 'executed-source.py').write_text(text, encoding='utf-8')
        try:
            compile_script(text, {'/work/inputs/value.json': file_contract(cases[0]['inputs'][0]['source']['path'])})
        except ValueError as error:
            put(directory / 'compile-0/admission-error.json', error.script_diagnostics)
            raise
        raise AssertionError('Original guard should reject the comment-prefixed string')
    service._learn = reject
    with pytest.raises(ValueError, match='unbound_path_literal') as caught:
        service.acquire(program, examples, source, 'located-admission')
    error = caught.value
    summary = error.evolution_diagnostic
    assert summary['stage'] == 'native_script_construction'
    assert summary['native_diagnostics'][0]['source_space'] == 'parameterized_template'
    assert summary['native_diagnostics'][0]['line'] > 0 and summary['native_diagnostics'][0]['column'] >= 0
    assert len(summary['native_diagnostics'][0]['source_line']) <= 240
    assert summary['native_diagnostics'][0]['source_line_characters'] > 240
    refs = error.evolution_evidence_refs
    original = next(ref for ref in refs if Path(ref['path']).name == 'admission-error.json')
    raw = json.loads(verify(original))
    assert raw == error.script_diagnostics
    assert raw['error'] == 'unbound_path_literal'
    assert summary['native_diagnostics'][0]['evidence_id'] == 'evidence_' + original['sha256']
    result = next(ref for ref in refs if Path(ref['path']).name == 'result.json')
    before = verify(result)
    assert json.loads(before)['script_diagnostics'] == raw
    resumed = service.acquire(program, examples, source, 'located-admission')
    assert len(calls) == 1 and resumed['status'] == 'failed'
    assert resumed['diagnostic']['native_diagnostics'][0]['error'] == 'unbound_path_literal'
    assert result in resumed['evidence_refs'] and 'script_diagnostics' not in resumed
    assert verify(result) == before and service.materials.records() == []


def test_original_certifier_input_dependence_rejection_is_reported_without_fake_location(tmp_path, data):
    service, program, examples, source, _ = data
    def reject(program, cases, directory, source_evidence, **options):
        put(directory / 'certification.json', {'published': 0, 'rejected': [
            {'id': 'diagnostic-program', 'reason': 'input_dependency_not_demonstrated'}]})
        raise ValueError('frontier_native_no_certified_program')
    service._learn = reject
    with pytest.raises(ValueError, match='no_certified_program') as caught:
        service.acquire(program, examples, source, 'input-dependence')
    card = caught.value.evolution_diagnostic['native_diagnostics'][0]
    assert card['error'] == 'input_dependency_not_demonstrated'
    assert 'line' not in card and 'column' not in card
    assert any(Path(ref['path']).name == 'certification.json' for ref in caught.value.evolution_evidence_refs)
    assert service.materials.records() == []


@pytest.mark.parametrize('literal', ['InstancedMesh', 'x' * 200])
def test_native_literal_feedback_retains_bounded_original_value_without_inventing_location(tmp_path, data, literal):
    service, program, examples, source, _ = data
    def reject(program, cases, directory, source_evidence, **options):
        put(directory / 'certification.json', {'published': 0, 'rejected': [
            {'id': 'diagnostic-program', 'reason': 'task_specific_literal_requires_binding',
             'diagnostic': {'literal': literal, 'source_task': 'source', 'heldout_task': 'heldout'}}]})
        raise ValueError('frontier_native_no_certified_program')
    service._learn = reject
    with pytest.raises(ValueError, match='no_certified_program') as caught:
        service.acquire(program, examples, source, 'literal-feedback')
    card = caught.value.evolution_diagnostic['native_diagnostics'][0]
    assert card['literal'] == literal[:160]
    assert card['error'] == 'task_specific_literal_requires_binding'
    assert 'line' not in card and 'column' not in card
    ref = next(ref for ref in caught.value.evolution_evidence_refs if Path(ref['path']).name == 'certification.json')
    assert json.loads(verify(ref))['rejected'][0]['diagnostic']['literal'] == literal
    resumed = service.acquire(program, examples, source, 'literal-feedback')
    assert resumed['diagnostic']['native_diagnostics'][0]['literal'] == literal[:160]
