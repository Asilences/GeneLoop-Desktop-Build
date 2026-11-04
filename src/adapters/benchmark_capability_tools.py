"""Expose registered native Capabilities inside one existing benchmark task.

The model selects real calls. File copies and JSON argument projections are host
bindings with explicit provenance. They do not manufacture Agent trajectories
or infer data dependencies between separate calls.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath

from .capability_contract import capability_digest, validate_capability_snapshot
from .capability_feedback import file_ref, verify
from .capability_improvement import save


def benchmark_capability_tools(materials, trial, directory, task_id):
    """Return tools, a dispatcher and original Runtime-call records for this task."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError('benchmark_capability_task_id_required')
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    catalog = materials.catalog()
    snapshot = validate_capability_snapshot(catalog['snapshot'], materials.owner)
    manifest = trial.manifest()
    fingerprint = manifest.get('source_identity')
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError('benchmark_capability_task_source_required')
    manifest_path = Path(trial.output) / 'manifest.json'
    manifest_ref = file_ref(manifest_path) if manifest_path.is_file() else None
    receipts = []
    cards = {card['capability']['id']: card for card in catalog.get('catalog', [])}
    capabilities = {cap['id']: cap for cap in snapshot['capabilities']}
    tools = [
        {'name': 'capability_list', 'description': 'List available certified reusable computations and their input/output interfaces.',
         'parameters': {'type': 'object', 'properties': {
             'offset': {'type': 'integer', 'minimum': 0},
             'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}, 'additionalProperties': False}},
        {'name': 'capability_call', 'description': 'Execute a listed certified computation on current task input. '
         'For a primitive, value is its complete run(value) input; input_file may instead name an absolute file '
         'in this task container, mechanically wrapped as {data: parsed_JSON} or {text: UTF8_text}. '
         'For a composition, value is the complete object matching its listed input_schema. '
         'Read that schema first; composition calls require value rather than the file shorthand.',
         'parameters': {'type': 'object', 'properties': {'capability_id': {'type': 'string'},
             'input_file': {'type': 'string'}, 'value': {}},
             'required': ['capability_id'], 'additionalProperties': False,
             'oneOf': [{'required': ['input_file']}, {'required': ['value']}]}}]

    def dispatch(name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError('benchmark_capability_arguments_invalid')
        if name == 'capability_list':
            if set(arguments) - {'offset', 'limit'}:
                raise ValueError('benchmark_capability_list_arguments_invalid')
            offset, limit = arguments.get('offset', 0), arguments.get('limit', 10)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError('benchmark_capability_list_page_invalid')
            roots = snapshot['roots']
            end = min(offset + limit, len(roots))
            return {'snapshot_sha256': snapshot['digest'], 'total': len(roots),
                    'next_offset': end if end < len(roots) else None, 'capabilities': [
                {'capability_id': reference['id'], 'capability': reference,
                 'description': cards.get(reference['id'], {}).get('description'),
                 'input_schema': capabilities[reference['id']]['contract']['input_schema'],
                 'output_schema': capabilities[reference['id']]['contract']['output_schema'],
                 'effects': capabilities[reference['id']]['contract']['effects']}
                for reference in roots[offset:end]]}
        if name != 'capability_call':
            raise ValueError('benchmark_capability_tool_unknown')
        if (set(arguments) - {'capability_id', 'input_file', 'value'}
                or 'capability_id' not in arguments
                or ('input_file' in arguments) == ('value' in arguments)):
            raise ValueError('benchmark_capability_one_input_required')
        reference = next((ref for ref in snapshot['roots'] if ref['id'] == arguments['capability_id']), None)
        if reference is None:
            raise ValueError('benchmark_capability_not_available')
        if not trial.prepared or trial.evaluated:
            raise ValueError('benchmark_capability_task_not_active')
        identifier = 'call_' + str(len(receipts))
        output = directory / identifier
        output.mkdir(mode=0o700)
        row = {'id': identifier, 'call_index': len(receipts), 'capability': reference,
               'status': 'started', 'task_id': task_id,
               'task_fingerprint': fingerprint, 'task_manifest': manifest_ref,
               'snapshot': snapshot, 'model_arguments': copy.deepcopy(arguments),
               'source_file': None, 'input_projection': 'actual_runtime_arguments_no_inferred_cross_call_dependency'}
        receipts.append(row)
        try:
            composition = capabilities[reference['id']]['implementation']['kind'] == 'composition'
            if composition and 'input_file' in arguments:
                required = capabilities[reference['id']]['contract']['input_schema'].get('required', [])
                raise ValueError('benchmark_capability_composition_requires_value_fields:' + ','.join(required))
            if 'input_file' in arguments:
                path = arguments['input_file']
                if (not isinstance(path, str) or not PurePosixPath(path).is_absolute()
                        or '\x00' in path or not path.strip('/')):
                    raise ValueError('benchmark_capability_container_file_required')
                target = output / 'container-input'
                copied = trial._invoke(['docker', 'cp', trial.container + ':' + path, str(target)])
                if copied['returncode'] != 0 or target.is_symlink() or not target.is_file():
                    raise ValueError('benchmark_capability_container_file_collection_failed')
                value = file_ref(target)
                row['source_file'] = {'container_path': path, 'file': value,
                    'copy_evidence': copied.get('record'), 'origin': 'host_collection_at_actual_tool_call',
                    'wrapper': 'json_data_or_utf8_text_by_native_material_adapter'}
            else:
                value = arguments['value']
            executed = (materials.execute_arguments(reference, value, output / 'runtime', task_id)
                        if composition else materials.execute(reference, value, output / 'runtime', task_id))
            trace = executed['trace']
            row.update(arguments=executed['arguments'], execution_ref=executed['execution_ref'], trace=trace)
            if (executed['snapshot']['digest'] != snapshot['digest']
                    or trace.get('task_id') != task_id or trace.get('root') != reference
                    or trace.get('snapshot_sha256') != snapshot['digest']):
                raise ValueError('benchmark_capability_runtime_scope_changed')
            original = json.loads(verify(executed['execution_ref']))
            if capability_digest(original) != capability_digest(trace):
                raise ValueError('benchmark_capability_runtime_trace_changed')
            row.update(status=trace['status'], arguments=executed['arguments'],
                       input_binding={'kind': 'input', 'path': [identifier]},
                       execution_ref=executed['execution_ref'], trace=trace)
            result = {'status': trace['status'], 'call_id': identifier,
                      'result': copy.deepcopy(trace.get('result')), 'receipt': executed['execution_ref']}
        except Exception as error:
            row.update(status='failed', error=type(error).__name__ + ':' + str(error))
            raise
        finally:
            save(output / 'call.json', row)
        return result

    return tools, dispatch, receipts


def capability_trace_projection(receipts):
    """Project recorded real Runtime arguments for original capture_capability_trace.

    Failed tool collection or incomplete native execution remains in the source
    records. The caller may select complete successful contiguous subtraces for
    this projection; cross-call dependencies are never guessed from equal data.
    """
    if not isinstance(receipts, list) or not receipts:
        raise ValueError('benchmark_capability_actual_calls_required')
    first = receipts[0]
    calls = []
    inputs = {}
    sources = []
    for row in receipts:
        if (row.get('status') != 'succeeded' or 'execution_ref' not in row
                or row.get('call_index') != first.get('call_index', 0) + len(calls)
                or row['task_id'] != first['task_id']
                or row['task_fingerprint'] != first['task_fingerprint']
                or row['snapshot']['digest'] != first['snapshot']['digest']):
            raise ValueError('benchmark_capability_incomplete_or_mixed_trace')
        verify(row['execution_ref'])
        identifier = row['id']
        if identifier in inputs:
            raise ValueError('benchmark_capability_duplicate_call')
        inputs[identifier] = copy.deepcopy(row['arguments'])
        calls.append({key: copy.deepcopy(row[key]) for key in
                      ('id', 'capability', 'input_binding', 'execution_ref')})
        if row.get('source_file') is not None:
            verify(row['source_file']['file'])
            sources.append(copy.deepcopy(row['source_file']))
    return {'snapshot': copy.deepcopy(first['snapshot']), 'task_id': first['task_id'],
            'task_fingerprint': first['task_fingerprint'], 'trace_inputs': inputs, 'calls': calls,
            'source_files': sources,
            'scope': 'input_projection_of_actual_native_calls_not_inferred_task_or_dependency_graph'}
