"""Expose registered native Capabilities inside one existing benchmark task.

The model selects real calls. File copies and JSON argument projections are host
bindings with explicit provenance. They do not manufacture Agent trajectories
or infer data dependencies between separate calls.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath

from .capability_contract import _binding, capability_digest, validate_capability_snapshot
from .capability_feedback import file_ref, verify
from .capability_improvement import save
from .capability_motif_learning import _bind, capture_capability_trace


def _resolve_call_binding(binding, records, snapshot, task_id, fingerprint):
    available = {row['id']: row for row in records if row.get('status') == 'succeeded'}
    _binding(binding, set(available))
    pending = [binding]
    referenced = set()
    while pending:
        item = pending.pop()
        if item['kind'] == 'input':
            raise ValueError('benchmark_capability_binding_input_source_unavailable: use value or input_file for external inputs')
        if item['kind'] == 'step':
            referenced.add(item['step_id'])
        elif item['kind'] == 'object':
            pending.extend(item['fields'].values())
        elif item['kind'] == 'array':
            pending.extend(item['items'])
    results = {}
    sources = []
    for identifier in sorted(referenced):
        row = available[identifier]
        if (row['task_id'] != task_id or row['task_fingerprint'] != fingerprint
                or row['snapshot'] != snapshot):
            raise ValueError('benchmark_capability_binding_source_scope_changed')
        # The original capture checks argument/result hashes, exact root, native
        # completion evidence and nested receipts before the result is reused.
        checked = capture_capability_trace(snapshot, task_id=task_id, task_input=row['arguments'],
            task_fingerprint=fingerprint, calls=[{'id': identifier, 'capability': row['capability'],
                'input_binding': {'kind': 'input', 'path': []}, 'execution_ref': row['execution_ref']}])
        results[identifier] = checked['steps'][0]['result']
        sources.append({'call_id': identifier, 'execution_ref': row['execution_ref']})
    return _bind(binding, {}, results), sources


def _validate_export(specification):
    if not isinstance(specification, dict) or set(specification) != {'path', 'container_path'}:
        raise ValueError('benchmark_capability_export_fields_required')
    _binding({'kind': 'step', 'step_id': 'result', 'path': specification['path']}, {'result'})
    path = specification['container_path']
    if (not isinstance(path, str) or not PurePosixPath(path).is_absolute()
            or '\x00' in path or not path.strip('/') or path.endswith('/')
            or path.split('/')[-1] in ('.', '..')):
        raise ValueError('benchmark_capability_export_container_file_required')


def _export_result(trial, executed, specification, directory):
    record = {'origin': 'host_delivery_from_original_runtime_result', 'status': 'failed',
              'source_receipt': executed['execution_ref'], 'source_path': specification['path'],
              'container_path': specification['container_path'], 'operations': []}
    try:
        if not trial.prepared or trial.evaluated:
            raise ValueError('benchmark_capability_task_not_active')
        original = json.loads(verify(executed['execution_ref']))
        selected = _bind({'kind': 'step', 'step_id': 'result', 'path': specification['path']}, {},
                         {'result': original.get('result')})
        if isinstance(selected, str):
            payload, encoding = selected.encode('utf-8'), 'utf8'
        else:
            payload = json.dumps(selected, ensure_ascii=False, allow_nan=False,
                                 sort_keys=True, separators=(',', ':')).encode('utf-8')
            encoding = 'canonical_json_utf8'
        artifact = directory / 'exported-result'
        artifact.write_bytes(payload)
        artifact.chmod(0o400)
        record.update(artifact=file_ref(artifact), bytes=len(payload), encoding=encoding)
        parent = str(PurePosixPath(specification['container_path']).parent)
        prepared = trial._invoke(['docker', 'exec', trial.container, '/bin/mkdir', '-p', parent])
        record['operations'].append(prepared.get('record'))
        if prepared['returncode'] != 0:
            raise ValueError('benchmark_capability_export_directory_failed')
        if not trial.prepared or trial.evaluated:
            raise ValueError('benchmark_capability_task_not_active')
        target = trial._invoke(['docker', 'exec', trial.container, '/bin/test', '!', '-d', specification['container_path']])
        record['operations'].append(target.get('record'))
        if target['returncode'] != 0:
            raise ValueError('benchmark_capability_export_target_is_directory')
        if not trial.prepared or trial.evaluated:
            raise ValueError('benchmark_capability_task_not_active')
        copied = trial._invoke(['docker', 'cp', str(artifact), trial.container + ':' + specification['container_path']])
        record['operations'].append(copied.get('record'))
        if copied['returncode'] != 0:
            raise ValueError('benchmark_capability_export_copy_failed')
        checked = directory / 'exported-copy-check'
        if not trial.prepared or trial.evaluated:
            raise ValueError('benchmark_capability_task_not_active')
        readback = trial._invoke(['docker', 'cp', trial.container + ':' + specification['container_path'], str(checked)])
        record['operations'].append(readback.get('record'))
        if readback['returncode'] != 0 or checked.is_symlink() or not checked.is_file() or checked.read_bytes() != payload:
            raise ValueError('benchmark_capability_export_copy_unverified')
        record.update(status='exported', sha256=record['artifact']['sha256'], copy_check=file_ref(checked))
    except Exception as error:
        record['error'] = type(error).__name__ + ':' + str(error)
    save(directory / 'export.json', record)
    return {**{key: record[key] for key in ('status', 'container_path', 'bytes', 'sha256', 'encoding', 'error') if key in record},
            'record': file_ref(directory / 'export.json')}


def benchmark_capability_tools(materials, trial, directory, task_id):
    """Return tools, a dispatcher and original Runtime-call records for this task."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError('benchmark_capability_task_id_required')
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    catalog = materials.catalog()
    snapshot = validate_capability_snapshot(catalog['snapshot'], materials.owner)
    manifest = trial.manifest()
    fingerprint = manifest.get('input_fingerprint', manifest.get('source_identity'))
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
         'Read that schema first; composition calls require value or input_binding rather than the file shorthand. '
         'input_binding uses the existing Binding over COMPLETE Runtime arguments, usually {value: ...} for a primitive. '
         'Use kind=step with step_id=an earlier successful call_id and path=output field names for result dependencies. '
         'kind=object uses fields, kind=array uses items, and kind=literal uses value. kind=input has no source here. '
         'Optionally export_result selects a result field path and absolute container_path. Strings are written as UTF-8, '
         'other values as compact sorted JSON. Export calls return file metadata and receipt instead of the large result.',
         'parameters': {'type': 'object', 'properties': {'capability_id': {'type': 'string'},
             'input_file': {'type': 'string'}, 'value': {}, 'input_binding': {'type': 'object',
                 'description': 'Existing step/literal/object/array Binding for complete Runtime arguments; step_id refers to this task session call_id.'},
             'export_result': {'type': 'object', 'properties': {
                 'path': {'type': 'array', 'items': {'type': 'string'}}, 'container_path': {'type': 'string'}},
                 'required': ['path', 'container_path'], 'additionalProperties': False}},
             'required': ['capability_id'], 'additionalProperties': False,
             'oneOf': [{'required': ['input_file']}, {'required': ['value']}, {'required': ['input_binding']}]}}]

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
        if (set(arguments) - {'capability_id', 'input_file', 'value', 'input_binding', 'export_result'}
                or 'capability_id' not in arguments
                or sum(key in arguments for key in ('input_file', 'value', 'input_binding')) != 1):
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
            if 'export_result' in arguments:
                _validate_export(arguments['export_result'])
            composition = capabilities[reference['id']]['implementation']['kind'] == 'composition'
            if composition and 'input_file' in arguments:
                required = capabilities[reference['id']]['contract']['input_schema'].get('required', [])
                raise ValueError('benchmark_capability_composition_requires_value_fields:' + ','.join(required))
            binding = {'kind': 'input', 'path': [identifier]}
            if 'input_binding' in arguments:
                binding = copy.deepcopy(arguments['input_binding'])
                value, binding_sources = _resolve_call_binding(binding, receipts[:-1], snapshot, task_id, fingerprint)
                row.update(binding_sources=binding_sources, input_projection='explicit_original_binding_from_runtime_receipts')
            elif 'input_file' in arguments:
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
            row['runtime_started'] = True
            executed = (materials.execute_arguments(reference, value, output / 'runtime', task_id)
                        if composition or 'input_binding' in arguments
                        else materials.execute(reference, value, output / 'runtime', task_id))
            trace = executed['trace']
            if 'input_binding' in arguments and capability_digest(executed['arguments']) != capability_digest(value):
                raise ValueError('benchmark_capability_bound_arguments_changed')
            row.update(arguments=executed['arguments'], execution_ref=executed['execution_ref'], trace=trace)
            if (executed['snapshot']['digest'] != snapshot['digest']
                    or trace.get('task_id') != task_id or trace.get('root') != reference
                    or trace.get('snapshot_sha256') != snapshot['digest']):
                raise ValueError('benchmark_capability_runtime_scope_changed')
            original = json.loads(verify(executed['execution_ref']))
            if capability_digest(original) != capability_digest(trace):
                raise ValueError('benchmark_capability_runtime_trace_changed')
            row.update(status=trace['status'], arguments=executed['arguments'],
                       input_binding=binding,
                       execution_ref=executed['execution_ref'], trace=trace)
            result = {'status': trace['status'], 'call_id': identifier,
                      'result': copy.deepcopy(trace.get('result')), 'receipt': executed['execution_ref']}
            if 'export_result' in arguments:
                if trace['status'] == 'succeeded':
                    try:
                        exported = _export_result(trial, executed, arguments['export_result'], output)
                    except Exception as export_error:
                        exported = {'status': 'failed', 'error': type(export_error).__name__ + ':' + str(export_error)}
                else:
                    exported = {'status': 'not_exported', 'reason': 'native_execution_not_succeeded'}
                row['result_export'] = exported
                result.pop('result')
                result.update(result_omitted=True, exported_file=exported)
        except Exception as error:
            row.update(status='failed', error=type(error).__name__ + ':' + str(error))
            # Native Script failures can write their genuine trace before the
            # adapter raises. Keep that fixed host output as a failed graph node.
            trace_path, args_path = output / 'runtime/trace.json', output / 'runtime/args.json'
            if row.get('runtime_started') and 'execution_ref' not in row and trace_path.is_file() and args_path.is_file():
                row['runtime_evidence'] = [file_ref(trace_path), file_ref(args_path)]
                try:
                    failed = json.loads(verify(row['runtime_evidence'][0]))
                    if (failed.get('status') == 'succeeded' or failed.get('task_id') != task_id
                            or failed.get('root') != reference or failed.get('snapshot_sha256') != snapshot['digest']):
                        raise ValueError('benchmark_capability_failed_runtime_scope_changed')
                    row.update(status=failed['status'], trace=failed,
                               arguments=json.loads(verify(row['runtime_evidence'][1])),
                               execution_ref=row['runtime_evidence'][0], input_binding=binding)
                except Exception as recovery_error:
                    row['runtime_recovery_error'] = type(recovery_error).__name__ + ':' + str(recovery_error)
            raise
        finally:
            save(output / 'call.json', row)
            row['attempt_ref'] = file_ref(output / 'call.json')
        return result

    return tools, dispatch, receipts


