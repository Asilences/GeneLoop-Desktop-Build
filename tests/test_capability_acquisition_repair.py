"""Existing controller repair with acquisition feedback; deterministic diagnostics."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.capability_contract import capability_ref,create_capability_snapshot
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_improvement import run_improvement,read
from tests.test_capability_improvement import plan_at,Adapter,put,events


def acquisition_adapter(tmp_path,*,kind='source',registered=False):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    adapter=Adapter(snapshot,proposal);base=adapter.construct
    records=[];original=[];count=[]
    def construct(task,library,attempt,parent,feedback):
        count.append((parent,feedback))
        if len(count)>1:return base(task,library,attempt,parent,feedback)
        attempt.mkdir()
        result={'status':'deferred','error':'capability_construction_gap','model_requested_program':True,
            'construction_snapshot_sha256':snapshot['digest'],'observed_model_usd':0.125,
            'construction_gap':{'reason':'missing_primitive','requirement':'Learn selected algorithm'}}
        put(attempt/'draft.json',{'capability_source':'diagnostic original source'})
        put(attempt/'result.json',result);original.append((attempt/'result.json', (attempt/'result.json').read_bytes()))
        return result
    def acquire(job,result,attempt):
        if registered:
            definition=copy.deepcopy(proposal);definition['contract']['input_schema']['description']='Newly native-certified test material'
            cap=compile_proposal(definition,snapshot,'owner')['capability'];cap={**cap,'certification':'certified','lifecycle':'active'}
            adapter.snapshot=create_capability_snapshot('owner',[*snapshot['roots'],capability_ref(cap)],[*snapshot['capabilities'],cap])
            return {'status':'registered'}
        if kind=='source':
            return {'status':'failed','repairable':True,'error':'native_source_rejected',
                'diagnostics':{'kind':'native_material_acquisition','issues':[{'path':['program','source'],'line':3}]}}
        return {'status':'deferred','reason':'unknown_native_environment_failure','diagnostics':{'kind':'native_material_acquisition'}}
    def record(job,attempt,result,candidate,outcome):
        records.append((attempt.name,copy.deepcopy(result),copy.deepcopy(outcome)))
    adapter.construct=construct;adapter.acquire=acquire;adapter.record_outcome=record
    adapter.admission=lambda job:('start','diagnostic')
    return plan,adapter,records,count,original


def test_located_native_acquisition_failure_repairs_same_attempt_context_without_rewriting_evidence(tmp_path):
    plan,adapter,records,count,original=acquisition_adapter(tmp_path)
    result=run_improvement(plan,adapter,execute=True)
    assert result['outcomes'][0]['status']=='published' and len(count)==2
    parent,feedback=count[1]
    assert parent.name=='attempt-0' and feedback['error']=='native_source_rejected'
    assert feedback['diagnostics']['issues'][0]['path']==['program','source']
    assert Path(feedback['acquisition_ref']['path']).parts[-2:]==('attempt-0','acquisition.json')
    assert [(name,row['status']) for name,row,_ in records]==[('attempt-0','failed'),('attempt-1','compiled_candidate')]
    assert sum(row.get('observed_model_usd') or 0 for _,row,_ in records)==0.125
    path,raw=original[0];assert path.read_bytes()==raw and read(path)['status']=='deferred'
    acquisition=read(path.with_name('acquisition.json'))
    assert acquisition['status']=='failed' and acquisition['repairable'] is True
    assert records[0][2]['evidence_ref']==feedback['acquisition_ref']
    attempt_events=[e['payload'] for e in events(plan) if e['kind']=='attempt' and e['payload']['phase']!='started']
    assert [row['observed_model_usd'] for row in attempt_events]==[0.125,None]


def test_registered_acquisition_and_published_followup_each_record_once(tmp_path):
    plan,adapter,records,count,original=acquisition_adapter(tmp_path,registered=True)
    result=run_improvement(plan,adapter,execute=True)
    assert result['outcomes'][0]['status']=='published' and len(count)==2
    assert count[1]==(None,None)  # Pool refresh, not repair against old aliases.
    assert [name for name,_,_ in records]==['attempt-0','attempt-1']
    assert records[0][1]['status']=='deferred' and records[0][1]['observed_model_usd']==0.125
    assert original[0][0].read_bytes()==original[0][1]


@pytest.mark.parametrize('max_repairs',[None,0])
def test_unknown_native_environment_remains_deferred_and_recorded_once(tmp_path,max_repairs):
    plan,adapter,records,count,original=acquisition_adapter(tmp_path,kind='unknown')
    plan['policy']['max_repairs']=max_repairs
    result=run_improvement(plan,adapter,execute=True)
    assert result['outcomes'][0]['status']=='deferred' and len(count)==1
    assert len(records)==1 and records[0][1]['status']=='deferred'
    assert original[0][0].read_bytes()==original[0][1]
    assert not any(e['kind']=='decision' and e['payload']['action']=='repair' for e in events(plan))


def test_known_acquisition_rejection_obeys_existing_explicit_repair_limit(tmp_path):
    plan,adapter,records,count,_=acquisition_adapter(tmp_path)
    plan['policy']['max_repairs']=0
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='deferred'
    assert len(count)==len(records)==1 and records[0][1]['status']=='failed'
