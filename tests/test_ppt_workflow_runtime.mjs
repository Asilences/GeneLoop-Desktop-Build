import test from 'node:test';
import assert from 'node:assert/strict';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {registerPptWorkflowContinuation,pptWorkflowOperations} from '../src/adapters/ppt_workflow_runtime.ts';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime,defineTool} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {randomUUID} from 'node:crypto';

function fixture(path='C:\\approved\\输出\\page.png',dispatch){
  const host={environment_sha256:'env',contracts:{export:{schema_sha256:'export-schema',read_only:false},
    image:{schema_sha256:'image-schema',read_only:true}}};
  const ir={version:1,kind:'observed_anchor_read_continuation',anchor:{tool:'export',schema_sha256:'export-schema'},
    success:['mechanical_status'],success_value:'passed',empty_findings:['findings'],collection:['review_pages'],collection_length:1,
    steps:[{id:'image0',tool:'image',schema_sha256:'image-schema',bindings:{file_path:['review_pages',0,'path']}}]};
  const witness=id=>({decision_id:id,source_signature:'source-'+id,question_sha256:'question-'+id});
  const program={id:'ppt_flow_'+digest(ir).slice(0,24),ir,status:'certified',provenance:[witness('a'),witness('b')],
    certification:{status:'passed',training_decisions:2,independent_replay_decisions:1,replay:[witness('c')]}};
  const body={version:1,kind:'trace_learned_tool_continuations',environment_sha256:'env',programs:[program]};
  const library={...body,digest:digest(body)},events=[],calls=[];
  const value={workflow:library,workflowAudit:row=>events.push(row),task:{status:'running',request:{task_id:'task',mode:'execute'},
    selection:{rsi:true},scene_options:{allow_output:true}}};
  let post;
  registerPptWorkflowContinuation({on:(_event,fn)=>{post=fn;},tools:{execute:async call=>{
    calls.push(call);return dispatch?dispatch(call):{isError:false,value:{},content:[{type:'image',attachment:{attachmentId:'sha256:image'}}]};
  }}},()=>value,host);
  const result={isError:false,value:{mechanical_status:'passed',findings:[],review_pages:[{path}]},content:[{type:'text',text:'export result'}]};
  const middleware=async(execution,next)=>{
    execution.agent.ctx??={tools:{get:()=>({output:{render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]}})}};
    const result=await next(),decision=await post(execution,result,async()=>({kind:'accept'}));
    return decision.content?{...result,content:decision.content}:result;
  };
  return {host,library,program,value,events,calls,result,middleware};
}

test('a witnessed continuation dispatches through the same host and returns images in the parent result',async()=>{
  for(const path of ['C:\\approved\\输出\\page.png','/Users/test/approved/page.png','/work/outputs/page.png']){
    const f=fixture(path),controller=new AbortController(),token={};
    const result=await f.middleware({name:'export',callId:'original',token,agent:{session:{id:'owned'}},signal:controller.signal},async()=>f.result);
    assert.equal(f.calls.length,1);assert.equal(f.calls[0].arguments.file_path,path);assert.equal(f.calls[0].parent,token);
    assert.equal(result.content[1].type,'image');assert.equal(JSON.parse(result.content[0].text).workflow_continuation.status,'completed');
    assert.equal(f.events.at(-1).model_requests_inside_continuation,0);
  }
});

test('Baseline, revoked permissions, changed contracts and unmatched page counts use the ordinary path',async()=>{
  for(const mutate of [f=>f.value.task.request.mode='baseline',f=>f.value.task.scene_options.allow_output=false,
    f=>f.host.contracts.image.read_only=false,f=>f.result.value.review_pages.push({path:'second'}),
    f=>f.result.value.findings.push({id:'real-defect'}),f=>f.library.environment_sha256='changed']){
    const f=fixture();mutate(f);
    assert.equal(await f.middleware({name:'export',callId:'original',agent:{session:{id:'owned'}}},async()=>f.result),f.result);
    assert.equal(f.calls.length,0);
  }
});

test('prototype paths in a generated program are rejected',()=>{
  const f=fixture();f.program.ir.steps[0].bindings.file_path=['__proto__','secret'];
  assert.throws(()=>pptWorkflowOperations(f.program,f.result.value),/field_invalid/);
});

test('a certified-looking partial collection cannot suppress remaining review pages',async()=>{
  const f=fixture();f.program.ir.collection_length=2;f.result.value.review_pages.push({path:'second.png'});
  f.program.id='ppt_flow_'+digest(f.program.ir).slice(0,24);
  const {digest:old,...body}=f.library;f.library.digest=digest(body);
  assert.equal(await f.middleware({name:'export',callId:'partial',agent:{session:{id:'owned'}}},async()=>f.result),f.result);
  assert.equal(f.calls.length,0);assert.equal(f.events.at(-1).reason,'ppt_workflow_full_collection_required');
});

test('a thrown child read preserves the successful export and permits ordinary recovery',async()=>{
  const f=fixture(undefined,async()=>{throw Error('read temporarily unavailable');});
  assert.equal(await f.middleware({name:'export',callId:'original',agent:{session:{id:'owned'}}},async()=>f.result),f.result);
  assert.equal(f.calls.length,1);
  assert.equal(f.events.at(-1).anchor_preserved,true);
});

test('a write program that owns preview prevents a second automatic read continuation',async()=>{
 const f=fixture();f.value.writePreviewOwned=new Set(['owned-by-writer']);
 assert.equal(await f.middleware({name:'export',callId:'owned-by-writer',agent:{session:{id:'owned'}}},async()=>f.result),f.result);
 assert.equal(f.calls.length,0);
});

test('installed Harness normalizes canonical values and retains the post-execute child image',async()=>{
  const ctx=new Context(),f=fixture('/owned/current.png');let reads=0;
  new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
  new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
  try{
    const loop=new AgentLoop(ctx,{agents:[]});
    const image={type:'image',attachment:{attachmentId:'sha256:'+'a'.repeat(64)}};
    ctx.tools.register(defineTool({name:'export',description:'Native dispatch diagnostic, no exporter side effects',parameters:{},
      output:{schema:{type:'json'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},execute:async()=>f.result.value}));
    ctx.tools.register(defineTool({name:'image',description:'Diagnostic image dispatch, no provider',parameters:{file_path:{type:'string',required:true}},
      output:{schema:{type:'json'},render:()=>[image]},execute:async()=>{reads++;return {source:'fixture'};}}));
    for(const [name,slot] of [['export',f.program.ir.anchor],['image',f.program.ir.steps[0]]]){
      slot.schema_sha256=digest(ctx.tools.get(name).parameters);f.host.contracts[name].schema_sha256=slot.schema_sha256;
    }
    f.program.id='ppt_flow_'+digest(f.program.ir).slice(0,24);
    const {digest:old,...body}=f.library;f.library.digest=digest(body);
    registerPptWorkflowContinuation(ctx,()=>f.value,f.host);
    const agent=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
    const result=await ctx.tools.execute({name:'export',arguments:{},callId:'native-'+randomUUID(),agent,signal:new AbortController().signal});
    assert.equal(result.isError,false,JSON.stringify(result));assert.equal(reads,1);
    assert.deepEqual(result.content.find(block=>block.type==='image'),image);
    assert.equal(JSON.parse(result.content[0].text).next_action,'review_returned_images_then_continue');
    assert.deepEqual(result.value,f.result.value,'Canonical export value remains owned by the tool');
  }finally{await ctx.fiber.dispose();}
});
