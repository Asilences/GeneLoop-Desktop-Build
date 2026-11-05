"""Project witnessed Capability calls into the existing Motif learning pipeline.

This is an opt-in offline adapter, not a second IR, registry or controller.
It never grants a certificate: mined candidates still require the ordinary
Capability Store's independent execution/quality validation before publication.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess

from jsonschema import Draft202012Validator

from .capability_builder import compile_proposal
from .capability_contract import capability_digest, capability_ref, validate_capability_snapshot, _binding, _tag
from .capability_improvement import evidence
from .dsh_trajectory import DshTrace, ToolContract, ToolRecord, mine_dsh_traces
from .rsi_protocol import validate_record
from src.motif_core.offline.trace_compiler import compile_read_motif, certify_read_motif


def _fail(reason):
    raise ValueError('capability_motif_' + reason)


def _trajectory_digest(value):
    """Hash bounded execution evidence using the existing canonical encoding.

    A trajectory retains inputs and witnessed arguments, so its envelope can be
    larger than one Capability definition or one Runtime value. Their existing
    limits remain enforced separately.
    """
    encoded = json.dumps(_tag(value), ensure_ascii=False, separators=(',', ':')).encode()
    if len(encoded) > 32_000_000:
        _fail('trajectory_too_large')
    return hashlib.sha256(encoded).hexdigest()


def _at(value, path):
    for field in path:
        if not isinstance(value, dict) or field not in value:
            _fail('binding_path_missing')
        value = value[field]
    return copy.deepcopy(value)


def _bind(binding, task_input, results):
    kind = binding['kind']
    if kind == 'input': return _at(task_input, binding['path'])
    if kind == 'step': return _at(results[binding['step_id']], binding['path'])
    if kind == 'literal': return copy.deepcopy(binding['value'])
    if kind == 'array': return [_bind(v, task_input, results) for v in binding['items']]
    return {k: _bind(v, task_input, results) for k, v in binding['fields'].items()}


def _wire_hashes(values):
    """Use the Runtime's exact JSON.stringify hash, including numeric keys/floats."""
    for value in values:
        capability_digest(value)
    result = subprocess.run(['node', '-e',
        "const fs=require('fs'),c=require('crypto');const v=JSON.parse(fs.readFileSync(0,'utf8'));"
        "process.stdout.write(JSON.stringify(v.map(x=>c.createHash('sha256').update(JSON.stringify(x)).digest('hex'))));"],
        input=json.dumps(values, ensure_ascii=False, allow_nan=False), text=True, encoding='utf-8',
        capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)


def _receipt_tree(receipts, root, capabilities, succeeded):
    """Recheck the actual Runtime tree and F02/native completion witnesses."""
    by_call = {r['call_id']: r for r in receipts}; visited = set()
    def visit(receipt):
        identity = receipt['call_id']
        if identity in visited: _fail('receipt_cycle_or_shared_child')
        visited.add(identity)
        cap = capabilities[receipt['capability']['id']]
        implementation = cap['implementation']
        if receipt.get('kind') != implementation['kind']: _fail('receipt_kind_changed')
        children = receipt.get('child_call_ids', [])
        if len(children) != len(set(children)): _fail('receipt_child_repeated')
        if succeeded and (receipt.get('dispatched') is not True or receipt.get('reason') is not None):
            _fail('execution_witness_missing')
        for child in children:
            if child not in by_call or by_call[child].get('parent_call_id') != identity:
                _fail('receipt_parent_changed')
        if implementation['kind'] == 'composition':
            expected = [s['capability'] for s in implementation['steps']]
            observed = [by_call[c]['capability'] for c in children]
            if observed != expected[:len(observed)] or succeeded and observed != expected:
                _fail('receipt_composition_changed')
            if receipt.get('backend_receipt') is not None or receipt.get('events') != []:
                _fail('receipt_composition_witness_invalid')
        else:
            if children: _fail('leaf_has_children')
            if succeeded:
                native = receipt.get('backend_receipt') or {}
                events = receipt.get('events', [])
                if (native.get('call_id') != identity or native.get('status') != 'succeeded' or
                        not isinstance(native.get('operation'), str) or
                        native.get('task_id', receipt['task_id']) != receipt['task_id'] or
                        native.get('parent_call_id', receipt['parent_call_id']) != receipt['parent_call_id'] or
                        len(events) != 2):
                    _fail('native_completion_missing')
                payloads = [validate_record(e)['payload'] for e in events]
                if ([p.get('phase') for p in payloads] != ['started', 'succeeded'] or
                        any(e['record_type'] != 'execution_event' for e in events)):
                    _fail('completion_events_missing')
                for payload in payloads:
                    if (payload['call_id'] != identity or payload['task_id'] != receipt['task_id'] or
                            payload['operation'] != native['operation'] or
                            payload['arguments_sha256'] != receipt['arguments_sha256'] or payload['error'] is not None):
                        _fail('completion_events_changed')
                if payloads[1]['result_sha256'] != receipt['result_sha256'] or any(
                        payloads[0][key] != payloads[1][key] for key in ('permission_ref', 'versions', 'dependencies')):
                    _fail('guard_evidence_changed')
        for child in children: visit(by_call[child])
    visit(root)
    if visited != set(by_call): _fail('orphan_receipt')


