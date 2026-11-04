"""Contract-summary research mode diagnostics; no model effectiveness claim."""
import copy
import json

import pytest

from src.adapters import capability_proposal as pilot
from src.adapters.capability_contract import capability_ref
from src.adapters.capability_source_authoring import source_authoring_context
from tests.test_capability_proposal_source import inputs, INTEGER, RECORD
from tests.test_capability_proposal_loop import DiagnosticGate, fake_harness


def test_summary_hides_implementation_and_native_transport_but_retains_contract():
    snapshot, task, audit, operation, names = inputs()
    catalog = {'catalog': [
        {'capability': capability_ref(audit), 'description': 'Read the project score.',
         'example_parameters': {'project': 'example'}},
        {'capability': capability_ref(operation), 'description': 'Transform a score.',
         'example_parameters': {'value': {'score': 7}}}],
        'preferred_roots': [capability_ref(operation)]}
    frozen = copy.deepcopy((snapshot, task, catalog))
    context = source_authoring_context(task, snapshot, catalog, abstract=True)
    assert 'capabilities' not in context and 'definition' not in json.dumps(context)
    assert context['contract_mode'] == 'host_fixed' and context['task'] == task
    row = context['source_interfaces'][0]
    assert row == {'alias': names[operation['id']], 'input_schema': RECORD,
                   'output_schema': RECORD, 'description': 'Transform a score.',
                   'effects': ['read'], 'input_example': {'score': 7},
                   'example_status': 'host_catalog_input_schema_checked_not_execution_evidence'}
    assert 'stdout' not in json.dumps(context) and 'native_input_schema_ref' not in json.dumps(context)
    assert (snapshot, task, catalog) == frozen
    ordinary = source_authoring_context(task, snapshot, catalog)
    assert any('definition' in row for row in ordinary['capabilities'])
    assert 'input_example' not in ordinary['source_interfaces'][0]


def test_invalid_example_is_not_presented_as_callable_input():
    snapshot, task, _, operation, names = inputs()
    catalog = {'catalog': [{'capability': capability_ref(operation),
                           'example_parameters': {'score': 7}}]}
    context = source_authoring_context(task, snapshot, catalog, abstract=True)
    assert not any('input_example' in row for row in context['source_interfaces'])


def test_preview_pins_mode_and_preserves_exact_snapshot_audit(tmp_path):
    snapshot, task, _, _, _ = inputs()
    output = tmp_path/'preview'
    result = pilot.propose_once(task=task, catalog={}, snapshot=snapshot, output=output, abstraction_view=True)
    assert result['status'] == 'preview' and not result['model_called']
    effective = pilot.read_json(output/'effective.json')
    assert effective['abstraction_view'] is True
    assert effective['system_sha256'] == pilot.sha(pilot.ABSTRACTION_SYSTEM)
    assert pilot.read_json(output/'snapshot.json') == snapshot
    assert pilot.read_json(output/'aliases.json') == pilot.aliases(snapshot)
    prompt = (output/'prompt.md').read_text()
    assert '"source_interfaces"' in prompt and '"definition"' not in prompt
    assert '"capabilities"' not in prompt


@pytest.mark.parametrize('before,after', [(False, True), (True, False)])
def test_repair_cannot_silently_change_host_mode(tmp_path, before, after):
    snapshot, task, _, _, _ = inputs()
    pilot.propose_once(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'before', abstraction_view=before)
    with pytest.raises(ValueError, match='proposal_repair_abstraction_view_changed'):
        pilot.prepare_attempt(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'after',
                              repair_from=tmp_path/'before', abstraction_view=after)


def test_summary_repair_does_not_reexpand_previous_compiled_graph(tmp_path):
    snapshot, task, _, _, _ = inputs()
    prior = tmp_path/'before'
    pilot.propose_once(task=task, catalog={}, snapshot=snapshot, output=prior, abstraction_view=True)
    pilot.write(prior/'proposal.json', {'internal_marker': 'do not expose'})
    _, prompt = pilot.prepare_attempt(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'repair',
                                     repair_from=prior, abstraction_view=True)
    assert 'internal_marker' not in prompt


