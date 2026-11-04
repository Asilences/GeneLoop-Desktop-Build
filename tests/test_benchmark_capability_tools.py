"""Task-tool bridge diagnostics. No actual Docker or model calls."""
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.adapters.benchmark_capability_tools import benchmark_capability_tools, capability_trace_projection
from src.adapters.capability_feedback import file_ref, verify
from tests.test_capability_feedback import fixture
from tests.test_capability_motif_learning import run_driver
from tests.test_capability_motif_learning import corpus


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


class Trial:
    def __init__(self, output):
        self.output = output
        self.container = 'owned-task-container'
        self.prepared = True
        self.evaluated = False
        self.operations = []
        self.files = {'/app/input.json': b'{"items":[1,2]}', '/app/mesh.obj': b'v 0 0 1\n'}
        self.symlink = False
        put(output / 'manifest.json', self.manifest())

    def manifest(self):
        return {'task_id': 'canonical-task', 'split': 'test', 'source_identity': 'original-task-source'}

    def _invoke(self, argv):
        self.operations.append(argv)
        assert argv[:2] == ['docker', 'cp']
        assert argv[2].startswith(self.container + ':')
        path = argv[2].split(':', 1)[1]
        if path not in self.files:
            return {'returncode': 1, 'record': put(self.output / 'copy-failure.json', {'argv': argv})}
        target = Path(argv[3])
        if self.symlink:
            target.symlink_to(self.output / 'manifest.json')
        else:
            target.write_bytes(self.files[path])
        return {'returncode': 0, 'record': put(self.output / ('copy-' + str(len(self.operations)) + '.json'), {'argv': argv})}


class Materials:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.owner = snapshot['owner']
        self.executions = []
        self.failure = None

    def catalog(self):
        return {'snapshot': self.snapshot, 'catalog': [
            {'capability': ref, 'description': 'Current-data transformation'} for ref in self.snapshot['roots']]}

    def execute(self, ref, value, directory, task_id):
        if self.failure is not None:
            raise self.failure
        directory.mkdir()
        if isinstance(value, dict) and set(value) == {'path', 'sha256'}:
            raw = verify(value).decode('utf-8')
            try:
                value = {'data': json.loads(raw)}
            except json.JSONDecodeError:
                value = {'text': raw}
        arguments = {'value': value}
        trace = {'status': 'succeeded', 'root': ref, 'task_id': task_id,
                 'snapshot_sha256': self.snapshot['digest'], 'owner': self.owner,
                 'result': {'stdout': '{"count":2}', 'value': {'count': 2}}, 'receipts': [], 'diagnostic': True}
        record = {'trace': trace, 'execution_ref': put(directory / 'trace.json', trace),
                  'snapshot': self.snapshot, 'arguments': arguments}
        self.executions.append(record)
        return record


@pytest.fixture
def data(tmp_path):
    _, library, _, _ = fixture(tmp_path)
    materials = Materials(library['snapshot'])
    trial = Trial(tmp_path / 'trial')
    tools, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'calls', 'actual-task')
    return materials, trial, tools, dispatch, receipts


def test_tools_list_native_interfaces_without_internal_graphs(data):
    materials, trial, tools, dispatch, receipts = data
    for tool in tools:
        Draft202012Validator.check_schema(tool['parameters'])
    assert {tool['name'] for tool in tools} == {'capability_list', 'capability_call'}
    catalog = dispatch('capability_list', {})
    assert len(catalog['capabilities']) == 2
    assert catalog['snapshot_sha256'] == materials.snapshot['digest']
    assert 'implementation' not in json.dumps(catalog)
    assert receipts == [] and trial.operations == []
    first = dispatch('capability_list', {'limit': 1})
    second = dispatch('capability_list', {'offset': first['next_offset'], 'limit': 1})
    assert first['total'] == 2
    assert first['capabilities'][0]['capability_id'] != second['capabilities'][0]['capability_id']
    assert second['next_offset'] is None


