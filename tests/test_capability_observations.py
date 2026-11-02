"""Synthetic offline observation/control wiring, not natural task or model evidence."""
import copy
import json
from pathlib import Path
import pytest
from src.adapters.capability_contract import capability_digest
from src.adapters.capability_improvement import run_improvement, discover
from src.adapters.capability_feedback import CapabilityFeedback, file_ref
from scenarios.remotion_edit.structured.capability_observations import discover_jobs, inspect_run
from scenarios.remotion_edit.structured.run_capability_improvement import SourceImprovementAdapter
from tests.test_capability_improvement import plan_at, put, Adapter


def records(tmp_path):
    plan,snapshot,proposal=plan_at(tmp_path)
    context=put(tmp_path/'context.json',{'owner':'owner','scope':'diagnostic-family',
        'contract':proposal['contract'],'publication_plan':plan['jobs'][0]['publication_plan']})
    entries=[]
    for i in range(2):
        run=tmp_path/str(i);run.mkdir();args={'value':i}
        put(run/'args.json',args);put(run/'snapshot.json',snapshot)
        manifest=put(run/'manifest.json',{'task_id':str(i)})
        put(run/'specification.json',{'diagnostic':True})
        put(run/'trace.json',{'owner':'owner','task_id':str(i),'mode':'execute','status':'succeeded',
            'manifest_sha256':manifest['sha256'],'root':snapshot['roots'][0],'snapshot_sha256':snapshot['digest'],'arguments_sha256':capability_digest(args)})
        put(run/'validation.json',{'passed':True,'checks':[{'status':'passed'}],
            'evidence_binding':{name+'_sha256':file_ref(run/(name+'.json'))['sha256'] for name in ('trace','manifest','specification')}})
        entries.append({'run':str(run),'kind':'capability_execution','role':'training','context':context})
    return plan,snapshot,proposal,entries


def test_actual_discovery_adapter_jobs_enter_common_controller(tmp_path):
    plan,snapshot,proposal,entries=records(tmp_path)
    plan.update(jobs=[],discovery=entries)
    adapter=Adapter(snapshot,proposal)
    adapter.discover_jobs=lambda directory:discover_jobs(entries,'owner',directory/'discovery')
    result=run_improvement(plan,adapter,execute=True)
    assert [r['status'] for r in result['outcomes']]==['published']
    jobs=json.loads((Path(plan['output'])/'resolved-jobs.json').read_text(encoding='utf-8'))
    assert len(jobs)==1 and len(jobs[0]['observations'])==2
    task=json.loads(Path(jobs[0]['task']['path']).read_text(encoding='utf-8'))
    assert 'steps' not in task and len(task['learning_evidence'])==2


def test_renamed_identical_input_not_independent_support(tmp_path):
    _,_,_,entries=records(tmp_path)
    # Duplicate evidence, despite a different task ID and directory.
    args={'value':0};run=Path(entries[1]['run']);put(run/'args.json',args)
    trace=json.loads((run/'trace.json').read_text(encoding='utf-8'));trace['arguments_sha256']=capability_digest(args);put(run/'trace.json',trace)
    qa=json.loads((run/'validation.json').read_text(encoding='utf-8'));qa['evidence_binding']['trace_sha256']=file_ref(run/'trace.json')['sha256'];put(run/'validation.json',qa)
    assert discover_jobs(entries,'owner',tmp_path/'discovery')==[]


@pytest.mark.parametrize('mutation',['owner','mode','args','quality','heldout','unrelated_qa'])
def test_invalid_or_heldout_observations_cannot_generate_jobs(tmp_path,mutation):
    _,_,_,entries=records(tmp_path);run=Path(entries[0]['run'])
    trace=json.loads((run/'trace.json').read_text(encoding='utf-8'))
    if mutation=='owner':trace['owner']='other'
    if mutation=='mode':trace['mode']='validate'
    if mutation=='args':trace['arguments_sha256']='0'*64
    if mutation=='quality':put(run/'validation.json',{'passed':False,'checks':[]})
    if mutation=='heldout':entries[0]['role']='heldout'
    if mutation=='unrelated_qa':(run/'validation.json').write_bytes((Path(entries[1]['run'])/'validation.json').read_bytes())
    put(run/'trace.json',trace)
    with pytest.raises(ValueError):discover_jobs(entries,'owner',tmp_path/'discovery')


def test_source_change_detected_and_repeated_opportunity_stable_across_output_paths(tmp_path):
    _,_,_,entries=records(tmp_path)
    first=discover_jobs(entries,'owner',tmp_path/'one')[0]
    second=discover_jobs(entries,'owner',tmp_path/'two')[0]
    assert first['task']['path']!=second['task']['path']
    assert SourceImprovementAdapter.opportunity_key(first)==SourceImprovementAdapter.opportunity_key(second)
    source=Path(entries[0]['run'])/'args.json';source.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError,match='evidence_changed'):discover(first)


