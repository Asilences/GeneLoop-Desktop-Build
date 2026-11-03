"""Encode one model source into the existing capability authoring protocol.

``build`` is a static binding language and is never executed. Pure helper source
is retained verbatim for the existing native admission/certification path. This
module grants no certificate, chooses no dependency and supplies no arguments.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import re

from .capability_authoring import aliases, expand_binding
from .capability_builder import _check_binding
from .capability_composition_source import (
    MAX_AST_NODES, MAX_SOURCE_BYTES, CompositionSourceError, _binding, _call,
)
from .capability_contract import capability_digest, validate_capability_snapshot
from .script_motif_compiler import FORBIDDEN, IMPORTS


FORMAT = 'capability_single_source_authoring_v1'
_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
_BRIDGE = 'capability_source_bridge_'
_RESERVED = {'value', 'capability', 'build', 'program',
             '__proto__', 'prototype', 'constructor'}


class SourceAuthoringError(ValueError):
    def __init__(self, expected, node=None, *, actual=None, line=None, column=None):
        super().__init__('proposal_capability_source_invalid')
        issue = {'path': ['capability_source'], 'expected': expected,
                 'actual': actual if actual is not None else type(node).__name__}
        line = getattr(node, 'lineno', None) if line is None else line
        offset = getattr(node, 'col_offset', None)
        column = (None if offset is None else offset + 1) if column is None else column
        if line is not None: issue['line'] = line
        if column is not None: issue['column'] = column
        self.diagnostics = {'kind': 'capability_source_authoring', 'error': str(self),
                            'issues': [issue]}


def _fail(expected, node=None, **details):
    raise SourceAuthoringError(expected, node, **details)


def _sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _span(node):
    return {'line': node.lineno, 'column': node.col_offset + 1,
            'end_line': node.end_lineno, 'end_column': node.end_col_offset + 1}


def _result_path(capability):
    """Only the exact Script native ABI has a host-owned result envelope."""
    implementation = capability['implementation']
    schema = capability['contract']['output_schema']
    if (implementation['kind'] == 'legacy'
            and implementation['legacy_ref'].get('backend') == 'script_motif'
            and schema.get('type') == 'object'
            and set(schema.get('properties', {})) == {'stdout', 'value'}
            and set(schema.get('required', [])) == {'stdout', 'value'}
            and schema.get('additionalProperties') is False
            and schema['properties']['stdout'].get('type') == 'string'):
        return ['value']
    return []


def source_callable_interfaces(snapshot):
    """Expose the same roots with semantic result views, without source guesses."""
    snapshot = validate_capability_snapshot(snapshot)
    lookup = {c['id']: c for c in snapshot['capabilities']}
    result = []
    for alias, ref in aliases(snapshot).items():
        cap = lookup[ref['id']]; path = _result_path(cap)
        schema = cap['contract']['output_schema']
        if path: schema = schema['properties']['value']
        result.append({'alias': alias, 'capability': copy.deepcopy(ref),
                       'input_schema': copy.deepcopy(cap['contract']['input_schema']),
                       'output_schema': copy.deepcopy(schema), 'result_path': path})
    return result


def _project(binding, projections):
    if isinstance(binding, list): return [_project(v, projections) for v in binding]
    if not isinstance(binding, dict): return binding
    if '$step' in binding:
        step, *path = binding['$step']
        return {'$step': [step, *projections[step], *path]}
    if '$input' in binding or '$literal' in binding: return copy.deepcopy(binding)
    return {key: _project(value, projections) for key, value in binding.items()}


def _bound(node, earlier, projections):
    try: return _project(_binding(node, earlier), projections)
    except CompositionSourceError as error:
        issue = error.diagnostics['issues'][0]
        _fail(issue['expected'], node, line=issue.get('line'), column=issue.get('column'))


def _signature(function):
    args = function.args
    if (function.decorator_list or function.returns is not None or function.type_comment
            or getattr(function, 'type_params', []) or args.posonlyargs
            or args.vararg or args.kwarg or args.defaults or any(v is not None for v in args.kw_defaults)
            or any(a.annotation is not None for a in [*args.args, *args.kwonlyargs])):
        _fail('an undecorated helper with explicit required parameters, no annotations/defaults/unpacking', function)
    positional = [arg.arg for arg in args.args]
    keywords = [arg.arg for arg in args.kwonlyargs]
    if len(set(positional + keywords)) != len(positional + keywords):
        _fail('unique helper parameter names', function)
    return positional, keywords


def _helper_arguments(call, function, earlier, projections):
    positional, keyword_only = _signature(function)
    if len(call.args) > len(positional) or any(isinstance(n, ast.Starred) for n in call.args):
        _fail('explicit helper arguments matching its declared parameters', call)
    values = {name: _bound(node, earlier, projections) for name, node in zip(positional, call.args)}
    for keyword in call.keywords:
        if (keyword.arg is None or keyword.arg not in positional + keyword_only
                or keyword.arg in values):
            _fail('each declared helper argument exactly once, without unpacking', keyword)
        values[keyword.arg] = _bound(keyword.value, earlier, projections)
    names = positional + keyword_only
    if set(values) != set(names):
        _fail('all declared helper parameters explicitly bound', call,
              actual={'required': names, 'provided': list(values)})
    return {name: values[name] for name in names}, positional, keyword_only


def _check_known(binding, expected, task, schemas, node):
    # The new program result is intentionally unknown until native certification.
    def references_unknown(value):
        if isinstance(value, list): return any(references_unknown(v) for v in value)
        if isinstance(value, dict):
            if '$step' in value: return schemas[value['$step'][0]] is None
            return any(references_unknown(v) for v in value.values())
        return False
    if references_unknown(binding): return
    try: _check_binding(expand_binding(binding), expected,
                        task['contract']['input_schema'], schemas)
    except ValueError as error:
        _fail('a binding compatible with the existing exact contract: ' + str(error), node,
              actual={'path': list(getattr(error, 'capability_path', ())),
                      'expected': getattr(error, 'capability_expected', None),
                      'actual': getattr(error, 'capability_actual', None)})


def compile_capability_source(source, task, snapshot, catalog=None):
    """Return a program request and exact composition encoded from one source.

    One local helper call is supported per graph. Other helper declarations can
    be its algorithm dependencies. ``run(x)`` is supported as a direct native
    single-parameter entry; another helper gets a mechanical ``run(value)``
    adapter. Old plain program and JSON authoring are separate, unchanged APIs.
    """
    snapshot = validate_capability_snapshot(snapshot)
    if not isinstance(source, str) or not source.strip(): _fail('nonempty Python source')
    try:
        if len(source.encode('utf-8')) > MAX_SOURCE_BYTES: _fail('source at most 262144 UTF-8 bytes')
        tree = ast.parse(source, type_comments=True)
    except (SyntaxError, ValueError, RecursionError, UnicodeError) as error:
        if isinstance(error, SourceAuthoringError): raise
        _fail('valid bounded Python source', line=getattr(error, 'lineno', None),
              column=getattr(error, 'offset', None))
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES: _fail('at most 10000 AST nodes', tree)
    helpers = {}; builds = []; retained = []; declared = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name in declared: _fail('unique top-level definitions', node)
            declared.add(node.name)
            if node.name == 'build': builds.append(node); continue
            if node.name in _RESERVED or node.name.startswith(_BRIDGE):
                _fail('a helper name distinct from authoring operators', node)
            _signature(node); helpers[node.name] = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            if (getattr(node, 'level', 0) or any(name not in IMPORTS for name in modules)
                    or any(a.name == '*' for a in node.names)):
                _fail('imports admitted by the existing native program policy', node)
            names = [a.asname or (a.name if isinstance(node, ast.ImportFrom) else a.name.split('.')[0]) for a in node.names]
            if any(n in declared or n in _RESERVED or n.startswith(_BRIDGE) for n in names):
                _fail('unambiguous import names distinct from authoring operators', node)
            declared.update(names)
        elif isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                _fail('one named literal module constant', node)
            name = node.targets[0].id
            if name in declared or name in _RESERVED or name.startswith(_BRIDGE):
                _fail('a unique literal constant name', node)
            try: ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, RecursionError):
                _fail('literal module constants; computation belongs inside helpers', node)
            declared.add(name)
        elif not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            _fail('imports, literal constants, pure helper definitions and one static build(value)', node)
        retained.append(node)
    if len(builds) != 1: _fail('exactly one static def build(value)')
    build = builds[0]; positional, keyword_only = _signature(build)
    if positional != ['value'] or keyword_only: _fail('def build(value)', build)
    # These checks do not replace native admission. They keep host calls and
    # executable module declarations out of residual helper source.
    for helper in helpers.values():
        for node in ast.walk(helper):
            if (isinstance(node, ast.Name) and (node.id in FORBIDDEN or node.id == 'build'
                    or node.id.startswith(_BRIDGE))):
                _fail('pure helper computation without dynamic evaluation or build calls', node)
            if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in FORBIDDEN):
                regex_compile = (node.attr == 'compile' and isinstance(node.value, ast.Name)
                                 and any(isinstance(n, ast.Import) and any(a.name == 're' and (a.asname or a.name) == node.value.id for a in n.names) for n in retained))
                if not regex_compile: _fail('native-admitted helper attributes', node)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'capability':
                _fail('capability calls in static build, not inside a native helper', node)
            if isinstance(node, (ast.Global, ast.Nonlocal, ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Yield)):
                _fail('pure helper statements admitted by the native compiler', node)
    body = build.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str): body = body[1:]
    if not body or not isinstance(body[-1], ast.Return) or body[-1].value is None:
        _fail('static assigned calls followed by a final return', build)
    table = aliases(snapshot); lookup = {c['id']: c for c in snapshot['capabilities']}
    steps = []; earlier = set(); projections = {}; schemas = {}; calls = []
    selected_helper = None; helper_arguments = None; new_step = None

    def append_call(call, name):
        nonlocal selected_helper, helper_arguments, new_step
        if isinstance(call.func, ast.Name) and call.func.id in helpers:
            if selected_helper is not None: _fail('one explicit new helper call per source graph', call)
            function = helpers[call.func.id]
            arguments, positional, keyword_only = _helper_arguments(call, function, earlier, projections)
            if function.name == 'run':
                if len(positional) != 1 or keyword_only: _fail('single-parameter run as a direct native entry; other helper names support multiple arguments', function)
                payload = arguments[positional[0]]
            else: payload = arguments
            _check_known(payload, {}, task, schemas, call)
            use = '$program'; args = {'value': payload}
            selected_helper = function; helper_arguments = (positional, keyword_only); new_step = name
            path = ['value']; schema = None; ref = '$program'
        else:
            try: use, raw = _call(call, earlier)
            except CompositionSourceError as error:
                issue = error.diagnostics['issues'][0]; _fail(issue['expected'], call, line=issue.get('line'), column=issue.get('column'))
            if use not in table: _fail('a currently visible capability alias', call, actual=use)
            ref = table[use]; cap = lookup[ref['id']]
            args = _project(raw, projections)
            _check_known(args, cap['contract']['input_schema'], task, schemas, call)
            path = _result_path(cap); schema = cap['contract']['output_schema']
        steps.append({'id': name, 'use': use, 'args': args})
        earlier.add(name); projections[name] = path; schemas[name] = schema
        calls.append({'step_id': name, 'capability': copy.deepcopy(ref),
                      'source_span': _span(call), 'semantic_result_path': path})

    for statement in body[:-1]:
        if (not isinstance(statement, ast.Assign) or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name) or statement.type_comment
                or not isinstance(statement.value, ast.Call)):
            _fail('one static assigned capability/helper call per statement', statement)
        name = statement.targets[0].id
        if not _NAME.fullmatch(name) or name in earlier or name in declared or name in _RESERVED:
            _fail('a unique safe step variable without shadowing source declarations', statement.targets[0])
        append_call(statement.value, name)
    result = body[-1].value
    if isinstance(result, ast.Call):
        name = 'source_return'; suffix = 0
        while name in earlier or name in declared:
            suffix += 1; name = 'source_return_' + str(suffix)
        append_call(result, name); output = {'$step': [name, *projections[name]]}
    else: output = _bound(result, earlier, projections)
    if not 1 <= len(steps) <= 64: _fail('a graph of 1 to 64 explicitly requested calls', build)
    retained_text = [ast.get_source_segment(source, node) for node in retained]
    wrapper = ''; program = None; entrypoint = None
    if selected_helper is not None:
        if 'run' in declared and selected_helper.name != 'run':
            _fail('run reserved for native entry; a selected single-argument run is allowed directly', selected_helper)
        positional, keyword_only = helper_arguments
        if selected_helper.name == 'run': entrypoint = 'direct_model_run'
        else:
            entries = ['value[' + repr(name) + ']' for name in positional]
            entries += [name + '=value[' + repr(name) + ']' for name in keyword_only]
            wrapper = 'def run(value):\n    return ' + selected_helper.name + '(' + ', '.join(entries) + ')\n'
            entrypoint = 'mechanical_argument_adapter'
        program_source = '\n\n'.join(retained_text) + '\n' + ('\n' + wrapper if wrapper else '')
        program = {'source': program_source, 'description': 'Model-defined ' + selected_helper.name + '; native and independent quality checks required',
                   'mode': 'json', 'interface': 'function_v1'}
    provenance = {'format': FORMAT, 'source_sha256': _sha(source),
                  'task_sha256': capability_digest(task), 'construction_snapshot_sha256': snapshot['digest'],
                  'build_executed': False, 'helper_algorithm_changed': False,
                  'entrypoint': entrypoint, 'generated_wrapper': wrapper,
                  'retained_source': [{'kind': type(node).__name__, 'source_span': _span(node), 'sha256': _sha(text)} for node, text in zip(retained, retained_text)],
                  'calls': calls}
    if selected_helper is not None:
        provenance['helper'] = {'name': selected_helper.name, 'source_span': _span(selected_helper),
                                'sha256': _sha(ast.get_source_segment(source, selected_helper)),
                                'parameter_names': [*helper_arguments[0], *helper_arguments[1]],
                                'program_source_sha256': _sha(program['source'])}
    return {'program': program, 'composition': {'steps': steps, 'output': output},
            'provenance': provenance, 'new_program_step_id': new_step}
