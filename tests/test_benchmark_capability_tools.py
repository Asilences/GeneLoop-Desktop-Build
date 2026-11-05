"""Task-tool bridge diagnostics. No actual Docker or model calls."""
import copy
import json
from pathlib import Path, PurePosixPath

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


@pytest.mark.parametrize('extra', [{}, {'input_file': '/app/input.json', 'value': {}}, {'unknown': 1},
    {'value': {}, 'input_binding': {'kind': 'literal', 'value': {}}},
    {'input_file': '/app/input.json', 'input_binding': {'kind': 'literal', 'value': {}}}])
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
    projected = capability_trace_projection(receipts)
    assert [call['id'] for call in projected['calls']] == ['call_0', 'call_2']
    assert projected['native_call_indices'] == [0, 2]
    assert projected['nonexecuted_attempts'][0]['id'] == 'call_1'
    assert 'native_failure' in projected['nonexecuted_attempts'][0]['error']
    assert capability_trace_projection([receipts[0], receipts[2]])['native_call_indices'] == [0, 2]
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


class RuntimeMaterials(Materials):
    """Original Runtime/native diagnostic authority, no model or Docker calls."""
    def execute_arguments(self, ref, arguments, directory, task_id):
        actual = run_driver({'action': 'run', 'snapshot': self.snapshot, 'root': ref,
                             'input': arguments, 'task_id': task_id})['execution']
        executed = {'trace': actual, 'execution_ref': put(directory / 'trace.json', actual),
                    'snapshot': self.snapshot, 'arguments': arguments}
        self.executions.append(executed)
        return executed

    def execute(self, ref, value, directory, task_id):
        return self.execute_arguments(ref, {'value': value}, directory, task_id)


def runtime_task(tmp_path, snapshot, task_id):
    from src.adapters.capability_contract import capability_digest
    class InputTrial(Trial):
        def manifest(self):
            return {**super().manifest(), 'input_fingerprint': capability_digest({'input': task_id})}
    materials = RuntimeMaterials(snapshot)
    trial = InputTrial(tmp_path / 'trial')
    tools, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'calls', task_id)
    return materials, trial, tools, dispatch, receipts


def result_binding(call_id):
    return {'kind': 'object', 'fields': {
        'value': {'kind': 'step', 'step_id': call_id, 'path': ['value']}}}


def actual_trace(receipts):
    from src.adapters.capability_motif_learning import capture_capability_trace
    projected = capability_trace_projection(receipts)
    return capture_capability_trace(projected['snapshot'], task_id=projected['task_id'],
        task_input=projected['trace_inputs'], task_fingerprint=projected['task_fingerprint'], calls=projected['calls'])


def test_explicit_runtime_binding_enters_original_miner_as_parameter_transfer(tmp_path, corpus):
    from src.adapters.capability_contract import capability_ref
    from src.adapters.capability_motif_learning import learn_capability_motifs
    _, snapshot, c_ref, operations, _ = corpus
    successor = capability_ref(operations['double'])
    traces = []
    for index, value in enumerate((2, 4, 7)):
        _, _, tools, dispatch, receipts = runtime_task(tmp_path / str(index), snapshot, 'binding-task-' + str(index))
        first = dispatch('capability_call', {'capability_id': c_ref['id'], 'value': {'value': value}})
        binding = result_binding(first['call_id'])
        arguments = {'capability_id': successor['id'], 'input_binding': binding}
        schema = next(tool['parameters'] for tool in tools if tool['name'] == 'capability_call')
        Draft202012Validator(schema).validate(arguments)
        second = dispatch('capability_call', arguments)
        assert second['result'] == {'value': 2 * (value + 1)}
        assert receipts[1]['arguments'] == {'value': value + 1}
        assert receipts[1]['input_binding'] == binding
        assert receipts[1]['binding_sources'] == [{'call_id': first['call_id'], 'execution_ref': first['receipt']}]
        assert set(capability_trace_projection(receipts)['trace_inputs']) == {'call_0'}
        traces.append(actual_trace(receipts))
    learned = learn_capability_motifs(traces[:2], traces[2:], snapshot)
    assert len(learned['candidates']) == 1
    candidate = learned['candidates'][0]
    assert candidate['motif']['transfer_evidence'][0]['from_tool'] == 'capability_' + c_ref['sha256']
    assert candidate['proposal']['steps'][1]['arguments'] == {'kind': 'object', 'fields': {
        'value': {'kind': 'step', 'step_id': 'call0', 'path': ['value']}}}
    assert set(candidate['proposal']['contract']['input_schema']['properties']) == {'p0_value'}


