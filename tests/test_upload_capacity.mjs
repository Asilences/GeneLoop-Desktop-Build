import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,rmSync,readFileSync,readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {bindSceneInputs} from '../src/adapters/harless_task_scope.ts';
import {FILE_MAX_BYTES} from '../src/adapters/geneloop_upload_limits.ts';

test('large PPT sources bind byte-exactly and failed admission leaves originals intact',async()=>{
 const root=mkdtempSync(join(tmpdir(),'geneloop-large-input-'));mkdirSync(join(root,'inputs'));
 const bytes=Buffer.alloc(24*1024*1024,23),refs=new Map([['large',{name:'large.pptx',bytes:bytes.length}],['oversize',{name:'bad.pptx',bytes:FILE_MAX_BYTES+1}]]);
 const ctx={fileUploads:{resolve:(_agent,id)=>refs.get(id)},attachments:{async *readFileStream(){for(let n=0;n<bytes.length;n+=65536)yield bytes.subarray(n,n+65536);}}};
 const scene={id:'ppt',adapter:'ppt'};
 try{
  const rows=await bindSceneInputs(ctx,{},root,scene,[{type:'file',receiptId:'large'}],{},'Read title','test');
  assert.deepEqual(readFileSync(join(root,'inputs',rows[0].file)),bytes);
  await assert.rejects(()=>bindSceneInputs(ctx,{},root,scene,[{type:'file',receiptId:'oversize'}],{},'Read title','test2'),/scene_input_limit/);
  assert.deepEqual(readFileSync(join(root,'inputs',rows[0].file)),bytes);
  assert.equal(readdirSync(root).some(name=>name.startsWith('.input-stage-')),false);
 }finally{rmSync(root,{recursive:true,force:true});}
});
