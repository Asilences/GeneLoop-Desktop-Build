"""Prepaid conditions remain those declared in the frozen study, not CLI edits."""
import copy
from datetime import datetime,timezone
import pytest
from scenarios.paper_proofreading.frontier.run import validate_request
from tests.test_capability_improvement import plan_at,put


def request_at(tmp_path):
    plan,snapshot,_=plan_at(tmp_path);plan['id']='cell';plan['jobs']=plan['jobs'][:1]
    protocol={'deadline_utc':'2040-01-01T00:00:00Z','phase_C_research_budget_usd':'2.00'}
    request={'deadline':datetime(2040,1,1,tzinfo=timezone.utc).timestamp(),'budget_usd':'0.80','cell':'cell'}
    study={'cells':[{'id':'cell','arm_id':'arm','task_id':'target','budget_usd':0.8}],
        'arms':[{'id':'arm','build_snapshot_sha256':snapshot['digest']}],
        'tasks':[{'id':'target','sha256':plan['jobs'][0]['task']['sha256']}]}
    return request,plan,protocol,study,snapshot


def test_fixed_budget_deadline_and_initial_seed_are_bound_before_payment(tmp_path):
    request,plan,protocol,study,snapshot=request_at(tmp_path)
    assert validate_request(request,plan,protocol,study)==snapshot['digest']
    for amount in ['0.81','0.79',None,float('nan')]:
        changed={**request,'budget_usd':amount}
        with pytest.raises(ValueError,match='budget_'):validate_request(changed,plan,protocol,study)
    with pytest.raises(ValueError,match='deadline_changed'):
        validate_request({**request,'deadline':request['deadline']+1},plan,protocol,study)
    changed=copy.deepcopy(study);changed['arms'][0]['build_snapshot_sha256']='0'*64
    with pytest.raises(ValueError,match='initial_exposure_changed'):validate_request(request,plan,protocol,changed)
    changed=copy.deepcopy(plan);changed['jobs'][0]['task']=put(tmp_path/'other-task.json',{'id':'target','instruction':'Different task'})
    with pytest.raises(ValueError,match='study_task_changed'):validate_request(request,changed,protocol,study)
    assert not (tmp_path/'ledger').exists() and not (tmp_path/'run').exists()


def test_nonstudy_C_phase_keeps_the_same_predeclared_budget(tmp_path):
    request,plan,protocol,_,_=request_at(tmp_path)
    assert validate_request({**request,'budget_usd':'2'},plan,protocol) is None
    with pytest.raises(ValueError,match='budget_changed'):validate_request(request,plan,protocol)