def test_equal_manually_copied_values_remain_external_inputs_without_edges(tmp_path, corpus):
    from src.adapters.capability_contract import capability_ref
    from src.adapters.capability_motif_learning import learn_capability_motifs
    _, snapshot, c_ref, operations, _ = corpus
    successor = capability_ref(operations['double'])
    traces = []
    for index, value in enumerate((3, 6, 9)):
        _, _, _, dispatch, receipts = runtime_task(tmp_path / str(index), snapshot, 'copied-task-' + str(index))
        first = dispatch('capability_call', {'capability_id': c_ref['id'], 'value': {'value': value}})
        dispatch('capability_call', {'capability_id': successor['id'], 'value': first['result']['value']})
        traces.append(actual_trace(receipts))
    learned = learn_capability_motifs(traces[:2], traces[2:], snapshot)
    assert len(learned['candidates']) == 1
    candidate = learned['candidates'][0]
    assert candidate['motif']['transfer_evidence'] == []
    assert set(candidate['proposal']['contract']['input_schema']['properties']) == {'p0_value', 'p1_value'}


def test_explicit_literal_is_complete_arguments_and_remains_literal_in_projection(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'literal-binding-diagnostic'})
    materials, trial, _, dispatch, receipts = runtime_task(tmp_path, snapshot, 'literal-task')
    binding = {'kind': 'literal', 'value': {'value': 3}}
    result = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'input_binding': binding})
    assert result['status'] == 'succeeded'
    assert materials.executions[0]['arguments'] == {'value': 3}
    projection = capability_trace_projection(receipts)
    assert projection['trace_inputs'] == {}
    assert projection['calls'][0]['input_binding'] == binding
    assert actual_trace(receipts)['steps'][0]['input_binding'] == binding
    assert trial.manifest()['input_fingerprint'] == receipts[0]['task_fingerprint']
    assert trial.manifest()['source_identity'] != receipts[0]['task_fingerprint']


@pytest.mark.parametrize('binding', [
    {'kind': 'input', 'path': []},
    {'kind': 'object', 'fields': {'value': {'kind': 'input', 'path': ['missing']}}}])
def test_external_input_binding_without_source_is_explicitly_rejected(data, binding):
    materials, _, _, dispatch, receipts = data
    with pytest.raises(ValueError, match='binding_input_source_unavailable'):
        dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'input_binding': binding})
    assert materials.executions == [] and receipts[0]['status'] == 'failed'


@pytest.mark.parametrize('source', ['call_0', 'call_1', 'foreign-task/call_0'])
def test_self_forward_and_foreign_call_ids_cannot_be_bound(data, source):
    materials, _, _, dispatch, receipts = data
    with pytest.raises(ValueError, match='binding_step_unavailable'):
        dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'],
                                    'input_binding': result_binding(source)})
    assert materials.executions == [] and receipts[0]['status'] == 'failed'


