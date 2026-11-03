"""Public source parsing diagnostics; fake Harness is never effectiveness evidence."""
import copy
import hashlib
import json

import pytest

from src.adapters import capability_proposal as pilot
from src.adapters.capability_authoring import aliases
from src.adapters.capability_source_authoring import prepare_capability_source_request, source_authoring_context
from tests.test_capability_source_authoring import fixture, INTEGER, RECORD
from tests.test_capability_proposal_loop import DiagnosticGate, fake_harness


def inputs():
    snapshot, task, audit, operation, names = fixture()
    task['instruction'] = 'Compose the authorized inputs into a reusable transformation.'
    return snapshot, task, audit, operation, names


def test_public_entry_keeps_new_algorithm_and_exact_intent_for_native_acquire(tmp_path, monkeypatch):
    snapshot, task, audit, _, names = inputs()
    original = copy.deepcopy(snapshot)
    algorithm = "def compare(previous, current):\n    # Preserve the model algorithm.\n    return {'delta':current['score']-previous['score']}"
    source = algorithm + "\n\ndef build(value):\n    old = capability." + names[audit['id']] + "(project=value['before'])\n    new = capability." + names[audit['id']] + "(project=value['after'])\n    return compare(old, new)\n"
    fake_harness(monkeypatch, json.dumps({'capability_source': source}))
    output = tmp_path/'source-request'
    result = pilot.propose_once(task=task, catalog={}, snapshot=snapshot, output=output, gate=DiagnosticGate())
    assert result['status'] == 'deferred' and result['construction_gap']['reason'] == 'missing_primitive'
    assert result['model_requested_program'] and result['program_training_mode'] == 'bound_prefix_v1'
    assert result['new_program_step_id'] == 'source_return'
    program = pilot.read_json(result['program_request'])
    assert algorithm in program['source']
    assert program['mode'] == 'json' and program['interface'] == 'function_v1'
    intent = pilot.read_json(result['composition_intent_ref']['path'])
    assert intent['program_sha256'] == pilot.capability_digest(program)
    assert [row['capability'] for row in intent['steps']] == [aliases(snapshot)[names[audit['id']]], aliases(snapshot)[names[audit['id']]], '$program']
    assert intent['steps'][-1]['arguments'] == {'kind':'object','fields':{'value':{'kind':'object','fields':{
        'previous':{'kind':'step','step_id':'old','path':[]}, 'current':{'kind':'step','step_id':'new','path':[]}}}}}
    for key in ('capability_source_ref', 'capability_source_encoding_ref', 'composition_intent_ref'):
        ref = result[key]
        assert hashlib.sha256(pilot.Path(ref['path']).read_bytes()).hexdigest() == ref['sha256']
    assert not (output/'candidate.json').exists()
    assert not (output/'native').exists()  # Parser grants no native execution.
    assert snapshot == original


def test_public_source_without_new_helper_compiles_existing_graph(tmp_path, monkeypatch):
    snapshot, task, _, operation, names = inputs()
    task['contract'] = {'input_schema':RECORD, 'output_schema':INTEGER, 'effects':['read']}
    source = "def build(value):\n    result = capability." + names[operation['id']] + "(score=value['score'])\n    return result['score']\n"
    fake_harness(monkeypatch, json.dumps({'capability_source':source}))
    output = tmp_path/'static'
    result = pilot.propose_once(task=task,catalog={},snapshot=snapshot,output=output,gate=DiagnosticGate())
    assert result['status'] == 'compiled_candidate'
    assert not result.get('program_request')
    candidate = pilot.read_json(output/'candidate.json')['capability']
    assert candidate['certification'] == 'candidate' and candidate['lifecycle'] == 'build_only'
    assert candidate['implementation']['steps'][0]['arguments']['fields'] == {
        'value':{'kind':'object','fields':{'score':{'kind':'input','path':['score']}}}}
    assert candidate['implementation']['output']['path'] == ['value','score']


def test_public_source_context_uses_semantic_interfaces_and_pins_actual_parser(tmp_path):
    snapshot, task, _, operation, names = inputs()
    context = source_authoring_context(task,snapshot,{})
    row = next(row for row in context['source_interfaces'] if row['alias'] == names[operation['id']])
    assert row == {'alias':names[operation['id']], 'input_schema':RECORD, 'output_schema':RECORD}
    assert not any(key in json.dumps(context['source_interfaces']) for key in ('sha256','result_path','input_projection'))
    effective,prompt = pilot.prepare_attempt(task=task,catalog={},snapshot=snapshot,output=tmp_path/'preview')
    assert effective['system_sha256'] == pilot.sha(pilot.SYSTEM)
    assert 'src/adapters/capability_source_authoring.py' in effective['code_versions']
    assert 'src/adapters/capability_program_encoding.py' in effective['code_versions']
    assert 'source_interfaces' in prompt and '"capability_source"' in prompt


def test_source_with_missing_host_contract_defers_to_explicit_diagnostic_without_guessing(tmp_path, monkeypatch):
    snapshot,task,_,_,_ = inputs()
    del task['contract']
    source = "def run(value):\n    return value\n\ndef build(value):\n    return run(value)\n"
    fake_harness(monkeypatch,json.dumps({'capability_source':source}))
    output = tmp_path/'no-contract'
    result = pilot.propose_once(task=task,catalog={},snapshot=snapshot,output=output,gate=DiagnosticGate())
    assert result['status'] == 'failed' and result['error'] == 'proposal_source_contract_required'
    assert result['diagnostics']['issues'][0]['path'] == ['contract']
    assert not (output/'program.json').exists() and not (output/'candidate.json').exists()


@pytest.mark.parametrize('extra', ['program', 'defer', 'steps'])
def test_public_source_request_rejects_multiple_authoring_interfaces(extra):
    snapshot,task,_,_,_ = inputs()
    with pytest.raises(ValueError,match='proposal_draft_shape'):
        prepare_capability_source_request({'capability_source':'def build(value):\n    return value',extra:{}},task,snapshot)
