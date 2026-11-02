"""Common engine + second scene. Proposal is diagnostic; native execution is real."""
import copy,json,os,subprocess
from pathlib import Path
import pytest
from src.adapters.capability_scene import load_scene_adapter
from src.adapters.capability_improvement import run_improvement
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_feedback import file_ref
from tests.test_capability_improvement import put

ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT/'examples/capability-scenes/counts/adapter.py'


def setup(tmp_path):
    # Execute two ordinary diagnostic tasks through the native TS Runtime.
    script="""
import {writeFileSync,mkdirSync} from 'node:fs';
import {seed,execute,contract} from './examples/capability-scenes/counts/runtime.mjs';
const directory=process.argv[1],snapshot=seed('owner');
writeFileSync(directory+'/seed.json',JSON.stringify(snapshot));
writeFileSync(directory+'/contract.json',JSON.stringify(contract));
for(let i=0;i<2;i++){
 const run=directory+'/native-'+i;mkdirSync(run);
 const args={rows:Array.from({length:i+1},()=>({group:'diagnostic-'+i}))};
 const result=await execute(snapshot,snapshot.roots[0],args,{taskId:'ordinary-'+i,mode:'execute'});
 if(result.execution.status!=='succeeded')throw Error(JSON.stringify(result.execution));
 for(const [name,value] of [['trace',result.execution],['args',args],['snapshot',snapshot]])writeFileSync(run+'/'+name+'.json',JSON.stringify(value));
}
"""
    subprocess.run(['node','--experimental-strip-types','--input-type=module','-e',script,str(tmp_path)],cwd=ROOT,check=True,capture_output=True,text=True)
    snapshot=json.loads((tmp_path/'seed.json').read_text());contract=json.loads((tmp_path/'contract.json').read_text())
    template=put(tmp_path/'publication-inputs.json',{
        'validation':{'id':'validation','input':{'rows':[{'group':'A'},{'group':'A'}]}},
        'followup':{'id':'followup','input':{'rows':[{'group':'B'}]}}})
    context=put(tmp_path/'context.json',{'owner':'owner','scope':'count-diagnostic','contract':contract,'publication_plan':template})
    plan={'format':'capability_improvement_plan_v1','id':'cross-scene-diagnostic','owner':'owner',
        'seed':file_ref(tmp_path/'seed.json'),'seed_catalog':put(tmp_path/'catalog.json',{}),
        'store':str(tmp_path/'store'),'ledger_root':str(tmp_path/'unused-ledger'),'output':str(tmp_path/'run'),
        'policy':{'version':'capability_improvement_policy_v1','max_repairs':None},'jobs':[],
        'scene_adapter':file_ref(ADAPTER),
        'scene_dependencies':[file_ref(ADAPTER.with_name(name)) for name in ('runtime.mjs','publish.mjs')],
        'discovery':[{'run':str(tmp_path/('native-'+str(i))),'kind':'count_execution','role':'training','context':context} for i in range(2)]}
    return plan,snapshot,contract


def test_second_scene_uses_common_discovery_controller_feedback_and_real_store(tmp_path):
    plan,snapshot,contract=setup(tmp_path);adapter=load_scene_adapter(plan);calls=[]
    def diagnostic_proposal(task,library,attempt,parent,feedback):
        calls.append(task);attempt.mkdir()
        proposal={'format':'capability_compose_proposal_v1','owner':'owner','contract':contract,
            'steps':[{'id':'count','capability':snapshot['roots'][0],'arguments':{'kind':'input','path':[]}}],
            'output':{'kind':'step','step_id':'count','path':[]}}
        put(attempt/'candidate.json',compile_proposal(proposal,library['snapshot'],'owner'))
        result={'status':'compiled_candidate','observed_model_usd':None,'diagnostic_only':True}
        put(attempt/'result.json',result);return result
    adapter.construct=diagnostic_proposal
    result=run_improvement(plan,adapter,execute=True)
    assert result['status']=='completed' and result['outcomes'][0]['status']=='published'
    assert len(calls)==1 and len(calls[0]['learning_evidence'])==2
    facts=list(adapter.feedback.read()['facts'].values())
    assert any(f['stage']=='construction' and f['status']=='passed' for f in facts)
    assert result['outcomes'][0]['capability'] in adapter.library()['snapshot']['roots']
    assert not Path(plan['ledger_root']).exists()


def test_changed_host_adapter_dependency_blocks_before_import_or_model(tmp_path):
    plan,_,_=setup(tmp_path)
    dependency=tmp_path/'host-module.py';dependency.write_text('# original')
    plan['scene_dependencies']=[file_ref(dependency)];dependency.write_text('# changed')
    with pytest.raises(ValueError,match='evidence_changed'):load_scene_adapter(plan)


def test_missing_material_gap_reopens_when_the_certified_catalog_changes(tmp_path):
    plan,snapshot,_=setup(tmp_path);adapter=load_scene_adapter(plan)
    directory=tmp_path/'preview';directory.mkdir();job=adapter.discover_jobs(directory)[0]
    attempt=tmp_path/'gap';attempt.mkdir()
    result={'status':'deferred','construction_snapshot_sha256':snapshot['digest'],'observed_model_usd':None}
    put(attempt/'result.json',result);adapter.record_outcome(job,attempt,result,None,None)
    assert adapter.admission(job)[0]=='defer'
    # Catalog-refresh mechanics only; no fabricated certification or publication.
    adapter.library=lambda:{'snapshot':{'digest':'different-certified-snapshot'}}
    assert adapter.admission(job)[0]=='start'


def test_failed_then_successful_same_input_keeps_negative_evidence(tmp_path):
    plan,_,_=setup(tmp_path)
    # Same input has a failed predecessor and later success. Preserve both;
    # their repetition does not create two independent supporting inputs.
    first=Path(plan['discovery'][0]['run']);second=Path(plan['discovery'][1]['run'])
    trace=json.loads((first/'trace.json').read_text());trace['status']='failed';put(first/'trace.json',trace)
    for name in ('args.json','snapshot.json'): (second/name).write_bytes((first/name).read_bytes())
    trace['status']='succeeded';trace['task_id']='later';trace['result']={'counts':{'diagnostic-0':1}};put(second/'trace.json',trace)
    adapter=load_scene_adapter(plan);directory=tmp_path/'preview';directory.mkdir()
    jobs=adapter.discover_jobs(directory)
    assert len(jobs)==1 and len(jobs[0]['observations'])==2
    assert {o['kind'] for o in jobs[0]['observations']}=={'task_failure','repeated_structure'}