@pytest.mark.parametrize('draft', [{'steps': [], 'output': {}},
                                  {'capability_source': 'def build(value):\n    return value', 'abstraction_view': False}])
def test_old_json_or_model_mode_override_is_explicitly_rejected(tmp_path, monkeypatch, draft):
    snapshot, task, _, _, _ = inputs()
    fake_harness(monkeypatch, json.dumps(draft))
    result = pilot.propose_once(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'bad',
                               gate=DiagnosticGate(), abstraction_view=True)
    assert result['status'] == 'failed' and result['error'] == 'proposal_abstraction_source_required'
    assert result['diagnostics']['issues'][0]['path'] == []
    assert not (tmp_path/'bad'/'candidate.json').exists()


def test_summary_source_uses_original_native_abi_encoder_and_compile(tmp_path, monkeypatch):
    snapshot, task, _, operation, names = inputs()
    task['contract'] = {'input_schema': RECORD, 'output_schema': INTEGER, 'effects': ['read']}
    source = 'def build(value):\n    result = capability.' + names[operation['id']] + "(score=value['score'])\n    return result['score']\n"
    fake_harness(monkeypatch, json.dumps({'capability_source': source}))
    output = tmp_path/'source'
    result = pilot.propose_once(task=task, catalog={}, snapshot=snapshot, output=output,
                               gate=DiagnosticGate(), abstraction_view=True)
    assert result['status'] == 'compiled_candidate'
    cap = pilot.read_json(output/'candidate.json')['capability']
    assert cap['certification'] == 'candidate' and cap['lifecycle'] == 'build_only'
    assert cap['implementation']['steps'][0]['arguments']['fields']['value']['fields']['score'] == {
        'kind': 'input', 'path': ['score']}
    assert cap['implementation']['output']['path'] == ['value', 'score']


def test_summary_accepts_defer(tmp_path, monkeypatch):
    snapshot, task, _, _, _ = inputs()
    fake_harness(monkeypatch, json.dumps({'defer': {'reason': 'insufficient_evidence', 'requirement': 'Independent input evidence'}}))
    result = pilot.propose_once(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'defer',
                               gate=DiagnosticGate(), abstraction_view=True)
    assert result['status'] == 'deferred' and not result.get('candidate_path')


def test_summary_requires_host_contract_and_real_boolean_flag(tmp_path):
    snapshot, task, _, _, _ = inputs()
    del task['contract']
    with pytest.raises(ValueError, match='proposal_source_contract_required'):
        pilot.prepare_attempt(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'absent', abstraction_view=True)
    assert not (tmp_path/'absent').exists()
    with pytest.raises(ValueError, match='proposal_abstraction_view_invalid'):
        pilot.prepare_attempt(task=task, catalog={}, snapshot=snapshot, output=tmp_path/'string', abstraction_view='false')


@pytest.mark.parametrize('enabled,semantic,expected', [(True,True,True),(False,True,False),(True,False,False)])
def test_scene_with_research_gate_honors_host_abstraction_view(tmp_path,monkeypatch,enabled,semantic,expected):
    from src.adapters.capability_scene import CapabilityImprovementAdapter
    snapshot,task,*_=inputs()
    adapter=CapabilityImprovementAdapter.__new__(CapabilityImprovementAdapter)
    adapter.plan={'id':'view-test','output':str(tmp_path),'recursive_abstraction':{'enabled':enabled,'semantic_view':semantic}}
    adapter.pending_programs={}
    class Gate:
        def register_attempt(self,*args):pass
    adapter.gate=Gate()
    seen=[]
    monkeypatch.setattr(pilot,'propose_once',lambda **kw: seen.append(kw) or {'status':'diagnostic'})
    adapter.construct(task,{'snapshot':snapshot,'source_catalog':{}},tmp_path/'attempt',None,None)
    assert seen[0]['abstraction_view'] is expected