def test_value_call_exposes_result_and_original_receipt_only(data):
    materials, _, _, dispatch, receipts = data
    ref = materials.snapshot['roots'][0]
    response = dispatch('capability_call', {'capability_id': ref['id'], 'value': {'data': {'items': [1, 2]}}})
    assert set(response) == {'status', 'call_id', 'result', 'receipt'}
    assert response['result']['value'] == {'count': 2}
    assert response['receipt'] == receipts[0]['execution_ref']
    assert receipts[0]['arguments'] == {'value': {'data': {'items': [1, 2]}}}
    assert receipts[0]['source_file'] is None


def test_container_file_is_collected_only_from_bound_task_and_provenance_retained(data):
    materials, trial, _, dispatch, receipts = data
    dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'input_file': '/app/input.json'})
    assert trial.operations[0][2] == 'owned-task-container:/app/input.json'
    row = receipts[0]
    assert row['arguments'] == {'value': {'data': {'items': [1, 2]}}}
    assert row['source_file']['origin'] == 'host_collection_at_actual_tool_call'
    assert row['source_file']['container_path'] == '/app/input.json'
    assert verify(row['source_file']['file']) == b'{"items":[1,2]}'
    assert row['task_fingerprint'] == 'original-task-source'
    assert row['task_manifest'] is not None


def test_text_file_wrapper_remains_explicit_host_preparation(data):
    materials, _, _, dispatch, receipts = data
    dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'input_file': '/app/mesh.obj'})
    assert receipts[0]['arguments'] == {'value': {'text': 'v 0 0 1\n'}}


@pytest.mark.parametrize('extra', [{}, {'input_file': '/app/input.json', 'value': {}}, {'unknown': 1}])
def test_exactly_one_input_is_required(data, extra):
    materials, _, _, dispatch, receipts = data
    with pytest.raises(ValueError, match='one_input_required'):
        dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], **extra})
    assert receipts == []


@pytest.mark.parametrize('path', ['relative.json', '/', '/app/bad\x00name'])
def test_container_path_validation_preserves_failed_tool_record(data, path):
    materials, trial, _, dispatch, receipts = data
    with pytest.raises(ValueError, match='container_file_required'):
        dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'input_file': path})
    assert trial.operations == []
    assert receipts[0]['status'] == 'failed'
    assert 'execution_ref' not in receipts[0]


def test_failed_copy_and_symlink_do_not_reach_runtime(data):
    materials, trial, _, dispatch, receipts = data
    reference = materials.snapshot['roots'][0]
    with pytest.raises(ValueError, match='collection_failed'):
        dispatch('capability_call', {'capability_id': reference['id'], 'input_file': '/app/missing'})
    trial.symlink = True
    with pytest.raises(ValueError, match='collection_failed'):
        dispatch('capability_call', {'capability_id': reference['id'], 'input_file': '/app/input.json'})
    assert materials.executions == []
    assert len(receipts) == 2 and all(row['status'] == 'failed' for row in receipts)


def test_unknown_capability_and_closed_task_do_not_run(data):
    materials, trial, _, dispatch, receipts = data
    with pytest.raises(ValueError, match='not_available'):
        dispatch('capability_call', {'capability_id': 'unknown', 'value': {}})
    trial.evaluated = True
    with pytest.raises(ValueError, match='not_active'):
        dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'value': {}})
    assert materials.executions == [] and receipts == []


def test_projection_uses_actual_arguments_as_inputs_without_literal_answers(data):
    materials, _, _, dispatch, receipts = data
    first, second = materials.snapshot['roots']
    dispatch('capability_call', {'capability_id': first['id'], 'value': {'data': [1, 2]}})
    dispatch('capability_call', {'capability_id': second['id'], 'value': {'data': [1, 2]}})
    projection = capability_trace_projection(receipts)
    assert projection['trace_inputs'] == {'call_0': {'value': {'data': [1, 2]}},
                                          'call_1': {'value': {'data': [1, 2]}}}
    assert [call['input_binding'] for call in projection['calls']] == [
        {'kind': 'input', 'path': ['call_0']}, {'kind': 'input', 'path': ['call_1']}]
    assert all(set(call) == {'id', 'capability', 'input_binding', 'execution_ref'} for call in projection['calls'])
    assert projection['task_id'] == 'actual-task'
    assert projection['task_fingerprint'] == 'original-task-source'


