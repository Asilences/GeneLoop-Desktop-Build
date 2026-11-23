import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime,defineTool} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {scopeOf} from '@deepseek-ai/dsh-scope';
import {formatFetchOutput} from '@deepseek-ai/dsh-tool-web';
import {bindPptWebFetch,isolatedPptFetch,pptFetchEnvironment} from '../src/adapters/ppt/sources/ppt_web_fetch.ts';
import {normalizePptFetchedValue} from '../src/adapters/ppt/sources/ppt_web_fetch_worker.mjs';

function script(body){
 const root=mkdtempSync(join(tmpdir(),'ppt fetch space ')),path=join(root,'worker.mjs');writeFileSync(path,body);return path;
}
const value={url:'https://example.com/',statusCode:200,body:{kind:'text',content:'Current source'},truncated:false};

test('PPT worker excludes model and control credentials from the child environment',()=>{
 const env=pptFetchEnvironment({PATH:process.env.PATH,HOME:'home',KOURI_API_KEY:'private',DEEPSEEK_API_KEY:'private',SSS_WEB_POLICY:'private',AWS_SECRET_ACCESS_KEY:'private'});
 assert.equal(env.HOME,'home');assert.equal(env.KOURI_API_KEY,undefined);assert.equal(env.DEEPSEEK_API_KEY,undefined);
 assert.equal(env.SSS_WEB_POLICY,undefined);assert.equal(env.AWS_SECRET_ACCESS_KEY,undefined);assert.equal(env.ELECTRON_RUN_AS_NODE,'1');
});

test('HTML conversion in the child preserves the original model-facing text and truncation',()=>{
 for(const html of ['<h1>Scientific result</h1><p>A &amp; B.</p>',
  '<table><tr><th>Method</th><th>Score</th></tr><tr><td>A</td><td>0.92</td></tr></table>',
  '<p>'+('content '.repeat(50000))+'</p>']){
  for(const cap of [200000]){
   const original={...value,body:{kind:'html',content:html}};
   const next=normalizePptFetchedValue(original);
   assert.equal(next.body.kind,'text');assert.equal(formatFetchOutput(next,cap),formatFetchOutput(original,cap));
  }
 }
});

test('a child exit becomes one tool failure and leaves the parent alive',async()=>{
 const workerPath=script('process.exit(139)');
 await assert.rejects(isolatedPptFetch(value.url,undefined,{workerPath}),/WEB_WORKER_FAILED/);
 const ok=script(`process.stdin.resume();process.stdin.on('end',()=>process.stdout.write(${JSON.stringify(JSON.stringify({ok:true,value}))}));`);
 assert.deepEqual(await isolatedPptFetch(value.url,undefined,{workerPath:ok}),value);
});

test('cancellation and a hung retrieval terminate only the short-lived worker',async()=>{
 const workerPath=script('setInterval(()=>{},1000)');
 await assert.rejects(isolatedPptFetch(value.url,undefined,{workerPath,timeoutMs:50}),/WEB_FETCH_TIMEOUT/);
 const controller=new AbortController();const promise=isolatedPptFetch(value.url,controller.signal,{workerPath});
 controller.abort();await assert.rejects(promise,/WEB_ABORTED/);
});

test('raw HTML and oversized results are not reintroduced into the host renderer',async()=>{
 const html={...value,body:{kind:'html',content:'<p>not normalized</p>'}};
 const invalid=script(`console.log(${JSON.stringify(JSON.stringify({ok:true,value:html}))});`);
 await assert.rejects(isolatedPptFetch(value.url,undefined,{workerPath:invalid}),/WEB_WORKER_INVALID_RESPONSE/);
 const huge=script("process.stdout.write('x'.repeat(3*1024*1024));");
 await assert.rejects(isolatedPptFetch(value.url,undefined,{workerPath:huge}),/WEB_RESPONSE_TOO_LARGE/);
});

test('the real provider still rejects loopback URLs without a model or network request',async()=>{
 await assert.rejects(isolatedPptFetch('http://127.0.0.1/private'),/WEB_BLOCKED_URL/);
});

test('scoped replacement preserves schemas and leaves another agent on the original tool',async()=>{
 const ctx=new Context();new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
 new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
 try{
  const loop=new AgentLoop(ctx,{agents:[]});let originalCalls=0,isolatedCalls=0;
  ctx.tools.register(defineTool({name:'web_fetch',description:'Fetch public page',parameters:{url:{type:'string',required:true}},
   output:{schema:{type:'json'},render:(_args,v)=>[{type:'text',text:JSON.stringify(v)}]},
   execute:async()=>{originalCalls++;return value;}}));
  const ppt=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
  const other=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
  const before=ctx.tools.schemas(scopeOf(ppt.ctx));
  const dispose=bindPptWebFetch(ppt,async()=>{isolatedCalls++;return value;});
  assert.deepEqual(ctx.tools.schemas(scopeOf(ppt.ctx)),before);
  for(const agent of [ppt,other]){
   const result=await ctx.tools.execute({name:'web_fetch',arguments:{url:value.url},callId:randomUUID(),agent,signal:new AbortController().signal});
   assert.equal(result.isError,false,JSON.stringify(result));
  }
  assert.equal(isolatedCalls,1);assert.equal(originalCalls,1);
  dispose();assert.deepEqual(ctx.tools.schemas(scopeOf(ppt.ctx)),before);
 }finally{await ctx.fiber.dispose();}
});
