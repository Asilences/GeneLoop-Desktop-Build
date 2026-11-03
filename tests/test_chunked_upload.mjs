import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createChunkedUpload} from '../src/adapters/geneloop_chunked_upload.ts';
test('chunks preserve bytes, native receipts, ownership, replay and cancellation',async()=>{
 const root=mkdtempSync(join(tmpdir(),'geneloop-chunks-')),saved=[];
 const ctx={connection:{requestRejection:r=>r.headers.get('x-test-auth')==='yes'?undefined:401},
  fileUploads:{async uploadStream({sessionId,name,data}){const b=[];for await(const c of data)b.push(c);saved.push({sessionId,name,data:Buffer.concat(b)});return {receiptId:'native-receipt'};}}};
 const service=createChunkedUpload(ctx,root,async id=>{if(!['owned','other'].includes(id))throw Error('not owned');});
 const call=async(action,body={},extra={},auth=true)=>service.fetch(new Request('http://local/api/harless/uploads?'+new URLSearchParams({action,session:'owned',...extra}),
  {method:'POST',headers:{'x-test-auth':auth?'yes':'no'},body:Buffer.isBuffer(body)?body:JSON.stringify(body)}));
 try{
  assert.equal((await call('begin',{name:'large.pptx',bytes:4},{},false)).status,401);
  assert.equal((await call('begin',{name:'../bad',bytes:4})).status,400);
  assert.equal((await call('begin',{name:'big',bytes:200*1024*1024+1})).status,413);
  const {id}=await(await call('begin',{name:'large.pptx',bytes:4})).json();
  assert.equal((await call('chunk',Buffer.from('ab'),{id,session:'other',offset:'0'})).status,404);
  assert.equal((await call('complete',{}, {id})).status,409);
  assert.equal((await call('chunk',Buffer.from('ab'),{id,offset:'1'})).status,409);
  assert.equal((await call('chunk',Buffer.from('ab'),{id,offset:'0'})).status,200);
  assert.equal((await call('chunk',Buffer.from('ab'),{id,offset:'0'})).status,200);
  assert.equal((await call('chunk',Buffer.from('xy'),{id,offset:'0'})).status,409);
  assert.equal((await call('chunk',Buffer.from('cde'),{id,offset:'2'})).status,409);
  assert.equal((await call('chunk',Buffer.from('cd'),{id,offset:'2'})).status,200);
  for(let i=0;i<2;i++)assert.deepEqual(await(await call('complete',{}, {id})).json(),{ok:true,value:{receiptId:'native-receipt'}});
  assert.equal(saved.length,1);assert.equal(saved[0].data.toString(),'abcd');
  const second=await(await call('begin',{name:'cancel.txt',bytes:1})).json();
  assert.equal((await call('abort',{}, {id:second.id})).status,200);
  assert.equal((await call('complete',{}, {id:second.id})).status,404);
 }finally{service.dispose();rmSync(root,{recursive:true,force:true});}
});
