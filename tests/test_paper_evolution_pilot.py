"""Host wiring diagnostics; no model session or empirical benefit claim."""
import importlib.util
import importlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adapters.capability_feedback import file_ref, verify
from tests.test_capability_evolution_inputs import valid_fixture, put


def module():
    path = Path(__file__).resolve().parents[1] / 'scripts/run-paper-evolution.py'
    spec = importlib.util.spec_from_file_location('paper_evolution_pilot_test', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def policy(tmp_path):
    return put(tmp_path / 'policy.json', {'quality_tolerance': 0, 'cost_tolerance_usd': '0.001',
        'minimum_samples': 1, 'max_cost_increase_ratio': '0.25', 'min_quality_gain': '0.01',
        'minimum_quality': 1})


@pytest.mark.parametrize('builder', [False, True])
def test_execution_only_and_combined_inputs_reach_same_no_change_continuation(tmp_path, monkeypatch, builder):
    pilot = module()
    adapter = importlib.import_module(pilot.PaperEvolutionAdapter.__module__)
    cycle = importlib.import_module(pilot.run_evolution_cycle.__module__)
    monkeypatch.setattr(adapter, 'OWNER', 'owner')
    monkeypatch.setattr(adapter, 'SCOPE', 'paper-research')
    row_ref = put(tmp_path / 'execution.json', {'task_id': 'original-execution', 'source_identity': 'input-one',
        'stage': 'execution', 'relation': 'paper-work', 'status': 'passed', 'capabilities': [], 'evidence': []})
    entry = {'split': 'training', 'scope': 'paper-research', 'evidence': row_ref}
    monkeypatch.setattr(adapter, 'index_history', lambda *_: ([entry], {'evaluation': [], 'development': []}))
    monkeypatch.setattr(adapter, 'inspect_history', lambda ref, owner: json.loads(verify(ref)))
    history = put(tmp_path / 'history.json', {})
    policy_ref = policy(tmp_path)
    for role in ('development', 'evaluation'):
        (tmp_path / 'evaluation-tasks' / role / 'task-one').mkdir(parents=True)
    monkeypatch.setattr(adapter, 'task_manifest', lambda path, **kwargs: {'id': path.name})
    class Gate:
        def __init__(self, *_): self.state = SimpleNamespace(reserved_usd=Decimal(0))
        def __enter__(self): return self
        def __exit__(self, *_): pass
    monkeypatch.setattr(pilot, 'CumulativeProposalGate', Gate)
    monkeypatch.setattr(adapter, 'BenchmarkHost', lambda *args, **kwargs: SimpleNamespace())
    def investigate(view, **kwargs):
        expected = 3 if builder else 1
        assert len(view.observations) == expected
        result = {'status': 'no_change', 'submissions': []}
        directory = kwargs['output']; directory.mkdir()
        put(directory / 'result.json', result)
        return result
    monkeypatch.setattr(cycle, 'run_investigation', investigate)
    monkeypatch.setattr(pilot.sys, 'platform', 'linux')
    args = ['run-paper-evolution', '--history', history['path'], '--policy', policy_ref['path'],
        '--output', str(tmp_path / 'run'), '--ledger-root', str(tmp_path / 'ledger'),
        '--max-tool-calls', '10', '--timeout-seconds', '60', '--call-model']
    if builder:
        manifest, snapshot, *_ = valid_fixture(tmp_path)
        args += ['--evolution-input-manifest', manifest['path'], '--require-builder-evidence']
    monkeypatch.setattr(pilot.sys, 'argv', args)
    pilot.main()
    feedback = json.loads((tmp_path / 'run/feedback-overview.json').read_text())
    assert feedback['experiences']['observations'] == (3 if builder else 1)
    assert feedback['capabilities']['selectable'] == (2 if builder else 0)
    frozen = json.loads((tmp_path / 'run/effective.json').read_text())
    assert frozen['experiment_scope'] == 'task_strategy_pilot'
    assert frozen['budget_usd'] is None and frozen['max_requests'] is None


def test_builder_specific_requirement_does_not_apply_to_general_execution_investigation(tmp_path, monkeypatch):
    pilot = module()
    monkeypatch.setattr(pilot.sys, 'argv', ['run-paper-evolution', '--history', 'unused', '--policy', 'unused',
        '--output', str(tmp_path / 'unused'), '--ledger-root', 'unused', '--max-tool-calls', '10',
        '--timeout-seconds', '60', '--require-builder-evidence'])
    with pytest.raises(SystemExit): pilot.main()
    assert not (tmp_path / 'unused').exists()


def candidate(tmp_path, name, cost, *, adoption=True):
    strategy = put(tmp_path / (name + '.json'), {'id': 'strategy-' + name, 'revision_sha256': name * 64})
    receipt = put(tmp_path / (name + '-receipt.json'), {'verdict': {'passed': True}})
    admitted = {'outcome': {'selection': {'strategy': strategy, 'evaluation': receipt}}}
    row = {'strategy_sha256': name * 64, 'semantic_adoption': adoption, 'verdict': {'passed': True},
           'runs': [{'score': 1, 'model': {'observed_model_usd': '1'}},
                    {'score': 1, 'model': {'observed_model_usd': cost}}]}
    return admitted, row


def test_selection_uses_frozen_gain_and_cost_instead_of_last_submission(tmp_path):
    pilot = module()
    best, best_row = candidate(tmp_path, 'a', '0.4')
    later, later_row = candidate(tmp_path, 'b', '0.8')
    choice = pilot.select_pilot_candidate([best, later], [best_row, later_row], policy(tmp_path))
    assert choice['selection'] == best['outcome']['selection']
    assert choice['ranking'][0]['task_model_cost_usd'] == '0.4'


@pytest.mark.parametrize('cost,adoption', [('1', True), ('1.2', True), (None, True), ('0.4', None), ('0.4', False)])
def test_neutral_negative_unknown_or_unobserved_behavior_keeps_current_method(tmp_path, cost, adoption):
    pilot = module()
    submission, row = candidate(tmp_path, 'a', cost, adoption=adoption)
    choice = pilot.select_pilot_candidate([submission], [row], policy(tmp_path))
    assert choice['status'] == 'retain_current' and choice['selection'] is None
