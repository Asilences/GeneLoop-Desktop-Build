"""Explain argument shape and binding locations without changing a contract.

Only explicit JSON Schema constraints can establish a contract violation.
Wrapping an already-array result in a new array is useful diagnostic evidence,
but remains advisory when the frozen target has no element constraint. This
module does not execute bindings, infer a schema from examples, repair values,
authorize retries, or change validation/publication outcomes.
"""
from __future__ import annotations

import copy
from itertools import islice

from jsonschema import Draft202012Validator

from .capability_contract import capability_digest, capability_ref, validate_capability_snapshot


MAX_DIAGNOSTICS = 64


def _composition(candidate):
    snapshot = validate_capability_snapshot(candidate['snapshot'])
    capabilities = {row['id']: row for row in snapshot['capabilities']}
    root = candidate['capability']
    if capabilities.get(root['id']) != root or root['implementation']['kind'] != 'composition':
        raise ValueError('shape_diagnostics_composition_changed')
    return snapshot, root, capabilities


def _path(schema, fields):
    """Read declared property shape only; unknown paths stay unknown."""
    for field in fields:
        if schema.get('type') != 'object':
            return {}
        schema = schema.get('properties', {}).get(field, {})
    return schema


def _declared_shape(binding, inputs, earlier):
    kind = binding['kind']
    if kind == 'input':
        return _path(inputs, binding['path'])
    if kind == 'step':
        return _path(earlier.get(binding['step_id'], {}), binding['path'])
    if kind in ('object', 'array'):
        return {'type': kind}
    value = binding.get('value')
    if value is None:
        return {'type': 'null'}
    return {'type': 'boolean' if type(value) is bool else 'object' if isinstance(value, dict)
            else 'array' if isinstance(value, list) else 'string' if isinstance(value, str)
            else 'number' if type(value) in (int, float) else 'unknown'}


def _shape(value):
    """Describe type, not private source values, keys or collection contents."""
    return _declared_shape({'kind': 'literal', 'value': value}, {}, {})['type']


def _location(binding, argument_path, base):
    """Map an actual JSON error to the model's closest explicit binding."""
    remaining = list(argument_path)
    while remaining:
        first = remaining[0]
        if binding['kind'] == 'object' and first in binding['fields']:
            base += ['fields', first]
            binding = binding['fields'][first]
        elif (binding['kind'] == 'array' and type(first) is int
              and 0 <= first < len(binding['items'])):
            base += ['items', first]
            binding = binding['items'][first]
        else:
            break
        remaining.pop(0)
    if binding['kind'] == 'literal':
        return base + ['value', *remaining]
    return base


def _array_advisories(binding, expected, inputs, earlier, location, argument_path, rows):
    if len(rows) >= MAX_DIAGNOSTICS:
        return
    if binding['kind'] == 'object':
        properties = expected.get('properties', {})
        for key, child in binding['fields'].items():
            _array_advisories(child, properties.get(key, {}), inputs, earlier,
                             location + ['fields', key], argument_path + [key], rows)
    elif binding['kind'] == 'array':
        for index, child in enumerate(binding['items']):
            if len(rows) >= MAX_DIAGNOSTICS:
                break
            source = _declared_shape(child, inputs, earlier)
            if source.get('type') == 'array':
                rows.append({'kind': 'explicit_array_wrapping_array',
                    'binding_path': location + ['items', index],
                    'argument_path': argument_path + [index],
                    'source_declared_type': 'array',
                    'target_items_declared': bool(expected.get('items')),
                    'contract_violation': False,
                    'observation': 'This binding adds an array layer to an already-array value. '
                        'This fact alone does not establish invalid input; inspect the declared '
                        'element contract and the failing execution evidence.'})
            _array_advisories(child, expected.get('items', {}), inputs, earlier,
                             location + ['items', index], argument_path + [index], rows)


def composition_shape_advisories(candidate):
    """Return bounded, nonbinding observations derived from explicit bindings."""
    _, root, capabilities = _composition(candidate)
    inputs = root['contract']['input_schema']
    earlier = {}
    rows = []
    for index, step in enumerate(root['implementation']['steps']):
        child = capabilities[step['capability']['id']]
        local = []
        _array_advisories(step['arguments'], child['contract']['input_schema'], inputs,
                         earlier, ['steps', index, 'arguments'], [], local)
        for row in local:
            rows.append({'step_id': step['id'], 'capability': copy.deepcopy(step['capability']), **row})
            if len(rows) >= MAX_DIAGNOSTICS:
                return rows
        earlier[step['id']] = child['contract']['output_schema']
    return rows


def diagnose_step_argument_shapes(candidate, step_id, arguments):
    """Validate actual arguments only against the exact frozen input schema.

    ``declared_contract_passed`` does not establish that a program can execute
    these values; source-equivalence certificates may have weak shape schemas.
    No repairability or permission decision is made here.
    """
    snapshot, root, capabilities = _composition(candidate)
    selected = [(index, row) for index, row in enumerate(root['implementation']['steps'])
                if row['id'] == step_id]
    if len(selected) != 1:
        raise ValueError('shape_diagnostics_step_missing')
    index, step = selected[0]
    contract = capabilities[step['capability']['id']]['contract']['input_schema']
    arguments_sha = capability_digest(arguments)
    issues = []
    errors = sorted(islice(Draft202012Validator(contract).iter_errors(arguments), MAX_DIAGNOSTICS + 1),
                    key=lambda error: repr(list(error.absolute_path)))
    for error in errors[:MAX_DIAGNOSTICS]:
        path = list(error.absolute_path)
        issues.append({'kind': 'declared_contract_violation', 'validator': error.validator,
            'argument_path': path,
            'binding_path': _location(step['arguments'], path, ['steps', index, 'arguments']),
            'expected_constraint': copy.deepcopy(error.validator_value),
            'actual_type': _shape(error.instance), 'contract_violation': True})
    return {'format': 'capability_argument_shape_diagnostics_v1',
        'snapshot_sha256': snapshot['digest'], 'root': capability_ref(root),
        'step_id': step_id, 'capability': copy.deepcopy(step['capability']),
        'capability_arguments_digest': arguments_sha,
        'input_schema_capability_digest': capability_digest(contract),
        'declared_contract_passed': not errors, 'issues': issues,
        'issues_truncated': len(errors) > MAX_DIAGNOSTICS,
        'advisories': [row for row in composition_shape_advisories(candidate) if row['step_id'] == step_id],
        'scope': 'Declared contract and explicit binding shape only; not worker-cause attribution, '
            'semantic validation, retry authorization, or automatic repair.'}