def _validation_manifest(snapshot, execution, task_input, reference):
    """Observe a host-granted candidate container, never certify that container."""
    raw = evidence(reference); manifest = json.loads(raw); grant = manifest.get('grant', {})
    if (manifest.get('format') != 'script_capability_task_v1' or
            manifest.get('owner') != snapshot['owner'] or manifest.get('task_id') != execution.get('task_id') or
            grant.get('task_id') != execution.get('task_id') or grant.get('snapshot_sha256') != snapshot['digest'] or
            grant.get('root') != execution.get('root') or grant.get('arguments_sha256') != capability_digest(task_input) or
            grant.get('mode') != 'validate' or grant.get('effects') != ['read'] or grant.get('revoked') is not False or
            execution.get('format') != 'script_capability_trace_v1' or execution.get('mode') != 'validate' or
            execution.get('grant_id') != grant.get('id') or not grant.get('id') or
            execution.get('validation_grant_id') != grant.get('id') or
            execution.get('manifest_sha256') != hashlib.sha256(raw).hexdigest() or
            execution.get('arguments_sha256') != capability_digest(task_input) or
            execution.get('input_versions') != manifest.get('inputs')):
        _fail('candidate_validation_grant_changed')
    # Manifest is a frozen trusted-host input. Its selected registry and native
    # libraries are rechecked, not inferred from candidate metadata.
    from pathlib import Path
    actual = validate_capability_snapshot(json.loads(Path(manifest['registry_path']).read_bytes()), snapshot['owner'])
    if actual != snapshot: _fail('candidate_validation_snapshot_changed')
    for ref in manifest.get('libraries', []): evidence(ref)
    root = execution['root']
    for cap in snapshot['capabilities']:
        if capability_ref(cap) == root:
            if cap['certification'] != 'candidate' or cap['implementation']['kind'] != 'composition':
                _fail('candidate_validation_container_required')
        elif cap['certification'] != 'certified' or cap['lifecycle'] != 'active':
            _fail('candidate_validation_dependency_not_certified')
    return manifest


