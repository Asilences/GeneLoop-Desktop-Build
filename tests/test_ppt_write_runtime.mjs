import test from 'node:test';
import assert from 'node:assert/strict';
import {executePptWriteProgram,pptWriteArguments} from '../src/adapters/ppt_write_runtime.ts';

const program={id:'learned',ir:{mode:'new',writer:{tool:'write_page',resource_argument:'project',identity_argument:'page',
 revision_argument:'expected_page_sha256',version_output:['sha256'],argument_names:['project','page','content']},
 delivery:{tool:'export',resource_argument:'project',argument_names:['project'],success:['status'],success_value:'passed',
 empty_findings:['findings'],collection:['images']}}};
function fixture(){
 const versions=new Map(),saved=new Map(),calls=[],events=[],controller=new AbortController();let fail;
 const host={check(){controller.signal.throwIfAborted();},audit:row=>events.push(row),admit:async()=>{},
  load:key=>saved.has(key)?structuredClone(saved.get(key)):null,save:(key,row)=>saved.set(key,structuredClone(row)),
  version:async operation=>versions.get(operation.arguments.page)??null,
  dispatch:async call=>{
   calls.push(call);
   if(call.name==='write_page'){
    if(call.arguments.page===fail)return {isError:true,content:[{type:'text',text:'specific capacity defect'}]};
    versions.set(call.arguments.page,'a'.repeat(64));return {isError:false,value:{sha256:'a'.repeat(64)},content:[]};
   }
   return {isError:false,value:{status:'passed',findings:[],images:[]},content:[]};
  }};
 return {versions,saved,calls,host,controller,events,fail:page=>fail=page,execution:{callId:'root',signal:controller.signal},
  input:{project:'owned',pages:[{page:'one.svg',content:{text:'new paper'}},{page:'two.svg',content:{text:'another fact'}}]}};
}

test('a learned loop writes all supplied pages and delivers without model dispatch',async()=>{
 const f=fixture();const result=await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.equal(result.status,'completed');assert.deepEqual(f.calls.map(c=>c.name),['write_page','write_page','export']);
 assert.equal(f.calls[1].arguments.content.text,'another fact');
 await executePptWriteProgram(program,f.input,f.execution,f.host);assert.equal(f.calls.length,3);
});

test('partial failure retains successful pages and explicit resume never repeats them',async()=>{
 const f=fixture();f.fail('two.svg');let result=await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.equal(result.status,'failed');assert.equal(result.completed.length,1);assert.ok(result.error_details[0].text.includes('capacity'));
 await assert.rejects(()=>executePptWriteProgram(program,f.input,f.execution,f.host),/explicit_resume/);
 f.fail(undefined);result=await executePptWriteProgram(program,{...f.input,resume:true},f.execution,f.host);
 assert.equal(result.status,'completed');assert.equal(f.calls.filter(c=>c.arguments.page==='one.svg').length,1);
});

test('changed completed pages, reused ids, extra tools and missing revision hashes are rejected',async()=>{
 const f=fixture();await executePptWriteProgram(program,f.input,f.execution,f.host);f.versions.set('one.svg','changed');
 await assert.rejects(()=>executePptWriteProgram(program,f.input,f.execution,f.host),/completed_page_changed/);
 assert.throws(()=>pptWriteArguments(program,{...f.input,pages:[f.input.pages[0],f.input.pages[0]]}),/identity_invalid/);
 assert.throws(()=>pptWriteArguments(program,{...f.input,pages:[{...f.input.pages[0],tool:'arbitrary_shell'}]}),/item_invalid/);
 const revision=structuredClone(program);revision.ir.mode='revision';revision.ir.writer.argument_names.push('expected_page_sha256');
 assert.throws(()=>pptWriteArguments(revision,f.input),/fields_required/);
});

test('cancellation between writes records partial progress and performs no delivery',async()=>{
 const f=fixture(),dispatch=f.host.dispatch;
 f.host.dispatch=async call=>{const result=await dispatch(call);f.controller.abort();return result;};
 await assert.rejects(()=>executePptWriteProgram(program,f.input,f.execution,f.host));assert.equal(f.calls.length,1);
 assert.equal([...f.saved.values()][0].status,'cancelled');
});

test('host-proven export annotation changes update checkpoints without repeating page writes',async()=>{
 const f=fixture(),dispatch=f.host.dispatch;
 f.host.dispatch=async call=>{const result=await dispatch(call);if(call.name==='export')f.versions.set('one.svg','b'.repeat(64));return result;};
 f.host.reconcile=async(_ops,saved)=>saved.map(row=>({...row,version:row.index===0?'b'.repeat(64):row.version}));
 const result=await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.equal(result.completed[0].version,'b'.repeat(64));
 await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.equal(f.calls.filter(row=>row.name==='write_page').length,2);
});

