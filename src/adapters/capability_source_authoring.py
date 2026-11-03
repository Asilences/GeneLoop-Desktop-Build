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
MAX_GRAPH_DEPTH = 8
MAX_GRAPH_NODES = 64
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


def _input_path(capability):
    """Expand only the certified Script JSON object's native value envelope.

    This is the single-source API's declared signature, never a guess from
    supplied values. Arrays/scalars and domain-level composition inputs remain
    ordinary named arguments exactly as specified by their native contracts.
    """
    implementation = capability['implementation']
    schema = capability['contract']['input_schema']
    if (implementation['kind'] != 'legacy'
            or implementation['legacy_ref'].get('backend') != 'script_motif'
            or schema.get('type') != 'object'
            or set(schema.get('properties', {})) != {'value'}
            or set(schema.get('required', [])) != {'value'}
            or schema.get('additionalProperties') is not False):
        return []
    value = schema['properties']['value']
    if (isinstance(value, dict) and value.get('type') == 'object' and isinstance(value.get('properties'), dict)
            and isinstance(value.get('required'), list)):
        return ['value']
    return []


def source_callable_interfaces(snapshot):
    """Expose semantic signatures; pin the unabridged native contract by ref."""
    snapshot = validate_capability_snapshot(snapshot)
    lookup = {c['id']: c for c in snapshot['capabilities']}
    result = []
    for alias, ref in aliases(snapshot).items():
        cap = lookup[ref['id']]; path = _result_path(cap); input_path = _input_path(cap)
        native_input = cap['contract']['input_schema']
        source_input = native_input['properties']['value'] if input_path else native_input
        schema = cap['contract']['output_schema']
        if path: schema = schema['properties']['value']
        result.append({'alias': alias, 'capability': copy.deepcopy(ref),
                       'input_schema': copy.deepcopy(source_input), 'input_projection': input_path,
                       'native_input_schema_ref': {'capability': copy.deepcopy(ref),
                           'schema_path': ['contract', 'input_schema'], 'sha256': capability_digest(native_input)},
                       'output_schema': copy.deepcopy(schema), 'result_path': path})
    return result


def _copy_binding(binding, node, budget):
    budget[0] -= 1
    if budget[0] < 0: _fail('expanded bindings at most 10000 nodes', node)
    if isinstance(binding, list): return [_copy_binding(value, node, budget) for value in binding]
    if isinstance(binding, dict): return {key: _copy_binding(value, node, budget) for key, value in binding.items()}
    return binding


def _resolve(binding, scope, node, budget=None):
    """Substitute explicit local symbols; scope values already have ABI views."""
    if budget is None: budget = [MAX_AST_NODES]
    budget[0] -= 1
    if budget[0] < 0: _fail('expanded bindings at most 10000 nodes', node)
    if isinstance(binding, list): return [_resolve(v, scope, node, budget) for v in binding]
    if not isinstance(binding, dict): return binding
    if '$input' in binding or '$step' in binding:
        name, path = ('value', binding['$input']) if '$input' in binding else (binding['$step'][0], binding['$step'][1:])
        if name not in scope: _fail('a declared parameter or preceding local call', node, actual=name)
        selected = scope[name]
        for index, field in enumerate(path):
            if isinstance(selected, dict) and ('$input' in selected or '$step' in selected):
                operator = '$input' if '$input' in selected else '$step'
                return {operator: [*selected[operator], *path[index:]]}
            if not isinstance(selected, dict) or field not in selected:
                _fail('an explicitly bound object field', node, actual=field)
            selected = selected[field]
        return _copy_binding(selected, node, budget)
    return {key: _resolve(value, scope, node, budget) for key, value in binding.items()}


def _bound(node, scope, budget=None):
    try: return _resolve(_binding(node, set(scope)), scope, node, budget)
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


def _helper_arguments(call, function, scope):
    positional, keyword_only = _signature(function)
    if len(call.args) > len(positional) or any(isinstance(n, ast.Starred) for n in call.args):
        _fail('explicit helper arguments matching its declared parameters', call)
    budget = [MAX_AST_NODES]
    values = {name: _bound(node, scope, budget) for name, node in zip(positional, call.args)}
    for keyword in call.keywords:
        if (keyword.arg is None or keyword.arg not in positional + keyword_only
                or keyword.arg in values):
            _fail('each declared helper argument exactly once, without unpacking', keyword)
        values[keyword.arg] = _bound(keyword.value, scope, budget)
    names = positional + keyword_only
    if set(values) != set(names):
        _fail('all declared helper parameters explicitly bound', call,
              actual={'required': names, 'provided': list(values)})
    return {name: values[name] for name in names}, positional, keyword_only


