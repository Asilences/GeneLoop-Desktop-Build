import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {projectPlatformLearningTrace,privacyLearningView,createLearningPrivacyBoundary,safeLearningError} from '../src/adapters/geneloop_privacy.ts';
import {capturePlatformLearningTrace} from '../src/adapters/harless_learning_trace.ts';
import {mountRsiSharing} from '../src/adapters/harless_rsi_sharing.ts';

const python=process.env.SSS_PYTHON;
const actualTools=!!python&&!!process.env.SSS_RSI_GITLEAKS;
const scenes=JSON.parse(readFileSync(new URL('../config/harless-scenes.json',import.meta.url))).scenes.map(row=>row.id);
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
