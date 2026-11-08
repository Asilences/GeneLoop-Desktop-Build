import test,{mock} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {performance} from 'node:perf_hooks';
import {closePrivacyWorkers,runPrivacyWorker} from '../src/adapters/privacy_worker_pool.ts';
import {projectPlatformLearningTrace,privacyLearningView,createLearningPrivacyBoundary,safeLearningError} from '../src/adapters/geneloop_privacy.ts';
import {capturePlatformLearningTrace} from '../src/adapters/harless_learning_trace.ts';
import {mountRsiSharing} from '../src/adapters/harless_rsi_sharing.ts';

const python=process.env.SSS_PYTHON;
const actualTools=!!python&&!!process.env.SSS_RSI_GITLEAKS;
const scenes=JSON.parse(readFileSync(new URL('../config/harless-scenes.json',import.meta.url))).scenes.map(row=>row.id);
test('privacy workers preserve declared CPU and cache settings without forwarding other environment',async()=>{
 const values={OMP_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1',MKL_NUM_THREADS:'1',
  HOME:'/synthetic-private-cache',USERPROFILE:'C:\\synthetic-private-cache',GENELOOP_PRIVACY_ENV_SENTINEL:'must-not-forward'};
 const before=Object.fromEntries(Object.keys(values).map(key=>[key,process.env[key]])),calls=[],frames=[];
 for(const [key,value] of Object.entries(values))process.env[key]=value;
 closePrivacyWorkers();
 const spy=mock.method(childProcess,'spawn',(file,args,options)=>{
  calls.push({file,args,options});
  const child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();
  child.unref=()=>{};child.kill=()=>true;
  child.stdin=new PassThrough();child.stdin.on('data',data=>{
   const request=JSON.parse(data.toString());frames.push(request);
   queueMicrotask(()=>child.stdout.write(JSON.stringify({id:request.id,ok:true,value:{}})+'\n'));
  });
  return child;
 });
 syncBuiltinESMExports();
 try{
  assert.deepEqual(await privacyLearningView({text:'synthetic input'},{python:'diagnostic-python'}),{});
  assert.equal(await projectPlatformLearningTrace('diagnostic-python','input','future-custom-mcp','completed',0,'catalog'),'{}');
  assert.equal(calls.length,1);assert.deepEqual(frames.map(row=>row.operation),['learning','project']);
  for(const {args,options} of calls){
   assert.ok(args.includes('-B'));
   for(const key of ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','HOME','USERPROFILE'])
    assert.equal(options.env[key],values[key]);
   assert.equal('GENELOOP_PRIVACY_ENV_SENTINEL' in options.env,false);
  }
 }finally{
  closePrivacyWorkers();spy.mock.restore();syncBuiltinESMExports();
  for(const [key,value] of Object.entries(before))if(value===undefined)delete process.env[key];else process.env[key]=value;
 }
});

test('privacy pool serializes requests and cancellation cannot return another source reply',async()=>{
 closePrivacyWorkers();const children=[],frames=[];
 const spy=mock.method(childProcess,'spawn',()=>{
  const child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();
  child.unref=()=>{};child.kills=0;child.kill=()=>{child.kills++;return true;};
  child.stdin=new PassThrough();child.stdin.on('data',raw=>frames.push({child,request:JSON.parse(raw.toString())}));
  children.push(child);return child;
 });syncBuiltinESMExports();
 try{
  const first=runPrivacyWorker('diagnostic-python','learning',{text:'first'});
  const queuedAbort=new AbortController();
  const queued=runPrivacyWorker('diagnostic-python','learning',{text:'queued'},queuedAbort.signal);
  const queuedRejected=assert.rejects(queued,/geneloop_privacy_rejected/);queuedAbort.abort();await queuedRejected;
  assert.equal(frames.length,1);assert.equal(children[0].kills,0);
  children[0].stdout.write(JSON.stringify({id:frames[0].request.id,ok:true,value:{text:'first-clean'}})+'\n');
  assert.deepEqual(await first,{text:'first-clean'});
  const currentAbort=new AbortController(),current=runPrivacyWorker('diagnostic-python','learning',{text:'cancel'},currentAbort.signal);
  const currentRejected=assert.rejects(current,/geneloop_privacy_rejected/);currentAbort.abort();await currentRejected;
  assert.equal(children[0].kills,1);
  const next=runPrivacyWorker('diagnostic-python','learning',{text:'next'});
  assert.equal(children.length,2);
  children[1].stdout.write(JSON.stringify({id:frames.at(-1).request.id,ok:true,value:{text:'next-clean'}})+'\n');
  assert.deepEqual(await next,{text:'next-clean'});
 }finally{closePrivacyWorkers();spy.mock.restore();syncBuiltinESMExports();}
});

test('privacy pool enforces the original 120 second total request deadline',async t=>{
 closePrivacyWorkers();t.mock.timers.enable({apis:['setTimeout']});let kills=0;
 const spy=mock.method(childProcess,'spawn',()=>{
  const child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();child.stdin=new PassThrough();
  child.unref=()=>{};child.kill=()=>{kills++;return true;};return child;
 });syncBuiltinESMExports();
 try{
  const pending=runPrivacyWorker('diagnostic-python','learning',{text:'never-completes'});
  const rejected=assert.rejects(pending,/geneloop_privacy_rejected/);
  t.mock.timers.tick(119999);assert.equal(kills,0);
  t.mock.timers.tick(1);await rejected;assert.equal(kills,1);
 }finally{closePrivacyWorkers();spy.mock.restore();syncBuiltinESMExports();t.mock.timers.reset();}
});

test('privacy pool bounds queued material and rejects mismatched response identifiers',async()=>{
 closePrivacyWorkers();let child,frame;
 const spy=mock.method(childProcess,'spawn',()=>{
  child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();child.stdin=new PassThrough();
  child.stdin.on('data',raw=>{frame=JSON.parse(raw.toString());});child.unref=()=>{};child.kill=()=>true;return child;
 });syncBuiltinESMExports();
 try{
  const jobs=[];let immediateRejections=0;
  for(let i=0;i<34;i++)jobs.push(runPrivacyWorker('diagnostic-python','learning',{index:i}).catch(error=>{immediateRejections++;throw error;}));
  const settled=Promise.allSettled(jobs);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(immediateRejections,1);
  child.stdout.write(JSON.stringify({id:frame.id+'bad',ok:true,value:{unapproved:'must-not-return'}})+'\n');
  closePrivacyWorkers();
  assert.ok((await settled).every(row=>row.status==='rejected'&&row.reason.message==='geneloop_privacy_rejected'));
 }finally{closePrivacyWorkers();spy.mock.restore();syncBuiltinESMExports();}
});

test('privacy pool rejects a late reply even before a delayed deadline callback runs',async()=>{
 closePrivacyWorkers();let current,frame,clock=0,kills=0,spawns=0;
 const timer=mock.method(performance,'now',()=>clock);
 const spawn=mock.method(childProcess,'spawn',()=>{
  spawns++;
  current=new EventEmitter();current.stdout=new PassThrough();current.stderr=new PassThrough();current.stdin=new PassThrough();
  current.stdin.on('data',raw=>{frame=JSON.parse(raw.toString());});current.unref=()=>{};current.kill=()=>{kills++;return true;};
  return current;
 });syncBuiltinESMExports();
 try{
  const pending=runPrivacyWorker('diagnostic-python','learning',{text:'synthetic material'});
  const queued=runPrivacyWorker('diagnostic-python','learning',{text:'expired queued material'});
  const rejected=assert.rejects(pending,/geneloop_privacy_rejected/);
  const queuedRejected=assert.rejects(queued,/geneloop_privacy_rejected/);
  // Simulate a stalled parent: elapsed time advances, timer callback has not run.
  clock=120001;
  current.stdout.write(JSON.stringify({id:frame.id,ok:true,value:{text:'late'}})+'\n');
  await Promise.all([rejected,queuedRejected]);assert.equal(kills,1);assert.equal(spawns,1);
 }finally{closePrivacyWorkers();spawn.mock.restore();timer.mock.restore();syncBuiltinESMExports();}
});
for(const scene of [...new Set([...scenes,'chat','coding','future-custom-mcp'])]){
 test('platform privacy Web/offline/share agree: '+scene,{skip:!actualTools,timeout:120000},async()=>{
  const directory=mkdtempSync(join(tmpdir(),'geneloop-privacy-'));
  const previous=process.env.SSS_RSI_PRIVACY_DIAGNOSTIC;
  process.env.SSS_RSI_PRIVACY_DIAGNOSTIC='1';
  const tool='mcp__diagnostic__analyze',input=join(directory,'events.jsonl'),catalog=join(directory,'effective-config.json');
  const events=[{type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'Keep RMSE and 24 fps. Email owner@example.com.'}]}},
   {type:'tool/call',data:{callId:'private-call-owner@example.com',name:tool,arguments:JSON.stringify({email:'owner@example.com',threshold:0.05})}},
   {type:'tool/result',data:{message:{source:{kind:'tool',callId:'private-call-owner@example.com'},content:[
    {type:'tool-result',toolCallId:'private-call-owner@example.com',isError:false,content:[{type:'text',text:JSON.stringify({text:'Keep RMSE',path:'/home/private-owner/data.csv'})}]}]}}}];
  writeFileSync(input,events.map(row=>JSON.stringify(row)).join('\n'));
  writeFileSync(catalog,JSON.stringify({allowed_tools:[tool]}));
  let dispose;
  try{
   await capturePlatformLearningTrace({provider_mode:'mock'},directory,scene,'completed',0);
   assert.equal(existsSync(join(directory,'privacy-learning-rejected')),false);
   const web=JSON.parse(readFileSync(join(directory,'privacy-learning.json')));
   const args=['-m','src.adapters.geneloop_learning_trace','--authorized','--input',input,'--scene',scene,
    '--status','completed','--start','0','--catalog',catalog];
   const offline=JSON.parse(execFileSync(python,args,{encoding:'utf8'}));
   assert.deepEqual(web,offline);
   for(const secret of ['owner@example.com','private-call-owner','/home/private-owner/data.csv'])assert.ok(!JSON.stringify(web).includes(secret));
   assert.ok(JSON.stringify(web).includes('RMSE'));assert.ok(JSON.stringify(web).includes('24 fps'));
   let route;
   const ctx={effect(fn){dispose=fn();},connection:{requestRejection:()=>undefined,
    fetch:{register(value){route=value;return async()=>{};}}}};
   mountRsiSharing(ctx,{output:directory,provider_mode:'mock'},async id=>{
    assert.equal(id,'owned');return {output:directory,scene,status:'completed',start:0};
   });
   const preview=await(await route.fetch(new Request('http://local/api/harless/rsi-sharing',{
    method:'POST',body:JSON.stringify({action:'preview',task_id:'owned'})}))).json();
   assert.ok(preview.payload,JSON.stringify(preview));
   const shared=JSON.parse(execFileSync(python,[...args,'--share-object'],{encoding:'utf8'}));
   assert.deepEqual(JSON.parse(preview.payload),shared);
   assert.equal(shared.trace.format,'geneloop.rsi-learning-trace/v4');assert.equal('content' in shared.trace,false);
   assert.equal(shared.trace.nodes[0].tool,'tool-0');assert.equal(shared.trace.scene,'generic');
   assert.ok(!preview.payload.includes(tool));
  }finally{
   await dispose?.();
   if(previous===undefined)delete process.env.SSS_RSI_PRIVACY_DIAGNOSTIC;else process.env.SSS_RSI_PRIVACY_DIAGNOSTIC=previous;
   rmSync(directory,{recursive:true,force:true});
  }
 });
}