def test_projection_rejects_failure_barriers_and_noncontiguous_slices(data):
    materials, _, _, dispatch, receipts = data
    ref = materials.snapshot['roots'][0]
    dispatch('capability_call', {'capability_id': ref['id'], 'value': 1})
    materials.failure = ValueError('native_failure')
    with pytest.raises(ValueError, match='native_failure'):
        dispatch('capability_call', {'capability_id': ref['id'], 'value': 2})
    materials.failure = None
    dispatch('capability_call', {'capability_id': ref['id'], 'value': 3})
    with pytest.raises(ValueError, match='incomplete_or_mixed'):
        capability_trace_projection(receipts)
    with pytest.raises(ValueError, match='incomplete_or_mixed'):
        capability_trace_projection([receipts[0], receipts[2]])
    assert len(capability_trace_projection(receipts[2:])['calls']) == 1


def test_runtime_scope_change_keeps_original_trace_for_diagnosis(data):
    materials, _, _, dispatch, receipts = data
    original = materials.execute
    def wrong_task(*args):
        result = original(*args)
        result['trace']['task_id'] = 'wrong-task'
        return result
    materials.execute = wrong_task
    with pytest.raises(ValueError, match='scope_changed'):
        dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'value': 1})
    assert receipts[0]['status'] == 'failed'
    assert 'execution_ref' in receipts[0]


def test_projected_real_diagnostic_runtime_calls_pass_original_capture(tmp_path):
    # Original Runtime + original diagnostic authority fixture, no invented receipts.
    snapshot = run_driver({'action': 'seed', 'owner': 'runtime-projection-diagnostic'})
    materials = Materials(snapshot)
    def execute(ref, value, directory, task_id):
        arguments = {'value': value}
        execution = run_driver({'action': 'run', 'snapshot': snapshot, 'root': ref,
                                'input': arguments, 'task_id': task_id})['execution']
        return {'trace': execution, 'execution_ref': put(directory / 'trace.json', execution),
                'snapshot': snapshot, 'arguments': arguments}
    materials.execute = execute
    trial = Trial(tmp_path / 'trial')
    _, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'calls', 'real-runtime-task')
    dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 3})
    projection = capability_trace_projection(receipts)
    from src.adapters.capability_motif_learning import capture_capability_trace
    trace = capture_capability_trace(projection['snapshot'], task_id=projection['task_id'],
        task_input=projection['trace_inputs'], task_fingerprint=projection['task_fingerprint'],
        calls=projection['calls'])
    assert trace['steps'][0]['arguments'] == {'value': 3}
    assert trace['steps'][0]['status'] == 'succeeded'


def test_composition_uses_exact_input_schema_object_and_rejects_file_shorthand(tmp_path, corpus):
    _, snapshot, composition_ref, _, _ = corpus
    materials = Materials(snapshot)
    executions = []
    def execute_arguments(ref, arguments, directory, task_id):
        executions.append(arguments)
        actual = run_driver({'action': 'run', 'snapshot': snapshot, 'root': ref,
                             'input': arguments, 'task_id': task_id})['execution']
        return {'trace': actual, 'execution_ref': put(directory / 'trace.json', actual),
                'snapshot': snapshot, 'arguments': arguments}
    materials.execute_arguments = execute_arguments
    trial = Trial(tmp_path / 'composition-trial')
    tools, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'composition-calls', 'composition-task')
    assert 'composition' in next(tool for tool in tools if tool['name'] == 'capability_call')['description']
    result = dispatch('capability_call', {'capability_id': composition_ref['id'], 'value': {'value': 3}})
    assert result['status'] == 'succeeded'
    assert executions == [{'value': 3}]
    with pytest.raises(ValueError, match='composition_requires_value_fields:value'):
        dispatch('capability_call', {'capability_id': composition_ref['id'], 'input_file': '/app/input.json'})
    assert trial.operations == []
