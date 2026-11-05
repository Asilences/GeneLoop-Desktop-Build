"""Actual Builder -> Runtime traces -> original miner -> Store -> next Builder.

Inputs and seed host authority are synthetic. All compiler operations, learning,
certification, publication and receipts execute; no autonomous-model claim.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.adapters.capability_builder_application import BuilderConstructionSession, builder_operation
from src.adapters.capability_contract import capability_ref
from src.adapters.capability_feedback import file_ref
from src.adapters.capability_improvement import save
from src.adapters.capability_motif_learning import learn_capability_motifs
from src.adapters.capability_source_authoring import prepare_capability_source_request
from tests.test_capability_source_authoring import fixture

ROOT = Path(__file__).resolve().parents[1]


def driver(request):
    result = subprocess.run(['node', 'tests/fixtures/rae_builder_driver.mjs'], cwd=ROOT,
        input=json.dumps(request), text=True, encoding='utf-8', capture_output=True,
        env={**os.environ, 'SSS_PYTHON': sys.executable}, timeout=90)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def construction(number):
    snapshot, task, audit, _, names = fixture()
    task = {**task, 'id': 'builder-task-'+str(number)}
    source = "def relation(value):\n    return {'delta': value['score'] + " + str(number) + "}\n\ndef build(value):\n    found = capability." + names[audit['id']] + "(project=value['before'])\n    return relation(found)\n"
    return {'capability_source': source}, task, snapshot, {}


def test_disabled_session_uses_original_builder_without_reading_configuration(tmp_path):
    args = construction(1)
    session = BuilderConstructionSession(enabled=False, snapshot={'bad': True}, directory=tmp_path/'off')
    assert prepare_capability_source_request(*args, construction_session=session) == prepare_capability_source_request(*args)
    assert not (tmp_path/'off').exists()


def test_operations_are_original_compiler_and_preserve_generated_source():
    draft, task, snapshot, catalog = construction(2)
    context = {'draft':draft, 'task':task, 'snapshot':snapshot, 'catalog':catalog}
    parsed = builder_operation('builder_parse', {'context_json':json.dumps(context)})
    frozen = builder_operation('builder_freeze', parsed)
    assert json.loads(frozen['result_json']) == prepare_capability_source_request(draft, task, snapshot, catalog)
    with pytest.raises(ValueError, match='not_allowed'):
        builder_operation('change_validator', {})


def test_builder_trace_learns_and_publishes_same_pipeline_primitive_then_reuses_it(tmp_path):
    seed = driver({'action':'seed', 'owner':'owner'})
    refs = {c['implementation']['legacy_ref']['object_id']: capability_ref(c) for c in seed['capabilities']}
    def executor(library):
        def run(ref, args, directory, task_id):
            directory.mkdir(parents=True)
            result = driver({'action':'run','snapshot':library,'root':ref,'input':args,'task_id':task_id})
            save(directory/'execution.json', result['execution'])
            return file_ref(directory/'execution.json')
        return run
    traces = []
    for number in (2, 3, 5):
        args = construction(number)
        output = tmp_path/('original-'+str(number))
        session = BuilderConstructionSession(enabled=True,snapshot=seed,
            parse_ref=refs['builder_parse'],freeze_ref=refs['builder_freeze'],execute=executor(seed),
            directory=output,task_id='builder-'+str(number))
        observed = prepare_capability_source_request(*args,construction_session=session)
        assert observed == prepare_capability_source_request(*args)
        assert json.loads((output/'result.json').read_text())['status']=='accepted'
        trace=json.loads((output/'trace.json').read_text())
        assert trace['role']=='builder' and len(trace['steps'])==2
        traces.append(trace)
    learned=learn_capability_motifs(traces[:2],traces[2:],seed)
    candidate=next(c for c in learned['candidates'] if len(c['proposal']['steps'])==2)
    assert candidate['provenance']['roles']==['builder']
    assert candidate['proposal']['contract']['input_schema']['required']==['p0_context_json']
    def publication_case(number):
        draft,task,snapshot,catalog=construction(number)
        context={'draft':draft,'task':task,'snapshot':snapshot,'catalog':catalog}
        context_json=json.dumps(context,ensure_ascii=False,separators=(',',':'))
        expected=prepare_capability_source_request(draft,task,snapshot,catalog)
        return {'p0_context_json':context_json},{'result_json':json.dumps(expected,ensure_ascii=False,separators=(',',':'))}
    left,left_expected=publication_case(7);right,right_expected=publication_case(11)
    published=driver({'action':'publish','compiled':candidate['compiled'],'seed':seed,
        'directory':str(tmp_path/'publish'),'validation_input':left,'followup_input':right,
        'expected_validation':left_expected,'expected_followup':right_expected})
    assert published['result']['followup_passed'] is True
    library=published['library']['snapshot']; root=published['result']['candidate']
    assert root in library['roots']
    output=tmp_path/'next-builder'
    selection={'root':root,'input_binding':{'kind':'object','fields':{
        'p0_context_json':{'kind':'input','path':['context_json']}}},'result_path':['result_json']}
    session=BuilderConstructionSession(enabled=True,snapshot=library,execute=executor(library),
        directory=output,task_id='builder-next',learned_selection=selection)
    args=construction(17)
    assert prepare_capability_source_request(*args,construction_session=session)==prepare_capability_source_request(*args)
    result=json.loads((output/'result.json').read_text())
    assert result['status']=='accepted' and result['behavior']=='learned_composition'
    trace=json.loads((output/'trace.json').read_text())
    assert trace['role']=='builder' and len(trace['steps'])==1 and trace['steps'][0]['capability']==root
    assert result['total_cost'] is None and result['efficiency_conclusion'] is None
    # Exact old behavior remains available after learning, with no Runtime call.
    disabled=BuilderConstructionSession(enabled=False,execute=lambda *a:pytest.fail('disabled called Runtime'))
    assert prepare_capability_source_request(*args,construction_session=disabled)==prepare_capability_source_request(*args)


def test_runtime_failure_keeps_evidence_and_uses_original_builder(tmp_path):
    seed=driver({'action':'seed','owner':'owner'})
    refs=[capability_ref(c) for c in seed['capabilities']]
    def fail(*args): raise ValueError('native_unavailable')
    session=BuilderConstructionSession(enabled=True,snapshot=seed,parse_ref=refs[0],freeze_ref=refs[1],
        execute=fail,directory=tmp_path/'failed',task_id='failed')
    args=construction(9)
    assert prepare_capability_source_request(*args,construction_session=session)==prepare_capability_source_request(*args)
    assert json.loads((tmp_path/'failed/result.json').read_text())['status']=='fallback'


def test_cancellation_is_preserved_without_running_baseline(tmp_path):
    seed=driver({'action':'seed','owner':'owner'})
    def cancel(*args): raise KeyboardInterrupt()
    session=BuilderConstructionSession(enabled=True,snapshot=seed,parse_ref=seed['roots'][0],
        execute=cancel,directory=tmp_path/'cancel',task_id='cancel')
    with pytest.raises(KeyboardInterrupt):
        session.prepare(*construction(4),ordinary=lambda:pytest.fail('cancelled ran fallback'))
    assert json.loads((tmp_path/'cancel/result.json').read_text())['status']=='interrupted'
