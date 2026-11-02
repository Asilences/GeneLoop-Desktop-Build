"""Offline compiler for supplied composition proposals, with no execution or model loop.

A successful build is candidate metadata, never certification or publication.
Static schema checks are deliberately conservative: ambiguous unions and optional
path traversals require a more precise contract instead of guessed compatibility.
"""
from __future__ import annotations
from jsonschema import Draft202012Validator
from .capability_contract import (capability_digest, capability_ref, create_capability,
    create_capability_snapshot, validate_capability_snapshot)

ANNOTATIONS = {'description', 'title', 'default', 'examples'}


def _fail(reason):
    raise ValueError('capability_build_' + reason)


def _semantic(schema):
    return {k: v for k, v in schema.items() if k not in ANNOTATIONS}


def _assignable(source, target):
    """Sufficient (not complete) proof that every source value satisfies target."""
    source, target = _semantic(source), _semantic(target)
    if not target or source == target:
        return True
    # Scalar finite domains can be checked exactly using the enforced schema.
    if 'const' in source or 'enum' in source:
        values = [source['const']] if 'const' in source else source['enum']
        return all(not list(Draft202012Validator(target).iter_errors(v)) for v in values)
    if 'oneOf' in source or 'oneOf' in target or 'const' in target or 'enum' in target:
        return False
    st, tt = source.get('type'), target.get('type')
    if st != tt and (st, tt) != ('integer', 'number'):
        return False
    if tt == 'object':
        sp, tp = source.get('properties', {}), target.get('properties', {})
        if not set(target.get('required', [])) <= set(source.get('required', [])):
            return False
        if target.get('additionalProperties', True) is False:
            if source.get('additionalProperties', True) is not False or not set(sp) <= set(tp):
                return False
        # An undeclared source property may exist when source is open.
        for key, schema in tp.items():
            if key in sp and not _assignable(sp[key], schema):
                return False
            if key not in sp and source.get('additionalProperties', True) and _semantic(schema):
                return False
        return True
    if tt == 'array':
        return _assignable(source.get('items', {}), target.get('items', {}))
    return tt is not None


def _path_schema(schema, path):
    for key in path:
        if schema.get('type') != 'object' or key not in schema.get('required', []) or key not in schema.get('properties', {}):
            _fail('path_not_guaranteed')
        schema = schema['properties'][key]
    return schema


def _check_binding(binding, expected, inputs, earlier):
    kind = binding['kind']
    if kind in ('input', 'step'):
        schema = inputs if kind == 'input' else earlier[binding['step_id']]
        if not _assignable(_path_schema(schema, binding['path']), expected):
            _fail('schema_incompatible')
    elif kind == 'literal':
        if list(Draft202012Validator(expected).iter_errors(binding['value'])):
            _fail('literal_schema_incompatible')
    elif kind == 'object':
        if not _semantic(expected):
            expected = {'type': 'object'}
        if expected.get('type') != 'object':
            _fail('object_schema_incompatible')
        fields, properties = binding['fields'], expected.get('properties', {})
        if not set(expected.get('required', [])) <= set(fields):
            _fail('required_input_missing')
        if expected.get('additionalProperties', True) is False and not set(fields) <= set(properties):
            _fail('extra_input')
        for key, child in fields.items():
            _check_binding(child, properties.get(key, {}), inputs, earlier)
    elif kind == 'array':
        if not _semantic(expected):
            expected = {'type': 'array'}
        if expected.get('type') != 'array':
            _fail('array_schema_incompatible')
        for child in binding['items']:
            _check_binding(child, expected.get('items', {}), inputs, earlier)


def compile_proposal(proposal, construction_snapshot, expected_owner):
    """Compile an agent-supplied proposal against an immutable visible library.

    Only snapshot roots are exposed construction primitives. Closure nodes are
    retained for execution/version pinning, but not silently exposed as tools.
    No external writes, execution, model calls or certificate upgrades occur.
    """
    snapshot = validate_capability_snapshot(construction_snapshot, expected_owner)
    capability_digest(proposal)
    keys = {'format', 'owner', 'contract', 'steps', 'output'}
    if not isinstance(proposal, dict) or set(proposal) != keys or proposal['format'] != 'capability_compose_proposal_v1':
        _fail('proposal_shape')
    if proposal['owner'] != expected_owner:
        _fail('foreign_owner')
    steps = proposal['steps']
    if not isinstance(steps, list) or any(not isinstance(step, dict) or 'capability' not in step for step in steps):
        _fail('steps_invalid')
    roots = {r['id']: r['sha256'] for r in snapshot['roots']}
    lookup = {c['id']: c for c in snapshot['capabilities']}
    dependencies = {}
    for step in steps:
        ref = step['capability']
        if not isinstance(ref, dict) or set(ref) != {'id', 'sha256'} or roots.get(ref.get('id')) != ref.get('sha256'):
            _fail('reference_not_visible_or_changed')
        dependencies[ref['id']] = ref
    candidate = create_capability({'owner': expected_owner, 'contract': proposal['contract'],
        'implementation': {'kind': 'composition', 'steps': steps, 'output': proposal['output']},
        'dependencies': list(dependencies.values())})
    earlier = {}
    for step in candidate['implementation']['steps']:
        child = lookup[step['capability']['id']]
        if child['lifecycle'] == 'archived' or child['certification'] == 'rejected':
            _fail('dependency_unavailable')
        if not set(child['contract']['effects']) <= set(candidate['contract']['effects']):
            _fail('effects_underdeclared')
        _check_binding(step['arguments'], child['contract']['input_schema'], candidate['contract']['input_schema'], earlier)
        earlier[step['id']] = child['contract']['output_schema']
    _check_binding(candidate['implementation']['output'], candidate['contract']['output_schema'], candidate['contract']['input_schema'], earlier)
    closure = {}
    def collect(ref):
        if ref['id'] in closure:
            return
        child = lookup[ref['id']]
        closure[ref['id']] = child
        for dependency in child['dependencies']:
            collect(dependency)
    for dependency in candidate['dependencies']:
        collect(dependency)
    result_snapshot = create_capability_snapshot(expected_owner, [capability_ref(candidate)], [candidate, *closure.values()])
    return {'capability': candidate, 'snapshot': result_snapshot,
            'construction_snapshot_sha256': snapshot['digest'], 'proposal_sha256': capability_digest(proposal)}
