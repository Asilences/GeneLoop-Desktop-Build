import assert from 'node:assert/strict';
import {test} from 'node:test';
import {acquireNativeOperation} from '../apps/desktop/runtime/native-resource-budget.mjs';
import {runNativeProcess} from '../apps/desktop/runtime/native-process.mjs';

test('two heavy commands run; queued cancellation never reaches subprocess spawn',async()=>{
  let starts=0,active=0,peak=0;const finish=[];
  const subprocess={spawn(){starts++;active++;peak=Math.max(peak,active);
    return {done:new Promise(resolve=>finish.push(()=>{active--;resolve({exitCode:0});})),
      collected:{stdout:{readFrom:()=>({text:'actual result'})},stderr:{readFrom:()=>({text:''})}}};}};
  const ctx={subprocess,get:()=>subprocess},a=new AbortController();ctx.root=ctx;
  const childScope={subprocess,root:ctx};
  const first=runNativeProcess(ctx,['diagnostic'],'scratch',a.signal),second=runNativeProcess(childScope,['diagnostic'],'scratch',a.signal);
  const cancel=new AbortController(),queued=runNativeProcess(ctx,['must-not-start'],'scratch',cancel.signal);
  const rejected=assert.rejects(queued,/canceled/);cancel.abort(Error('canceled'));
  await rejected;assert.equal(starts,2);assert.equal(peak,2);
  finish.shift()();finish.shift()();assert.equal((await first).stdout,'actual result');await second;
  const release=await acquireNativeOperation(ctx,a.signal);release();release();
});

test('failed spawn releases its slot and separate DSH owners do not block each other',async()=>{
  const aborted=new AbortController();aborted.abort(Error('already canceled'));
  assert.throws(()=>acquireNativeOperation({subprocess:{}},aborted.signal),/already canceled/);
  const signal=new AbortController().signal,ctx={subprocess:{spawn(){throw Error('launch failed');}}};
  await assert.rejects(runNativeProcess(ctx,[],'scratch',signal),/launch failed/);
  const one=await acquireNativeOperation(ctx,signal),two=await acquireNativeOperation(ctx,signal);
  const other=await acquireNativeOperation({subprocess:{}},signal);other();one();two();
});
