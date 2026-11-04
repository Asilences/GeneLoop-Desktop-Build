"""Public acquisition state diagnostics and opt-in real Script sandbox chain.

No model API calls or Paper task/evaluator are involved. Stubs test control flow
only; the marked Linux test alone executes original native admission/certifiers.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.adapters import capability_scene as scene,capability_proposal as pilot
from src.adapters.capability_contract import capability_ref,create_capability_snapshot,capability_digest
from src.adapters.capability_improvement import evidence
from src.adapters.capability_materials import CapabilityMaterials
from src.adapters.capability_source_authoring import prepare_capability_source_request
from tests.test_capability_improvement import put
from tests.test_capability_program_composition import data
from tests.test_capability_proposal_loop import DiagnosticGate,fake_harness


class HostAdapter(scene.CapabilityImprovementAdapter):
    def freeze_publication_inputs(self,job):return json.loads(evidence(job['publication_plan']))


def setup_request(tmp_path):
    d=data(tmp_path)
    route={'backend':'script_motif','libraries':[], 'construction_cases':[
        {'id':'training-'+str(i),'split':'training','input':{'value':i+1},'inputs':[]} for i in range(2)]}
    job={'id':'generic-transform','task':put(tmp_path/'host-task.json',d.task),
        'publication_plan':put(tmp_path/'publication.json',{'program_learning':route}),
        'observations':[]}
    adapter=HostAdapter.__new__(HostAdapter)
    adapter.plan={'owner':'owner'};adapter.materials=CapabilityMaterials(tmp_path/'materials','owner')
    adapter.pending_programs={};adapter.templates={job['id']:{'program_learning':copy.deepcopy(route)}}
    adapter.library=lambda:{'snapshot':d.before}
    attempt=tmp_path/'source-attempt';attempt.mkdir()
    source=d.program['source']+'\ndef build(value):\n    return run(value)\n'
    encoded=prepare_capability_source_request({'capability_source':source},d.task,d.before)
    program_ref=put(attempt/'program.json',encoded['program'])
    result={'status':'deferred','construction_snapshot_sha256':d.before['digest'],
        'model_requested_program':True,'program_training_mode':'bound_prefix_v1',
        'program_request':program_ref['path'],'composition_intent_ref':put(attempt/'composition-intent.json',encoded['composition_intent']),
        'capability_source_ref':put(attempt/'source.json',{'source':source}),
        'capability_source_encoding_ref':put(attempt/'encoding.json',encoded['provenance'])}
    put(attempt/'result.json',result)
    return d,adapter,job,result,attempt,route


def stub_native(monkeypatch,d,calls,*,fail=False):
    from src.adapters import capability_program_training,capability_script_learning
    def prepare(task,snapshot,program_ref,intent_ref,cases,libraries,directory,*,source_refs):
        calls.append(('prefix',copy.deepcopy(cases),json.loads(evidence(intent_ref))))
        Path(directory).mkdir();ref=put(Path(directory)/'result.json',{'diagnostic':True})
        return {'cases':[{'id':'derived-'+str(i),'inputs':[]} for i in range(2)],'evidence':ref}
    def learn(program,cases,directory,source_ref):
        calls.append(('learn',program,cases))
        Path(directory).mkdir()
        if isinstance(fail,BaseException):raise fail
        if fail:raise ValueError('diagnostic_native_rejected')
        put(Path(directory)/'observations.json',json.loads(evidence(d.observations)))
        put(Path(directory)/'certification.json',{'diagnostic':True})
        return d.library
    monkeypatch.setattr(capability_program_training,'prepare_program_cases',prepare)
    monkeypatch.setattr(capability_script_learning,'learn',learn)
    monkeypatch.setattr(scene.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=json.dumps({'capabilities':[d.native]})))


def test_default_acquire_routes_exact_source_intent_through_existing_learner_and_admission(tmp_path,monkeypatch):
    d,adapter,job,result,attempt,route=setup_request(tmp_path);calls=[]
    stub_native(monkeypatch,d,calls)
    outcome=adapter.acquire(job,result,attempt)
    assert outcome['status']=='registered' and len(adapter.materials.records())==1
    assert [row[0] for row in calls]==['prefix','learn']
    assert calls[0][1]==route['construction_cases']
    assert calls[0][2]['steps'][0]['capability']=='$program'
    assert calls[1][2][0]['id']=='derived-0'  # Not route.native_cases.
    saved=json.loads(evidence(outcome['continuation']))
    assert saved['composition_intent_ref']==result['composition_intent_ref']
    assert adapter.pending_programs[capability_digest(d.task)]==outcome['continuation']
    assert adapter.acquire(job,result,attempt)['reason']=='scene_program_acquisition_already_attempted'
    assert len(calls)==2



@pytest.mark.parametrize('outer,inner',[(False,True),(True,False),(True,True)])
def test_builder_learning_is_forwarded_only_when_both_host_flags_are_enabled(tmp_path,monkeypatch,outer,inner):
    from src.adapters import capability_program_training
    d,adapter,job,result,attempt,_=setup_request(tmp_path);calls=[]
    stub_native(monkeypatch,d,calls)
    original=capability_program_training.prepare_program_cases;seen=[]
    def observe(*args,**kwargs):
        seen.append(kwargs.pop('builder_learning',None))
        return original(*args,**kwargs)
    monkeypatch.setattr(capability_program_training,'prepare_program_cases',observe)
    config={'enabled':inner}
    adapter.plan['recursive_abstraction']={'enabled':outer,'builder_learning':config}
    outcome=adapter.acquire(job,result,attempt)
    assert outcome['status']=='registered'
    assert seen==[config if outer and inner else None]


def test_failed_native_acquisition_keeps_negative_evidence_and_never_registers_or_replays(tmp_path,monkeypatch):
    d,adapter,job,result,attempt,_=setup_request(tmp_path);calls=[]
    stub_native(monkeypatch,d,calls,fail=True)
    outcome=adapter.acquire(job,result,attempt)
    assert outcome['status']=='deferred' and outcome['reason']=='diagnostic_native_rejected'
    assert adapter.materials.records()==[] and not adapter.pending_programs
    assert adapter.acquire(job,result,attempt)['reason']=='scene_program_acquisition_already_attempted'
    assert len(calls)==2
    assert list(adapter.materials.directory.glob('acquisitions/*/result.json'))


def test_only_located_model_source_rejection_enters_the_existing_repair_protocol(tmp_path,monkeypatch):
    d,adapter,job,result,attempt,_=setup_request(tmp_path);calls=[]
    error=ValueError('script_admission_rejected')
    error.script_diagnostics={'kind':'script_admission','error':'forbidden_call','line':4,'column':2,
        'source_space':'executable_source','source_line':'example call'}
    stub_native(monkeypatch,d,calls,fail=error)
    before=(attempt/'result.json').read_bytes()
    outcome=adapter.acquire(job,result,attempt)
    assert outcome['status']=='failed' and outcome['repairable'] is True
    assert outcome['diagnostics']['source']==error.script_diagnostics
    assert outcome['diagnostics']['issues'][0]['path']==['program','source']
    assert (attempt/'result.json').read_bytes()==before
    assert not adapter.materials.records() and not adapter.pending_programs


@pytest.mark.parametrize('kind',['compile','verified-data','unknown-runtime','permission','timeout'])
def test_prefix_diagnostics_do_not_authorize_repair_of_unknown_environment_failures(tmp_path,monkeypatch,kind):
    d,adapter,job,result,attempt,_=setup_request(tmp_path);calls=[]
    from src.adapters import capability_program_training
    stub_native(monkeypatch,d,calls)
    error=ValueError('diagnostic_prefix_failure')
    if kind=='compile':
        error.program_training_diagnostics={'kind':'construction_prefix_compile',
            'diagnostics':{'issues':[{'path':['steps',0,'arguments'],'expected':'valid current binding','actual':'bad field'}]}}
    else:
        error.program_training_diagnostics={'kind':'construction_prefix','worker_failures':[{
            'verified_call_binding':kind in ('verified-data','permission','timeout'),'argument_shapes':{},
            'diagnostic':{'category':'data_operation_error' if kind=='verified-data' else 'unknown',
                'exception_type':'TypeError' if kind=='verified-data' else None}}]}
    def reject(*a,**k):raise error
    monkeypatch.setattr(capability_program_training,'prepare_program_cases',reject)
    outcome=adapter.acquire(job,result,attempt)
    assert outcome['status']==('failed' if kind in ('compile','verified-data') else 'deferred')
    assert bool(outcome.get('repairable'))==(kind in ('compile','verified-data'))
    assert outcome['diagnostics']['prefix']==error.program_training_diagnostics
    assert calls==[] and adapter.materials.records()==[]


def test_no_route_and_changed_source_cannot_dispatch_native_learning(tmp_path,monkeypatch):
    d,adapter,job,result,attempt,_=setup_request(tmp_path);calls=[]
    stub_native(monkeypatch,d,calls)
    adapter.templates[job['id']]={}
    assert adapter.acquire(job,result,attempt)['reason']=='scene_program_learning_route_unavailable'
    adapter.templates[job['id']]=json.loads(evidence(job['publication_plan']))
    Path(result['capability_source_ref']['path']).write_text('{}')
    with pytest.raises(ValueError,match='evidence_changed'):adapter.acquire(job,result,attempt)
    assert calls==[]


def test_unsupported_native_prefix_remains_explicitly_deferred(tmp_path,monkeypatch):
    d,adapter,job,result,attempt,_=setup_request(tmp_path);calls=[]
    stub_native(monkeypatch,d,calls)
    result['program_request']=d.program_ref['path'];result['composition_intent_ref']=d.intent_ref
    outcome=adapter.acquire(job,result,attempt)
    assert outcome['reason']=='scene_program_prefix_backend_unsupported'
    assert calls==[] and adapter.materials.records()==[]


@pytest.mark.parametrize('change',['heldout','duplicate-input','bad-path','unknown-command','wrong-backend'])
def test_host_route_validation_fails_closed_before_any_native_action(tmp_path,change):
    _,_,_,_,_,route=setup_request(tmp_path)
    if change=='heldout':route['construction_cases'][1]['split']='heldout'
    elif change=='duplicate-input':route['construction_cases'][1]['input']=route['construction_cases'][0]['input']
    elif change=='bad-path':route['construction_cases'][0]['inputs']=[{'path':'/private/secret','source':put(tmp_path/'x.json',{})}]
    elif change=='unknown-command':route['command']='untrusted executable'
    else:route['backend']='arbitrary_mcp'
    with pytest.raises(ValueError,match='improvement_program_'):HostAdapter.validate_program_learning(route)


def test_common_construct_reconnects_frozen_intent_after_alias_drift_without_model(tmp_path,monkeypatch):
    d=data(tmp_path);adapter=HostAdapter.__new__(HostAdapter)
    continuation=put(tmp_path/'continuation.json',{'format':'capability_program_acquisition_continuation_v1',
        'task_sha256':capability_digest(d.task),'program_ref':d.program_ref,'composition_intent_ref':d.intent_ref,
        'library':d.library,'observations':d.observations,'capability_source_ref':put(tmp_path/'source.json',{})})
    adapter.pending_programs={capability_digest(d.task):continuation}
    monkeypatch.setattr(scene,'run_child',lambda *a,**k:pytest.fail('host encoding must not call model'))
    output=tmp_path/'encoded'
    result=adapter.construct(d.task,{'snapshot':d.after,'source_catalog':{}},output,None,None)
    assert result['status']=='compiled_candidate' and result['provider_requests']==0
    assert not result['model_called'] and result['observed_model_usd']==0
    proposal=json.loads((output/'proposal.json').read_text())
    assert [step['capability'] for step in proposal['steps']]==[capability_ref(d.old),capability_ref(d.native)]
    assert proposal['steps'][1]['arguments']==d.intent['steps'][1]['arguments']
    assert adapter.pending_programs=={}


@pytest.mark.parametrize('module,name',[
    ('scenarios.paper_proofreading.capability_adapter','PaperCapabilityAdapter'),
    ('scenarios.remotion_edit.structured.run_capability_improvement','SourceImprovementAdapter')])
def test_existing_scene_override_delegates_new_source_program_to_common_acquire(monkeypatch,module,name):
    import importlib
    cls=getattr(importlib.import_module(module),name)
    monkeypatch.setattr(scene.CapabilityImprovementAdapter,'acquire',lambda *a:{'status':'diagnostic-common-route'})
    assert cls.__new__(cls).acquire({}, {'model_requested_program':True}, Path('/unused'))=={'status':'diagnostic-common-route'}


native=sys.platform=='linux' and Path('/usr/bin/bwrap').exists() and os.environ.get('RUN_SCRIPT_CAPABILITY_SANDBOX')=='1'
@pytest.mark.skipif(not native,reason='explicit Linux native public acquisition diagnostic')
def test_public_default_acquire_certifies_registers_refreshes_and_executes_new_algorithm(tmp_path,monkeypatch):
    from src.adapters.capability_script_learning import learn
    from src.adapters.capability_script_execution import execute
    construction=[];old_cases=[]
    for i,n in enumerate((2,8)):
        path=tmp_path/('input-'+str(i)+'.json')
        path.write_text(json.dumps({'n':n},sort_keys=True,separators=(',',':')),encoding='utf-8')
        source=scene.reference(path)
        item={'path':'/work/inputs/value.json','source':source}
        old_cases.append({'id':'old-'+str(i),'inputs':[item]})
        construction.append({'id':'training-'+str(i),'split':'training','input':{'first':{'n':n}},'inputs':[item]})
    old_program={'source':"def run(value):\n    return {'n':value['n']+1}\n",'mode':'json',
        'interface':'function_v1','description':'Generic diagnostic increment'}
    old_library=learn(old_program,old_cases,tmp_path/'old-native',scene.reference(__file__),origin='host_diagnostic')
    catalog=json.loads(subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',old_library['path'],
        '--owner','owner'],cwd=scene.ROOT,capture_output=True,text=True,check=True).stdout)
    old=next(cap for cap in catalog['capabilities'] if cap['contract']['input_schema'].get('required')==['value'])
    snapshot=create_capability_snapshot('owner',[capability_ref(old)],[old])
    task={'id':'public-arithmetic','instruction':'Return the transformed current measurement.', 'contract':{
        'input_schema':{'type':'object','properties':{'first':copy.deepcopy(old['contract']['input_schema']['properties']['value'])},
            'required':['first'],'additionalProperties':False},
        'output_schema':{'type':'object','properties':{'total':{'type':'number'}},'required':['total'],'additionalProperties':False},'effects':['read']}}
    template={'program_learning':{'backend':'script_motif','libraries':[old_library],'construction_cases':construction}}
    job={'id':'generic-algorithm','task':put(tmp_path/'task.json',task),
        'publication_plan':put(tmp_path/'publication.json',template),'observations':[]}
    plan={'owner':'owner','seed':put(tmp_path/'seed.json',snapshot),'seed_catalog':put(tmp_path/'catalog.json',catalog),
        'store':str(tmp_path/'store'),'jobs':[job]}
    adapter=HostAdapter(plan)
    source="def combine(prior, margin):\n    return {'total':prior['n']+margin}\n\ndef build(value):\n    previous = capability.c1(n=value['first']['n'])\n    return combine(previous, 3)\n"
    fake_harness(monkeypatch,json.dumps({'capability_source':source}))
    attempt=tmp_path/'proposal'
    result=pilot.propose_once(task=task,catalog=catalog,snapshot=snapshot,output=attempt,gate=DiagnosticGate())
    assert result['status']=='deferred' and result['program_training_mode']=='bound_prefix_v1'
    acquired=adapter.acquire(job,result,attempt)  # Real default, not FrontierAdapter.
    assert acquired['status']=='registered',acquired
    records=adapter.materials.records();assert len(records)==1 and records[0]['backend']=='script_motif'
    request=next(adapter.materials.directory.glob('acquisitions/*/program-training/result.json'))
    training=json.loads(request.read_text())
    assert [json.loads(evidence(case['value'])) for case in training['cases']]==[
        {'prior':{'n':3},'margin':3},{'prior':{'n':9},'margin':3}]
    current=adapter.library()
    assert current['snapshot']['digest']!=snapshot['digest']
    monkeypatch.setattr(scene,'run_child',lambda *a,**k:pytest.fail('exact intent must reconnect without model'))
    output=tmp_path/'after-acquisition'
    compiled=adapter.construct(task,current,output,None,None)
    assert compiled['status']=='compiled_candidate' and not compiled['model_called']
    candidate=json.loads((output/'candidate.json').read_text())
    libraries=[old_library,records[0]['library']]
    heldout_path=tmp_path/'independent.json'
    heldout_path.write_text(json.dumps({'n':14},sort_keys=True,separators=(',',':')),encoding='utf-8')
    heldout_source=scene.reference(heldout_path)
    trace=execute(candidate['snapshot'],capability_ref(candidate['capability']),libraries,
        [{'path':'/work/inputs/value.json','source':heldout_source}],{'first':{'n':14}},tmp_path/'independent',
        'independent-public-check',mode='validate')
    assert trace['result']=={'total':18}  # Independent host arithmetic check.
    assert candidate['capability']['certification']=='candidate'  # No semantic promotion.
