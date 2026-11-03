"""Opportunity-event diagnostics; synthetic proposals are not autonomous gains."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.capability_contract import capability_digest, capability_ref
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_improvement import run_improvement
from src.adapters.capability_opportunities import OpportunityDiscovery
from src.adapters.capability_feedback import file_ref
from tests.test_capability_improvement import plan_at, Adapter, put


def context_at(tmp_path, owner='owner', status='open'):
    need=put(tmp_path/'actual-need.json',{'user_requirement':'Maintain current project consistency','diagnostic':True})
    context={'format':'capability_opportunity_context_v1','owner':owner,'task_scope':'project-maintenance',
        'allowed_effects':['read'],'needs':[{'id':'maintain','description':'Find worthwhile improvements for the current project',
            'status':status,'evidence':[need]}]}
    ref=put(tmp_path/'opportunity-context.json',context)
    return {'context':ref,'directory':str(tmp_path/'opportunity-ledger'),'max_reconsiderations':1,'max_candidates':2}


def wire(tmp_path, *, goals=None, review='accepted', committed=False):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    config=context_at(tmp_path);plan['opportunity_discovery']=config
    adapter=Adapter(snapshot,proposal,committed=committed);calls=[]
    adapter.configure_jobs=lambda jobs:None
    def propose(request,output):
        calls.append(copy.deepcopy(request))
        rows=goals if goals is not None else [{'need_id':'maintain','proposed_goal':'Check dependency changes across current versions',
            'expected_dependencies':request['newly_visible'],'reason':'A newly certified abstraction may simplify this unmet need'}]
        return {'goals':copy.deepcopy(rows),'model_called':False,'request_ids':[],
            'observed_model_usd':None,'diagnostic_only':True}
    def admit(goal,request,directory):
        if review!='accepted':return {'decision':review,'reason':'independent_conditions_unavailable'}
        task={'id':'host-reviewed-goal','instruction':goal['proposed_goal'],'contract':copy.deepcopy(proposal['contract'])}
        job={**copy.deepcopy(plan['jobs'][0]),'execution_scope':request['task_scope'],
            'task':put(directory/('task-'+capability_digest(goal)[:12]+'.json'),task)}
        job['observations'][0]['kind']='new_requirement'
        return {'decision':'accepted','job':job,'evidence':put(directory/'host-review.json',{'independent_host_diagnostic':True})}
    adapter.propose_opportunities=propose;adapter.review_opportunity=admit
    return plan,adapter,calls


def round_files(config,name):
    return list(Path(config['directory']).glob('*/*/'+name))


def test_publication_reconsiders_unmet_need_and_new_goal_enters_original_builder(tmp_path):
    plan,adapter,calls=wire(tmp_path)
    result=run_improvement(plan,adapter,execute=True)
    assert len(calls)==1 and len(adapter.calls)==2
    assert [r['status'] for r in result['outcomes']]==['published','published']
    request=calls[0];assert request['origin']=='capability_update'
    assert request['previous_snapshot']['digest']!=request['capability_snapshot']['digest']
    assert request['newly_visible']==[adapter.published[0]]
    row=json.loads(round_files(plan['opportunity_discovery'],'decisions.json')[0].read_text())[0]
    assert row['decision']=='selected' and row['expected_dependencies']==[adapter.published[0]]
    assert result['outcomes'][1]['opportunity_id']==row['goal_id']
    assert row['actual_dependencies'] is None
    events=round_files(plan['opportunity_discovery'],'outcome-*.json')
    assert any(json.loads(p.read_text())['decision']=='completed' for p in events)
    assert all(json.loads(p.read_text())['actual_dependencies'] is None for p in events)
    assert result['efficiency_conclusion'] is None


def test_same_update_does_not_repeat_even_across_discovery_instances(tmp_path):
    plan,adapter,calls=wire(tmp_path,review='pending')
    before=copy.deepcopy(adapter.snapshot)
    adapter.publish(plan['jobs'][0],compile_proposal(adapter.proposal,before,'owner'),tmp_path,None)
    after=adapter.library();proof=put(tmp_path/'verified-publication.json',{'diagnostic':True})
    engine=OpportunityDiscovery(plan['opportunity_discovery'],'owner')
    assert engine.reconsider(before,after,proof,[],adapter,tmp_path)==[]
    assert len(calls)==1
    again=OpportunityDiscovery(plan['opportunity_discovery'],'owner')
    assert again.reconsider(before,after,proof,[],adapter,tmp_path)==[] and len(calls)==1
    assert again.reconsider(after['snapshot'],after,proof,[],adapter,tmp_path)==[]


@pytest.mark.parametrize('status', ['resolved'])
def test_no_unresolved_need_does_not_call_proposer(tmp_path,status):
    plan,adapter,calls=wire(tmp_path)
    plan['opportunity_discovery']=context_at(tmp_path,status=status)
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='published'
    assert calls==[]


def test_disabled_default_preserves_existing_controller_and_no_goal_artifacts(tmp_path):
    plan,adapter,calls=wire(tmp_path);del plan['opportunity_discovery']
    result=run_improvement(plan,adapter,execute=True)
    assert len(result['outcomes'])==1 and calls==[]
    assert not Path(tmp_path/'opportunity-ledger').exists()


@pytest.mark.parametrize('change',['wrong-need','invisible-version','bad-goal','too-many'])
def test_invalid_and_unselected_proposals_are_retained_without_constructing(tmp_path,change):
    goal={'need_id':'maintain','proposed_goal':'One useful improvement','expected_dependencies':[],'reason':'Current need'}
    if change=='wrong-need':goal['need_id']='outside-user-scope'
    elif change=='invisible-version':goal['expected_dependencies']=[{'id':'cap_unknown','sha256':'0'*64}]
    elif change=='bad-goal':goal['proposed_goal']=''
    goals=[goal] if change!='too-many' else [{**goal,'proposed_goal':f'Useful improvement {i}'} for i in range(3)]
    plan,adapter,calls=wire(tmp_path,goals=goals,review='pending')
    run_improvement(plan,adapter,execute=True)
    rows=json.loads(round_files(plan['opportunity_discovery'],'decisions.json')[0].read_text())
    assert len(rows)==len(goals) and len(adapter.calls)==1
    assert rows[-1]['decision']==('not_selected' if change=='too-many' else 'rejected')


def test_host_review_cannot_broaden_authorized_effects(tmp_path):
    plan,adapter,calls=wire(tmp_path);original=adapter.review_opportunity
    def review(*args):
        result=original(*args);path=Path(result['job']['task']['path']);task=json.loads(path.read_text())
        task['contract']['effects']=['write'];result['job']['task']=put(path,task);return result
    adapter.review_opportunity=review
    run_improvement(plan,adapter,execute=True)
    row=json.loads(round_files(plan['opportunity_discovery'],'decisions.json')[0].read_text())[0]
    assert row['decision']=='rejected' and row['reason']=='opportunity_admission_scope_changed'
    assert len(adapter.calls)==1


def test_committed_or_validation_failure_never_triggers_discovery(tmp_path):
    plan,adapter,calls=wire(tmp_path,committed=True)
    result=run_improvement(plan,adapter,execute=True)
    assert result['status']=='needs_review' and calls==[]


def test_failed_proposal_is_preserved_and_not_replayed(tmp_path):
    plan,adapter,calls=wire(tmp_path)
    def broken(request,output):calls.append(request);raise RuntimeError('diagnostic_proposer_interrupted')
    adapter.propose_opportunities=broken
    result=run_improvement(plan,adapter,execute=True)
    saved=json.loads(round_files(plan['opportunity_discovery'],'result.json')[0].read_text())
    assert result['status']=='completed' and saved['status']=='failed' and len(calls)==1
    assert round_files(plan['opportunity_discovery'],'claim.json')


def test_changed_context_is_rejected_before_any_proposal(tmp_path):
    plan,adapter,calls=wire(tmp_path)
    Path(plan['opportunity_discovery']['context']['path']).write_text('{}')
    with pytest.raises(ValueError,match='evidence_changed'):run_improvement(plan,adapter,execute=True)
    assert calls==[]


def test_default_proposer_has_no_implicit_paid_authorization(tmp_path):
    from src.adapters.capability_goal_proposal import propose
    assert propose({},tmp_path/'unused')['model_called'] is False
    with pytest.raises(ValueError,match='finite_budget'):propose({},tmp_path/'unused',object())


def test_execution_observation_is_separate_from_proposed_and_compiled_dependencies(tmp_path):
    plan,adapter,calls=wire(tmp_path)
    run_improvement(plan,adapter,execute=True)
    row=json.loads(round_files(plan['opportunity_discovery'],'decisions.json')[0].read_text())[0]
    engine=OpportunityDiscovery(plan['opportunity_discovery'],'owner');engine.jobs[row['goal_id']]=round_files(plan['opportunity_discovery'],'decisions.json')[0].parent
    candidate=compile_proposal(adapter.proposal,adapter.snapshot,'owner')
    selected=candidate['capability']['dependencies'][0]
    assert row['expected_dependencies']!=[selected]  # Model claimed C; this diagnostic graph uses A/B.
    trace={'owner':'owner','root':capability_ref(candidate['capability']),
        'snapshot_sha256':candidate['snapshot']['digest'],'status':'succeeded','mode':'validate',
        'receipts':[{'call_id':'root','capability':capability_ref(candidate['capability']),'status':'succeeded',
            'parent_call_id':None,'child_call_ids':['selected']},
            {'call_id':'selected','parent_call_id':'root','capability':selected,'status':'succeeded','child_call_ids':[]}]}
    trace_ref=put(tmp_path/'actual-trace.json',trace)
    attempt=tmp_path/'observed-attempt';attempt.mkdir();put(attempt/'result.json',{'status':'compiled_candidate','observed_model_usd':0})
    engine.record(row['job'],attempt,{'observed_model_usd':0},candidate,{'status':'failed','execution_trace_refs':[trace_ref]})
    records=[json.loads(p.read_text()) for p in round_files(plan['opportunity_discovery'],'outcome-*.json')]
    observed=next(r for r in records if r.get('execution_trace_refs'))
    assert observed['actual_dependencies']==[selected] and row['expected_dependencies'][0] not in observed['actual_dependencies']


def test_permission_or_quality_failure_of_new_goal_uses_existing_publication_path(tmp_path):
    plan,adapter,calls=wire(tmp_path);publish=adapter.publish
    def reject_new_goal(job,candidate,attempt,expected):
        if job['id'].startswith('goal-'):
            ref=put(attempt/'validation.json',{'passed':False,'reason':'permission_denied'})
            return {'status':'failed','committed':False,'repairable':False,'error':'permission_denied','evidence_ref':ref}
        return publish(job,candidate,attempt,expected)
    adapter.publish=reject_new_goal
    result=run_improvement(plan,adapter,execute=True)
    assert len(adapter.published)==1
    assert result['outcomes'][1]['status']=='deferred'
    records=[json.loads(p.read_text()) for p in round_files(plan['opportunity_discovery'],'outcome-*.json')]
    assert records and all(r['decision']!='completed' for r in records)


def test_library_change_during_proposal_keeps_goal_pending(tmp_path):
    plan,adapter,calls=wire(tmp_path);propose=adapter.propose_opportunities
    def changed(request,output):
        response=propose(request,output)
        # Diagnostic withdrawal: the next pool differs, so do not admit from an old view.
        adapter.library=lambda:{'snapshot':request['previous_snapshot'],'catalog':[],'head':None}
        return response
    adapter.propose_opportunities=changed
    run_improvement(plan,adapter,execute=True)
    row=json.loads(round_files(plan['opportunity_discovery'],'decisions.json')[0].read_text())[0]
    assert row['decision']=='pending' and row['reason']=='capability_snapshot_changed'
    assert len(adapter.calls)==1


def test_material_acquisition_failure_is_not_reported_as_independent_quality_failure(tmp_path):
    plan,adapter,_=wire(tmp_path);run_improvement(plan,adapter,execute=True)
    path=round_files(plan['opportunity_discovery'],'decisions.json')[0]
    goal=json.loads(path.read_text())[0]
    engine=OpportunityDiscovery(plan['opportunity_discovery'],'owner');engine.jobs[goal['goal_id']]=path.parent
    attempt=tmp_path/'native-material-failure';attempt.mkdir()
    put(attempt/'result.json',{'status':'deferred','observed_model_usd':None})
    acquisition=put(attempt/'acquisition.json',{'status':'failed','diagnostics':{'kind':'native_material_acquisition'}})
    engine.record(goal['job'],attempt,{'observed_model_usd':None},None,
        {'status':'failed','repairable':True,'evidence_ref':acquisition})
    records=[json.loads(p.read_text()) for p in round_files(plan['opportunity_discovery'],'outcome-*.json')]
    row=next(r for r in records if r.get('acquisition_result'))
    assert row['acquisition_result']==acquisition and row['verification'] is None and row['observed_model_usd'] is None