def test_existing_native_witness_collector_is_used_and_source_pinned(tmp_path):
    _,_,_,entries=records(tmp_path);entry=entries[0];run=Path(entry['run'])
    entry['kind']='native_source';task={'id':'native','partition':'training','instruction':'diagnostic'}
    work=run/'native';(work/'src').mkdir(parents=True);(work/'out/render-1').mkdir(parents=True)
    (run/'qa').mkdir();source='export default function Demo() { return null; }'
    (work/'src/index.tsx').write_text(source, encoding='utf-8')
    import hashlib
    digest=hashlib.sha256(source.encode()).hexdigest()
    put(run/'effective.json',{'task':task});put(run/'result.json',{'status':'completed'})
    put(run/'events.jsonl',{'type':'tool/call','data':{'name':'render_source','callId':'witness','arguments':{'text':source}}})
    put(work/'out/render-1/receipt.json',{'source_version':digest,'video_sha256':'diagnostic'})
    put(run/'qa/verification.json',{'technical_pass':True,'selected_source_frames_pass':True,'video_sha256':'diagnostic'})
    observed=inspect_run(entry,'owner')
    assert observed['trace']['witness']['source_sha256']==digest
    assert str(work/'src/index.tsx') in [r['path'] for r in observed['evidence']]
    (work/'src/index.tsx').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError,match='not_witnessed'):inspect_run(entry,'owner')


def test_feedback_admission_uses_original_evidence_and_actual_failed_attempts(tmp_path):
    _,_,_,entries=records(tmp_path)
    job=discover_jobs(entries,'owner',tmp_path/'one')[0]
    adapter=object.__new__(SourceImprovementAdapter)
    adapter.feedback=CapabilityFeedback(tmp_path/'feedback','owner')
    for i in range(2):
        attempt=tmp_path/('attempt-'+str(i));attempt.mkdir()
        result={'status':'failed','observed_model_usd':0.01};put(attempt/'result.json',result)
        adapter.record_outcome(job,attempt,result,None,None)
    new_job=discover_jobs(entries,'owner',tmp_path/'two')[0]
    assert adapter.admission(new_job)[0]=='defer'
    assert sum(f['cost'] for f in adapter.feedback.read()['facts'].values())==0.02


@pytest.mark.parametrize('reason,withdrawn',[
    ('capability_legacy_changed',True),('source_task_input_changed',False)])
def test_ordinary_execution_feedback_is_ingested_and_only_version_guard_quarantines(tmp_path,reason,withdrawn):
    plan,snapshot,_,entries=records(tmp_path);run=Path(entries[0]['run'])
    trace=json.loads((run/'trace.json').read_text(encoding='utf-8'));trace.update(status='rejected',receipts=[{'reason':reason}]);put(run/'trace.json',trace)
    adapter=object.__new__(SourceImprovementAdapter)
    adapter.plan={**plan,'discovery':entries};adapter.seed=snapshot;adapter.seed_catalog={};adapter.templates={}
    adapter.feedback=CapabilityFeedback(tmp_path/'feedback','owner')
    adapter.freeze(tmp_path)
    state=adapter.feedback.read()
    assert len(state['facts'])==2
    assert bool(state['blocked'])==withdrawn
    assert all(f['scope']=='diagnostic-family' and f['cost'] is None for f in state['facts'].values())


def test_changed_original_evidence_after_build_blocks_publication(tmp_path):
    plan,snapshot,proposal,entries=records(tmp_path);plan.update(jobs=[],discovery=entries)
    adapter=Adapter(snapshot,proposal)
    adapter.discover_jobs=lambda directory:discover_jobs(entries,'owner',directory/'discovery')
    construct=adapter.construct
    def changing(*args):
        result=construct(*args)
        (Path(entries[0]['run'])/'args.json').write_text('{}', encoding='utf-8')
        return result
    adapter.construct=changing
    with pytest.raises(ValueError,match='evidence_changed'):run_improvement(plan,adapter,execute=True)
    assert not adapter.published


def test_published_contribution_feeds_both_values_and_skips_identical_opportunity(tmp_path):
    plan,snapshot,proposal,entries=records(tmp_path)
    job=discover_jobs(entries,'owner',tmp_path/'one')[0]
    adapter=object.__new__(SourceImprovementAdapter);adapter.feedback=CapabilityFeedback(tmp_path/'feedback','owner')
    fake=Adapter(snapshot,proposal);attempt=tmp_path/'attempt'
    result=fake.construct({},fake.library(),attempt,None,None)
    candidate=json.loads((attempt/'candidate.json').read_text(encoding='utf-8'));outcome=fake.publish(job,candidate,attempt,None)
    adapter.record_outcome(job,attempt,result,candidate,outcome)
    facts=list(adapter.feedback.read()['facts'].values())
    assert sum(f['stage']=='construction' for f in facts)==2
    assert next(f for f in facts if f['stage']=='execution')['scope']=='diagnostic-family'
    assert adapter.admission(discover_jobs(entries,'owner',tmp_path/'two')[0])[0]=='skip'


def test_discovery_cannot_be_silently_ignored_without_adapter(tmp_path):
    plan,_,_,entries=records(tmp_path);plan.update(jobs=[],discovery=entries)
    with pytest.raises(ValueError,match='discovery_adapter_required'):run_improvement(plan,None)
