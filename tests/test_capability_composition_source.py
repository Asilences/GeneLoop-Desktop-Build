"""Static authoring diagnostics, not a model or recursive-effect experiment."""
import copy

import pytest

from src.adapters.capability_authoring import aliases, diagnose, expand_draft
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_composition_source import (
    CompositionSourceError, compile_composition_source,
)
from tests.test_capability_builder import setup


def test_python_spelling_encodes_existing_capabilities_and_program_placeholder():
    source = '''def build(value):
    before = capability.c4(project=value['before'])
    after = capability.c4(project=value['after'])
    compared = program(value={'before': before, 'after': after})
    return compared['value']
'''
    assert compile_composition_source(source) == {
        'steps': [
            {'id': 'before', 'use': 'c4', 'args': {'project': {'$input': ['before']}}},
            {'id': 'after', 'use': 'c4', 'args': {'project': {'$input': ['after']}}},
            {'id': 'compared', 'use': '$program', 'args': {'value': {
                'before': {'$step': ['before']}, 'after': {'$step': ['after']}}}},
        ],
        'output': {'$step': ['compared', 'value']},
    }


def test_existing_IR_keeps_identity_versions_and_dataflow():
    snapshot, expected = setup()
    original = copy.deepcopy(snapshot)
    current = {ref['id']: name for name, ref in aliases(snapshot).items()}
    first = current[expected['steps'][0]['capability']['id']]
    second = current[expected['steps'][1]['capability']['id']]
    draft = compile_composition_source(f'''def build(value):
    first = capability.{first}(value=value['value'])
    second = capability.{second}(value=first['value'])
    return second
''')
    task = {'id': 'diagnostic', 'instruction': 'Compose current values',
            'contract': expected['contract']}
    proposal = expand_draft(draft, task, snapshot)
    # The first input is assembled explicitly here; its graph meaning remains
    # subject to the existing compiler, not Python execution or type inference.
    expected['steps'][0]['arguments'] = {'kind': 'object', 'fields': {
        'value': {'kind': 'input', 'path': ['value']}}}
    assert proposal == expected
    assert compile_proposal(proposal, snapshot, 'owner')['capability']['certification'] == 'candidate'
    assert snapshot == original
    bad = copy.deepcopy(draft)
    bad['steps'][0]['use'] = 'c99'
    with pytest.raises(ValueError):
        expand_draft(bad, task, snapshot)


def test_whole_input_nested_fields_and_JSON_values_are_bindings_only():
    draft = compile_composition_source('''def build(value):
    """No execution occurs."""
    seen = capability.c12(input=value, nested=value['outer']['inner'], items=[None, True, -2, +3.5, {'text': '$input'}])
    return {'all': seen, 'selected': [seen['result']['name'], value['other']]}
''')
    assert draft['steps'][0]['args'] == {
        'input': {'$input': []}, 'nested': {'$input': ['outer', 'inner']},
        'items': [None, True, -2, 3.5, {'text': '$input'}],
    }
    assert draft['output'] == {'all': {'$step': ['seen']}, 'selected': [
        {'$step': ['seen', 'result', 'name']}, {'$input': ['other']}]}


@pytest.mark.parametrize('source', [
    "import os\ndef build(value):\n x=capability.c1()\n return x",
    "def other(value):\n x=capability.c1()\n return x",
    "@evil\ndef build(value):\n x=capability.c1()\n return x",
    "async def build(value):\n x=capability.c1()\n return x",
    "def build(value, extra=None):\n x=capability.c1()\n return x",
    "def build(value: dict):\n x=capability.c1()\n return x",
    "def build(value) -> dict:\n x=capability.c1()\n return x",
    "def build(value):\n import os\n x=capability.c1()\n return x",
    "def build(value):\n for item in value:\n  x=capability.c1()\n return x",
    "def build(value):\n if value:\n  x=capability.c1()\n return x",
    "def build(value):\n x=capability.c1()\n x=capability.c2()\n return x",
    "def build(value):\n value=capability.c1()\n return value",
    "def build(value):\n capability=capability.c1()\n return capability",
    "def build(value):\n program=capability.c1()\n return program",
    "def build(value):\n x=y=capability.c1()\n return x",
    "def build(value):\n x,y=capability.c1()\n return x",
    "def build(value):\n x: dict=capability.c1()\n return x",
    "def build(value):\n x=eval(value['source'])\n return x",
    "def build(value):\n x=__import__('os').system('anything')\n return x",
    "def build(value):\n x=capability.__getattribute__('c1')()\n return x",
    "def build(value):\n x=capability.c0()\n return x",
    "def build(value):\n x=capability.c01()\n return x",
    "def build(value):\n x=capability.c1(value)\n return x",
    "def build(value):\n x=capability.c1(*value)\n return x",
    "def build(value):\n x=capability.c1(**value)\n return x",
    "def build(value):\n x=capability.c1(v=1,v=2)\n return x",
    "def build(value):\n x=capability.c1(v=x)\n return x",
    "def build(value):\n x=capability.c1(v=later)\n later=capability.c1()\n return x",
    "def build(value):\n x=capability.c1(v=capability.c2())\n return x",
    "def build(value):\n x=capability.c1(v=value.attribute)\n return x",
    "def build(value):\n x=capability.c1(v=value[0])\n return x",
    "def build(value):\n x=capability.c1(v=value[value['key']])\n return x",
    "def build(value):\n x=capability.c1(v=value['__proto__'])\n return x",
    "def build(value):\n x=capability.c1(v={'a': 1, 'a': 2})\n return x",
    "def build(value):\n x=capability.c1(v={**value})\n return x",
    "def build(value):\n x=capability.c1(v={'$step': ['hidden']})\n return x",
    "def build(value):\n x=capability.c1(v=[a for a in value])\n return x",
    "def build(value):\n x=capability.c1(v=1+2)\n return x",
    "def build(value):\n x=capability.c1(v=(1,2))\n return x",
    "def build(value):\n x=capability.c1(v=1e999)\n return x",
    "def build(value):\n x=capability.c1(v=b'bytes')\n return x",
    "def build(value):\n x=capability.c1()\n return x\n x=capability.c2()",
    "def build(value):\n return value",
    "def build(value):\n x=capability.c1()\n return",
    "def build(value):\n x=capability.c1()\n return x\ndef another():\n pass",
])
def test_ambiguous_or_executable_Python_is_rejected(source):
    with pytest.raises(CompositionSourceError, match='proposal_composition_source_invalid'):
        compile_composition_source(source)


def test_diagnostics_include_source_location_without_running_source():
    with pytest.raises(CompositionSourceError) as caught:
        compile_composition_source("def build(value):\n    x = eval(value['code'])\n    return x\n")
    issue = diagnose(caught.value)['issues'][0]
    assert issue['path'] == ['composition_source']
    assert issue['line'] == 2 and issue['column'] == 9
    assert issue['actual'] == 'Name'


@pytest.mark.parametrize('source', [None, {}, '', '  ', 'def build(:', '\ud800'])
def test_invalid_source_values_fail_with_the_public_error(source):
    with pytest.raises(CompositionSourceError):
        compile_composition_source(source)


def test_source_size_and_binding_depth_are_bounded():
    with pytest.raises(CompositionSourceError):
        compile_composition_source(' ' * 262145 + 'def build(value):\n x=capability.c1()\n return x')
    source = 'def build(value):\n x=capability.c1(v=' + '[' * 50 + '0' + ']' * 50 + ')\n return x'
    with pytest.raises(CompositionSourceError):
        compile_composition_source(source)
