"""Capability sidecars; metadata validation never grants execution authority.

New identities hash typed canonical JSON: scalar tags, float64 big-endian hex
(-0 becomes 0), Unicode scalar key order. Legacy digests retain their native
encoding. Neither mapping nor snapshotting rewrites a legacy library/certificate.
"""
from __future__ import annotations
import copy
import base64
import subprocess
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from jsonschema import Draft202012Validator
from .rsi_protocol import _supported_schema

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / 'schemas/capability-v1.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
IDENTITY_KEYS = ('owner', 'contract', 'implementation', 'dependencies')
BACKENDS = ('source_program', 'artifact_motif')


def _fail(message):
    raise ValueError('capability_' + message)


def _string(value):
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        _fail('invalid_unicode')
    return value


def _tag(value, depth=0):
    if depth > 64:
        _fail('too_deep')
    if value is None:
        return ['null']
    if isinstance(value, bool):
        return ['boolean', value]
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or abs(value) > 9007199254740991:
            _fail('number_out_of_range')
        return ['number', struct.pack('>d', 0.0 if value == 0 else value).hex()]
    if isinstance(value, str):
        return ['string', _string(value)]
    if isinstance(value, list):
        return ['array', [_tag(v, depth + 1) for v in value]]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return ['object', [[_string(k), _tag(value[k], depth + 1)] for k in sorted(value)]]
    _fail('non_json_value')


def capability_digest(value):
    encoded = json.dumps(_tag(value), ensure_ascii=False, separators=(',', ':')).encode()
    if len(encoded) > 4_000_000:
        _fail('too_large')
    return hashlib.sha256(encoded).hexdigest()


def _identifier(value):
    if not isinstance(value, str) or not value.strip(' \t\r\n\f\v') or len(value) > 256:
        _fail('identifier_invalid')
    _string(value)


def _sha(value):
    if not isinstance(value, str) or re.fullmatch('[a-f0-9]{64}', value) is None:
        _fail('digest_invalid')