test('concurrent programs cannot write the same project while awaiting admission',async()=>{
 const f=fixture();let release;f.host.admit=()=>new Promise(resolve=>release=resolve);
 const first=executePptWriteProgram(program,f.input,f.execution,f.host);
 await assert.rejects(()=>executePptWriteProgram(program,f.input,f.execution,f.host),/execution_running/);
 release();assert.equal((await first).status,'completed');
});

test('mechanical delivery failure returns its exact findings and keeps completed page checkpoints',async()=>{
 const f=fixture(),dispatch=f.host.dispatch;
 f.host.dispatch=call=>call.name==='export'?Promise.resolve({isError:false,value:{status:'failed',findings:[{page:2,rule:'overflow'}]}}):dispatch(call);
 const result=await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.equal(result.status,'failed');assert.equal(result.completed.length,2);assert.equal(result.error_details.findings[0].rule,'overflow');
});

test('images already supplied by an inherited delivery continuation are reused without rereading',async()=>{
 const f=fixture(),dispatch=f.host.dispatch;
 const image={type:'image',attachment:{attachmentId:'sha256:'+'c'.repeat(64)}};
 f.host.dispatch=call=>call.name==='export'?Promise.resolve({isError:false,value:{status:'passed',findings:[],images:[{sha256:'c'.repeat(64)}]},content:[image]}):dispatch(call);
 const result=await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.equal(result.preview_complete,true);assert.deepEqual(result.images,[image]);
 assert.equal(f.calls.filter(call=>call.name==='write_page').length,2);
});

test('native input adaptation binds current file values before the execution journal key',async()=>{
 const f=fixture();let text='first';
 f.host.prepareInput=(_program,input)=>({...input,pages:input.pages.map(page=>({...page,content:{text}}))});
 const first=await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.equal(f.calls[0].arguments.content.text,'first');
 text='changed';const second=await executePptWriteProgram(program,f.input,f.execution,f.host);
 assert.notEqual(first.key,second.key);assert.equal(f.calls[3].arguments.content.text,'changed');
});

test('review-only findings require current images and never hide blocking findings',async()=>{
 const p=structuredClone(program);p.ir.delivery.allowed_finding_severities=['review'];
 const image={type:'image',attachment:{attachmentId:'sha256:'+'c'.repeat(64)}};
 for(const severity of ['review','error',undefined]){
  const f=fixture(),dispatch=f.host.dispatch;
  f.host.dispatch=call=>call.name==='export'?Promise.resolve({isError:false,value:{status:'passed',
   findings:[{rule:'check_text',severity}],images:[{sha256:'c'.repeat(64)}]},content:[image]}):dispatch(call);
  const result=await executePptWriteProgram(p,f.input,f.execution,f.host);
  assert.equal(result.status,severity==='review'?'completed':'failed');
  if(severity==='review')assert.equal(result.delivery.findings[0].rule,'check_text');
 }
 const f=fixture(),dispatch=f.host.dispatch;
 f.host.dispatch=call=>call.name==='export'?Promise.resolve({isError:false,value:{status:'passed',findings:[{severity:'review'}],images:[]},content:[]}):dispatch(call);
 assert.equal((await executePptWriteProgram(p,f.input,f.execution,f.host)).failure,'ppt_write_advisory_review_images_required');
});


test('learned PNG collection binding reads all pages and leaves other deliverables alone',async()=>{
 const p=structuredClone(program);p.ir.preview={tool:'read_image',bindings:{file_path:'path'},collection:['artifacts'],path_suffix:'.png'};
 const f=fixture(),dispatch=f.host.dispatch;
 const files=[{path:'deck.pptx',sha256:'e'.repeat(64)},{path:'one.png',sha256:'c'.repeat(64)},{path:'two.png',sha256:'d'.repeat(64)}];
 f.host.dispatch=async call=>{
  if(call.name==='export'){f.calls.push(call);return {isError:false,value:{status:'passed',findings:[],images:[],artifacts:files},content:[]};}
  if(call.name==='read_image'){f.calls.push(call);const file=files.find(row=>row.path===call.arguments.file_path);return {isError:false,value:{},content:[{type:'image',attachment:{attachmentId:'sha256:'+file.sha256}}]};}
  return dispatch(call);
 };
 const result=await executePptWriteProgram(p,f.input,f.execution,f.host);
 assert.equal(result.status,'completed');assert.equal(result.preview_complete,true);assert.equal(result.images.length,2);
 assert.deepEqual(f.calls.filter(c=>c.name==='read_image').map(c=>c.arguments.file_path),['one.png','two.png']);
});