def capture_capability_trace(snapshot, *, task_id, task_input, task_fingerprint, calls, role='task',
                             _validation_manifest_ref=None):
    """Capture an actual host execution graph without flattening called capabilities.

    Each call supplies its original IR input_binding and immutable execution_ref.
    A hash is evidence integrity, not authentication of an untrusted filesystem;
    like CapabilityStore this adapter must be fed by the trusted task host.
    Failed calls remain barriers, not successful learning examples.
    """
    snapshot = validate_capability_snapshot(snapshot)
    if role not in ('task', 'builder') or not isinstance(task_id, str) or not task_id or not task_fingerprint:
        _fail('task_identity_required')
    if not isinstance(calls, list) or not calls or len(calls) > 64:
        _fail('bounded_calls_required')
    by_id = {c['id']: c for c in snapshot['capabilities']}
    roots = snapshot['roots']; results = {}; steps = []; seen_receipts = set()
    for call in calls:
        if set(call) != {'id', 'capability', 'input_binding', 'execution_ref'}:
            _fail('call_shape_invalid')
        identity = call['id']
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', identity) or identity in results:
            _fail('call_identity_invalid')
        ref = call['capability']
        if ref not in roots: _fail('call_not_visible')
        cap = by_id[ref['id']]
        if (cap['certification'] != 'certified' or cap['lifecycle'] != 'active') and _validation_manifest_ref is None:
            _fail('call_not_certified')
        _binding(call['input_binding'], set(results))
        args = _bind(call['input_binding'], task_input, results)
        execution = json.loads(evidence(call['execution_ref']))
        if _validation_manifest_ref is not None:
            if len(calls) != 1 or role != 'builder': _fail('candidate_validation_builder_container_required')
            _validation_manifest(snapshot, execution, task_input, _validation_manifest_ref)
        receipts = execution.get('receipts', [])
        outer = [r for r in receipts if r.get('parent_call_id') is None]
        if len(outer) != 1: _fail('root_receipt_required')
        root = outer[0]
        if (root.get('capability') != ref or root.get('task_id') != task_id or
                root.get('snapshot_sha256') != snapshot['digest']):
            _fail('receipt_scope_changed')
        if any(r.get('task_id') != task_id or r.get('snapshot_sha256') != snapshot['digest'] or
               r.get('capability') not in [capability_ref(c) for c in snapshot['capabilities']] for r in receipts):
            _fail('receipt_scope_changed')
        ids = [r.get('call_id') for r in receipts]
        if len(ids) != len(set(ids)) or set(ids) & seen_receipts: _fail('receipt_reused')
        seen_receipts.update(ids)
        for receipt in receipts:
            if any(child not in ids for child in receipt.get('child_call_ids', [])):
                _fail('receipt_child_missing')
            if receipt is not root and receipt.get('parent_call_id') not in ids:
                _fail('receipt_parent_missing')
        status = execution.get('status')
        if status != root.get('status'): _fail('receipt_status_changed')
        if (execution.get('owner', snapshot['owner']) != snapshot['owner'] or
                execution.get('task_id', task_id) != task_id or
                execution.get('snapshot_sha256', snapshot['digest']) != snapshot['digest'] or
                execution.get('root', ref) != ref):
            _fail('execution_scope_changed')
        args_sha, result_sha = _wire_hashes([args, execution.get('result')])
        if root.get('arguments_sha256') != args_sha: _fail('arguments_changed')
        succeeded = status == 'succeeded'
        if succeeded:
            if (root.get('result_sha256') != result_sha or
                    any(r.get('status') != 'succeeded' for r in receipts)):
                _fail('result_changed')
            if list(Draft202012Validator(cap['contract']['input_schema']).iter_errors(args)) or list(
                    Draft202012Validator(cap['contract']['output_schema']).iter_errors(execution['result'])):
                _fail('contract_mismatch')
        _receipt_tree(receipts, root, by_id, succeeded)
        results[identity] = execution.get('result')
        steps.append({'call_id': identity, 'kind': 'CapabilityCall', 'capability': copy.deepcopy(ref),
                      'input_binding': copy.deepcopy(call['input_binding']), 'arguments': args,
                      'result': copy.deepcopy(execution.get('result')), 'status': status,
                      'receipt_ref': copy.deepcopy(call['execution_ref']), 'runtime_call_id': root['call_id'],
                      'parent_trace_id': task_id, 'guard_evidence': copy.deepcopy(call['execution_ref']),
                      'output_refs': {'call_id': identity, 'path': []}})
    value = {'format': 'capability_trajectory_v1', 'projection': 'capability_calls_v1',
             'owner': snapshot['owner'], 'trace_id': task_id, 'task_id': task_id,
             'task_fingerprint': task_fingerprint, 'role': role, 'task_input': copy.deepcopy(task_input),
             'snapshot': copy.deepcopy(snapshot), 'calls': copy.deepcopy(calls), 'steps': steps,
             'evidence': [copy.deepcopy(c['execution_ref']) for c in calls],
             'quality': 'unreviewed', 'benefit': None}
    value['digest'] = _trajectory_digest(value)
    return value


def _checked(trace, owner):
    if not isinstance(trace, dict) or trace.get('owner') != owner:
        _fail('owner_changed')
    if trace.get('projection') == 'capability_composition_calls_v1':
        rebuilt = capture_composition_trace(trace['snapshot'], execution_ref=trace['execution_ref'],
            task_input=trace['execution_input'], task_fingerprint=trace['task_fingerprint'],
            parent_call_id=trace['parent_call_id'], role=trace['role'],
            validation_manifest_ref=trace.get('validation_manifest_ref'), available_snapshot=trace.get('available_snapshot'))
        if trace != rebuilt: _fail('trace_changed')
        return rebuilt
    rebuilt = capture_capability_trace(trace['snapshot'], task_id=trace['task_id'],
        task_input=trace['task_input'], task_fingerprint=trace['task_fingerprint'],
        calls=trace['calls'], role=trace['role'])
    if trace != rebuilt: _fail('trace_changed')
    return rebuilt


