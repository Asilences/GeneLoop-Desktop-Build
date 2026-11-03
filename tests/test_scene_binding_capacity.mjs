import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {bindUploadedSourceTask,bindUploadedPptTask,bindApprovedUploadedReadTask} from '../src/adapters/harless_rsi_binding.ts';
test('all scene source binders admit 36 approved files while still rejecting changed bytes',()=>{
 const root=realpathSync(mkdtempSync(join(tmpdir(),'scene-binding-capacity-')));mkdirSync(join(root,'inputs'));
 try{
  const inputs=Array.from({length:36},(_,i)=>{const file=`note-${i}.txt`,data=`value ${i}`;writeFileSync(join(root,'inputs',file),data);return {document_id:`doc_${i+1}`,file,version_sha256:createHash('sha256').update(data).digest('hex')};});
  writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files:Object.fromEntries(inputs.map(r=>[r.file,r.version_sha256]))}));
  writeFileSync(join(root,'job.json'),JSON.stringify({job_id:'task',instruction:'read',inputs:inputs.map(r=>({...r,path:join(root,'inputs',r.file)}))}));
  const request={task_id:'task',session_id:'session',content:[{type:'text',text:'read'}]};
  const calls=[()=>bindUploadedSourceTask(root,inputs,request,{contracts:{pin:{observed_anchor:true}},version_fields:{pin:'version_sha256'}}),
   ()=>bindUploadedPptTask(root,inputs,request,{version_fields:{mcp__ppt__pin_source:'version_sha256',mcp__ppt__read_source:'version_sha256'}})];
  for(const [scene,pin,read] of [['paper-proofreading','mcp__paper_checks__pin_paper_sources','mcp__paper_checks__read_pinned_paper_sources'],['research-data-analysis','mcp__data_analysis__pin_dataset','mcp__data_analysis__read_pinned_dataset_summary']]){
   const manifest={version_fields:{[pin]:'version_sha256',[read]:'version_sha256'},artifacts:[{tools:[pin,read],transfer_evidence:[{from_tool:pin,to_tool:read,from_field:'source_id',to_param:'source_id'}]}]};
   calls.push(()=>bindApprovedUploadedReadTask(root,inputs,request,manifest,scene));
  }
  for(const bind of calls)assert.equal(bind().task_id,'task');
  writeFileSync(join(root,'inputs',inputs[35].file),'changed after approval');
  for(const bind of calls)assert.throws(bind,/source_version_mismatch/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
