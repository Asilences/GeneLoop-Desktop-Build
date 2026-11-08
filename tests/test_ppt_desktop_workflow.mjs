import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {stagePptWorkflow} from '../apps/desktop/scripts/stage-ppt-workflow.mjs';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';

test('desktop stages the shared executor and verifies native schema, bundle and revocation',async()=>{
  const target=mkdtempSync(resolve('.local/ppt-workflow-desktop-'));
  writeFileSync(join(target,'local-ppt-master.mjs'),'// current native implementation');
  stagePptWorkflow(resolve('.'),target);
  const adapter=await import(pathToFileURL(join(target,'local-ppt-workflow.mjs')));
  const environment=adapter.localPptWorkflowEnvironment(),controller=new AbortController();
  const schema={type:'object',properties:{path:{type:'string'}},required:['path']};
  const ir={version:1,kind:'observed_anchor_read_continuation',anchor:{tool:'local_ppt_master_export',schema_sha256:digest(schema)},
    success:['status'],success_value:'passed',empty_findings:['findings'],collection:['artifacts'],collection_length:1,
    steps:[{id:'inspect',tool:'local_ppt_read_material',schema_sha256:digest(schema),bindings:{path:['artifacts',0,'path']}}]};
  const witness=id=>({decision_id:id,source_signature:'source-'+id,question_sha256:'question-'+id});
  const program={id:'ppt_flow_'+digest(ir).slice(0,24),ir,status:'certified',provenance:[witness('a'),witness('b')],
    certification:{status:'passed',training_decisions:2,independent_replay_decisions:1,replay:[witness('c')]}};
  const body={version:1,kind:'trace_learned_tool_continuations',environment_sha256:environment,programs:[program]};
  let post,calls=0;
  const scope={on:(_name,fn)=>post=fn,tools:{execute:async()=>{calls++;return {isError:false,content:[],value:{}};}}};
  const handle=adapter.installLocalPptWorkflow(scope,{enabled:true,library:{...body,digest:digest(body)},taskId:'diagnostic',
    sessionId:'owned',signal:controller.signal,audit(){}});
  const execution={name:'local_ppt_master_export',callId:'root',signal:controller.signal,
    agent:{session:{id:'owned'},ctx:{tools:{get:()=>({parameters:schema,output:{render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]}})}}}};
  const result={isError:false,value:{status:'passed',findings:[],artifacts:[{path:'本机演示.pptx'}]},content:[]};
  assert.equal(JSON.parse((await post(execution,result,async()=>({kind:'accept'}))).content[0].text).workflow_continuation.status,'completed');
  assert.equal(calls,1);
  handle.close();assert.deepEqual(await post(execution,result,async()=>({kind:'accept'})),{kind:'accept'});assert.equal(calls,1);
  writeFileSync(join(target,'local-ppt-master.mjs'),'// changed native implementation');
  assert.throws(()=>adapter.localPptWorkflowEnvironment(),/bundle_changed/);
  writeFileSync(join(target,'local-ppt-master.mjs'),'// current native implementation');
  writeFileSync(join(target,'ppt-shared/adapters/ppt_execution.mjs'),'changed');
  assert.throws(()=>adapter.localPptWorkflowEnvironment(),/bundle_changed/);
});

test('desktop learned writes use the same interpreter with native version and authority callbacks',async()=>{
 const target=mkdtempSync(resolve('.local/ppt-write-desktop-'));stagePptWorkflow(resolve('.'),target);
 const adapter=await import(pathToFileURL(join(target,'local-ppt-workflow.mjs')));
 const environment=adapter.localPptWorkflowEnvironment(),controller=new AbortController();
 const schema={type:'object'},role={resource_argument:'project',identity_argument:'page',revision_argument:'expected_sha256',version_output:['sha256']};
 const completion={success:['status'],success_value:'passed',empty_findings:['findings'],collection:['artifacts']};
 const ir={version:1,kind:'observed_page_write_delivery',mode:'new',writer:{tool:'local_ppt_page_write',schema_sha256:digest(schema),
   ...role,argument_names:['project','page','content']},delivery:{tool:'local_ppt_export_project',schema_sha256:digest(schema),resource_argument:'project',argument_names:['project'],...completion}};
 const witness=id=>({decision_id:id,source_signature:'source-'+id,question_sha256:'question-'+id});
 const program={id:'ppt_write_'+digest(ir).slice(0,24),ir,status:'certified',provenance:[witness('a'),witness('b')],
   certification:{scope:'independent_observed_write_binding_replay',status:'passed',training_decisions:2,independent_replay_decisions:1,replay:[witness('c')]}};
 const body={version:1,kind:'trace_learned_tool_continuations',environment_sha256:environment,programs:[program]};
 const tools=new Map(),versions=new Map(),journals=new Map(),calls=[];
 const scope={on(){},tools:{guard(){},register:tool=>tools.set(tool.name,tool),execute:async call=>{
   calls.push(call);if(call.name==='local_ppt_page_write'){versions.set(call.arguments.page,'a'.repeat(64));return {isError:false,value:{sha256:'a'.repeat(64)},content:[]};}
   return {isError:false,value:{status:'passed',findings:[],artifacts:[]},content:[]};
 }}};
 const handle=adapter.installLocalPptWorkflow(scope,{enabled:true,library:{...body,digest:digest(body)},taskId:'native-diagnostic',
   sessionId:'owned',signal:controller.signal,audit(){},writeHost:{contracts:{
    local_ppt_page_write:{read_only:false,page_write:role},local_ppt_export_project:{read_only:false,resource_argument:'project',observed_completion:completion}},
    admit(){},version:operation=>versions.get(operation.arguments.page)??null,load:key=>journals.get(key),save:(key,value)=>journals.set(key,structuredClone(value))}});
 const execution={callId:'root',agent:{session:{id:'owned'},ctx:{tools:{get:()=>({parameters:schema})}}},signal:controller.signal};
 for(const project of ['C:\\Users\\example\\演示','/Users/example/演示']){
   versions.clear();const result=await tools.get('execute_ppt_program').execute({id:program.id,project,pages:[{page:'one',content:{text:'current'}}]},execution);
   assert.equal(result.status,'completed');assert.equal(calls.at(-2).arguments.project,project);
 }
 handle.close();await assert.rejects(()=>tools.get('execute_ppt_program').execute({},execution),/revoked/);
});

test('a missing desktop page-write backend preserves the ordinary Agent instead of failing startup',async()=>{
 const target=mkdtempSync(resolve('.local/ppt-write-no-host-'));stagePptWorkflow(resolve('.'),target);
 const adapter=await import(pathToFileURL(join(target,'local-ppt-workflow.mjs'))),audit=[];
 const handle=adapter.installLocalPptWorkflow({},{enabled:true,library:{programs:[{ir:{kind:'observed_page_write_delivery'}}]},audit:row=>audit.push(row)});
 assert.equal(handle.status,'ordinary_tools_only');assert.equal(audit[0].ordinary_tools_preserved,true);handle.close();
});
