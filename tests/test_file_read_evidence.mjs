import test from 'node:test';
import assert from 'node:assert/strict';
import {fileReadEvidence,withFileReadEvidence} from '../src/adapters/file_read_evidence.ts';
import {prepareLearnedAction,prepareLearnedDecision,bindLearnedDecision} from '../src/adapters/learned_decision_program.ts';
const prefix='mcp__file_management__';
const file={file_id:'fresh',path:'reference.txt',sha256:'a'.repeat(64)};
const row={...file,source_id:'source-fresh',status:'readable',truncated:false,text:'Current rules'};
const context=()=>({goal:'current goal',receipts:{[prefix+'list_files']:{files:[file]}}});
test('single and batch reads produce the same current evidence without editing raw receipts',()=>{
 const a=context(),b=context();a.receipts[prefix+'read_file']=row;b.receipts[prefix+'read_files']={reads:[row]};
 const before=JSON.stringify(a),x=fileReadEvidence(a),y=fileReadEvidence(b);
 assert.equal(x.files[0].complete,true);assert.equal(y.files[0].complete,true);
 assert.equal(x.reads[0].text,y.reads[0].text);assert.equal(x.reads[0].receipt_sha256,y.reads[0].receipt_sha256);
 assert.equal(JSON.stringify(a),before);assert.equal(a.read_evidence,undefined);
});
test('stale versions, metadata previews and partial text never become complete readings',()=>{
 for(const change of [{sha256:'b'.repeat(64)},{truncated:true},{metadata:{preview_only:true}}]){
  const c=context();c.receipts[prefix+'read_file']={...row,...change};
  assert.equal(fileReadEvidence(c).files[0].complete,false);
 }
});
test('history-only single reads are found, duplicates coalesce and foreign coverage is ignored',()=>{
 const c=context();c.history=[{tool:prefix+'read_file',out:row}];c.receipts[prefix+'read_file']=row;
 assert.equal(fileReadEvidence(c).reads.length,1);
 c.history=[];c.receipts[prefix+'read_file']={...row,truncated:true};
 c.receipts[prefix+'document_coverage']={source_id:'other',source_sha256:file.sha256,complete:true};
 assert.equal(fileReadEvidence(c).files[0].complete,false);
 c.receipts[prefix+'document_coverage'].source_id=row.source_id;
 assert.equal(fileReadEvidence(c).files[0].complete,true);
 c.read_evidence={files:[{complete:true}]};c.receipts[prefix+'document_coverage'].source_sha256='b'.repeat(64);
 assert.equal(withFileReadEvidence(c).read_evidence.files[0].complete,false);
});
test('a model-authored direct program prepares and binds without a question or model call',()=>{
 const c=context();c.receipts[prefix+'read_file']=row;
 const candidate={format:'geneloop-learned-decision-v1',description:'diagnostic direct program',scope_description:'toy facts only',
  guard:['eq',['get',['at',['get',['get',['var','input'],['lit','read_evidence']],['lit','files']],['lit',0]],['lit','complete']],['lit',true]],
  request:['object',{mode:['lit','direct']}],
  bind:['object',{tool:['lit','demo'],arguments:['object',{text:['get',['at',['get',['get',['var','input'],['lit','read_evidence']],['lit','reads']],['lit',0]],['lit','text']]}]}],
  training_witnesses:[{snapshot_id:'toy',values:{}}]};
 assert.equal(prepareLearnedAction(candidate,c).kind,'direct');
 assert.deepEqual(bindLearnedDecision(candidate,c,{}).arguments,{text:'Current rules'});
 assert.throws(()=>prepareLearnedDecision(candidate,c),/direct program/);
 assert.equal(prepareLearnedAction(candidate,context()),null);
});
function paged(){
 const c=context();const sid='current-document';
 c.history=[{tool:prefix+'pin_file',out:{file_id:file.file_id,source_id:sid}},
  {tool:prefix+'open_document',out:{document_id:'doc',source_id:sid,source_sha256:file.sha256,mode:'ocr',page_count:2,request_id:'c1'}},
  ...[{request_id:'c1',page:1,offset:0,end_offset:2,page_characters:3,text:'资料',page_complete:false,next_request_id:'c2'},
   {request_id:'c2',page:1,offset:2,end_offset:3,page_characters:3,text:'😀',page_complete:true,next_request_id:'c3'},
   {request_id:'c3',page:2,offset:0,end_offset:0,page_characters:0,text:'',page_complete:true,next_request_id:null}]
   .map(x=>({tool:prefix+'read_document_chunk',out:{document_id:'doc',source_id:sid,source_sha256:file.sha256,mode:'ocr',...x}}))];
 return c;
}
test('actual complete chunk chains establish factual coverage without an extra coverage tool call',()=>{
 const c=paged(),before=JSON.stringify(c),e=fileReadEvidence(c);
 assert.equal(e.files[0].complete,true);assert.equal(e.files[0].coverage[0].derived_from,'actual_open_and_chunk_chain');
 assert.equal(e.files[0].coverage[0].chunk_receipt_sha256.length,3);
 assert.equal(JSON.stringify(c),before);assert.equal(e.reads.length,0);
});
test('a final page, stale version, changed continuation or missing interval does not establish full coverage',()=>{
 const changes=[c=>c.history.splice(2,1),c=>c.history[3].out.offset=1,
  c=>c.history[4].out.source_sha256='b'.repeat(64),c=>c.history[2].out.next_request_id='missing',
  c=>c.history[4].out.page=3,c=>c.history[3].out.text='truncated',
  c=>c.history.push({...c.history[2],out:{...c.history[2].out,text:'XX'}})];
 for(const change of changes){const c=paged();change(c);assert.equal(fileReadEvidence(c).files[0].complete,false);}
});