def test_failed_runtime_call_is_unavailable_as_result_source(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'failed-binding-diagnostic'})
    materials, _, _, dispatch, receipts = runtime_task(tmp_path, snapshot, 'failed-source-task')
    first = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 'invalid-number'})
    assert first['status'] != 'succeeded'
    with pytest.raises(ValueError, match='binding_step_unavailable'):
        dispatch('capability_call', {'capability_id': snapshot['roots'][1]['id'],
                                    'input_binding': result_binding(first['call_id'])})
    assert len(materials.executions) == 1
    assert receipts[0]['status'] == first['status']
    assert receipts[1]['status'] == 'failed'


def test_result_reference_from_another_task_is_rejected_before_execution(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'cross-task-binding-diagnostic'})
    _, _, _, earlier, previous = runtime_task(tmp_path / 'previous', snapshot, 'previous-task')
    first = earlier('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 4})
    materials, _, _, dispatch, receipts = runtime_task(tmp_path / 'current', snapshot, 'current-task')
    receipts.append(copy.deepcopy(previous[0]))
    with pytest.raises(ValueError, match='binding_source_scope_changed'):
        dispatch('capability_call', {'capability_id': snapshot['roots'][1]['id'],
                                    'input_binding': result_binding(first['call_id'])})
    assert materials.executions == []


def test_binding_source_original_receipt_hash_is_checked_before_execution(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'changed-binding-diagnostic'})
    materials, _, _, dispatch, _ = runtime_task(tmp_path, snapshot, 'changed-source-task')
    first = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 4})
    Path(first['receipt']['path']).write_text('{}')
    with pytest.raises(ValueError, match='evidence_changed'):
        dispatch('capability_call', {'capability_id': snapshot['roots'][1]['id'],
                                    'input_binding': result_binding(first['call_id'])})
    assert len(materials.executions) == 1


def test_array_binding_is_resolved_by_original_binder_and_checked_by_runtime(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'array-binding-diagnostic'})
    materials, _, _, dispatch, receipts = runtime_task(tmp_path, snapshot, 'array-task')
    binding = {'kind': 'object', 'fields': {'value': {'kind': 'array', 'items': [
        {'kind': 'literal', 'value': 1}, {'kind': 'literal', 'value': 2}]}}}
    outcome = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'input_binding': binding})
    assert materials.executions[0]['arguments'] == {'value': [1, 2]}
    # The arithmetic fixture requires a number, so its original Runtime rejects
    # this typed input. The binding adapter preserves that genuine outcome.
    assert outcome['status'] != 'succeeded'
    assert receipts[0]['input_binding'] == binding


def test_dependent_slice_cannot_silently_turn_missing_parent_result_into_input(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'orphan-binding-diagnostic'})
    _, _, _, dispatch, receipts = runtime_task(tmp_path, snapshot, 'dependent-slice-task')
    first = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 5})
    dispatch('capability_call', {'capability_id': snapshot['roots'][1]['id'],
                                'input_binding': result_binding(first['call_id'])})
    with pytest.raises(ValueError, match='binding_step_unavailable'):
        capability_trace_projection(receipts[1:])


def test_repaired_binding_error_does_not_block_real_dependent_calls(tmp_path, corpus):
    from src.adapters.capability_contract import capability_ref
    _, snapshot, c_ref, operations, _ = corpus
    _, _, _, dispatch, receipts = runtime_task(tmp_path, snapshot, 'repair-then-compose-task')
    with pytest.raises(ValueError, match='binding_step_unavailable'):
        dispatch('capability_call', {'capability_id': c_ref['id'], 'input_binding': result_binding('future')})
    first = dispatch('capability_call', {'capability_id': c_ref['id'], 'value': {'value': 6}})
    dispatch('capability_call', {'capability_id': capability_ref(operations['double'])['id'],
                                'input_binding': result_binding(first['call_id'])})
    projection = capability_trace_projection(receipts)
    assert projection['native_call_indices'] == [1, 2]
    assert projection['nonexecuted_attempts'][0]['id'] == 'call_0'
    assert projection['nonexecuted_attempts'][0]['status'] == 'failed'
    assert 'binding_step_unavailable' in projection['nonexecuted_attempts'][0]['error']
    assert 'runtime_started' not in projection['nonexecuted_attempts'][0]
    assert verify(projection['nonexecuted_attempts'][0]['attempt_ref'])
    trace = actual_trace(receipts)
    assert [step['call_id'] for step in trace['steps']] == ['call_1', 'call_2']
    assert trace['steps'][1]['input_binding']['fields']['value']['step_id'] == 'call_1'
    assert trace['steps'][1]['result'] == {'value': 14}