def _graph_helpers(helpers):
    """Propagate host-call ownership through local named calls, never execute."""
    edges = {name: {node.func.id for node in ast.walk(function)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in helpers} for name, function in helpers.items()}
    graph = {name for name, function in helpers.items()
             if any(isinstance(node, ast.Name) and node.id == 'capability' for node in ast.walk(function))}
    while True:
        expanded = graph | {name for name, calls in edges.items() if calls & graph}
        if expanded == graph: break
        graph = expanded
    visited = set()
    def visit(name, stack):
        if name in stack: _fail('nonrecursive static graph helpers', helpers[name], actual=[*stack, name])
        if len(stack) >= MAX_GRAPH_DEPTH: _fail('static graph helper depth at most 8', helpers[name])
        if name in visited: return
        for target in edges[name] & graph: visit(target, [*stack, name])
        visited.add(name)
    for name in sorted(graph): visit(name, [])
    return graph


def _static_body(function, declared):
    positional, keyword_only = _signature(function)
    parameters = positional + keyword_only
    if any(not _NAME.fullmatch(name) or name in declared or name in _RESERVED - {'value'} for name in parameters):
        _fail('explicit static parameters without declaration/operator shadowing', function)
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str): body = body[1:]
    if not body or not isinstance(body[-1], ast.Return) or body[-1].value is None:
        _fail('static assigned calls followed by a final return', function)
    names = set(parameters)
    for statement in body[:-1]:
        if (not isinstance(statement, ast.Assign) or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name) or statement.type_comment
                or not isinstance(statement.value, ast.Call)):
            _fail('one static assigned capability/helper call per statement', statement)
        name = statement.targets[0].id
        if not _NAME.fullmatch(name) or name in names or name in declared or name in _RESERVED:
            _fail('a unique safe local variable without parameter/declaration shadowing', statement.targets[0])
        names.add(name)
    return body


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

    Static graph helpers inline exact calls and explicit parameter bindings;
    one new pure helper call is supported across the expanded graph. Other pure
    helpers can be its algorithm dependencies. ``run(x)`` is a direct native
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
    graph_helpers = _graph_helpers(helpers)
    bodies = {name: _static_body(function, declared) for name, function in helpers.items() if name in graph_helpers}
    bodies['build'] = _static_body(build, declared)
    retained = [node for node in retained if not (isinstance(node, ast.FunctionDef) and node.name in graph_helpers)]
    # These checks do not replace native admission. They keep host calls and
    # executable module declarations out of residual helper source.
    for helper in (function for name, function in helpers.items() if name not in graph_helpers):
        for node in ast.walk(helper):
            if (isinstance(node, ast.Name) and (node.id in FORBIDDEN or node.id == 'build' or node.id in graph_helpers
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
    table = aliases(snapshot); lookup = {c['id']: c for c in snapshot['capabilities']}
    steps = []; used = set(); schemas = {}; calls = []; expansions = []
    selected_helper = None; helper_arguments = None; new_step = None; macro_count = 0
    root_names = {s.targets[0].id for s in bodies['build'][:-1]}

    def append_call(call, name, scope, stack, parent_expansion=None):
        nonlocal selected_helper, helper_arguments, new_step, macro_count
        if isinstance(call.func, ast.Name) and call.func.id in graph_helpers:
            function = helpers[call.func.id]
            if len(stack) >= MAX_GRAPH_DEPTH: _fail('static graph helper depth at most 8', call)
            if function.name in stack: _fail('nonrecursive static graph helpers', call)
            macro_count += 1
            if macro_count > MAX_GRAPH_NODES: _fail('at most 64 static graph helper expansions', call)
            arguments, _, _ = _helper_arguments(call, function, scope)
            expansion_id = 'source_macro_' + str(macro_count)
            first = len(steps); expansion = {'id': expansion_id, 'helper': function.name,
                'source_span': _span(call), 'parameter_bindings': copy.deepcopy(arguments),
                'parent_expansion': parent_expansion}
            expansions.append(expansion)
            output = lower(function, arguments, [*stack, function.name], expansion_id)
            expansion['step_ids'] = [step['id'] for step in steps[first:]]
            expansion['output_binding'] = copy.deepcopy(output)
            return output
        if len(steps) >= MAX_GRAPH_NODES: _fail('a graph of 1 to 64 explicitly requested calls', call)
        if isinstance(call.func, ast.Name) and call.func.id in helpers:
            if selected_helper is not None: _fail('one explicit new helper call per source graph', call)
            function = helpers[call.func.id]
            arguments, positional, keyword_only = _helper_arguments(call, function, scope)
            if function.name == 'run':
                if len(positional) != 1 or keyword_only: _fail('single-parameter run as a direct native entry; other helper names support multiple arguments', function)
                payload = arguments[positional[0]]
            else: payload = arguments
            _check_known(payload, {}, task, schemas, call)
            use = '$program'; args = {'value': payload}
            selected_helper = function; helper_arguments = (positional, keyword_only); new_step = name
            path = ['value']; input_path = ['value']; schema = None; ref = '$program'
        else:
            try: use, raw = _call(call, set(scope))
            except CompositionSourceError as error:
                issue = error.diagnostics['issues'][0]; _fail(issue['expected'], call, line=issue.get('line'), column=issue.get('column'))
            if use not in table: _fail('a currently visible capability alias', call, actual=use)
            ref = table[use]; cap = lookup[ref['id']]
            args = _resolve(raw, scope, call); input_path = _input_path(cap)
            if input_path:
                # Source kwargs are the declared object parameters. Only this
                # host-owned ABI envelope is added; no argument is invented.
                args = {'value': args}
            _check_known(args, cap['contract']['input_schema'], task, schemas, call)
            path = _result_path(cap); schema = cap['contract']['output_schema']
        steps.append({'id': name, 'use': use, 'args': args})
        used.add(name); schemas[name] = schema
        calls.append({'step_id': name, 'capability': copy.deepcopy(ref),
                      'source_span': _span(call), 'semantic_result_path': path,
                      'input_projection': input_path,
                      'host_input_envelope': 'script_json_value' if input_path else None,
                      'graph_helper_stack': list(stack), 'graph_expansion_id': parent_expansion})
        return {'$step': [name, *path]}

    def lower(function, arguments, stack, namespace=None):
        scope = dict(arguments); body = bodies[function.name]
        def step_name(local):
            if namespace is None: return local
            candidate = namespace + '_' + local[:40]; suffix = 0
            while candidate in used or candidate in root_names or candidate in declared:
                suffix += 1; candidate = namespace + '_' + local[:36] + '_' + str(suffix)
            return candidate
        for statement in body[:-1]:
            local = statement.targets[0].id
            scope[local] = append_call(statement.value, step_name(local), scope, stack, namespace)
        result = body[-1].value
        if not isinstance(result, ast.Call): return _bound(result, scope)
        local = 'source_return'; suffix = 0
        while local in scope or local in declared or step_name(local) in used:
            suffix += 1; local = 'source_return_' + str(suffix)
        return append_call(result, step_name(local), scope, stack, namespace)

    output = lower(build, {'value': {'$input': []}}, [])
    if not 1 <= len(steps) <= 64: _fail('a graph of 1 to 64 explicitly requested calls', build)
    # The limit applies to the whole expanded IR, not separately to arguments:
    # many individually small bindings must not amplify one source unchecked.
    _copy_binding({'steps': steps, 'output': output}, build, [MAX_AST_NODES])
    retained_text = [ast.get_source_segment(source, node) for node in retained]
    wrapper = ''; program = None; entrypoint = None
    if selected_helper is not None:
        if 'run' in declared and 'run' not in graph_helpers and selected_helper.name != 'run':
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
                  'graph_helpers': [{'name': name, 'source_span': _span(helpers[name]),
                      'sha256': _sha(ast.get_source_segment(source, helpers[name]))} for name in sorted(graph_helpers)],
                  'graph_expansions': expansions,
                  'calls': calls}
    if selected_helper is not None:
        provenance['helper'] = {'name': selected_helper.name, 'source_span': _span(selected_helper),
                                'sha256': _sha(ast.get_source_segment(source, selected_helper)),
                                'parameter_names': [*helper_arguments[0], *helper_arguments[1]],
                                'program_source_sha256': _sha(program['source'])}
    return {'program': program, 'composition': {'steps': steps, 'output': output},
            'provenance': provenance, 'new_program_step_id': new_step}