test('privacy workers fail closed without Python; learning handles preserve private lookup scope',async()=>{
 const prior=process.env.SSS_PYTHON;delete process.env.SSS_PYTHON;
 try{
  await assert.rejects(()=>privacyLearningView({text:'no raw fallback'}),/geneloop_privacy_rejected/);
  const error=await safeLearningError(Error('owner@example.com /private/account'));
  assert.equal(error.message,'geneloop_privacy_rejected');assert.equal(error.stack,undefined);
 }
 finally{if(prior!==undefined)process.env.SSS_PYTHON=prior;}
 const boundary=createLearningPrivacyBoundary();
 assert.throws(()=>boundary.resolve({packet_id:'private-unknown'}),/geneloop_privacy_rejected/);
 assert.deepEqual(boundary.resolve({input:{count:3}}),{input:{count:3}});
});

for(const scene of ['paper-proofreading','ppt','coding','future-custom-mcp']){
 test('numeric text and duplicate source JSON use the same Web/offline/share rules: '+scene,
 {skip:!actualTools,timeout:120000},async()=>{
  const directory=mkdtempSync(join(tmpdir(),'privacy-source-')),tool='mcp__diagnostic__analyze';
  const input=join(directory,'events.jsonl'),catalog=join(directory,'effective-config.json');
  const phone='13800138000',events=[
   {type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:phone}]}},
   {type:'tool/call',data:{callId:'synthetic-call',name:tool,arguments:'{"count":3,"threshold":0.05}'}},
  ];
  writeFileSync(input,events.map(row=>JSON.stringify(row)).join('\n'));
  writeFileSync(catalog,JSON.stringify({allowed_tools:[tool]}));
  const args=['-m','src.adapters.geneloop_learning_trace','--authorized','--input',input,'--scene',scene,
   '--status','completed','--start','0','--catalog',catalog];
  try{
   const web=JSON.parse(await projectPlatformLearningTrace(python,input,scene,'completed',0,catalog));
   const offline=JSON.parse(execFileSync(python,args,{encoding:'utf8'}));
   assert.deepEqual(web,offline);
   assert.ok(!JSON.stringify(web).includes(phone));
   assert.deepEqual(web.content.find(row=>row.type==='tool/call').value,{count:3,threshold:0.05});
   events[1].data.arguments='{"password":"diagnostic-only","password":""}';
   const raw=events.map(row=>JSON.stringify(row)).join('\n');writeFileSync(input,raw);
   for(const share of [false,true]){
    await assert.rejects(()=>projectPlatformLearningTrace(python,input,scene,'completed',0,catalog,share),/geneloop_privacy_rejected/);
    assert.throws(()=>execFileSync(python,[...args,...(share?['--share-object']:[])],{encoding:'utf8',stdio:'pipe'}),
     error=>error.status===1&&error.stdout===''&&error.stderr.trim()==='geneloop_privacy_rejected');
   }
   assert.equal(readFileSync(input,'utf8'),raw);
   writeFileSync(catalog,'{"allowed_tools":["private"],"allowed_tools":[]}');
   assert.throws(()=>execFileSync(python,args,{encoding:'utf8',stdio:'pipe'}),error=>error.status===1);
  }finally{rmSync(directory,{recursive:true,force:true});}
 });
}