def test_real_runtime_failure_stays_in_captured_graph_as_barrier(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'failed-graph-diagnostic'})
    _, _, _, dispatch, receipts = runtime_task(tmp_path, snapshot, 'failed-graph-task')
    bad = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 'invalid-number'})
    dispatch('capability_call', {'capability_id': snapshot['roots'][1]['id'], 'value': 5})
    projected = capability_trace_projection(receipts)
    assert len(projected['calls']) == 2 and projected['nonexecuted_attempts'] == []
    trace = actual_trace(receipts)
    assert trace['steps'][0]['status'] == bad['status'] != 'succeeded'
    assert trace['steps'][1]['status'] == 'succeeded'
    assert trace['task_fingerprint'] == receipts[0]['task_fingerprint']


def test_native_adapter_exception_preserves_already_written_failed_execution(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'failed-exception-diagnostic'})
    materials, _, _, dispatch, receipts = runtime_task(tmp_path, snapshot, 'native-exception-task')
    original = materials.execute_arguments
    def raising(ref, arguments, directory, task_id):
        executed = original(ref, arguments, directory, task_id)
        assert executed['trace']['status'] != 'succeeded'
        put(directory / 'args.json', arguments)
        raise ValueError('native_runtime_reported_failure')
    materials.execute_arguments = raising
    with pytest.raises(ValueError, match='native_runtime_reported_failure'):
        dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 'invalid-number'})
    assert receipts[0]['execution_ref'] == file_ref(tmp_path / 'calls/call_0/runtime/trace.json')
    assert 'native_runtime_reported_failure' in receipts[0]['error']
    projection = capability_trace_projection(receipts)
    assert projection['nonexecuted_attempts'] == []
    trace = actual_trace(receipts)
    assert trace['steps'][0]['status'] != 'succeeded'
    assert 'call_0' in projection['trace_inputs']


class ExportTrial(Trial):
    """Original trial operation shape with in-memory diagnostic container files."""
    def __init__(self, output):
        super().__init__(output)
        self.export_fail = False
        self.corrupt_export = False
        self.end_after_mkdir = False
        self.directories = {'/', '/app'}

    def _invoke(self, argv):
        if argv[:3] == ['docker', 'exec', self.container]:
            self.operations.append(argv)
            if argv[3] == '/bin/test':
                assert argv[3:6] == ['/bin/test', '!', '-d']
                return {'returncode': 1 if argv[6] in self.directories else 0,
                        'record': put(self.output / ('target-' + str(len(self.operations)) + '.json'), {'argv': argv})}
            assert argv[3:5] == ['/bin/mkdir', '-p']
            assert PurePosixPath(argv[5]).is_absolute()
            self.directories.add(argv[5])
            if self.end_after_mkdir:
                self.evaluated = True
            return {'returncode': 0, 'record': put(self.output / ('mkdir-' + str(len(self.operations)) + '.json'), {'argv': argv})}
        if argv[:2] == ['docker', 'cp'] and not argv[2].startswith(self.container + ':'):
            self.operations.append(argv)
            assert argv[3].startswith(self.container + ':')
            destination = argv[3].split(':', 1)[1]
            if not self.export_fail:
                self.files[destination] = b'corrupt' if self.corrupt_export else Path(argv[2]).read_bytes()
            return {'returncode': 1 if self.export_fail else 0,
                    'record': put(self.output / ('export-' + str(len(self.operations)) + '.json'), {'argv': argv})}
        return super()._invoke(argv)


