"""Evidence/flow diagnostics only. Fake Harness is not empirical RSI evidence."""
import copy
import json
from pathlib import Path

import pytest
from src.adapters.capability_construction_history import capture,build_history,feedback_library,model_context
from src.adapters.capability_feedback import file_ref
from src.adapters.capability_improvement import run_improvement
from src.adapters.capability_scene import CapabilityImprovementAdapter
from src.adapters import capability_proposal as pilot
from tests.test_capability_improvement import plan_at,Adapter,put,events
from tests.test_capability_proposal_loop import inputs,DiagnosticGate,fake_harness


def recorded(tmp_path,job,snapshot,name='attempt',cost='0.100000000000000001',rid=1,outcome=None):
    directory=tmp_path/name;directory.mkdir()
    ledger=str(tmp_path/'ledger.jsonl')
    put(directory/'result.json',{'status':'failed','error':'proposal_draft_shape',
        'diagnostics':{'kind':'authoring','issues':[{'path':['steps',0,'args']} ]},
        'model_called':True,'provider_requests':1,'request_ids':[rid],'ledger_ref':ledger,
        'observed_model_usd':float(cost) if cost else None,'observed_model_usd_decimal':cost})
    (directory/'requests.jsonl').write_text('\n'.join(json.dumps(row) for row in (
        {'phase':'booked','request_id':rid,'ledger_ref':ledger},
        {'phase':'settled','request_id':rid,'ledger_ref':ledger,'observed_peak_usd':float(cost) if cost else None}))+'\n')
    return capture(job,directory,snapshot,{'capability':{}} if outcome else None,outcome)


def test_costs_are_decimal_unknown_is_retained_and_duplicate_evidence_not_counted_twice(tmp_path):
    plan,snapshot,_=plan_at(tmp_path);job=plan['jobs'][0]
    first=recorded(tmp_path,job,snapshot)
    second=recorded(tmp_path,job,snapshot,'second',cost='0.2',rid=2)
    view=build_history([first,first,second],job['task'])
    assert len(view['attempts'])==2 and view['physical_requests']==2
    assert view['construction_model_usd_decimal']=='0.300000000000000001'
    assert view['all_stages_model_usd_decimal'] is None and view['shared_discovery_model_usd_decimal'] is None
    unknown=recorded(tmp_path,job,snapshot,'unknown',cost=None,rid=3)
    view=build_history([first,second,unknown],job['task'])
    assert view['construction_model_usd_decimal'] is None
    assert view['known_construction_model_usd_decimal']=='0.300000000000000001'
    assert view['attempts'][0]['diagnostics']['issues'][0]['path']==['steps',0,'args']
    assert view['attempts'][0]['failure_cause']=='unknown'


def test_reused_request_across_different_attempt_owners_is_rejected(tmp_path):
    plan,snapshot,_=plan_at(tmp_path);job=plan['jobs'][0]
    first=recorded(tmp_path,job,snapshot)
    other=recorded(tmp_path,job,snapshot,'other')
    with pytest.raises(ValueError,match='request_owner_changed'):build_history([first,other],job['task'])


def test_source_tampering_is_not_repaired_or_silently_repriced(tmp_path):
    plan,snapshot,_=plan_at(tmp_path);job=plan['jobs'][0];ref=recorded(tmp_path,job,snapshot)
    (tmp_path/'attempt/result.json').write_text('{}')
    with pytest.raises(ValueError,match='evidence_changed'):build_history([ref],job['task'])


def test_success_cost_and_whole_episode_cost_are_separate(tmp_path):
    plan,snapshot,_=plan_at(tmp_path);job=plan['jobs'][0]
    refs=[recorded(tmp_path,job,snapshot,cost='0.1'),
        recorded(tmp_path,job,snapshot,'success',cost='0.2',rid=2,outcome={'status':'published','evidence_ref':put(tmp_path/'published.json',{'diagnostic':True})}),
        recorded(tmp_path,job,snapshot,'later',cost='0.4',rid=3)]
    view=build_history(refs,job['task'])
    assert view['first_quality_success']['construction_model_usd_decimal']=='0.3'
    assert view['construction_model_usd_decimal']=='0.7'
    assert view['attempts'][1]['actual_dependencies'] is None
    assert view['attempts'][1]['other_stage_model_usd_decimal']['verification'] is None


