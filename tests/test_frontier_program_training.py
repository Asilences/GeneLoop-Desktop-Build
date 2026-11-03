"""Bound-input preparation diagnostics, not model behavior or quality evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.adapters.capability_authoring import aliases
from src.adapters.capability_contract import capability_ref,create_capability_snapshot
from src.adapters.capability_program_encoding import freeze_program_composition
from src.adapters.capability_scene import reference
from scenarios.paper_proofreading.frontier import program_training
from tests.test_capability_builder import setup as builder_setup,RECORD
from tests.test_capability_improvement import put


def fixture(tmp_path,*,prefix=True,payload=None):
    original,_=builder_setup()
    caps=[{**cap,'certification':'certified','lifecycle':'active'} for cap in original['capabilities']]
    snapshot=create_capability_snapshot('owner',[capability_ref(cap) for cap in caps],caps)
    task={'id':'training-diagnostic','instruction':'Compute a reusable relation from current inputs',
        'contract':{'input_schema':RECORD,'output_schema':RECORD,'effects':['read']},
        'program_interface':{'modes':['json','paths']}}
    program={'source':"def run(value):\n    return {'value':value['previous']['value']+value['bonus']}\n",
        'description':'Diagnostic helper, no model or quality claim','mode':'json','interface':'function_v1'}
    steps=[{'id':'prior','use':'c1','args':{'$input':[]}}] if prefix else []
    payload=payload if payload is not None else {'previous':{'$step':['prior']},'bonus':4}
    steps.append({'id':'relation','use':'$program','args':{'value':payload}})
    composition={'steps':steps,'output':{'$step':['relation','value']}}
    intent=freeze_program_composition(task,snapshot,program,composition)
    program_ref=put(tmp_path/'program.json',program);intent_ref=put(tmp_path/'intent.json',intent)
    cases=[]
    for index,n in enumerate((2,8)):
        source=tmp_path/('task-'+str(index)+'.json');source.write_text(json.dumps({'value':n}))
        cases.append({'id':'independent-'+str(index),'split':'training','input':{'value':n},
            'inputs':[{'path':'/work/inputs/task.json','source':reference(source)}]})
    return SimpleNamespace(**locals())


def prepare(d,**changes):
    fields={'task':d.task,'snapshot':d.snapshot,'program_ref':d.program_ref,'intent_ref':d.intent_ref,
        'construction_cases':d.cases,'libraries':[],'directory':d.tmp_path/'prepared'}
    fields.update(changes)
    return program_training.prepare_program_cases(**fields)


def test_actual_model_prefix_is_validated_without_upgrading_its_certificate(tmp_path,monkeypatch):
    d=fixture(tmp_path);calls=[]
    def native(snapshot,root,libraries,inputs,current,directory,task_id,*,mode):
        selected=next(cap for cap in snapshot['capabilities'] if capability_ref(cap)==root)
        assert mode=='validate' and selected['certification']=='candidate' and selected['lifecycle']=='build_only'
        assert all(cap['certification']=='certified' for cap in snapshot['capabilities'] if cap['id']!=root['id'])
        assert selected['implementation']['steps'][0]['capability']==aliases(d.snapshot)['c1']
        calls.append({'input':current,'inputs':inputs,'prefix':selected})
        # A diagnostic native boundary returns current-call data, never oracle examples.
        trace={'status':'succeeded','mode':'validate','result':{'previous':{'value':current['value']+10},'bonus':4},'receipts':[]}
        directory.mkdir(parents=True);(directory/'trace.json').write_text(json.dumps(trace))
        return trace
    monkeypatch.setattr(program_training,'execute',native)
    result=prepare(d)
    values=[json.loads(Path(row['inputs'][0]['source']['path']).read_text()) for row in result['cases']]
    assert values==[{'previous':{'value':12},'bonus':4},{'previous':{'value':18},'bonus':4}]
    assert [call['input'] for call in calls]==[{'value':2},{'value':8}]
    record=json.loads(Path(result['evidence']['path']).read_text())
    assert all(row['prefix_trace'] and row['origin']=='candidate_validation_of_certified_dependencies' for row in record['cases'])
    assert d.snapshot['digest']==record['construction_snapshot_sha256']
    assert all(cap['certification']=='certified' for cap in d.snapshot['capabilities'])


@pytest.mark.parametrize('payload,expected',[
    ({'$input':[]},[{'value':2},{'value':8}]),
    ([{'$input':['value']},'literal'],[[2,'literal'],[8,'literal']]),
    ({'$input':['value']},[2,8]),
])
def test_zero_call_helper_gets_exact_explicit_input_binding(tmp_path,monkeypatch,payload,expected):
    d=fixture(tmp_path,prefix=False,payload=payload)
    monkeypatch.setattr(program_training,'execute',lambda *a,**k:pytest.fail('no calls were selected'))
    result=prepare(d)
    assert [json.loads(Path(row['inputs'][0]['source']['path']).read_text()) for row in result['cases']]==expected


@pytest.mark.parametrize('change',['missing','heldout','changed-source','changed-intent','wrong-program','uncertified','hidden','extra-case'])
def test_untrusted_or_missing_training_data_never_runs_a_prefix(tmp_path,monkeypatch,change):
    d=fixture(tmp_path);changes={}
    monkeypatch.setattr(program_training,'execute',lambda *a,**k:pytest.fail('invalid evidence must fail before execution'))
    if change=='missing':changes['construction_cases']=None
    elif change=='heldout':changes['construction_cases']=[{**row,'split':'final_test'} for row in d.cases]
    elif change=='changed-source':Path(d.cases[0]['inputs'][0]['source']['path']).write_text('changed')
    elif change=='changed-intent':Path(d.intent_ref['path']).write_text('{}')
    elif change=='wrong-program':changes['program_ref']=put(tmp_path/'wrong-program.json',{**d.program,'source':'def run(value):\n return {}\n'})
    elif change=='uncertified':
        caps=[{**cap,'certification':'candidate','lifecycle':'build_only'} for cap in d.snapshot['capabilities']]
        changed=create_capability_snapshot('owner',d.snapshot['roots'],caps)
        updated={**d.intent,'construction_snapshot_sha256':changed['digest']}
        changes.update(snapshot=changed,intent_ref=put(tmp_path/'uncertified-intent.json',updated))
    elif change=='hidden':
        hidden=aliases(d.snapshot)['c1']
        kept=[cap for cap in d.snapshot['capabilities'] if capability_ref(cap)!=hidden]
        changed=create_capability_snapshot('owner',[capability_ref(cap) for cap in kept],kept)
        updated={**d.intent,'construction_snapshot_sha256':changed['digest']}
        changes.update(snapshot=changed,intent_ref=put(tmp_path/'hidden-intent.json',updated))
    else:changes['construction_cases']=[*d.cases,d.cases[0]]
    with pytest.raises((ValueError,program_training.TrainingEvidenceUnavailable)):prepare(d,**changes)


def test_unknown_input_field_is_not_filled_from_precomputed_examples(tmp_path):
    d=fixture(tmp_path,prefix=False,payload={'$input':['not_in_contract']})
    with pytest.raises(ValueError,match='path_not_guaranteed'):prepare(d)


def test_multiple_new_helper_calls_are_not_silently_collapsed(tmp_path):
    d=fixture(tmp_path);intent=copy.deepcopy(d.intent)
    intent['steps'].append({**intent['steps'][-1],'id':'another'})
    with pytest.raises(ValueError,match='single_program_call'):
        prepare(d,intent_ref=put(tmp_path/'multiple.json',intent))


def test_author_extracts_one_source_and_keeps_reference_cards_non_callable(tmp_path,monkeypatch):
    from scenarios.paper_proofreading.frontier import author
    d=fixture(tmp_path)
    source="def merge(previous, margin):\n    return {'value':previous['value']+margin}\n\ndef build(value):\n    prior=capability.c1(value=value['value'])\n    return merge(prior, 3)\n"
    response=SimpleNamespace(final_response=json.dumps({'capability_source':source}),finish_reason='completed')
    class Harness:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def run(self,*args,**kwargs):return response
    monkeypatch.setattr(author,'create_harness',lambda **kwargs:Harness())
    gate=SimpleNamespace(register_attempt=lambda *a:None,budget=SimpleNamespace(limit='1'),cell='diagnostic',
        environment=lambda:{},costs=lambda output:{'provider_requests':0,'observed_model_usd':0})
    card={'format':'capability_reference_interface_v1','reference':{'id':'cap_'+'f'*24,'sha256':'f'*64},
        'contract':d.task['contract'],'description':'An interface only, unavailable for calls'}
    output=tmp_path/'author'
    result=author.propose(task=d.task,library={'snapshot':d.snapshot,'source_catalog':{'reference_interfaces':[card]}},
        output=output,gate=gate,owner_id='diagnostic')
    assert result['status']=='deferred' and result['program_training_mode']=='bound_prefix_v1'
    assert result['new_program_step_id']=='source_return'
    intent=json.loads((output/'composition-intent.json').read_text())
    assert intent['steps'][0]['capability']==aliases(d.snapshot)['c1']
    assert intent['steps'][1]['arguments']['fields']['value']['fields']['margin']=={'kind':'literal','value':3}
    assert (output/'capability-source.py').read_text()==source
    context=json.loads((output/'prompt.md').read_text().split('FROZEN CONSTRUCTION CONTEXT:\n')[1])
    assert context['reference_interfaces']==[card]
    assert {entry['capability']['id'] for entry in context['source_callable_interfaces']}=={r['id'] for r in d.snapshot['roots']}
    assert card['reference']['id'] not in {entry['capability']['id'] for entry in context['source_callable_interfaces']}


def test_adapter_certifies_bound_prefix_values_instead_of_task_example_payloads(tmp_path,monkeypatch):
    from scenarios.paper_proofreading.frontier import adapter
    d=fixture(tmp_path);output=tmp_path/'run/attempt-0';output.mkdir(parents=True)
    program=put(output/'program.json',d.program);answer=output/'answer.txt';answer.write_text('diagnostic source request')
    source=output/'capability-source.py';source.write_text('diagnostic source bytes')
    encoding=put(output/'capability-source-encoding.json',{'scope':'diagnostic extraction metadata'})
    result={'status':'deferred','program_request':program['path'],'composition_intent_ref':d.intent_ref,
        'program_training_mode':'bound_prefix_v1','capability_source_ref':reference(source),'capability_source_encoding_ref':encoding}
    instance=adapter.FrontierAdapter.__new__(adapter.FrontierAdapter)
    instance.plan={'id':'diagnostic','output':str(tmp_path/'run')};instance.gate=None
    instance.templates={'diagnostic':{'native_cases':{'json':[{'unrelated_precomputed_payload':True}]},
        'construction_cases':d.cases,'libraries':[]}}
    instance.materials=SimpleNamespace(records=lambda:[])
    monkeypatch.setattr(adapter,'propose',lambda **kwargs:copy.deepcopy(result))
    def prefix(snapshot,root,libraries,inputs,current,directory,task_id,*,mode):
        assert mode=='validate'
        trace={'status':'succeeded','result':{'previous':current,'bonus':4},'receipts':[]}
        directory.mkdir(parents=True);(directory/'trace.json').write_text(json.dumps(trace));return trace
    monkeypatch.setattr(program_training,'execute',prefix)
    def certify(program,cases,directory,source_evidence,**options):
        assert [json.loads(Path(row['inputs'][0]['source']['path']).read_text()) for row in cases]==[
            {'previous':{'value':2},'bonus':4},{'previous':{'value':8},'bonus':4}]
        directory.mkdir();put(directory/'observations.json',[]);put(directory/'certification.json',{'diagnostic':True})
        return put(directory/'library.json',{'diagnostic':True})
    monkeypatch.setattr(adapter,'learn',certify)
    observed=instance.construct(d.task,{'snapshot':d.snapshot,'source_catalog':{}},output,None,None)
    assert observed['native_library'] and observed['program_training_ref']
    assert instance.pending_complete['composition_intent_ref']==d.intent_ref
    registered=[]
    instance.materials=SimpleNamespace(register=lambda **kwargs:registered.append(kwargs) or {'diagnostic':'material'})
    instance.opportunity_key=lambda job:'diagnostic'
    job={'publication_plan':encoding}
    assert instance.acquire(job,observed,output)['status']=='registered'
    assert observed['program_training_ref'] in registered[0]['refs']
    assert observed['capability_source_ref'] in registered[0]['refs']


def test_source_helper_missing_host_training_cases_defers_without_fake_certification(tmp_path,monkeypatch):
    from scenarios.paper_proofreading.frontier import adapter
    d=fixture(tmp_path);output=tmp_path/'run/attempt-0';output.mkdir(parents=True)
    put(output/'program.json',d.program);(output/'answer.txt').write_text('diagnostic')
    source=put(output/'source.json',{'source':'diagnostic'})
    instance=adapter.FrontierAdapter.__new__(adapter.FrontierAdapter)
    instance.plan={'id':'diagnostic','output':str(tmp_path/'run')};instance.gate=None
    instance.templates={'diagnostic':{'native_cases':{'json':[]},'libraries':[]}}
    instance.materials=SimpleNamespace(records=lambda:[])
    monkeypatch.setattr(adapter,'propose',lambda **kwargs:{'status':'deferred','program_request':str(output/'program.json'),
        'program_training_mode':'bound_prefix_v1','capability_source_ref':source,'capability_source_encoding_ref':source,
        'composition_intent_ref':d.intent_ref})
    monkeypatch.setattr(adapter,'learn',lambda *a,**k:pytest.fail('missing evidence must not silently use generic probes'))
    result=instance.construct(d.task,{'snapshot':d.snapshot,'source_catalog':{}},output,None,None)
    assert result['status']=='deferred' and result['construction_gap']['reason']=='insufficient_evidence'
    assert 'native_library' not in result and instance.pending_complete is None


def test_failed_prefix_keeps_case_trace_worker_evidence_without_claiming_bad_contract(tmp_path,monkeypatch):
    from tests.test_capability_program_composition import data
    original=data(tmp_path)
    # The synthetic native interface is used only to diagnose provenance; no
    # certified execution or model behavior is inferred from this stand-in.
    snapshot=create_capability_snapshot('owner',[capability_ref(original.native)],[original.native])
    composition={'steps':[{'id':'prior','use':'c1','args':{'value':{'$input':[]}}},
        {'id':'relation','use':'$program','args':{'value':{'$step':['prior','value']}}}],
        'output':{'$step':['relation','value']}}
    intent_ref=put(tmp_path/'prefix-intent.json',freeze_program_composition(original.task,snapshot,original.program,composition))
    cases=[]
    for i,n in enumerate((2,8)):
        source=tmp_path/('input-'+str(i)+'.json');source.write_text(json.dumps({'value':n}))
        cases.append({'id':'case-'+str(i),'split':'training','input':{'value':n},
            'inputs':[{'path':'/work/inputs/task.json','source':reference(source)}]})
    def failed(snapshot,root,libraries,inputs,current,directory,task_id,*,mode):
        directory.mkdir(parents=True);call='native-call-0';work=directory/'work/calls'/call;(work/'inputs').mkdir(parents=True)
        payload=json.dumps(current,separators=(',',':')).encode();(work/'inputs/value.json').write_bytes(payload)
        args_sha=hashlib.sha256(json.dumps({'value':current},separators=(',',':')).encode()).hexdigest()
        trace={'status':'failed','result':None,'receipts':[
            {'call_id':'prefix-root','parent_call_id':None,'capability':root,'reason':'script_worker_failed','child_call_ids':[call]},
            {'call_id':call,'parent_call_id':'prefix-root','capability':capability_ref(original.native),
                'reason':'script_worker_failed','arguments_sha256':args_sha}]}
        (directory/'trace.json').write_text(json.dumps(trace))
        put(work/'failure.json',{'format':'script_capability_call_failure_v1','call_id':call,
            'capability':capability_ref(original.native),'arguments_sha256':args_sha,
            'input_versions':[hashlib.sha256(payload).hexdigest()],
            'diagnostic':{'category':'data_operation_error','exception_type':'TypeError'}})
        raise ValueError('frontier_execution_failed: retained trace')
    monkeypatch.setattr(program_training,'execute',failed)
    out=tmp_path/'failed-training'
    with pytest.raises(ValueError,match='frontier_execution_failed') as caught:
        program_training.prepare_program_cases(original.task,snapshot,original.program_ref,intent_ref,cases,[],out)
    detail=caught.value.program_training_diagnostics
    assert detail['failed_case']=='case-0' and detail['worker_failures'][0]['verified_call_binding']
    assert detail['worker_failures'][0]['argument_shapes']['declared_contract_passed'] is True
    assert detail['worker_failures'][0]['argument_shapes']['issues']==[]
    assert detail['worker_failures'][0]['diagnostic']['exception_type']=='TypeError'
    assert caught.value.program_training_evidence_ref==reference(out/'failure.json')
    assert json.loads((out/'failure.json').read_text())['status']=='failed'
    assert not (out/'result.json').exists()


def test_candidate_validation_mode_is_explicit_and_unknown_mode_is_rejected_before_io(tmp_path):
    from scenarios.paper_proofreading.frontier.execute import execute
    with pytest.raises(ValueError,match='execution_mode_invalid'):
        execute(None,None,[],[],{},tmp_path/'uncreated','diagnostic',mode='unknown')
    assert not (tmp_path/'uncreated').exists()


native=(sys.platform=='linux' and Path('/usr/bin/bwrap').exists() and os.environ.get('RUN_SCRIPT_CAPABILITY_SANDBOX')=='1')
@pytest.mark.skipif(not native,reason='explicit Linux native sandbox diagnostic')
def test_certified_prefix_native_probe_and_final_candidate_share_the_same_bound_values(tmp_path):
    """Real native execution, input certification and composition; no model call."""
    from scenarios.paper_proofreading.frontier.learn import learn
    from scenarios.paper_proofreading.frontier.execute import execute
    from src.adapters.capability_program_encoding import encode_program_composition
    from src.adapters.capability_source_authoring import compile_capability_source
    values=[];construction=[]
    for i,n in enumerate((2,8)):
        path=tmp_path/('old-'+str(i)+'.json');path.write_text(json.dumps({'n':n},sort_keys=True,separators=(',',':')))
        item={'path':'/work/inputs/value.json','source':reference(path)}
        values.append({'id':'old-'+str(i),'inputs':[item]})
        construction.append({'id':'case-'+str(i),'split':'training','input':{'first':{'n':n}},'inputs':[item]})
    old_program={'source':"def run(value):\n    return {'n':value['n']+1}\n",'mode':'json','interface':'function_v1','description':'Native diagnostic old computation'}
    old_library=learn(old_program,values,tmp_path/'old-native',reference(__file__),origin='host_diagnostic')
    catalog=json.loads(subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',old_library['path'],'--owner','owner'],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,check=True).stdout)
    selected=next(cap for cap in catalog['capabilities'] if cap['contract']['input_schema'].get('required')==['value'])
    snapshot=create_capability_snapshot('owner',[capability_ref(selected)],[selected])
    number={'type':'number'};record={'type':'object','properties':{'n':number},'required':['n'],'additionalProperties':False}
    task={'id':'native-source-diagnostic','contract':{'input_schema':{'type':'object','properties':{'first':record},'required':['first'],'additionalProperties':False},
        'output_schema':{'type':'object','properties':{'total':number},'required':['total'],'additionalProperties':False},'effects':['read']}}
    source="def merge(previous, margin):\n    return {'total':previous['n']+margin}\n\ndef build(value):\n    prior = capability.c1(value=value['first'])\n    return merge(prior, 3)\n"
    encoded=compile_capability_source(source,task,snapshot)
    program=encoded['program'];program_ref=put(tmp_path/'new-program.json',program)
    intent_ref=put(tmp_path/'model-intent.json',freeze_program_composition(task,snapshot,program,encoded['composition']))
    probes=program_training.prepare_program_cases(task,snapshot,program_ref,intent_ref,construction,[old_library],tmp_path/'bound')
    assert [json.loads(Path(case['inputs'][0]['source']['path']).read_text()) for case in probes['cases']]==[
        {'previous':{'n':3},'margin':3},{'previous':{'n':9},'margin':3}]
    new_library=learn(program,probes['cases'],tmp_path/'new-native',reference(__file__),origin='host_diagnostic')
    new_catalog=json.loads(subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',new_library['path'],'--owner','owner'],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,check=True).stdout)
    new=next(cap for cap in new_catalog['capabilities'] if cap['contract']['input_schema'].get('required')==['value'])
    after=create_capability_snapshot('owner',[capability_ref(selected),capability_ref(new)],[selected,new])
    result=encode_program_composition(task,after,program_ref,intent_ref,new_library,reference(tmp_path/'new-native/observations.json'))
    candidate=result['candidate']
    trace=execute(candidate['snapshot'],capability_ref(candidate['capability']),[old_library,new_library],construction[1]['inputs'],construction[1]['input'],
        tmp_path/'final-execute','native-source-final',mode='validate')
    assert trace['result']=={'total':12} and trace['mode']=='validate'
    assert candidate['capability']['certification']=='candidate'