def export_tools(tmp_path, *, snapshot=None):
    if snapshot is None:
        _, library, _, _ = fixture(tmp_path)
        snapshot = library['snapshot']
    materials = Materials(snapshot)
    trial = ExportTrial(tmp_path / 'trial')
    tools, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'calls', 'export-task')
    return materials, trial, tools, dispatch, receipts


def test_export_object_writes_canonical_json_and_returns_small_file_receipt(tmp_path):
    materials, trial, tools, dispatch, receipts = export_tools(tmp_path)
    arguments = {'capability_id': materials.snapshot['roots'][0]['id'], 'value': {},
                 'export_result': {'path': ['value'], 'container_path': '/app/output/count.json'}}
    schema = next(tool['parameters'] for tool in tools if tool['name'] == 'capability_call')
    Draft202012Validator(schema).validate(arguments)
    result = dispatch('capability_call', arguments)
    assert result['status'] == 'succeeded' and result['result_omitted'] is True
    assert 'result' not in result
    exported = result['exported_file']
    assert exported['status'] == 'exported' and exported['encoding'] == 'canonical_json_utf8'
    assert trial.files['/app/output/count.json'] == b'{"count":2}'
    detail = json.loads(verify(exported['record']))
    assert verify(detail['artifact']) == trial.files['/app/output/count.json']
    assert detail['artifact']['sha256'] == exported['sha256'] == detail['copy_check']['sha256']
    assert detail['source_receipt'] == result['receipt']
    assert len(detail['operations']) == 4 and all(verify(ref) for ref in detail['operations'])
    assert receipts[0]['status'] == 'succeeded' and receipts[0]['result_export'] == exported


def test_string_export_preserves_utf8_and_newlines_without_echoing_source(tmp_path):
    materials, trial, _, dispatch, _ = export_tools(tmp_path)
    original = materials.execute
    source = 'export const 名称 = "雪";\r\n' * 400
    def execute(*args):
        executed = original(*args)
        executed['trace']['result']['stdout'] = source
        executed['execution_ref'] = put(Path(executed['execution_ref']['path']), executed['trace'])
        return executed
    materials.execute = execute
    result = dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'value': {},
        'export_result': {'path': ['stdout'], 'container_path': '/app/generated.js'}})
    assert trial.files['/app/generated.js'] == source.encode('utf-8')
    assert result['exported_file']['encoding'] == 'utf8'
    assert result['exported_file']['bytes'] == len(source.encode('utf-8'))
    assert 'export const' not in json.dumps(result)
    assert len(json.dumps(result)) < len(source) / 4


@pytest.mark.parametrize('specification', [
    {'path': ['value'], 'container_path': 'relative.js'},
    {'path': ['value'], 'container_path': '/'},
    {'path': ['value'], 'container_path': '/app/directory/'},
    {'path': ['value'], 'container_path': '/app/..'},
    {'path': ['value'], 'container_path': '/app/.'},
    {'path': ['value'], 'container_path': '/app/bad\x00.js'},
    {'path': [0], 'container_path': '/app/result.json'},
    {'container_path': '/app/result.json'}])
def test_invalid_export_request_does_not_execute_or_create_native_edge(tmp_path, specification):
    materials, trial, _, dispatch, receipts = export_tools(tmp_path)
    with pytest.raises(ValueError):
        dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'],
                                    'value': {}, 'export_result': specification})
    assert materials.executions == [] and trial.operations == []
    projection = capability_trace_projection(receipts)
    assert projection['calls'] == [] and len(projection['nonexecuted_attempts']) == 1


