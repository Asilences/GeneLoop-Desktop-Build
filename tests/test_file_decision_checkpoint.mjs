import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const options={skip:!process.features?.typescript};
async function fixture(){
 const {digest}=await import('../src/motif_core/runtime/online_skill_runtime.mjs');
 const {prepareLearnedAction,bindLearnedDecision}=await import('../src/adapters/learned_decision_program.ts');
 const payload={candidate:{format:'geneloop-learned-decision-v1',description:'diagnostic only',scope_description:'toy',
  guard:['lit',true],request:['lit',{state:'current toy evidence',questions:[{id:'x',question:{type:'noul',instructions:'Is the toy condition true?'}}]}],
  bind:['lit',{tool:'toy-stage',arguments:{current:'file'}}],training_witnesses:[{snapshot_id:'toy',values:{x:true}}]}};
 const context={goal:'toy',history:[]},request=prepareLearnedAction(payload.candidate,context).request;
 const resolution={accepted:true,values:{x:true}},binding=bindLearnedDecision(payload.candidate,context,resolution.values);
 const current={payload,task_sha256:'task',owner:'owner',task_id:'task-id',runtime_sha256:'runtime',models_sha256:'models',
  previous_call_ids:['old'],history:[],workspace:{files:{'current.txt':'original'},directories:[]},schema:{type:'object'},effect:'stage',external_roots:false};
 const pending={format:'file-paid-decision-checkpoint-v1',task_sha256:'task',owner:'owner',task_id:'task-id',
  payload_sha256:digest(payload),runtime_sha256:'runtime',models_sha256:'models',context,request,resolution,binding,
  workspace:current.workspace,tool_schema_sha256:digest(current.schema)};
 return {pending,current};
}
test('cached decisions rebind without a model call; changed grants, files, schema or task progress invalidate',options,async()=>{
 const {validatePendingDecision}=await import('../src/adapters/file_management/file_decision_checkpoint.ts');const {pending,current}=await fixture();
 assert.equal(validatePendingDecision(pending,current).kind,'replay');
 for(const patch of [{task_sha256:'different'},{owner:'different'},{runtime_sha256:'different'},{models_sha256:'different'},
  {effect:'authorized_write'},{external_roots:true},{history:[{tool:'intervening'}]},
  {workspace:{files:{'current.txt':'modified'},directories:[]}},{schema:{type:'string'}}]){
  assert.equal(validatePendingDecision(pending,{...current,...patch}).kind,'invalid',JSON.stringify(patch));
 }
 assert.equal(validatePendingDecision({...pending,resolution:{accepted:false,values:{}}},current).kind,'invalid');
});
test('actual completed predecessor is consumed without repeating effects',options,async()=>{
 const {validatePendingDecision}=await import('../src/adapters/file_management/file_decision_checkpoint.ts');const {pending,current}=await fixture();
 const history=[{call_id:'old',tool:pending.binding.tool,args:pending.binding.arguments}];
 assert.equal(validatePendingDecision(pending,{...current,history,workspace:{files:{new:'effect'},directories:[]}}).kind,'completed');
 assert.equal(validatePendingDecision(pending,{...current,history:[{...history[0],args:{different:true}}]}).kind,'invalid');
});
test('only an actual original-scope initialization read can precede replay',options,async()=>{
 const {validatePendingDecision}=await import('../src/adapters/file_management/file_decision_checkpoint.ts');const {pending,current}=await fixture();
 const scope={owner:'original'},primer={call_id:'init',tool:'original-init'};
 const row={...primer,args:{},out:{_sss_scope:scope}};
 assert.equal(validatePendingDecision(pending,{...current,primer,scope,history:[row]}).kind,'replay');
 assert.equal(validatePendingDecision(pending,{...current,primer,scope,history:[{...row,out:{_sss_scope:{owner:'other'}}}]}).kind,'invalid');
 assert.equal(validatePendingDecision(pending,{...current,primer,scope,history:[row,{call_id:'new-action'}]}).kind,'invalid');
});
test('workspace version detects changed bytes and added directories',options,async()=>{
 const {workspaceSnapshot}=await import('../src/adapters/file_management/file_decision_checkpoint.ts');const dir=mkdtempSync(join(tmpdir(),'file-checkpoint-'));
 try{writeFileSync(join(dir,'input'),'before');const before=workspaceSnapshot(dir);writeFileSync(join(dir,'input'),'after');
  assert.notDeepEqual(workspaceSnapshot(dir),before);mkdirSync(join(dir,'added'));assert.deepEqual(workspaceSnapshot(dir).directories,['added']);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
test('legacy semantic initialization metadata does not erase a witnessed task-read capability',options,async()=>{
 const {originalInitialization}=await import('../src/adapters/file_management/file_decision_checkpoint.ts');
 const {digest}=await import('../src/motif_core/runtime/online_skill_runtime.mjs');
 const tool='mcp__file_management__read_task',schema={type:'object',properties:{},title:'read_taskArguments'},scope={original:true};
 const operation={scope,catalog:{[tool]:{contract:{effect:'semantic'},schema_sha256:digest(schema)}}};
 const pending={context:{history:[{tool,args:{},out:{_sss_scope:scope}}]}};
 assert.equal(originalInitialization(operation,pending,[{name:tool,parameters:schema}]),tool);
 assert.throws(()=>originalInitialization(operation,{context:{history:[]}},[{name:tool,parameters:schema}]),/unavailable/);
 assert.throws(()=>originalInitialization(operation,pending,[{name:tool,parameters:{type:'object',properties:{new:{type:'string'}}}}]),/unavailable/);
});
