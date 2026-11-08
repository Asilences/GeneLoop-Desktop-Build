import test from 'node:test';
import assert from 'node:assert/strict';
import {executePptOperations,admitPptComponent} from '../src/adapters/ppt_execution.ts';

test('sequential host execution preserves parent authorization and stops at a failed child',async()=>{
  const calls=[],controller=new AbortController(),parent={owner:'original'};
  const execution={callId:'root',token:parent,agent:{session:{id:'owned'}},signal:controller.signal};
  const result=await executePptOperations([{id:'first',tool:'one',arguments:{text:'current'}},
    {id:'second',tool:'two',arguments:{}},{id:'third',tool:'three',arguments:{}}],execution,
    {check(){},audit(){},dispatch:async call=>{calls.push(call);return {isError:call.name==='two',content:[]};}});
  assert.equal(result.status,'failed');assert.equal(result.failed_operation,'second');assert.equal(calls.length,2);
  assert.equal(calls[0].parent,parent);assert.equal(calls[0].signal,controller.signal);assert.equal(calls[0].rootCallId,'root');
});

test('cancellation between child calls prevents later work',async()=>{
  const controller=new AbortController();let calls=0;
  await assert.rejects(()=>executePptOperations([{id:'a',tool:'one',arguments:{}},{id:'b',tool:'two',arguments:{}}],
    {callId:'root',signal:controller.signal},{check(){},audit(){},dispatch:async()=>{calls++;controller.abort();return {isError:false};}}));
  assert.equal(calls,1);
});

test('component admission enforces certification and capacity before running a tool',()=>{
  const program={id:'page',source_sha256:'version',component:{parameters_schema:{type:'object',
    properties:{title:{type:'string',maxLength:8}},required:['title'],additionalProperties:false}},
    certification:{passed:true,component_source_equivalence:{passed:true}}};
  const input={title:'当前内容'},admitted=admitPptComponent(program,input);input.title='changed';
  assert.equal(admitted.parameters.title,'当前内容');
  assert.throws(()=>admitPptComponent(program,{title:'this title is far too long'}),/component_parameters_invalid/);
  assert.throws(()=>admitPptComponent({...program,certification:{passed:false}},input),/independent_certification/);
});
