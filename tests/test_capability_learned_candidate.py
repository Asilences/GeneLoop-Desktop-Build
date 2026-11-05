"""Frozen learned candidates use the original controller and independent Store.

Actual local Runtime arithmetic is diagnostic, with no model or RSI benefit claim.
The scene subclass supplies host inputs/publication only; construct is inherited.
"""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.capability_contract import capability_ref
from src.adapters.capability_improvement import evidence, run_improvement
from src.adapters.capability_motif_learning import learn_capability_motifs
from src.adapters.capability_scene import CapabilityImprovementAdapter
from tests.test_capability_motif_learning import corpus, put, run_driver


class ArithmeticScene(CapabilityImprovementAdapter):
    def freeze_publication_inputs(self, job):
        return json.loads(evidence(job['publication_plan']))

    def inspect_run(self, entry, owner):
        raise AssertionError('this explicit diagnostic has no discovery input')

    def raw_library(self):
        return copy.deepcopy(getattr(self, 'published_library', {
            'snapshot': self.seed, 'head': None, 'catalog': []}))

    def publish(self, job, candidate, attempt, expected_latest):
        # Host-frozen independent predicates, never selected by the learned row.
        inputs = self.templates[job['id']]
        publication = run_driver({'action': 'publish', 'compiled': candidate,
            'seed': self.seed, 'directory': str(Path(self.plan['store']).parent),
            'label': job['id'], 'expectedLatest': expected_latest, **inputs})
        self.published_library = publication['library']
        self.publication = publication
        ref = put(attempt / 'publication-evidence.json', publication)
        return {'status': 'published',
            'publication_sha256': publication['publication']['publication_sha256'],
            'evidence_ref': ref}


@pytest.fixture
def learned_plan(tmp_path, corpus):
    _, snapshot, c_ref, _, traces = corpus
    learned = learn_capability_motifs(traces[:2], traces[2:], snapshot)['candidates'][0]
    task = {'id': 'learn-D', 'instruction': 'Diagnose learned C plus double composition',
            'contract': copy.deepcopy(learned['proposal']['contract'])}
    independent = {'validation_input': {'p0_value': 11}, 'followup_input': {'p0_value': 17},
                   'expected_validation': {'value': 24}, 'expected_followup': {'value': 36}}
    job = {'id': 'learn-D', 'objective': 'capability_acquisition',
        'task': put(tmp_path / 'task.json', task),
        'learned_candidate': put(tmp_path / 'learned.json', learned),
        'publication_plan': put(tmp_path / 'independent-check.json', independent),
        'observations': [{'task_id': trace['task_id'], 'kind': 'repeated_structure',
            'split': 'training', 'summary': 'Observed C followed by double',
            'evidence': put(tmp_path / (trace['task_id'] + '.json'), trace)} for trace in traces[:2]]}
    plan = {'format': 'capability_improvement_plan_v1', 'id': 'learned-controller-wiring',
        'owner': snapshot['owner'], 'output': str(tmp_path / 'controller'),
        'store': str(tmp_path / 'D' / 'store'), 'ledger_root': str(tmp_path / 'ledger'),
        'seed': put(tmp_path / 'seed.json', snapshot), 'seed_catalog': put(tmp_path / 'catalog.json', {}),
        'recursive_abstraction': {'enabled': True},
        'policy': {'version': 'capability_improvement_policy_v1', 'max_repairs': 0}, 'jobs': [job]}
    return plan, learned, c_ref


def test_learned_D_enters_original_scene_controller_and_store(learned_plan):
    plan, learned, c_ref = learned_plan
    adapter = ArithmeticScene(plan)
    assert ArithmeticScene.construct is CapabilityImprovementAdapter.construct
    result = run_improvement(plan, adapter, execute=True)
    d_ref = capability_ref(learned['compiled']['capability'])
    assert result['outcomes'][0]['status'] == 'published'
    assert result['outcomes'][0]['capability'] == d_ref
    assert adapter.publication['result']['followup_passed'] is True
    current = adapter.library()['snapshot']
    assert d_ref in current['roots'] and c_ref in current['roots']
    assert next(c for c in current['capabilities'] if c['id'] == d_ref['id'])['certification'] == 'certified'
    attempt = Path(plan['output']) / 'learn-D' / 'attempt-0'
    construction = json.loads((attempt / 'result.json').read_text(encoding='utf-8'))
    assert construction['model_called'] is False and construction['provider_requests'] == 0
    assert construction['publication_authorized'] is False
    assert json.loads((attempt / 'learning-provenance.json').read_text(encoding='utf-8')) == learned['provenance']
    assert result['efficiency_conclusion'] is None and result['creation_benefit'] is None


@pytest.mark.parametrize('setting', [None, {'enabled': False}])
def test_learned_candidate_requires_explicit_research_enablement(learned_plan, setting):
    plan, _, _ = learned_plan
    if setting is None:
        plan.pop('recursive_abstraction')
    else:
        plan['recursive_abstraction'] = setting
    with pytest.raises(ValueError, match='recursive_abstraction_disabled'):
        ArithmeticScene(plan)
    with pytest.raises(ValueError, match='recursive_abstraction_disabled'):
        run_improvement(plan, None, execute=True)
    assert not Path(plan['output']).exists()


def test_frozen_candidate_bytes_cannot_change_after_configuration(learned_plan):
    plan, _, _ = learned_plan
    adapter = ArithmeticScene(plan)
    Path(plan['jobs'][0]['learned_candidate']['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence_changed'):
        run_improvement(plan, adapter, execute=True)
    assert not Path(plan['output']).exists()


@pytest.mark.parametrize('change', ['provenance', 'identity', 'contract'])
def test_evidence_identity_and_host_contract_guards_prevent_publication(learned_plan, change):
    plan, learned, _ = learned_plan
    job = plan['jobs'][0]
    if change == 'identity':
        learned['compiled']['capability']['id'] = 'forged-identity'
        job['learned_candidate'] = put(Path(job['learned_candidate']['path']), learned)
        expected = 'identity_changed'
    elif change == 'contract':
        task = json.loads(evidence(job['task']))
        task['contract']['input_schema']['description'] = 'Different host-frozen contract'
        job['task'] = put(Path(job['task']['path']), task)
        expected = 'learned_contract_changed'
    else:
        Path(learned['provenance']['evidence'][0]['path']).write_text('{}', encoding='utf-8')
        expected = 'evidence_changed'
    adapter = ArithmeticScene(plan)
    result = run_improvement(plan, adapter, execute=True)
    assert all(row['status'] != 'published' for row in result['outcomes'])
    attempt = Path(plan['output']) / 'learn-D' / 'attempt-0'
    failure = json.loads((attempt / 'result.json').read_text(encoding='utf-8'))
    assert failure['status'] == 'failed' and expected in failure['error']
    assert failure['provider_requests'] == 0 and not hasattr(adapter, 'publication')