test('opaque references round trip in declared arrays and model views remain stable',
 {skip:!actualTools,timeout:120000},async()=>{
 const boundary=createLearningPrivacyBoundary();
 const visible=await boundary.show({packet_id:'synthetic-owner@example.com'});
 assert.match(visible.packet_id,/^private-/);
 assert.deepEqual(await boundary.show(visible),visible);
 assert.deepEqual(boundary.resolve({source_packet_ids:[visible.packet_id],binding:{packet_id:visible.packet_id}}),
  {source_packet_ids:['synthetic-owner@example.com'],binding:{packet_id:'synthetic-owner@example.com'}});
 assert.throws(()=>boundary.resolve({source_packet_ids:['private-unknown']}),/geneloop_privacy_rejected/);
});

test('actual privacy child reuses weights with fresh packet aliases and recovers after cancellation',
 {skip:!actualTools,timeout:120000},async()=>{
 closePrivacyWorkers();const children=[],spawn=childProcess.spawn;
 const spy=mock.method(childProcess,'spawn',(...args)=>{
  const child=spawn(...args);children.push(child);return child;
 });syncBuiltinESMExports();
 try{
  for(const address of ['first-packet@example.com','second-packet@example.com']){
   const result=await privacyLearningView({email:address,text:'Compare results using n = 12 and mean ± SD.',count:3,threshold:0.05});
   assert.equal(result.email,'<EMAIL_ADDRESS_1>');
   assert.equal(result.count,3);assert.equal(result.threshold,0.05);
   assert.ok(result.text.includes('n = 12')&&result.text.includes('mean ± SD'));
   assert.ok(!JSON.stringify(result).includes(address));
  }
  assert.equal(children.length,1);
  const controller=new AbortController();
  const interrupted=privacyLearningView({text:'cancel this synthetic packet'},{signal:controller.signal});
  const rejected=assert.rejects(interrupted,/geneloop_privacy_rejected/);
  controller.abort();await rejected;
  assert.equal(children[0].killed,true);
  const recovered=await privacyLearningView({email:'after-cancel@example.com',text:'Retain n = 12.',count:7});
  assert.equal(recovered.email,'<EMAIL_ADDRESS_1>');assert.equal(recovered.count,7);
  assert.equal(children.length,2);assert.notEqual(children[0].pid,children[1].pid);
 }finally{closePrivacyWorkers();spy.mock.restore();syncBuiltinESMExports();}
});