def _symbol(ref):
    return 'capability_' + ref['sha256']


def capture_composition_trace(snapshot, *, execution_ref, task_input, task_fingerprint,
                              parent_call_id=None, role='task', validation_manifest_ref=None, available_snapshot=None):
    """Project direct children from ORIGINAL Script Runtime evidence, without replay.

    Native stdout is decoded exactly as script_capability_runtime does. Every
    recovered node's input/output is checked against its original receipt hash;
    neither child receipts nor their parent IDs are rewritten as new executions.
    Other backends or missing output fail closed. Old evidence is never altered.
    """
    snapshot = validate_capability_snapshot(snapshot)
    execution = json.loads(evidence(execution_ref))
    # Reuse all existing root/tree, native completion, event and scope guards.
    checked = capture_capability_trace(snapshot, task_id=execution['task_id'], task_input=task_input,
        task_fingerprint=task_fingerprint, role=role, calls=[{'id': 'execution',
            'capability': execution['root'], 'input_binding': {'kind': 'input', 'path': []},
            'execution_ref': execution_ref}], _validation_manifest_ref=validation_manifest_ref)
    available = snapshot if available_snapshot is None else validate_capability_snapshot(available_snapshot, snapshot['owner'])
    if validation_manifest_ref is not None and (available_snapshot is None or role != 'builder'):
        _fail('candidate_validation_available_builder_library_required')
    if execution['status'] != 'succeeded': _fail('composition_success_required')
    receipts = {r['call_id']: r for r in execution['receipts']}
    root = next(r for r in receipts.values() if r['parent_call_id'] is None)
    selected = parent_call_id or root['call_id']
    if selected not in receipts: _fail('composition_parent_missing')
    caps = {c['id']: c for c in snapshot['capabilities']}; recovered = {}; hashes = []
    def visit(receipt, args):
        cap = caps[receipt['capability']['id']]; implementation = cap['implementation']
        if list(Draft202012Validator(cap['contract']['input_schema']).iter_errors(args)):
            _fail('contract_mismatch')
        if implementation['kind'] == 'legacy':
            legacy = implementation['legacy_ref']
            native = (receipt.get('backend_receipt') or {}).get('native_receipt') or {}
            stdout = native.get('output')
            if (legacy['backend'] != 'script_motif' or native.get('kind') != 'script_motif_receipt'
                    or native.get('program_id') != legacy['object_id'] or native.get('script_version') != legacy
                    or not isinstance(stdout, str) or native.get('network_evidence') != []
                    or hashlib.sha256(stdout.encode('utf-8')).hexdigest() != native.get('output_sha256')):
                _fail('script_output_witness_missing_or_changed')
            result = {'stdout': stdout}
            if 'value' in cap['contract']['output_schema'].get('properties', {}):
                try: result['value'] = json.loads(stdout)
                except (ValueError, TypeError): _fail('script_output_invalid_json')
        else:
            results = {}
            for step, child in zip(implementation['steps'], receipt['child_call_ids']):
                results[step['id']] = visit(receipts[child], _bind(step['arguments'], args, results))
            result = _bind(implementation['output'], args, results)
        if list(Draft202012Validator(cap['contract']['output_schema']).iter_errors(result)):
            _fail('contract_mismatch')
        recovered[receipt['call_id']] = {'arguments': args, 'result': result}
        hashes.extend([args, result])
        return result
    result = visit(root, task_input)
    wire = iter(_wire_hashes(hashes))
    # recovered preserves the same post-order in which hashes were collected.
    for identity in recovered:
        if (next(wire) != receipts[identity]['arguments_sha256'] or
                next(wire) != receipts[identity]['result_sha256']):
            _fail('recovered_call_hash_changed')
    if result != execution['result']: _fail('recovered_root_result_changed')
    parent = receipts[selected]; cap = caps[parent['capability']['id']]
    if cap['implementation']['kind'] != 'composition': _fail('composition_parent_required')
    steps = []
    for step, identity in zip(cap['implementation']['steps'], parent['child_call_ids']):
        receipt = receipts[identity]; child = caps[receipt['capability']['id']]
        if (receipt['capability'] not in available['roots'] or child['certification'] != 'certified'
                or child['lifecycle'] != 'active'):
            _fail('call_not_visible_or_certified')
        live = next(c for c in available['capabilities'] if c['id'] == child['id'])
        if live != child: _fail('call_available_version_changed')
        steps.append({'call_id': step['id'], 'kind': 'CapabilityCall',
            'capability': copy.deepcopy(receipt['capability']), 'input_binding': copy.deepcopy(step['arguments']),
            **copy.deepcopy(recovered[identity]), 'status': receipt['status'],
            'receipt_ref': copy.deepcopy(execution_ref), 'runtime_call_id': identity,
            'parent_runtime_call_id': selected, 'parent_trace_id': execution['task_id'],
            'guard_evidence': copy.deepcopy(execution_ref), 'output_refs': {'call_id': step['id'], 'path': []}})
    value = {'format': checked['format'], 'projection': 'capability_composition_calls_v1',
        'owner': snapshot['owner'], 'trace_id': execution['task_id'], 'task_id': execution['task_id'],
        'task_fingerprint': task_fingerprint, 'role': role,
        'task_input': copy.deepcopy(recovered[selected]['arguments']), 'execution_input': copy.deepcopy(task_input),
        'snapshot': copy.deepcopy(snapshot), 'execution_ref': copy.deepcopy(execution_ref),
        'parent_call_id': selected, 'steps': steps, 'evidence': [copy.deepcopy(execution_ref)],
        'quality': 'unreviewed', 'benefit': None}
    if available_snapshot is not None: value['available_snapshot'] = copy.deepcopy(available_snapshot)
    if validation_manifest_ref is not None:
        value['validation_manifest_ref'] = copy.deepcopy(validation_manifest_ref)
        value['evidence'].append(copy.deepcopy(validation_manifest_ref))
        value['container_certification'] = 'candidate'
    value['digest'] = _trajectory_digest(value)
    return value