def capability_trace_projection(receipts):
    """Project recorded real Runtime arguments for original capture_capability_trace.

    Attempts without a captured native receipt remain separately indexed. Real
    Runtime failures stay in the graph as original learner barriers. Original
    call indices remain increasing, including gaps; dependencies are explicit.
    """
    if not isinstance(receipts, list) or not receipts:
        raise ValueError('benchmark_capability_actual_calls_required')
    first = receipts[0]
    calls = []
    inputs = {}
    sources = []
    seen = set()
    attempts = set()
    nonexecuted = []
    indices = []
    last_index = -1
    results = {}
    for row in receipts:
        if (type(row.get('call_index')) is not int or row['call_index'] <= last_index
                or row['task_id'] != first['task_id']
                or row['task_fingerprint'] != first['task_fingerprint']
                or row['snapshot']['digest'] != first['snapshot']['digest']):
            raise ValueError('benchmark_capability_incomplete_or_mixed_trace')
        last_index = row['call_index']
        identifier = row['id']
        if identifier in attempts:
            raise ValueError('benchmark_capability_duplicate_call')
        attempts.add(identifier)
        if 'execution_ref' not in row:
            nonexecuted.append({key: copy.deepcopy(row[key]) for key in
                ('id', 'call_index', 'status', 'error', 'model_arguments', 'runtime_started',
                 'runtime_evidence', 'runtime_recovery_error', 'attempt_ref') if key in row})
            continue
        verify(row['execution_ref'])
        indices.append(row['call_index'])
        _binding(row['input_binding'], seen)
        if row['input_binding']['kind'] == 'input':
            inputs[identifier] = copy.deepcopy(row['arguments'])
        bound = _bind(row['input_binding'], inputs, results)
        if capability_digest(bound) != capability_digest(row['arguments']):
            raise ValueError('benchmark_capability_projected_arguments_changed')
        seen.add(identifier)
        results[identifier] = json.loads(verify(row['execution_ref'])).get('result')
        calls.append({key: copy.deepcopy(row[key]) for key in
                      ('id', 'capability', 'input_binding', 'execution_ref')})
        if row.get('source_file') is not None:
            verify(row['source_file']['file'])
            sources.append(copy.deepcopy(row['source_file']))
    return {'snapshot': copy.deepcopy(first['snapshot']), 'task_id': first['task_id'],
            'task_fingerprint': first['task_fingerprint'], 'trace_inputs': inputs, 'calls': calls,
            'source_files': sources, 'native_call_indices': indices, 'nonexecuted_attempts': nonexecuted,
            'nonexecuted_scope': 'No captured native receipt; runtime_started retains uncertain backend execution.',
            'scope': 'actual_native_arguments_and_explicit_original_bindings_no_inferred_dependencies'}
