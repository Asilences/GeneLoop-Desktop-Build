"""Coordinator state-machine diagnostics; adapter is synthetic, no model/quality claim."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from src.adapters.capability_improvement import run_improvement, validate, discover
from src.adapters.capability_contract import create_capability_snapshot, capability_ref
from src.adapters.capability_builder import compile_proposal
from tests.test_capability_builder import setup


def put(path,value):
    path.write_text(json.dumps(value))
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def plan_at(tmp_path):
    snapshot,proposal=setup()
    snapshot=create_capability_snapshot('owner',snapshot['roots'],[{**c,'certification':'certified','lifecycle':'active'} for c in snapshot['capabilities']])
    source=put(tmp_path/'observation.json',{'task_id':'failed-original','status':'failed'})
    task=put(tmp_path/'task.json',{'id':'target','instruction':'Synthetic construction diagnostic','contract':proposal['contract']})
    seed=put(tmp_path/'seed.json',snapshot);catalog=put(tmp_path/'catalog.json',{})
    template=put(tmp_path/'template.json',{})
    job={'id':'first','objective':'capability_acquisition','task':task,'publication_plan':template,
         'observations':[{'task_id':'failed-original','kind':'task_failure','split':'training','summary':'Diagnostic failure','evidence':source}]}
    plan={'format':'capability_improvement_plan_v1','id':'diagnostic','owner':'owner','output':str(tmp_path/'run'),
          'store':str(tmp_path/'store'),'seed':seed,'seed_catalog':catalog,'ledger_root':str(tmp_path/'ledger'),
          'policy':{'version':'capability_improvement_policy_v1','max_repairs':None},'jobs':[job,{**job,'id':'second'}]}
    return plan,snapshot,proposal


class Adapter:
    def __init__(self,snapshot,proposal,failures=0,committed=False):
        self.snapshot,self.proposal=snapshot,proposal
        self.failures,self.committed=failures,committed
        self.calls=[];self.head=None;self.published=[]
    def library(self):return {'snapshot':copy.deepcopy(self.snapshot),'head':self.head,'catalog':[]}
    def construct(self,task,library,attempt,parent,feedback):
        self.calls.append((copy.deepcopy(library),parent,feedback));attempt.mkdir()
        if self.failures:
            self.failures-=1;result={'status':'failed','error':'same_failure','observed_model_usd':None}
        else:
            proposal=copy.deepcopy(self.proposal)
            if self.published:
                proposal['steps']=[{'id':'use-c','capability':self.published[-1],'arguments':{'kind':'input','path':[]}}]
                proposal['output']={'kind':'step','step_id':'use-c','path':[]}
            compiled=compile_proposal(proposal,library['snapshot'],'owner')
            put(attempt/'candidate.json',compiled)
            result={'status':'compiled_candidate','observed_model_usd':None}
        put(attempt/'result.json',result);return result
    def publish(self,job,candidate,attempt,expected):
        assert expected==self.head
        ref=put(attempt/'publication.json',{'diagnostic':True})
        if self.committed:return {'status':'failed','committed':True,'error':'followup_failed','evidence_ref':ref}
        c={**candidate['capability'],'certification':'certified','lifecycle':'active'}
        self.published.append(capability_ref(c));self.head=hashlib.sha256(c['id'].encode()).hexdigest()
        self.snapshot=create_capability_snapshot('owner',[*self.snapshot['roots'],capability_ref(c)],[*self.snapshot['capabilities'],c])
        return {'status':'published','publication_sha256':self.head,'evidence_ref':ref}


def events(plan):return [json.loads(line) for line in (Path(plan['output'])/'events.jsonl').read_text().splitlines()]


def test_preview_has_no_adapter_calls_or_ledger(tmp_path):
    plan,_,_=plan_at(tmp_path)
    result=run_improvement(plan,None)
    assert result['status']=='preview' and not Path(plan['ledger_root']).exists()
    for event in events(plan):validate('event',event)


def test_publish_refreshes_builder_for_second_generation(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);adapter=Adapter(snapshot,proposal)
    result=run_improvement(plan,adapter,execute=True)
    assert [r['status'] for r in result['outcomes']]==['published','published']
    assert adapter.published[0] in adapter.calls[1][0]['snapshot']['roots']
    contributions=[e['payload'] for e in events(plan) if e['kind']=='contribution']
    assert any(c['capability']==adapter.published[0] and c['beneficiary']==adapter.published[1] and c['stage']=='construction' for c in contributions)
    assert all(c['benefit'] is None for c in contributions)
    assert any(e['payload'].get('action')=='retain' for e in events(plan))
    for event in events(plan):validate('event',event)


def test_failure_repair_freezes_snapshot_and_keeps_attempt_cost_unknown(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    adapter=Adapter(snapshot,proposal,failures=1)
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='published'
    assert adapter.calls[1][1].name=='attempt-0'
    assert adapter.calls[1][2]['error']=='same_failure'
    assert adapter.calls[0][0]==adapter.calls[1][0]
    assert len([e for e in events(plan) if e['kind']=='attempt' and e['payload']['phase']=='started'])==2


def test_repeated_failure_defers_without_third_attempt(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    adapter=Adapter(snapshot,proposal,failures=10)
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='deferred'
    assert len(adapter.calls)==2


def test_committed_followup_failure_stops_without_replay_or_next_job(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);adapter=Adapter(snapshot,proposal,committed=True)
    assert run_improvement(plan,adapter,execute=True)['status']=='needs_review'
    assert len(adapter.calls)==1


def test_acquisition_not_blocked_by_failed_baseline_but_cost_requires_assessment(tmp_path):
    plan,_,_=plan_at(tmp_path);job=plan['jobs'][0]
    assert discover(job)['action']=='start'
    job['objective']='cost_reduction'
    assert discover(job)['action']=='defer'
    job['objective']='capability_acquisition';job['observations'][0]['split']='heldout'
    assert discover(job)['action']=='defer'


def test_tampered_evidence_fails_before_adapter_and_existing_run_never_replayed(tmp_path):
    plan,_,_=plan_at(tmp_path)
    run_improvement(plan,None)
    with pytest.raises(FileExistsError):run_improvement(plan,None)
    Path(plan['jobs'][0]['task']['path']).write_text('{}')
    with pytest.raises(ValueError,match='evidence_changed'):run_improvement(plan,None)


def test_f02_assessment_is_validated_and_bound_to_observed_task(tmp_path):
    from tests.test_rsi_optimization import context
    plan,_,_=plan_at(tmp_path);job=plan['jobs'][0];job['objective']='cost_reduction'
    assessment=context()['assessments'][0]
    job['optimization_assessment']=put(tmp_path/'assessment.json',assessment)
    with pytest.raises(ValueError,match='assessment_task_mismatch'):discover(job)
    job['observations'][0]['task_id']=assessment['payload']['discovery_task_ids'][0]
    assert discover(job)['action']=='start'
    job['optimization_assessment']=put(tmp_path/'assessment.json',{'payload':{'action':'start'}})
    with pytest.raises(ValueError):discover(job)


def test_infrastructure_failure_does_not_trigger_paid_model_repair(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    adapter=Adapter(snapshot,proposal)
    adapter.publish=lambda *args: {'status':'failed','committed':False,'error':'capability_store_cas_conflict'}
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='deferred'
    assert len(adapter.calls)==1


def test_corrupted_catalog_never_reaches_builder(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);adapter=Adapter(snapshot,proposal)
    caps=copy.deepcopy(snapshot['capabilities']);caps[0]['certification']='candidate'
    adapter.snapshot=create_capability_snapshot('owner',snapshot['roots'],caps)
    with pytest.raises(ValueError,match='not_certified'):run_improvement(plan,adapter,execute=True)
    assert not adapter.calls
    assert json.loads((Path(plan['output'])/'result.json').read_text())['status']=='failed'