def _layout(cap):
    """Reversible typed slots, used only by the scalar Motif compiler.

    Original JSON values, schemas and IR bindings remain authoritative. Canonical
    JSON encoding permits empty arrays/objects and nested values without teaching
    the old compiler an unrelated serialization or execution protocol.
    """
    if cap['contract']['effects'] != ['read'] or cap['contract']['input_schema'].get('type') != 'object':
        _fail('unsupported_motif_contract')
    inputs = {}; outputs = {}; reserved = set(cap['contract']['input_schema'].get('properties', {}))
    def inputs_at(schema, path):
        if schema.get('type') == 'object':
            props = schema.get('properties', {})
            if schema.get('additionalProperties') is not False or set(schema.get('required', [])) != set(props):
                _fail('unsupported_motif_contract')
            if props:
                for key in sorted(props): inputs_at(props[key], [*path, key])
                return
            if not path: return  # Preserve original no-argument read capabilities.
        if not path or schema.get('type') not in ('string', 'number', 'integer', 'boolean', 'null', 'array', 'object'):
            _fail('unsupported_motif_contract')
        name = path[0] if len(path) == 1 else 'slot' + str(len(inputs))
        if len(path) != 1:
            while name in reserved or name in inputs: name = '_' + name
        inputs[name] = {'path': path, 'schema': copy.deepcopy(schema), 'encoding': 'canonical_json'}
    def outputs_at(schema, path):
        outputs['o' + str(len(outputs))] = {'path': path, 'schema': copy.deepcopy(schema), 'encoding': 'canonical_json'}
        if schema.get('type') == 'object':
            for key in sorted(schema.get('required', [])):
                if key in schema.get('properties', {}): outputs_at(schema['properties'][key], [*path, key])
    inputs_at(cap['contract']['input_schema'], [])
    outputs_at(cap['contract']['output_schema'], [])
    return {'capability': capability_ref(cap), 'input_schema': copy.deepcopy(cap['contract']['input_schema']),
            'output_schema': copy.deepcopy(cap['contract']['output_schema']), 'inputs': inputs, 'outputs': outputs}


