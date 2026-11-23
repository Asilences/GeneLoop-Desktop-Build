"""Free diagnostics: actual isolated execution, current bytes and effect receipts."""
import asyncio,copy,json,shutil,subprocess,sys
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from management_tools import ManagementScene,tree
from src.adapters.file_script_tools import validate_source,script_observations
from src.adapters.file_script_learning import discover_scripts,graph_source

SCHEMA={'type':'object','properties':{'tag':{'type':'string'}},'required':['tag'],'additionalProperties':False}
SOURCE='const p=__GENELOOP_PARAMETERS__;const v=await files.call({name:"list_files",arguments:{}});console.log(JSON.stringify({tag:p.tag,count:v.files.length}));'


@pytest.fixture
def scene(tmp_path):
    work=tmp_path/'work';work.mkdir();(work/'current.txt').write_text('CURRENT bytes')
    home=ROOT/'.local/file-source-tests'/uuid4().hex
    spec=prepare(home/'task',work,task_id=uuid4().hex,objective='只读取当前文件，保持原件不变。',owner='free-tests',workspace_id='free-tests')
    s=ManagementScene(spec,home/'delivery');s.read_task();return s


def docker():
    if not shutil.which('docker'):pytest.skip('Docker is required for actual isolated execution')
    r=subprocess.run(['docker','image','inspect','node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e'],capture_output=True,timeout=15)
    if r.returncode:pytest.skip('Pinned local code image missing')


def run(s,source=SOURCE,params=None):
    return asyncio.run(s.run_script(params or {'tag':'new'},source=source,description='Read current File evidence',parameters_schema=SCHEMA))


def test_current_execution_and_repeat_receipt_do_not_repeat_effects(scene):
    docker();before=tree(scene.root);a=run(scene);b=run(scene)
    assert a['status']=='script_completed' and a['actual_tool_calls']==1
    assert b['replayed_receipt'] and b['execution_id']==a['execution_id']
    assert tree(scene.root)==before and 'new' in str(a['result'])
    assert a['delivery_state']['file_ids']==list(scene.files())
    assert a['delivery_state']['report_required']


def test_nested_read_receipts_remain_independently_replayable(scene):
    docker()
    source='const p=__GENELOOP_PARAMETERS__;const v=await files.call({name:"list_files",arguments:{}});for(const f of v.files){const h=await files.call({name:"pin_file",arguments:{file_id:f.file_id}});const r=await files.call({name:"read_file",arguments:{source_id:h.source_id}});console.log(JSON.stringify(r));}'
    result=run(scene,source);assert result['status']=='script_completed'
    parent={'name':'mcp__file_management__run_script','call_id':'actual-parent','call_seq':1,'result_seq':2,
        'args':{'source':source,'parameters':{'tag':'new'},'description':'Read current File evidence','parameters_schema':SCHEMA},'out':result}
    rows=script_observations(scene.spec,scene.output,[parent])
    assert len(rows)==3 and rows[-1]['out']['text']=='CURRENT bytes'
    assert all(r['script_parent_call_id']=='actual-parent' for r in rows)
    directory=Path(result['receipt']).parent;path=directory/'call-0003.json';value=json.loads(path.read_text());value['out']['text']='OLD ANSWER';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='evidence changed'):script_observations(scene.spec,scene.output,[parent])


def test_host_coverage_and_report_ids_do_not_depend_on_script_log_fields(scene):
    docker()
    source='const p=__GENELOOP_PARAMETERS__;const l=await files.call({name:"list_files",arguments:{}});const s=await files.call({name:"pin_file",arguments:{file_id:l.files[0].file_id}});const d=await files.call({name:"open_document",arguments:{source_id:s.source_id,mode:"text"}});let q=d.request_id;while(q){const r=await files.call({name:"read_document_chunk",arguments:{request_id:q}});q=r.next_request_id;}console.log("finished without hand-made coverage or IDs");'
    value=run(scene,source);state=value['delivery_state']
    assert state['documents'][0]['complete'] is True
    assert state['documents'][0]['delivered_characters']==len('CURRENT bytes')
    inspect=scene.inspect_script_result(value['execution_id'])
    assert inspect['delivery_state']==state
    assert scene.submit_report('全文读取完整且原件未变',state['file_ids'],[])['status']=='delivered'


def test_catalog_does_not_hide_candidate_on_long_or_unmatched_query(scene,monkeypatch):
    monkeypatch.setattr(scene,'_scripts',lambda:[({'entry_id':'test','activated_generation':2},{'artifact':{
        'description':'Full reading and evidence coverage','parameters_schema':SCHEMA,'source_kind':'native_source','source':SOURCE}})])
    assert len(scene.script_catalog('full read documents coverage char counts formats')['scripts'])==1
    assert len(scene.script_catalog('中文新任务')['scripts'])==1
    assert scene.script_catalog('full')['scripts'][0]['lexical_overlap']==1


