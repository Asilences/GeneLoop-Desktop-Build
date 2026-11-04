"""Research-entry preflight/accounting diagnostics; no model requests."""
import copy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_capability_improvement import plan_at, put

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rae_real_acceptance',
    ROOT / 'examples/capability-scenes/run-rae-real-acceptance.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def fixture(tmp_path, monkeypatch):
    plan, snapshot, _ = plan_at(tmp_path)
    plan['jobs'] = plan['jobs'][:1]
    Path(plan['ledger_root']).mkdir()
    before = put(tmp_path / 'before.json', {'diagnostic': 'training'})
    validation = put(tmp_path / 'validation.json', {'diagnostic': 'validation'})
    followup = put(tmp_path / 'followup.json', {'diagnostic': 'followup'})
    def case(name, ref):
        return {'id': name, 'inputs': [{'path': '/work/inputs/before.zip', 'source': ref}],
                'input': {'before': '/work/inputs/before.zip'}, 'specification': {'kind': 'frontier_literal_v1'}}
    template = {'libraries': [], 'native_cases': {'paths': [case('training', before)]},
                'validation': case('validation', validation), 'followup': case('followup', followup),
                'program_examples': []}
    plan['jobs'][0]['publication_plan'] = put(tmp_path / 'template.json', template)
    source = tmp_path / 'source.json'
    put(source, plan)
    monkeypatch.setattr(entry, 'FrontierGate', lambda *a, **k: pytest.fail('preview opened model gate'))
    return source, plan, template, snapshot


def test_preview_preserves_fixed_task_and_checks_native_catalog_without_payment(tmp_path, monkeypatch):
    source, plan, template, _ = fixture(tmp_path, monkeypatch)
    plan['construction_feedback'] = {'max_reconsiderations': 1, 'history': []}
    plan['recursive_abstraction'] = {'enabled': True}
    plan['discovery'] = []
    put(source, plan)
    result = entry.acceptance(source, tmp_path / 'preview', private_root=tmp_path)
    assert result['status'] == 'frozen_preview' and result['model_requests'] == 0
    frozen = entry.read(tmp_path / 'preview/frozen.json')
    new = entry.read(tmp_path / 'preview/plan.json')
    new_template = entry.read(tmp_path / 'preview/publication-template.json')
    assert new['seed'] == plan['seed'] and new['jobs'][0]['task'] == plan['jobs'][0]['task']
    assert new['ledger_root'] == plan['ledger_root'] and new['policy']['max_repairs'] == 2
    assert set(frozen['removed_options']) == {'construction_feedback', 'recursive_abstraction', 'discovery'}
    assert 'construction_feedback' not in new and frozen['effective_max_reconsiderations'] == 0
    assert frozen['observe_builder'] is False and 'recursive_abstraction' not in new
    assert 'not a total request cap' in frozen['repair_limit_scope']
    assert new_template['validation'] == template['validation'] and new_template['followup'] == template['followup']
    assert new_template['presentation']['source_primary'] is True
    assert frozen['authoring_view'] == 'source_primary_v1'
    assert frozen['presentation_change']['before'] == template.get('presentation', {})
    assert new_template['construction_cases'][0]['split'] == 'training'
    assert new_template['construction_cases'][0]['inputs'] == template['native_cases']['paths'][0]['inputs']
    assert (tmp_path / 'preview/native-catalogs.json').is_file()
    assert not (tmp_path / 'preview/run').exists() and not (tmp_path / 'preview/research-requests.jsonl').exists()
    assert frozen['head'] == entry.checkout_head() and frozen['code_sha256']
    with pytest.raises(FileExistsError):
        entry.acceptance(source, tmp_path / 'preview', private_root=tmp_path)


def test_builder_observation_is_an_explicit_new_condition(tmp_path, monkeypatch):
    source, plan, _, _ = fixture(tmp_path, monkeypatch)
    old = {'enabled': False}
    plan['recursive_abstraction'] = old
    put(source, plan)
    entry.acceptance(source, tmp_path / 'observed', private_root=tmp_path, observe_builder=True)
    frozen = entry.read(tmp_path / 'observed/frozen.json')
    new = entry.read(tmp_path / 'observed/plan.json')
    assert new['recursive_abstraction'] == {'enabled': True, 'builder_learning': {'enabled': True}}
    assert frozen['observe_builder'] is True and frozen['removed_options']['recursive_abstraction'] == old
    assert new['jobs'][0]['task'] == plan['jobs'][0]['task'] and new['seed'] == plan['seed']


@pytest.mark.parametrize('failure', ['changed_input', 'foreign_split', 'missing_ledger', 'multiple_jobs'])
def test_preflight_rejection_is_persisted_before_payment(tmp_path, monkeypatch, failure):
    source, plan, template, _ = fixture(tmp_path, monkeypatch)
    if failure == 'changed_input':
        Path(template['validation']['inputs'][0]['source']['path']).write_text('{}', encoding='utf-8')
    elif failure == 'foreign_split':
        template['construction_cases'] = [{**template['validation'], 'split': 'validation'}]
        plan['jobs'][0]['publication_plan'] = put(tmp_path / 'template.json', template)
    elif failure == 'missing_ledger':
        plan['ledger_root'] = str(tmp_path / 'missing')
    else:
        plan['jobs'].append({**copy.deepcopy(plan['jobs'][0]), 'id': 'another'})
    put(source, plan)
    with pytest.raises(ValueError):
        entry.acceptance(source, tmp_path / 'rejected', private_root=tmp_path)
    assert entry.read(tmp_path / 'rejected/failure.json')['status'] == 'failed'
    assert not (tmp_path / 'rejected/research-requests.jsonl').exists()


class Gate:
    def __init__(self, root, journal, *, deadline):
        self.root = Path(root)
        self.state = SimpleNamespace(request_count=7, reserved_usd=0.5)
        self.request_cells = {7: 'research'}
        self.exact_costs = {7: None}
        self.completed = {}
        self.budget = None
        self.deadline = deadline
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def activate(self, cell, limit):
        self.budget = SimpleNamespace(spent=Decimal('0.5'))


@pytest.mark.parametrize('interrupted', [False, True])
def test_failed_or_interrupted_controller_keeps_unknown_usage_and_never_claims_acceptance(tmp_path, monkeypatch, interrupted):
    source, _, _, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(entry, 'FrontierGate', Gate)
    def controller(*args, **kwargs):
        assert kwargs['execute'] is True
        if interrupted:
            raise KeyboardInterrupt('diagnostic cancellation')
        return {'status': 'completed', 'outcomes': [{'status': 'deferred'}]}
    monkeypatch.setattr(entry, 'run_improvement', controller)
    if interrupted:
        with pytest.raises(KeyboardInterrupt):
            entry.acceptance(source, tmp_path / 'run', call_model=True, private_root=tmp_path)
    else:
        entry.acceptance(source, tmp_path / 'run', call_model=True, private_root=tmp_path)
    result = entry.read(tmp_path / 'run/result.json')
    assert result['status'] == ('interrupted' if interrupted else 'not_accepted')
    assert result['model_requests'] == 1 and result['observed_model_usd_decimal'] is None
    assert result['research_accounted_usd_decimal'] == '0.5'
    assert result['total_economic_cost'] is None and result['requests'][0]['usage'] is None


def test_archive_does_not_inherit_parent_checkout_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(entry, 'ROOT', tmp_path)
    monkeypatch.setattr(entry.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=str(tmp_path.parent)))
    assert entry.checkout_head() is None
