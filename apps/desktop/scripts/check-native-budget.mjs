// Exercise the official DSH process owner, including real child cancellation.
// Synthetic commands only; no model requests or memory reduction claims.
import assert from 'node:assert/strict';
import {mkdtempSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const runtime=resolve(process.env.GENELOOP_NATIVE_RUNTIME||'runtime-bundle');
const req=createRequire(pathToFileURL(join(runtime,'local-worker.mjs')));
const {Context}=await import(pathToFileURL(req.resolve('@deepseek-ai/cordis')).href);
const {LocalSubprocessRuntime}=await import(pathToFileURL(req.resolve('@deepseek-ai/dsh-subprocess-local')).href);
const {runNativeProcess}=await import(pathToFileURL(join(runtime,'native-process.mjs')).href);
const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-process-budget-'))),ctx=new Context();
new LocalSubprocessRuntime(ctx);
const service=ctx.get('subprocess'),spawn=service.spawn;let starts=0,active=0,peak=0;
service.spawn=function(spec){const child=spawn.call(this,spec);starts++;active++;peak=Math.max(peak,active);
  child.done.then(()=>active--,()=>active--);return child;};
const command=milliseconds=>[process.execPath,'-e',`setTimeout(()=>process.stdout.write('native result'),${milliseconds})`];
try {
  const signal=new AbortController().signal;
  const first=runNativeProcess(ctx,command(250),root,signal),second=runNativeProcess(ctx,command(250),root,signal);
  const canceled=new AbortController(),queued=runNativeProcess(ctx,command(1),root,canceled.signal);
  const rejection=assert.rejects(queued,/queued canceled/);canceled.abort(Error('queued canceled'));
  const expired=assert.rejects(runNativeProcess(ctx,command(1),root,signal,{timeoutMs:20}),/timeout|aborted/i);
  await rejection;await expired;await first;await second;
  assert.equal(starts,2);assert.equal(peak,2);
  await Promise.all(Array.from({length:4},()=>runNativeProcess(ctx,command(100),root,signal)));
  assert.equal(starts,6);assert.equal(active,0);assert.equal(peak,2);
  const stopping=new AbortController(),running=runNativeProcess(ctx,command(30000),root,stopping.signal);
  const stopped=assert.rejects(running,/running canceled/);
  await new Promise(r=>setTimeout(r,150));stopping.abort(Error('running canceled'));await stopped;
  assert.equal(active,0);
  console.log(JSON.stringify({platform:process.platform,architecture:process.arch,kind:'native_process_resource_diagnostic',
    actual_child_processes:starts,peak_heavy_processes:peak,queued_cancel_did_not_start:true,queued_timeout_did_not_start:true,
    running_cancel_reaped:true,model_requests:0}));
} finally {service.spawn=spawn;await ctx.fiber.dispose();}