def _shape(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail('shape_invalid')


def _ref(ref):
    _shape(ref, ('id', 'sha256'))
    _sha(ref['sha256'])
    if ref['id'] != 'cap_' + ref['sha256'][:24]:
        _fail('reference_invalid')
    return ref['id'] + ':' + ref['sha256']


def _binding(binding, earlier, depth=0):
    if depth > 32 or not isinstance(binding, dict):
        _fail('binding_invalid')
    kind = binding.get('kind')
    if kind in ('input', 'step'):
        _shape(binding, ('kind', 'path', 'step_id') if kind == 'step' else ('kind', 'path'))
        if not isinstance(binding['path'], list) or len(binding['path']) > 32 or any(not isinstance(k, str) or k in ('__proto__', 'prototype', 'constructor') for k in binding['path']):
            _fail('binding_path_invalid')
        if kind == 'step' and binding['step_id'] not in earlier:
            _fail('binding_step_unavailable')
    elif kind == 'literal':
        _shape(binding, ('kind', 'value'))
        capability_digest(binding['value'])
    elif kind == 'object':
        _shape(binding, ('kind', 'fields'))
        if not isinstance(binding['fields'], dict) or any(k in ('__proto__', 'prototype', 'constructor') for k in binding['fields']):
            _fail('binding_fields_invalid')
        for child in binding['fields'].values():
            _binding(child, earlier, depth + 1)
    elif kind == 'array':
        _shape(binding, ('kind', 'items'))
        if not isinstance(binding['items'], list):
            _fail('binding_items_invalid')
        for child in binding['items']:
            _binding(child, earlier, depth + 1)
    else:
        _fail('binding_kind_invalid')


def capability_identity(capability):
    return {key: capability[key] for key in IDENTITY_KEYS}


def validate_capability(value, expected_owner=None):
    capability_digest(value)
    if not isinstance(value, dict) or value.get('format') != 'capability_v1' or list(VALIDATOR.iter_errors(value)):
        _fail('schema_invalid')
    _identifier(value['owner'])
    if expected_owner is not None and value['owner'] != expected_owner:
        _fail('foreign_owner')
    _supported_schema(value['contract']['input_schema'])
    _supported_schema(value['contract']['output_schema'])
    effects = value['contract']['effects']
    if not effects or len(effects) != len(set(effects)) or any(e not in ('read', 'workspace_write', 'external_write', 'opaque') for e in effects):
        _fail('effects_invalid')
    deps = [_ref(r) for r in value['dependencies']]
    if len(deps) != len(set(deps)) or deps != sorted(deps):
        _fail('dependencies_not_unique_sorted')
    impl = value['implementation']
    if impl['kind'] == 'legacy':
        ref = impl['legacy_ref']
        if ref['backend'] not in BACKENDS or deps:
            _fail('legacy_backend_or_dependencies')
        _identifier(ref['object_id'])
        for key in ('library_sha256', 'library_digest', 'object_sha256', 'certificate_sha256'):
            _sha(ref[key])
    else:
        steps, earlier, called = impl['steps'], set(), set()
        if not 1 <= len(steps) <= 64:
            _fail('steps_invalid')
        for step in steps:
            _identifier(step['id'])
            if step['id'] in earlier or step['id'] in ('__proto__', 'prototype', 'constructor'):
                _fail('step_duplicate_or_reserved')
            called.add(_ref(step['capability']))
            _binding(step['arguments'], earlier)
            earlier.add(step['id'])
        _binding(impl['output'], earlier)
        if called != set(deps):
            _fail('dependencies_do_not_match_calls')
    expected = capability_digest(capability_identity(value))
    if value['revision_sha256'] != expected or value['id'] != 'cap_' + expected[:24]:
        _fail('identity_changed')
    return copy.deepcopy(value)


def create_capability(definition, states=None):
    _shape(definition, IDENTITY_KEYS)
    states = states or {}
    if set(states) - {'lifecycle', 'certification', 'migration'}:
        _fail('states_invalid')
    definition = copy.deepcopy(definition)
    definition['dependencies'].sort(key=_ref)
    revision = capability_digest(definition)
    return validate_capability({'format': 'capability_v1', 'id': 'cap_' + revision[:24], 'revision_sha256': revision,
        **definition, 'lifecycle': states.get('lifecycle', 'build_only'), 'certification': states.get('certification', 'candidate'),
        'migration': states.get('migration', 'testing')})


def capability_ref(value):
    checked = validate_capability(value)
    return {'id': checked['id'], 'sha256': checked['revision_sha256']}


def validate_capability_snapshot(value, expected_owner=None):
    capability_digest(value)
    if not isinstance(value, dict) or value.get('format') != 'capability_snapshot_v1' or list(VALIDATOR.iter_errors(value)):
        _fail('snapshot_schema_invalid')
    _identifier(value['owner'])
    if expected_owner is not None and value['owner'] != expected_owner:
        _fail('foreign_owner')
    roots = [_ref(r) for r in value['roots']]
    if not roots or len(roots) != len(set(roots)) or roots != sorted(roots):
        _fail('roots_not_unique_sorted')
    capabilities = [validate_capability(c, value['owner']) for c in value['capabilities']]
    ids = [c['id'] for c in capabilities]
    if len(ids) != len(set(ids)) or ids != sorted(ids):
        _fail('snapshot_duplicates_or_order')
    lookup = {c['id']: c for c in capabilities}
    visiting, visited = set(), set()
    def visit(ref):
        key = _ref(ref)
        if key in visiting:
            _fail('dependency_cycle')
        if key in visited:
            return
        target = lookup.get(ref['id'])
        if target is None or target['revision_sha256'] != ref['sha256']:
            _fail('dependency_missing_or_changed')
        visiting.add(key)
        for dependency in target['dependencies']:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
    for ref in value['roots']:
        visit(ref)
    if len(visited) != len(capabilities):
        _fail('snapshot_extra_capability')
    if value['digest'] != capability_digest({k: v for k, v in value.items() if k != 'digest'}):
        _fail('snapshot_changed')
    return copy.deepcopy(value)


def create_capability_snapshot(owner, roots, capabilities):
    body = {'format': 'capability_snapshot_v1', 'owner': owner, 'roots': sorted(copy.deepcopy(roots), key=_ref),
            'capabilities': sorted(copy.deepcopy(capabilities), key=lambda c: c['id'])}
    return validate_capability_snapshot({**body, 'digest': capability_digest(body)}, owner)


def map_legacy_library(raw, owner, backend, expected_sha256):
    """Map exact bytes through the authoritative TypeScript legacy validator.

    The offline compiler already uses Node. This fixed bridge only reads JSON;
    it does not evaluate candidate source, alter libraries or upgrade authority.
    Native digest semantics (including numeric/Unicode handling) have one owner.
    The online TypeScript path does not depend on Python.
    """
    raw = raw.encode('utf-8') if isinstance(raw, str) else raw
    _sha(expected_sha256)
    if not isinstance(raw, bytes) or len(raw) > 4_000_000 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        _fail('legacy_bytes_changed')
    root = Path(__file__).resolve().parents[2]
    request = {'raw_base64': base64.b64encode(raw).decode('ascii'), 'owner': owner,
               'backend': backend, 'expected_sha256': expected_sha256}
    try:
        result = subprocess.run(['node', '--experimental-strip-types', str(root / 'scripts/map-capability-legacy.mjs')],
                                input=json.dumps(request), text=True, capture_output=True, cwd=root, timeout=30)
        reply = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise ValueError('capability_legacy_bridge_failed') from error
    if result.returncode != 0 or not isinstance(reply, dict) or 'capabilities' not in reply:
        raise ValueError(reply.get('error', 'capability_legacy_bridge_failed') if isinstance(reply, dict) else 'capability_legacy_bridge_failed')
    if not isinstance(reply['capabilities'], list):
        _fail('legacy_bridge_invalid')
    return [validate_capability(value, owner) for value in reply['capabilities']]