def test_exhausted_repair_can_reconsider_once_without_changing_the_contract(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1];plan['policy']['max_repairs']=0
    plan['construction_feedback']={'max_reconsiderations':1}
    adapter=Adapter(snapshot,proposal,failures=1)
    adapter.construction_budget=lambda job:{'limit_usd':'1','remaining_usd':'0.9'}
    result=run_improvement(plan,adapter,execute=True)
    assert result['outcomes'][0]['status']=='published' and len(adapter.calls)==2
    context=adapter.calls[1][0]['source_catalog']['construction_feedback']
    assert context['reconsider'] is True and context['trigger']=='repair_stopped'
    assert adapter.calls[1][1:] == (None,None)
    view=json.loads(Path(context['history']['path']).read_text())
    assert len(view['attempts'])==1 and view['attempts'][0]['error']=='same_failure'
    assert len([e for e in events(plan) if e['payload'].get('reason')=='construction_strategy_reconsideration'])==1


@pytest.mark.parametrize('budget',[None,{'limit_usd':'0','remaining_usd':'0'},{'limit_usd':'1','remaining_usd':'0'}])
def test_missing_or_exhausted_finite_budget_never_adds_a_strategy_request(tmp_path,budget):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1];plan['policy']['max_repairs']=0
    plan['construction_feedback']={'max_reconsiderations':1}
    adapter=Adapter(snapshot,proposal,failures=10);adapter.construction_budget=lambda job:budget
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='deferred'
    assert len(adapter.calls)==1


def test_reconsideration_does_not_restart_repair_allowances_or_loop_on_new_source(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1];plan['policy']['max_repairs']=0
    plan['construction_feedback']={'max_reconsiderations':5}
    adapter=Adapter(snapshot,proposal,failures=10)
    adapter.construction_budget=lambda job:{'limit_usd':'1','remaining_usd':'1'}
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='deferred'
    assert len(adapter.calls)==2


