import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,readdirSync,realpathSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const enabled={skip:!process.features?.typescript};
const api=()=>import('../src/adapters/typed_decisions.ts');
const packet=scene=>({format:'geneloop-typed-decision-v1',scene,contract:'test-contract-v1',owner:'account-a',task_id:'task-a',parent_call_id:'parent-a',evidence:[{id:'document',sha256:'a'.repeat(64),scope:'complete current text'}],request:{state:'The document is an invoice.',questions:{category:{type:'choice',instructions:'Choose category',criteria:{invoice:'invoice',contract:'contract',unknown:'insufficient'}}}}});
const result={model:'jev-1.14.0',answers:{category:{type:'choice',choice:'invoice',probabilities:{invoice:.98,contract:.01,unknown:.01}}},usage:{input_tokens:100,output_tokens:9,cost:.0001}};
test('the same decision protocol accepts different scene evidence without File fields',enabled,async()=>{
 const {validateDecisionPacket}=await api();for(const scene of ['files','ppt','data-report'])assert.equal(validateDecisionPacket(packet(scene)).scene,scene);
 const p=packet('files');delete p.evidence;assert.throws(()=>validateDecisionPacket(p),/invalid_decision_packet/);
});
test('only a valid, sufficiently supported current option may produce a branch',enabled,async()=>{
 const {acceptDecision}=await api();assert.equal(acceptDecision(packet('files'),result,.9).accepted,true);
 for(const change of [r=>delete r.answers.category.probabilities,r=>r.answers.category.probabilities={invoice:.6,contract:.3,unknown:.1},r=>r.answers.category.probabilities={invoice:.98,contract:.01},r=>r.answers.category.choice='unknown']){
  const r=structuredClone(result);change(r);assert.equal(acceptDecision(packet('files'),r,.9).accepted,false);
 }
});
test('noul keeps a real abstention band and rejects values outside the API range',enabled,async()=>{
 const {acceptDecision}=await api();const p=packet('files');p.request.questions={check:{type:'noul',instructions:'Is sufficient evidence present?'}};
 const r=n=>({model:'jev',answers:{check:{type:'noul',noul:n}}});
 assert.deepEqual(acceptDecision(p,r(.98),.9).values,{check:true});assert.deepEqual(acceptDecision(p,r(.01),.9).values,{check:false});
 assert.equal(acceptDecision(p,r(.5),.9).accepted,false);assert.throws(()=>acceptDecision(p,r(2),.9),/invalid_noul_range/);
});
test('meter admission precedes actual fetch and cannot be omitted',{skip:enabled.skip||process.platform==='win32'},async t=>{
 const {runTypedDecision}=await api();let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;throw Error('not expected');});
 const root=realpathSync(mkdtempSync(join(tmpdir(),'typed-decision-')));
 try{
  await assert.rejects(runTypedDecision(packet('files'),{provider:'jev',recordRoot:root,meter:async()=>{throw Error('admission denied');}}),/admission denied/);
  assert.equal(calls,0);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('JEV usage and generic ownership link are preserved without inventing USD cost',{skip:enabled.skip||process.platform==='win32'},async t=>{
 const {runTypedDecision}=await api();const root=realpathSync(mkdtempSync(join(tmpdir(),'typed-decision-'))),config=join(root,'private.env');
 writeFileSync(config,'KOURI_API_KEY=test-key\nKOURI_BASE_URL=https://api.kourichat.com/v1\n',{mode:0o600});const events=[];
 t.mock.method(globalThis,'fetch',async()=>{assert.equal(events[0].status,'started');return new Response(JSON.stringify(result));});
 try{const r=await runTypedDecision(packet('files'),{provider:'jev',recordRoot:join(root,'runs'),config,meter:async e=>events.push(e)});
  assert.equal(r.decision.accepted,true);assert.equal(r.reference_cost_usd,null);assert.equal(r.provider_reported_cost,.0001);
  assert.equal(r.provider_cost_currency,null);assert.equal(events[1].call_id,events[0].call_id);assert.equal(events[1].parent_call_id,'parent-a');
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('DeepSeek uses the same state/questions, retains raw usage and identifies estimated probabilities',{skip:enabled.skip||process.platform==='win32'},async t=>{
 const {runTypedDecision}=await api();const root=realpathSync(mkdtempSync(join(tmpdir(),'typed-decision-'))),config=join(root,'private.env');
 writeFileSync(config,'KOURI_API_KEY=test-key\nKOURI_BASE_URL=https://api.kourichat.com/v1\n',{mode:0o600});
 t.mock.method(globalThis,'fetch',async(url,opt)=>{assert(url.endsWith('/chat/completions'));const b=JSON.parse(opt.body);
  assert.deepEqual(JSON.parse(b.messages[1].content),packet('files').request);assert.equal(b.max_tokens,393216);
  return new Response(JSON.stringify({model:'deepseek-v4.1-flash',choices:[{message:{content:JSON.stringify({answers:result.answers})}}],usage:{prompt_tokens:100,completion_tokens:10,total_tokens:110,prompt_tokens_details:{cached_tokens:50}}}));});
 try{const r=await runTypedDecision(packet('files'),{provider:'deepseek',recordRoot:join(root,'runs'),config,meter:async()=>{}});
  assert.equal(r.probability_source,'text_generated_estimate');assert.equal(r.decision.accepted,true);assert(r.reference_cost_usd>0);assert.equal(r.provider_reported_cost,null);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('transport failure is retained once with unknown charge and no automatic retry',{skip:enabled.skip||process.platform==='win32'},async t=>{
 const {runTypedDecision}=await api();const root=realpathSync(mkdtempSync(join(tmpdir(),'typed-decision-'))),config=join(root,'private.env');
 writeFileSync(config,'KOURI_API_KEY=test-key\nKOURI_BASE_URL=https://api.kourichat.com/v1\n',{mode:0o600});let calls=0;const events=[];
 t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response('{}',{status:503});});
 try{await assert.rejects(runTypedDecision(packet('files'),{provider:'jev',recordRoot:join(root,'runs'),config,meter:async e=>events.push(e)}),/http_503/);
  assert.equal(calls,1);assert.equal(events[1].status,'failed');assert.equal(events[1].charge_unknown,true);
 }finally{rmSync(root,{recursive:true,force:true});}
});

test('compatible SSE text is decoded without discarding the original final usage',enabled,async()=>{
 const {decodeDecisionChat}=await api();
 const frames=[{model:'deepseek-v4.1-flash',choices:[{index:0,delta:{content:'{"answers":'}}]},
  {choices:[{index:0,delta:{content:'{}}'}}]}, {choices:[],usage:{prompt_tokens:12,completion_tokens:3,total_tokens:15}}];
 const raw=decodeDecisionChat(frames.map(x=>'data: '+JSON.stringify(x)+'\r\n\r\n').join('')+'data: [DONE]\r\n\r\n');
 assert.equal(raw.choices[0].message.content,'{"answers":{}}');assert.equal(raw.usage.total_tokens,15);
 assert.throws(()=>decodeDecisionChat('data: not-json\n\n'));
});

test('usage-only SSE stays a failed decision while its cost is recorded',{skip:enabled.skip||process.platform==='win32'},async t=>{
 const {runTypedDecision}=await api();const root=realpathSync(mkdtempSync(join(tmpdir(),'typed-decision-'))),config=join(root,'private.env');
 writeFileSync(config,'KOURI_API_KEY=test-key\nKOURI_BASE_URL=https://api.kourichat.com/v1\n',{mode:0o600});const events=[];
 t.mock.method(globalThis,'fetch',async(url,opt)=>{
  assert.equal(JSON.parse(opt.body).stream,false);
  return new Response('data: '+JSON.stringify({choices:[],usage:{prompt_tokens:100,completion_tokens:0,total_tokens:100}})+'\n\ndata: [DONE]\n\n');
 });
 try{
  await assert.rejects(runTypedDecision(packet('files'),{provider:'deepseek',recordRoot:join(root,'runs'),config,meter:async e=>events.push(e)}),/empty_model_answer/);
  assert.equal(events[1].status,'failed');assert.equal(events[1].reported_usage.prompt_tokens,100);
  assert.equal(events[1].reference_cost_usd,.00003);assert.equal(events[1].charge_unknown,false);
 }finally{rmSync(root,{recursive:true,force:true});}
});
