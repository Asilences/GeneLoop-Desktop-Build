import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../src/adapters/harless_web_client/client.js',import.meta.url),'utf8');
const code=source.slice(source.indexOf('    function installLargeFileUpload(ctx)'),source.indexOf('    function apply(ctx)'));
function setup(fetch){
 const effects=[],native=[];
 const original=async(...args)=>{native.push(args);return {ok:true,value:{receiptId:'native'}};};
 const ctx={fileUpload:{upload:original},effect(fn){effects.push(fn());}};
 vm.runInNewContext(code+';installLargeFileUpload(ctx)',{ctx,Blob,Uint8Array,URLSearchParams,AbortController,fetch});
 return {ctx,native,original,effects};
}
test('large browser files use bounded chunks and retain native receipt contract',async()=>{
 const calls=[],progress=[],receipt={ok:true,value:{receiptId:'large-native'}};
 const state=setup(async(url,init)=>{
  const query=new URL('http://localhost'+url).searchParams,action=query.get('action');
  calls.push({action,bytes:init.body instanceof Blob?init.body.size:0,offset:query.get('offset')});
  assert.equal(init.credentials,'same-origin');
  return Response.json(action==='begin'?{id:'opaque',chunk_bytes:8*1024*1024}:action==='complete'?receipt:{offset:0});
 });
 assert.deepEqual(await state.ctx.fileUpload.upload('s',new Blob(['small']),'s.txt'),{ok:true,value:{receiptId:'native'}});
 assert.equal(state.native.length,1);assert.equal(calls.length,0);
 const result=await state.ctx.fileUpload.upload('s',new Blob([new Uint8Array(21*1024*1024)]),'deck.pptx',undefined,p=>progress.push(p.loaded));
 assert.deepEqual(result,receipt);
 assert.deepEqual(calls.map(c=>c.action),['begin','chunk','chunk','chunk','complete']);
 assert.deepEqual(calls.filter(c=>c.action==='chunk').map(c=>c.bytes),[8,8,5].map(n=>n*1024*1024));
 assert.equal(progress.at(-1),21*1024*1024);
 state.effects.forEach(fn=>fn());assert.equal(state.ctx.fileUpload.upload,state.original);
});
test('failed large upload aborts its own staging handle',async()=>{
 const calls=[];
 const state=setup(async(url)=>{
  const action=new URL('http://localhost'+url).searchParams.get('action');calls.push(action);
  return Response.json(action==='begin'?{id:'opaque',chunk_bytes:8*1024*1024}:action==='chunk'?{error:{message:'chunk failed'}}:{cancelled:true},{status:action==='chunk'?400:200});
 });
 await assert.rejects(state.ctx.fileUpload.upload('s',new Blob([new Uint8Array(17*1024*1024)]),'deck.pptx'),/chunk failed/);
 assert.deepEqual(calls,['begin','chunk','abort']);
});