def test_infrastructure_or_permission_failure_does_not_reconsider(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    plan['construction_feedback']={'max_reconsiderations':1}
    adapter=Adapter(snapshot,proposal)
    adapter.construction_budget=lambda job:{'limit_usd':'1','remaining_usd':'1'}
    adapter.publish=lambda *args:{'status':'failed','error':'permission_denied','repairable':False}
    assert run_improvement(plan,adapter,execute=True)['outcomes'][0]['status']=='deferred'
    assert len(adapter.calls)==1


def test_strategy_and_verified_history_reach_existing_model_turn(tmp_path,monkeypatch):
    task,catalog,snapshot,proposal=inputs();task_ref=put(tmp_path/'task.json',task)
    history=put(tmp_path/'history.json',build_history([],task_ref))
    library=feedback_library({'snapshot':snapshot,'source_catalog':catalog},history,
        trigger='construction',budget={'limit_usd':'1','remaining_usd':'1'})
    wrapped={'strategy':{'approach':'Compose current primitives','reason':'No prior evidence requires a new helper','uses':['c1']},'proposal':proposal}
    observed=fake_harness(monkeypatch,json.dumps(wrapped))
    result=pilot.propose_once(task=task,catalog=library['source_catalog'],snapshot=snapshot,output=tmp_path/'turn',gate=DiagnosticGate())
    assert result['status']=='compiled_candidate'
    assert 'construction_feedback' in observed['prompt'] and 'remaining_usd' in observed['prompt']
    strategy=json.loads((tmp_path/'turn/strategy.json').read_text())
    assert strategy['expected_dependencies']==[snapshot['roots'][0]] and strategy['actual_dependencies'] is None
    assert not result['publication_authorized']
    altered=copy.deepcopy(snapshot);altered['digest']='0'*64
    with pytest.raises(ValueError,match='snapshot_changed'):model_context(library['source_catalog'],task,altered)


def test_default_configuration_does_not_create_new_history_or_strategy_turns(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);adapter=Adapter(snapshot,proposal)
    run_improvement(plan,adapter,execute=True)
    assert not list(Path(plan['output']).rglob('construction-evidence.json'))
    assert all('construction_feedback' not in call[0].get('source_catalog',{}) for call in adapter.calls)


def test_public_adapter_never_infers_research_budget_from_platform_null():
    assert CapabilityImprovementAdapter.__new__(CapabilityImprovementAdapter).construction_budget({}) is None


def test_reconsidering_uses_original_model_entry_instead_of_replaying_old_fixed_bindings(tmp_path,monkeypatch):
    from src.adapters.capability_contract import capability_digest
    task,catalog,snapshot,proposal=inputs();task_ref=put(tmp_path/'task.json',task)
    history=put(tmp_path/'history.json',build_history([],task_ref))
    library=feedback_library({'snapshot':snapshot,'source_catalog':catalog},history,
        trigger='repair_stopped',budget={'limit_usd':'1','remaining_usd':'1'},reconsider=True)
    fake_harness(monkeypatch,json.dumps({'strategy':{'approach':'Fresh composition',
        'reason':'Reconsider prior decomposition','uses':[]},'proposal':proposal}))
    adapter=CapabilityImprovementAdapter.__new__(CapabilityImprovementAdapter)
    adapter.plan={'id':'diagnostic','output':str(tmp_path)}
    adapter.pending_programs={capability_digest(task):{'path':'must-not-be-read','sha256':'0'*64}}
    adapter.gate=DiagnosticGate();registered=[]
    adapter.gate.register_attempt=lambda path,owner:registered.append((path,owner))
    result=adapter.construct(task,library,tmp_path/'fresh',None,None)
    assert result['status']=='compiled_candidate' and result['model_called'] and len(registered)==1
    assert not adapter.pending_programs


def test_historical_index_writes_only_to_new_output(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('offline_construction_inspect',Path(__file__).parents[1]/'scripts/inspect-capability-construction.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    plan,snapshot,_=plan_at(tmp_path);job=plan['jobs'][0];recorded(tmp_path,job,snapshot)
    original=tmp_path/'attempt';before={p.name:p.read_bytes() for p in original.iterdir()}
    snapshot_ref=put(tmp_path/'snapshot.json',snapshot)
    result=module.inspect({'goal_id':job['id'],'task':job['task'],'attempts':[
        {'directory':str(original),'snapshot':snapshot_ref}]},tmp_path/'offline-view')
    assert json.loads(Path(result['path']).read_text())['construction_model_usd_decimal']=='0.100000000000000001'
    assert before=={p.name:p.read_bytes() for p in original.iterdir()}


def test_following_run_consumes_explicit_historical_evidence(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    ref=recorded(tmp_path,plan['jobs'][0],snapshot,'historical')
    plan['construction_feedback']={'max_reconsiderations':0,'history':[ref]}
    adapter=Adapter(snapshot,proposal);run_improvement(plan,adapter,execute=True)
    context=adapter.calls[0][0]['source_catalog']['construction_feedback']
    view=json.loads(Path(context['history']['path']).read_text())
    assert view['attempts'][0]['result_ref']['path'].endswith('historical/result.json')
    assert view['construction_model_usd_decimal']=='0.100000000000000001'


def test_history_for_a_different_task_is_refused_before_any_constructor_call(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path);plan['jobs']=plan['jobs'][:1]
    ref=recorded(tmp_path,plan['jobs'][0],snapshot,'historical')
    plan['jobs'][0]['task']=put(tmp_path/'different-task.json',{'instruction':'Different goal'})
    plan['construction_feedback']={'max_reconsiderations':0,'history':[ref]}
    adapter=Adapter(snapshot,proposal)
    with pytest.raises(ValueError,match='history_task_changed'):run_improvement(plan,adapter,execute=True)
    assert not adapter.calls


def test_pending_booking_does_not_turn_reported_cost_into_known_cost(tmp_path):
    plan,snapshot,_=plan_at(tmp_path);job=plan['jobs'][0];recorded(tmp_path,job,snapshot)
    path=tmp_path/'attempt/requests.jsonl';path.write_text(path.read_text().splitlines()[0]+'\n')
    ref=capture(job,tmp_path/'attempt',snapshot,output=tmp_path/'pending-index.json')
    view=build_history([ref],job['task'])
    assert view['physical_requests']==1 and view['construction_model_usd_decimal'] is None


def test_committed_followup_failure_remains_review_only(tmp_path):
    plan,snapshot,_=plan_at(tmp_path);job=plan['jobs'][0]
    ref=recorded(tmp_path,job,snapshot,outcome={'status':'failed','committed':True})
    history=put(tmp_path/'history.json',build_history([ref],job['task']))
    library=feedback_library({'snapshot':snapshot,'source_catalog':{}},history,trigger='construction',budget=None)
    task=json.loads(Path(job['task']['path']).read_text())
    with pytest.raises(ValueError,match='requires_review'):model_context(library['source_catalog'],task,snapshot)
