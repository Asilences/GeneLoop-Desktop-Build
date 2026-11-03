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
from .capability_contract import capability_digest, capability_ref, validate_capability_snapshot, _binding
from .capability_improvement import evidence
from .dsh_trajectory import DshTrace, ToolContract, ToolRecord, mine_dsh_traces
from .rsi_protocol import validate_record
from src.motif_core.offline.trace_compiler import compile_read_motif, certify_read_motif


def _fail(reason):
    raise ValueError('capability_motif_' + reason)


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
    capability_digest(values)
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


def capture_capability_trace(snapshot, *, task_id, task_input, task_fingerprint, calls, role='task'):
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
        if cap['certification'] != 'certified' or cap['lifecycle'] != 'active':
            _fail('call_not_certified')
        _binding(call['input_binding'], set(results))
        args = _bind(call['input_binding'], task_input, results)
        execution = json.loads(evidence(call['execution_ref']))
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
    value['digest'] = capability_digest(value)
    return value


def _checked(trace, owner):
    if not isinstance(trace, dict) or trace.get('owner') != owner:
        _fail('owner_changed')
    rebuilt = capture_capability_trace(trace['snapshot'], task_id=trace['task_id'],
        task_input=trace['task_input'], task_fingerprint=trace['task_fingerprint'],
        calls=trace['calls'], role=trace['role'])
    if trace != rebuilt: _fail('trace_changed')
    return rebuilt


def _symbol(ref):
    return 'capability_' + ref['sha256']


def _fields(schema, path=()):
    """Guaranteed scalar/list output fields supported by the existing compiler."""
    if schema.get('type') == 'object':
        return [p for name in sorted(schema.get('required', []))
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
                for p in _fields(schema.get('properties', {}).get(name, {}), (*path, name))]
    if schema.get('type') in ('string', 'number', 'integer', 'boolean') or (
            schema.get('type') == 'array' and schema.get('items', {}).get('type') in ('string', 'number', 'integer', 'boolean')):
        return [path] if path else []
    return []


def _tool_contract(cap):
    schema = cap['contract']['input_schema']; props = schema.get('properties', {})
    if (cap['contract']['effects'] != ['read'] or schema.get('type') != 'object' or
            schema.get('additionalProperties') is not False or set(schema.get('required', [])) != set(props) or
            any(s.get('type') not in ('string', 'number', 'integer', 'boolean', 'array') or
                s.get('type') == 'array' and s.get('items', {}).get('type') not in ('string', 'number', 'integer', 'boolean')
                for s in props.values()) or cap['contract']['output_schema'].get('type') != 'object'):
        _fail('unsupported_motif_contract')
    return ToolContract(required_params=tuple(sorted(props)), read_only=True,
                        output_fields=tuple('.'.join(p) for p in _fields(cap['contract']['output_schema'])),
                        collection_params=tuple(sorted(k for k, s in props.items() if s.get('type') == 'array')))


def _project(trace, contracts, region):
    steps = trace['steps']
    if region is not None:
        ids = [s['call_id'] for s in steps]
        if not isinstance(region, list) or not region or len(region) != len(set(region)) or any(i not in ids for i in region):
            _fail('region_invalid')
        start = ids.index(region[0])
        if ids[start:start + len(region)] != region: _fail('region_not_contiguous')
        steps = steps[start:start + len(region)]
    records = []; segments = []; current = []; prior = {}
    for index, step in enumerate(steps):
        symbol = _symbol(step['capability']); source = {}; binding = step['input_binding']
        eligible = step['status'] == 'succeeded' and symbol in contracts
        if eligible and binding['kind'] == 'object':
            for param, item in binding['fields'].items():
                if item['kind'] == 'step' and item['step_id'] in prior:
                    previous = prior[item['step_id']]
                    field = '.'.join(item['path'])
                    if field in contracts[_symbol(previous['capability'])].output_fields:
                        source[param] = {'from_tool': _symbol(previous['capability']), 'from_field': field}
        records.append(ToolRecord(symbol, step['arguments'], capability_digest(step['result']), eligible,
            'witnessed_capability_call' if eligible else 'failed_or_unsupported_call', index,
            step['result'] if isinstance(step['result'], dict) else None, source or None))
        if eligible:
            current.append(symbol); prior[step['call_id']] = step
        elif current:
            segments.append(tuple(current)); current = []; prior = {}
    if current: segments.append(tuple(current))
    return DshTrace(trace['trace_id'], tuple(records), tuple(segments), trace['task_fingerprint'])


def _proposal(artifact, lookup, owner):
    steps = []; inputs = {}; tool_steps = {}
    for index, tool in enumerate(artifact['tools']):
        cap = lookup[tool]; operator = artifact['dependencies']['operators'][tool]
        transfers = {b['to_param']: b for b in operator['bindings']}; arguments = {}
        for param in operator['required_params']:
            if param in transfers:
                b = transfers[param]
                arguments[param] = {'kind': 'step', 'step_id': tool_steps[b['from_tool']], 'path': b['from_field'].split('.')}
            else:
                key = 'p' + str(index) + '_' + param
                inputs[key] = copy.deepcopy(cap['contract']['input_schema']['properties'][param])
                arguments[param] = {'kind': 'input', 'path': [key]}
        identity = 'call' + str(index); tool_steps[tool] = identity
        steps.append({'id': identity, 'capability': capability_ref(cap), 'arguments': {'kind': 'object', 'fields': arguments}})
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
    contracts = {}; unsupported = []
    for tool, cap in lookup.items():
        if cap['certification'] != 'certified' or cap['lifecycle'] != 'active': continue
        try: contracts[tool] = _tool_contract(cap)
        except ValueError: unsupported.append(capability_ref(cap))
    for trace in rows:
        for step in trace['steps']:
            if step['capability'] not in snapshot['roots']:
                _fail('learning_dependency_changed')
    projected = [_project(r, contracts, None if regions is None else regions[r['trace_id']]) for r in rows]
    train = projected[:len(training)]; validation = projected[len(training):]
    candidates = []; rejected = []
    for candidate in mine_dsh_traces(train, min_trace_support=2):
        try:
            compiled_motif = compile_read_motif(candidate, train, contracts)
            certified = [certify_read_motif(compiled_motif, trace, contracts) for trace in validation]
            artifact = certified[0]
            proposal = _proposal(artifact, lookup, snapshot['owner'])
            compiled = compile_proposal(proposal, snapshot, snapshot['owner'])
            candidates.append({'motif': artifact, 'proposal': proposal, 'compiled': compiled,
                'provenance': {'training': [r['digest'] for r in rows[:len(training)]],
                    'heldout': [r['digest'] for r in rows[len(training):]], 'regions': copy.deepcopy(regions),
                    'roles': sorted({r['role'] for r in rows}),
                    'evidence': [ref for r in rows for ref in r['evidence']],
                    'scope': 'witnessed_parameter_flow_not_task_quality_or_causal_benefit'}})
        except (ValueError, KeyError, TypeError) as error:
            rejected.append({'motif_id': candidate['motif_id'], 'reason': str(error)})
    return {'candidates': candidates, 'rejected': rejected, 'unsupported_capabilities': unsupported,
            'model_requests': 0, 'creation_value': None, 'scope': 'offline_candidate_learning_requires_independent_publication'}