@pytest.mark.parametrize('failure', ['copy', 'changed_bytes', 'missing_result_field', 'ended'])
def test_export_failure_keeps_genuine_runtime_success_and_its_binding_available(tmp_path, failure):
    snapshot = run_driver({'action': 'seed', 'owner': 'export-failure-diagnostic'})
    trial = ExportTrial(tmp_path / 'trial')
    materials = RuntimeMaterials(snapshot)
    _, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'calls', 'export-failure-task')
    trial.export_fail = failure == 'copy'
    trial.corrupt_export = failure == 'changed_bytes'
    trial.end_after_mkdir = failure == 'ended'
    first = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 3,
        'export_result': {'path': ['missing'] if failure == 'missing_result_field' else ['value'],
                          'container_path': '/app/output.json'}})
    assert first['status'] == 'succeeded' and first['exported_file']['status'] == 'failed'
    assert receipts[0]['status'] == 'succeeded'
    assert actual_trace(receipts)['steps'][0]['status'] == 'succeeded'
    if failure == 'ended':
        assert all(operation[:2] != ['docker', 'cp'] for operation in trial.operations)
        with pytest.raises(ValueError, match='task_not_active'):
            dispatch('capability_call', {'capability_id': snapshot['roots'][1]['id'],
                                        'input_binding': result_binding(first['call_id'])})
    else:
        second = dispatch('capability_call', {'capability_id': snapshot['roots'][1]['id'],
                                             'input_binding': result_binding(first['call_id'])})
        assert second['status'] == 'succeeded'
        assert actual_trace(receipts)['steps'][1]['input_binding']['fields']['value']['kind'] == 'step'


def test_successful_original_runtime_result_exports_without_rewriting_its_trace(tmp_path):
    snapshot = run_driver({'action': 'seed', 'owner': 'native-export-diagnostic'})
    materials = RuntimeMaterials(snapshot)
    trial = ExportTrial(tmp_path / 'trial')
    _, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'calls', 'native-export-task')
    result = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 3,
        'export_result': {'path': [], 'container_path': '/app/native-result.json'}})
    assert result['exported_file']['status'] == 'exported'
    assert json.loads(trial.files['/app/native-result.json']) == json.loads(verify(result['receipt']))['result']
    assert receipts[0]['trace'] == json.loads(verify(result['receipt']))
    assert actual_trace(receipts)['steps'][0]['result'] == receipts[0]['trace']['result']


def test_export_does_not_copy_a_directory_back_as_the_requested_file(tmp_path):
    materials, trial, _, dispatch, receipts = export_tools(tmp_path)
    result = dispatch('capability_call', {'capability_id': materials.snapshot['roots'][0]['id'], 'value': {},
        'export_result': {'path': ['value'], 'container_path': '/app'}})
    assert result['status'] == 'succeeded'
    assert 'target_is_directory' in result['exported_file']['error']
    assert not any(operation[:2] == ['docker', 'cp'] for operation in trial.operations)
    assert receipts[0]['status'] == 'succeeded'


def test_export_receipt_write_failure_does_not_relabel_native_execution(tmp_path, monkeypatch):
    import src.adapters.benchmark_capability_tools as bridge
    snapshot = run_driver({'action': 'seed', 'owner': 'export-audit-diagnostic'})
    materials = RuntimeMaterials(snapshot)
    trial = ExportTrial(tmp_path / 'trial')
    _, dispatch, receipts = benchmark_capability_tools(materials, trial, tmp_path / 'calls', 'export-audit-task')
    original_save = bridge.save
    def save(path, value):
        if Path(path).name == 'export.json':
            raise OSError('diagnostic_export_receipt_unwritable')
        return original_save(path, value)
    monkeypatch.setattr(bridge, 'save', save)
    outcome = dispatch('capability_call', {'capability_id': snapshot['roots'][0]['id'], 'value': 3,
        'export_result': {'path': ['value'], 'container_path': '/app/export.json'}})
    assert outcome['status'] == 'succeeded'
    assert 'receipt_unwritable' in outcome['exported_file']['error']
    assert receipts[0]['status'] == 'succeeded'
    assert actual_trace(receipts)['steps'][0]['status'] == 'succeeded'
