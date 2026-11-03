"""Shared Script extraction diagnostics; no model or scene quality claim."""
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.adapters.capability_contract import capability_ref, create_capability_snapshot
from src.adapters.capability_program_encoding import freeze_program_composition
from src.adapters.capability_scene import reference
from tests.test_capability_contract import leaf


@pytest.mark.parametrize('legacy,shared,symbols', [
    ('learn', 'capability_script_learning', ['function_module', 'executable_source', 'learn']),
    ('execute', 'capability_script_execution', ['execute']),
    ('program_training', 'capability_program_training', ['TrainingEvidenceUnavailable', 'prepare_program_cases']),
])
def test_legacy_import_is_the_same_shared_implementation(legacy, shared, symbols):
    old = importlib.import_module('scenarios.paper_proofreading.frontier.' + legacy)
    public = importlib.import_module('src.adapters.' + shared)
    assert old is public
    for symbol in symbols:
        assert getattr(old, symbol) is getattr(public, symbol)
        assert getattr(public, symbol).__module__ == 'src.adapters.' + shared


def test_legacy_prefix_injection_reaches_the_shared_function_globals(monkeypatch):
    old = importlib.import_module('scenarios.paper_proofreading.frontier.program_training')
    public = importlib.import_module('src.adapters.capability_program_training')
    sentinel = object()
    monkeypatch.setattr(old, 'execute', sentinel)
    assert public.prepare_program_cases.__globals__['execute'] is sentinel


def test_fresh_public_imports_do_not_load_a_scenario():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', """
import sys
from src.adapters.capability_script_learning import learn, executable_source
from src.adapters.capability_script_execution import execute
from src.adapters.capability_program_training import prepare_program_cases
assert not [name for name in sys.modules if name == 'scenarios' or name.startswith('scenarios.')]
"""], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_shared_training_accepts_an_unrelated_host_task_without_paper_examples(tmp_path, monkeypatch):
    from src.adapters import capability_program_training as training
    cap = leaf('warehouse-diagnostic')
    snapshot = create_capability_snapshot('owner', [capability_ref(cap)], [cap])
    record = {'type': 'object', 'properties': {'quantity': {'type': 'integer'}},
              'required': ['quantity'], 'additionalProperties': False}
    task = {'id': 'warehouse-count', 'contract': {'input_schema': record, 'output_schema': {}, 'effects': ['read']}}
    source = "def run(value):\n    return {'count': value['quantity']}\n"
    program = {'source': source, 'description': 'Generic host diagnostic', 'mode': 'json', 'interface': 'function_v1'}
    composition = {'steps': [{'id': 'count', 'use': '$program',
        'args': {'value': {'quantity': {'$input': ['quantity']}}}}], 'output': {'$step': ['count', 'value']}}
    intent = freeze_program_composition(task, snapshot, program, composition)
    program_path = tmp_path/'program.json'; program_path.write_text(json.dumps(program))
    intent_path = tmp_path/'intent.json'; intent_path.write_text(json.dumps(intent))
    cases = []
    for number in (3, 9):
        path = tmp_path/('order-' + str(number) + '.json')
        path.write_text(json.dumps({'quantity': number}))
        cases.append({'id': 'order-' + str(number), 'split': 'training', 'input': {'quantity': number},
            'inputs': [{'path': '/work/inputs/order.json', 'source': reference(path)}]})
    monkeypatch.setattr(training, 'execute', lambda *a, **k: pytest.fail('No certified prefix was selected'))
    result = training.prepare_program_cases(task, snapshot, reference(program_path), reference(intent_path),
        cases, [], tmp_path/'prepared')
    payloads = [json.loads(Path(case['inputs'][0]['source']['path']).read_text()) for case in result['cases']]
    assert payloads == [{'quantity': 3}, {'quantity': 9}]
    saved = json.loads(Path(result['evidence']['path']).read_text())
    assert saved['task_sha256'] == intent['task_sha256']
    assert all(row['prefix_trace'] is None and row['origin'] == 'explicit_input_or_literal_binding_no_calls' for row in saved['cases'])
    assert json.loads(program_path.read_text())['source'] == source
