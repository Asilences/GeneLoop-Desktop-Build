"""Statically encode a small Python spelling of an existing Compose draft.

This is an authoring syntax, not a Python executor. Calls become graph nodes;
names and string subscripts become bindings. Existing draft/IR checks remain
responsible for visibility, exact versions, types, effects and certification.
"""
from __future__ import annotations

import ast
import math
import re


MAX_SOURCE_BYTES = 262144
MAX_AST_NODES = 10000
MAX_BINDING_DEPTH = 48
_ALIAS = re.compile(r'c[1-9][0-9]*\Z')
_RESERVED = frozenset(('value', 'capability', 'program', 'build',
                       '__proto__', 'prototype', 'constructor'))
_UNSAFE_FIELDS = frozenset(('__proto__', 'prototype', 'constructor'))


class CompositionSourceError(ValueError):
    def __init__(self, expected, node=None, *, line=None, column=None):
        super().__init__('proposal_composition_source_invalid')
        issue = {'path': ['composition_source'], 'expected': expected,
                 'actual': type(node).__name__ if node is not None else None}
        if line is None:
            line = getattr(node, 'lineno', None)
        if column is None:
            offset = getattr(node, 'col_offset', None)
            column = None if offset is None else offset + 1
        if line is not None:
            issue['line'] = line
        if column is not None:
            issue['column'] = column
        self.diagnostics = {'kind': 'composition_source', 'error': str(self),
                            'issues': [issue]}


def _fail(expected, node=None):
    raise CompositionSourceError(expected, node)


def _field(node):
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        _fail('a literal string field name; numeric/dynamic indexes are not bindings', node)
    if node.value in _UNSAFE_FIELDS:
        _fail('a safe field name', node)
    return node.value


def _binding(node, earlier, depth=0):
    if depth > MAX_BINDING_DEPTH:
        _fail('binding nesting at most 48 levels', node)
    if isinstance(node, (ast.Name, ast.Subscript)):
        path = []
        root = node
        while isinstance(root, ast.Subscript):
            path.append(_field(root.slice))
            root = root.value
        path.reverse()
        if not isinstance(root, ast.Name):
            _fail('a field path rooted at value or a preceding step name', node)
        if root.id == 'value':
            return {'$input': path}
        if root.id in earlier:
            return {'$step': [root.id, *path]}
        _fail('value or a preceding step name; no forward/self references', root)
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None or type(value) in (bool, int, str):
            return value
        if type(value) is float and math.isfinite(value):
            return value
        _fail('a finite JSON scalar', node)
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub))
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in (int, float)):
        value = node.operand.value
        value = -value if isinstance(node.op, ast.USub) else value
        if type(value) is float and not math.isfinite(value):
            _fail('a finite JSON number', node)
        return value
    if isinstance(node, ast.List):
        return [_binding(item, earlier, depth + 1) for item in node.elts]
    if isinstance(node, ast.Dict):
        fields = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                _fail('explicit string keys; dictionary unpacking is not supported', node)
            name = _field(key)
            if name.startswith('$'):
                _fail('ordinary object fields, not compact binding operators', key)
            if name in fields:
                _fail('unique object field names', key)
            fields[name] = _binding(value, earlier, depth + 1)
        return fields
    _fail('JSON scalars, objects, lists, or field paths; no computation or nested calls', node)


def _call(node, earlier):
    if not isinstance(node, ast.Call):
        _fail('a capability.cN(...) or program(...) call assigned to a step', node)
    target = node.func
    if isinstance(target, ast.Name) and target.id == 'program':
        use = '$program'
    elif (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
          and target.value.id == 'capability' and _ALIAS.fullmatch(target.attr)):
        use = target.attr
    else:
        _fail('only capability.cN(...) or program(...) calls', target)
    if node.args:
        _fail('named arguments only; no positional or starred arguments', node)
    arguments = {}
    for keyword in node.keywords:
        if keyword.arg is None:
            _fail('explicit named arguments; no keyword unpacking', keyword)
        if keyword.arg in _UNSAFE_FIELDS or keyword.arg.startswith('$'):
            _fail('a safe argument field name', keyword)
        if keyword.arg in arguments:
            _fail('unique named arguments', keyword)
        arguments[keyword.arg] = _binding(keyword.value, earlier)
    return use, arguments


def compile_composition_source(source: str) -> dict:
    """Return ``{steps, output}`` without running any supplied source.

    The module contains one undecorated ``def build(value)``. Its statements
    assign capability/program calls to unique names, followed by one return.
    ``program(...)`` is the existing newly-acquired-material placeholder;
    resolving it and all capability aliases belongs to the host's IR encoder.
    """
    if not isinstance(source, str) or not source.strip():
        _fail('a nonempty composition source string')
    try:
        size = len(source.encode('utf-8'))
    except UnicodeError as error:
        raise CompositionSourceError('valid UTF-8 composition source') from error
    if size > MAX_SOURCE_BYTES:
        _fail('composition source no larger than 262144 UTF-8 bytes')
    try:
        module = ast.parse(source, mode='exec', type_comments=True)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise CompositionSourceError('valid restricted Python syntax',
                                     line=getattr(error, 'lineno', None),
                                     column=getattr(error, 'offset', None)) from error
    if sum(1 for _ in ast.walk(module)) > MAX_AST_NODES:
        _fail('composition syntax no larger than 10000 AST nodes', module)
    if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
        _fail('exactly one def build(value) function and no module statements', module)
    function = module.body[0]
    args = function.args
    if (function.name != 'build' or function.decorator_list or function.returns is not None
            or function.type_comment is not None or getattr(function, 'type_params', [])
            or args.posonlyargs or len(args.args) != 1 or args.args[0].arg != 'value'
            or args.args[0].annotation is not None or args.vararg is not None
            or args.kwarg is not None or args.kwonlyargs or args.defaults
            or args.kw_defaults):
        _fail('an undecorated def build(value) without annotations or other parameters', function)
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]  # An optional documentation string has no graph meaning.
    if len(body) < 2 or not isinstance(body[-1], ast.Return) or body[-1].value is None:
        _fail('one or more assigned calls followed by one final return expression', function)
    earlier = set()
    steps = []
    for statement in body[:-1]:
        if (not isinstance(statement, ast.Assign) or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name)
                or statement.type_comment is not None):
            _fail('a simple name assignment for each capability call', statement)
        name = statement.targets[0].id
        if name in _RESERVED or name in earlier:
            _fail('a unique step name that does not shadow value/capability/program/build', statement.targets[0])
        use, arguments = _call(statement.value, earlier)
        steps.append({'id': name, 'use': use, 'args': arguments})
        earlier.add(name)
    return {'steps': steps, 'output': _binding(body[-1].value, earlier)}