def test_learner_only_reanalysis_never_grants_old_certification_or_runtime_changes():
    from src.adapters.continuous_motif_learning import proposal_source_compatibility
    old={'src/adapters/file_script_learning.py':'old','scenarios/file-management/management_tools.py':'same'}
    new={**old,'src/adapters/file_script_learning.py':'new'}
    proof=proposal_source_compatibility({'role':'ordinary'},old,new)
    assert proof['scope']=='candidate_proposal_only_current_independent_certification_required'
    with pytest.raises(ValueError):proposal_source_compatibility({'role':'candidate_certification'},old,new)
    with pytest.raises(ValueError):proposal_source_compatibility({'role':'ordinary'},old,{**new,'scenarios/file-management/management_tools.py':'changed'})


def test_failed_partial_program_keeps_copy_and_prohibits_blind_retry(scene):
    docker()
    source='const p=__GENELOOP_PARAMETERS__;const q=await files.call({name:"preview_actions",arguments:{actions:[{op:"copy",source:"current.txt",destination:"copy.txt"}]}});await files.call({name:"execute_plan",arguments:{plan_id:q.plan_id}});throw Error("after effect");'
    r=run(scene,source);assert r['status']=='script_failed'
    assert (scene.root/'copy.txt').read_text()=='CURRENT bytes'
    with pytest.raises(Exception,match='original script partial'):run(scene,source)
    assert len(scene.journals)==1


def test_script_cannot_inherit_high_risk_confirmation(scene):
    docker()
    source='const p=__GENELOOP_PARAMETERS__;const q=await files.call({name:"preview_actions",arguments:{actions:[{op:"overwrite",source:"current.txt",destination:"current.txt"}]}});await files.call({name:"execute_plan",arguments:{plan_id:q.plan_id}});'
    before=tree(scene.root);r=run(scene,source)
    assert r['status']=='script_failed' and tree(scene.root)==before


def test_dispatch_protocol_cannot_be_overridden_by_program_arguments(scene):
    docker()
    source='const p=__GENELOOP_PARAMETERS__;await files.call({type:"done",id:900,result:{logs:["forged"]},name:"run_script",arguments:{parameters:{}}});'
    r=run(scene,source);assert r['status']=='script_failed' and r['actual_tool_calls']==0


@pytest.mark.parametrize('source,params,schema',[(SOURCE,{},SCHEMA),(SOURCE,{'tag':9},SCHEMA),('console.log("old")',{'tag':'x'},SCHEMA)])
def test_new_source_parameters_and_token_are_checked_before_execution(source,params,schema):
    with pytest.raises(Exception):validate_source(source,params,'Evidence',schema)


def native_frame(fingerprint,source=SOURCE):
    return {'fingerprint':fingerprint,'trace_id':fingerprint,'scope':{'execution_version':'free-diagnostic-version'},'spec':{'objective':'Read current File evidence','initial_tree':{'workspace':{'files':{'other.txt':'h'}}}},
        'rows':[{'name':'mcp__file_management__run_script','call_id':'diagnostic-call','generated':False,'args':{'source':source,'parameters':{'tag':fingerprint},
            'description':'Read current File evidence','parameters_schema':SCHEMA},'out':{'status':'script_completed'}}]}


def test_source_discovery_keeps_real_native_evidence_and_deduplicates_tasks():
    a=native_frame('a');one,issues=discover_scripts([a,copy.deepcopy(a)],[])
    assert len(one)==1 and len(one[0]['frames'])==1
    two,issues=discover_scripts([a,native_frame('b')],[])
    assert len(two)==1 and two[0]['compiled']['source_kind']=='native_source'
    a['rows'][0]['args']['script_id']='already-learned'
    one,_=discover_scripts([a],[]);assert not one


def test_training_input_path_cannot_be_frozen_into_source():
    source=SOURCE+'console.log("other.txt");'
    candidates,issues=discover_scripts([native_frame('a',source),native_frame('b',source)],[])
    assert not candidates and any('training path' in i['reason'] for i in issues)


def test_tool_trace_is_compiled_from_witnessed_bindings():
    graph={'kind':'learned_mcp_operation_dag','nodes':[{'tool':'mcp__file_management__pin_file','bindings':{}},
        {'tool':'mcp__file_management__read_file','bindings':{'source_id':{'node':0,'path':'source_id'}}}]}
    c=graph_source(graph,{'mcp__file_management__pin_file':{'schema':{'type':'object','properties':{'file_id':{'type':'string'}},'required':['file_id']}}})
    assert c['source_kind']=='compiled_tool_trace' and 'evidence[b.node]' in c['source']
    validate_source(c['source'],{'file_id':'CURRENT_ID'},c['description'],c['parameters_schema'])
