import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,realpathSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash,randomUUID} from 'node:crypto';

const supported={skip:!process.features?.typescript};
async function setup(t){
  const {openFileDecisions}=await import('../apps/desktop/runtime/local-file-decisions.mjs');
  const home=realpathSync(mkdtempSync(join(tmpdir(),'gl-file-jev-')));
  const path=join(home,'source.txt');
  writeFileSync(path,'Invoice for microscope reagents, total 125 CNY.');
  t.after(()=>rmSync(home,{recursive:true,force:true}));
  const sources=[{path:'source.txt',sha256:createHash('sha256').update(readFileSync(path)).digest('hex')}];
  const reader={readBytes:()=>readFileSync(path)};
  const args={reader,home,sessionId:randomUUID(),prompt:'Classify the document',enabled:true,account:'a'.repeat(64),
    signal:new AbortController().signal,endpoint:'https://fixture.invalid/api/harless/desktop-model/v1',token:'fixture-task-token'};
  const questions=JSON.stringify({category:{type:'choice',instructions:'Classify the actual content',
    criteria:{invoice:'Invoice',paper:'Scientific paper',unknown:'Insufficient evidence'}}});
  const result={model:'jev-fixture',answers:{category:{type:'choice',choice:'invoice',probabilities:{invoice:0.98,paper:0.01,unknown:0.01}}},usage:{cost:0.001}};
  return {open:()=>openFileDecisions(args),args,sources,questions,path,result};
}
test('File JEV uses actual bytes and resumes paid judgement without another request',supported,async t=>{
  const f=await setup(t);let calls=0;
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    calls++;
    assert.equal(url.href,'https://fixture.invalid/api/harless/desktop-model/v1/systemone');
    assert.equal(options.redirect,'error');
    const input=JSON.parse(options.body);
    assert.equal(input.packet.task_id,f.args.sessionId);
    const evidence=JSON.parse(input.packet.request.state);
    assert.equal(evidence.materials[0].text,readFileSync(f.path,'utf8'));
    return Response.json({result:f.result,decision:{threshold:0.9},accounting:{reported_cost:0.001}});
  });
  const first=await f.open()({sources:f.sources,questions:f.questions});
  assert.equal(first.decision.accepted,true);
  const recovered=await f.open()({sources:f.sources,questions:f.questions});
  assert.equal(recovered.reused,true);assert.equal(calls,1);
  writeFileSync(f.path,'Changed document');
  await assert.rejects(()=>f.open()({sources:f.sources,questions:f.questions}),/已变化/);
  assert.equal(calls,1);
});
test('File JEV recovery keeps uncertain paid outcomes unknown and asks the server for the same identity',supported,async t=>{
  const f=await setup(t),identities=[];
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    identities.push(JSON.parse(options.body).request_id);
    if(identities.length===1)throw Error('connection closed after provider admission');
    return Response.json({error:'outcome unknown'},{status:409});
  });
  await assert.rejects(()=>f.open()({sources:f.sources,questions:f.questions}),/connection closed/);
  await assert.rejects(()=>f.open()({sources:f.sources,questions:f.questions}),/未重复付费/);
  assert.equal(identities[0],identities[1]);
});
test('File JEV rejects missing grant and invalid probabilities instead of authorizing an action',supported,async t=>{
  const f=await setup(t);
  const {openFileDecisions}=await import('../apps/desktop/runtime/local-file-decisions.mjs');
  await assert.rejects(()=>openFileDecisions({...f.args,enabled:false})({sources:f.sources,questions:f.questions}),/尚未启用/);
  t.mock.method(globalThis,'fetch',async()=>Response.json({result:{...f.result,answers:{category:{
    type:'choice',choice:'invoice',probabilities:{invoice:0.6,paper:0.3,unknown:0.1}}}},decision:{threshold:0.9}}));
  const result=await f.open()({sources:f.sources,questions:f.questions});
  assert.equal(result.decision.accepted,false);
  assert.equal(result.decision.status,'fallback_required');
});


test('File JEV cache is private to the authenticated account and gateway origin',supported,async t=>{
  const f=await setup(t);let calls=0;
  t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json({result:f.result,decision:{threshold:0.9}});});
  const input={sources:f.sources,questions:f.questions};
  await f.open()(input);
  const {openFileDecisions}=await import('../apps/desktop/runtime/local-file-decisions.mjs');
  await openFileDecisions({...f.args,account:'b'.repeat(64)})(input);
  await openFileDecisions({...f.args,endpoint:'https://other.invalid/api/harless/desktop-model/v1'})(input);
  assert.equal(calls,3,'another account or server cannot reuse the original paid receipt');
  assert.equal((await f.open()(input)).reused,true);assert.equal(calls,3);
});