def _tool_contract(cap):
    layout = _layout(cap)
    return ToolContract(required_params=tuple(layout['inputs']), read_only=True,
                        output_fields=tuple(layout['outputs']))


def _encoded(value):
    capability_digest(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def _binding_at(binding, path):
    if binding['kind'] in ('input', 'step'):
        return {**binding, 'path': [*binding['path'], *path]}
    if not path: return binding
    if binding['kind'] == 'object': return _binding_at(binding['fields'][path[0]], path[1:])
    return None  # literals/arrays are values, never inferred dependency sources


def _project(trace, contracts, region, layouts):
    steps = trace['steps']
    if region is not None:
        ids = [s['call_id'] for s in steps]
        if not isinstance(region, list) or not region or len(region) != len(set(region)) or any(i not in ids for i in region):
            _fail('region_invalid')
        start = ids.index(region[0])
        if ids[start:start + len(region)] != region: _fail('region_not_contiguous')
        steps = steps[start:start + len(region)]
    records = []; segments = []; current = []; prior = {}; latest = {}
    for index, step in enumerate(steps):
        symbol = _symbol(step['capability']); source = {}; binding = step['input_binding']
        eligible = step['status'] == 'succeeded' and symbol in contracts
        arguments = step['arguments']; observation = step['result']
        if eligible:
            layout = layouts[symbol]
            arguments = {key: _encoded(_at(step['arguments'], slot['path'])) for key, slot in layout['inputs'].items()}
            observation = {key: _encoded(_at(step['result'], slot['path'])) for key, slot in layout['outputs'].items()}
            for param, slot in layout['inputs'].items():
                item = _binding_at(binding, slot['path'])
                if item and item['kind'] == 'step' and item['step_id'] in prior:
                    previous = prior[item['step_id']]
                    previous_symbol = _symbol(previous['capability'])
                    # The old compiler addresses tools, not occurrences. Never
                    # let an older repeated C masquerade as the later C in a
                    # unique suffix, even when both returned equal JSON values.
                    if latest.get(previous_symbol) != item['step_id']: continue
                    for field, output in layouts[previous_symbol]['outputs'].items():
                        if output['path'] == item['path']:
                            source[param] = {'from_tool': previous_symbol, 'from_field': field}
        records.append(ToolRecord(symbol, arguments, capability_digest(step['result']), eligible,
            'witnessed_capability_call' if eligible else 'failed_or_unsupported_call', index,
            observation if isinstance(observation, dict) else None, source or None))
        if eligible:
            current.append(symbol); prior[step['call_id']] = step; latest[symbol] = step['call_id']
        elif current:
            segments.append(tuple(current)); current = []; prior = {}; latest = {}
    if current: segments.append(tuple(current))
    # Keep complete observations (including the original repeat rejection), and
    # expose maximal non-repeated contiguous windows supported by the EXISTING
    # compiler. These are segments of ONE trace, not extra independent tasks.
    for segment in list(segments):
        for start in range(len(segment)):
            end = start; seen = set()
            while end < len(segment) and segment[end] not in seen:
                seen.add(segment[end]); end += 1
            window = segment[start:end]
            if len(window) >= 2 and window not in segments and (start == 0 or segment[start - 1] in seen):
                segments.append(window)
    return DshTrace(trace['trace_id'], tuple(records), tuple(segments), trace['task_fingerprint'])


def _proposal(artifact, lookup, owner, layouts):
    steps = []; inputs = {}; tool_steps = {}
    for index, tool in enumerate(artifact['tools']):
        cap = lookup[tool]; operator = artifact['dependencies']['operators'][tool]
        transfers = {b['to_param']: b for b in operator['bindings']}; bindings = {}
        for param in operator['required_params']:
            slot = layouts[tool]['inputs'][param]
            if param in transfers:
                b = transfers[param]
                bindings[tuple(slot['path'])] = {'kind': 'step', 'step_id': tool_steps[b['from_tool']],
                    'path': copy.deepcopy(layouts[b['from_tool']]['outputs'][b['from_field']]['path'])}
            else:
                key = 'p' + str(index) + '_' + param
                inputs[key] = copy.deepcopy(slot['schema'])
                bindings[tuple(slot['path'])] = {'kind': 'input', 'path': [key]}
        def assemble(schema, path=()):
            if path in bindings: return bindings[path]
            return {'kind': 'object', 'fields': {key: assemble(child, (*path, key))
                for key, child in schema.get('properties', {}).items()}}
        identity = 'call' + str(index); tool_steps[tool] = identity
        steps.append({'id': identity, 'capability': capability_ref(cap), 'arguments': assemble(cap['contract']['input_schema'])})
    return {'format': 'capability_compose_proposal_v1', 'owner': owner,
            'contract': {'input_schema': {'type': 'object', 'properties': inputs, 'required': list(inputs), 'additionalProperties': False},
                         'output_schema': copy.deepcopy(lookup[artifact['tools'][-1]]['contract']['output_schema']), 'effects': ['read']},
            'steps': steps, 'output': {'kind': 'step', 'step_id': steps[-1]['id'], 'path': []}}


def learn_capability_motifs(training, heldout, snapshot, *, regions=None):
    """Use the original miner/compiler/certifier, then original Capability compiler.

    Regions are explicit host/model candidates, never authority. Each selected
    range is still mined across independent witnessed tasks and held-out traces.
    Nothing is published, and an old primitive need not occur in any candidate.
    """
    snapshot = validate_capability_snapshot(snapshot)
    rows = [_checked(t, snapshot['owner']) for t in [*training, *heldout]]
    if len(training) < 2 or not heldout or len({r['trace_id'] for r in rows}) != len(rows) or len(
            {r['task_fingerprint'] for r in rows}) != len(rows):
        _fail('independent_tasks_required')
    if regions is not None and (not isinstance(regions, dict) or set(regions) != {r['trace_id'] for r in rows}):
        _fail('regions_must_cover_all_traces')
    lookup = {_symbol(capability_ref(c)): c for c in snapshot['capabilities'] if capability_ref(c) in snapshot['roots']}
    contracts = {}; layouts = {}; unsupported = []
    for tool, cap in lookup.items():
        if cap['certification'] != 'certified' or cap['lifecycle'] != 'active': continue
        try:
            contracts[tool] = _tool_contract(cap); layouts[tool] = _layout(cap)
        except ValueError: unsupported.append(capability_ref(cap))
    for trace in rows:
        for step in trace['steps']:
            if step['capability'] not in snapshot['roots']:
                _fail('learning_dependency_changed')
    projected = [_project(r, contracts, None if regions is None else regions[r['trace_id']], layouts) for r in rows]
    train = projected[:len(training)]; validation = projected[len(training):]
    candidates = []; rejected = []
    for candidate in mine_dsh_traces(train, min_trace_support=2):
        try:
            compiled_motif = compile_read_motif(candidate, train, contracts)
            certified = [certify_read_motif(compiled_motif, trace, contracts) for trace in validation]
            artifact = certified[0]
            proposal = _proposal(artifact, lookup, snapshot['owner'], layouts)
            compiled = compile_proposal(proposal, snapshot, snapshot['owner'])
            candidates.append({'motif': artifact, 'proposal': proposal, 'compiled': compiled,
                'provenance': {'training': [r['digest'] for r in rows[:len(training)]],
                    'heldout': [r['digest'] for r in rows[len(training):]], 'regions': copy.deepcopy(regions),
                    'roles': sorted({r['role'] for r in rows}),
                    'typed_projection': {tool: layouts[tool] for tool in artifact['tools']},
                    'source_input_bindings': [{'input_name': 'p' + str(index) + '_' + param,
                        'step_index': index, 'capability': capability_ref(lookup[tool]),
                        'argument_path': copy.deepcopy(layouts[tool]['inputs'][param]['path'])}
                        for index, tool in enumerate(artifact['tools'])
                        for param in artifact['dependencies']['operators'][tool]['required_params']
                        if param not in {binding['to_param'] for binding in artifact['dependencies']['operators'][tool]['bindings']}],
                    'evidence': [ref for r in rows for ref in r['evidence']],
                    'scope': 'witnessed_parameter_flow_not_task_quality_or_causal_benefit'}})
        except (ValueError, KeyError, TypeError) as error:
            rejected.append({'motif_id': candidate['motif_id'], 'reason': str(error)})
    return {'candidates': candidates, 'rejected': rejected, 'unsupported_capabilities': unsupported,
            'model_requests': 0, 'creation_value': None, 'scope': 'offline_candidate_learning_requires_independent_publication'}
