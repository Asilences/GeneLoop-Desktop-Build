import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,mkdirSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {createGateway} from '../scripts/harless_gateway.mjs';
import {motifEvidenceView as readMotifEvidence} from '../scripts/harless_motif_view.ts';
import {usd} from '../src/adapters/motif_evidence_projection.ts';
const sample=()=>JSON.parse(readFileSync(new URL('../apps/desktop/ui/desktop/motif-example.json',import.meta.url),'utf8'));
test('公开证据只统计实际调用，未知费用和耗时保持未知',()=>{
  const data=sample(),view=readMotifEvidence(data);
  assert.equal(view.summary.certified,1);assert.equal(view.summary.applied,1);assert.equal(view.summary.fallbacks,1);assert.equal(view.summary.savings,null);
  assert.equal(view.capabilities[0].cost,'未知');assert.equal(view.runs[0].elapsedLabel,'未知');assert.notEqual(usd(0),usd(null));
  data.events=data.events.filter(e=>e.kind!=='invoke');assert.equal(readMotifEvidence(data).summary.applied,0);
});
test('拒绝执行授权、伪造认证及断开的证据引用',()=>{
  let data=sample();data.execution_authorized=true;assert.throws(()=>readMotifEvidence(data));
  data=sample();data.capabilities[0].version.certificate_digest=null;assert.throws(()=>readMotifEvidence(data));
  data=sample();data.events[0].evidence_refs=['f'.repeat(64)];assert.throws(()=>readMotifEvidence(data));
  data=sample();data.events.push(data.events[0]);assert.throws(()=>readMotifEvidence(data));
  data=sample();data.events[0].actual_execution=true;assert.throws(()=>readMotifEvidence(data));
});
test('待认证、失效与空库均保持独立状态',()=>{
  for(const status of ['pending_certification','invalid']){const data=sample();const c=data.capabilities[0];c.status=c.certification.status=status;c.in_frozen_library=false;c.version.certificate_digest=null;data.library.certified_count=0;assert.equal(readMotifEvidence(data).capabilities[0].status,status);}
  const data=sample();data.capabilities=[];data.events=[];data.library.certified_count=0;assert.equal(readMotifEvidence(data).summary.applied,0);
});
test('真实网关的只读接口隔离账号与工作区，更新导出无需重启',async t=>{
  const tempRoot=realpathSync(tmpdir()),root=realpathSync(mkdtempSync(join(tempRoot,'motif-view-')));t.after(()=>{assert.equal(dirname(root),tempRoot);rmSync(root,{recursive:true,force:true});});
  const db=join(root,'db');mkdirSync(db);const file=join(root,'snapshot.json');writeFileSync(file,JSON.stringify(sample()));
  const tokens={owner:'a'.repeat(40),other:'b'.repeat(40)};
  writeFileSync(join(db,'accounts.json'),JSON.stringify({version:1,users:Object.keys(tokens).map(id=>({id,role:id==='owner'?'owner':'member',username:id,displayName:id})),sessions:Object.entries(tokens).map(([userId,value])=>({userId,hash:createHash('sha256').update(value).digest('hex'),expiresAt:Date.now()+60000})),invites:[],ownerClaim:null}));
  const gateway=createGateway({dataDir:db,publicOrigin:'https://fixture.example',motifEvidence:{sources:[{accountId:'owner',workspaceId:'workspace',path:file,executionLocation:'cloud'}]}});
  await new Promise(done=>gateway.server.listen(0,'127.0.0.1',done));t.after(()=>new Promise(done=>{gateway.server.once('close',done);gateway.close();}));
  const base='http://127.0.0.1:'+gateway.server.address().port;
  const get=(suffix='',token=tokens.owner,extra={})=>fetch(base+'/api/harless/motif-library'+suffix,{...extra,headers:{...(token?{cookie:'harless_sess='+token}:{}),...extra.headers}});
  assert.equal((await get('',null)).status,401);
  let response=await get();assert.equal(response.status,200);assert.match(response.headers.get('cache-control'),/no-store/);
  const first=await response.json();assert.equal(first.workspaces.length,1);assert.equal(first.workspaces[0].compatibility,'unverified');assert.equal(JSON.stringify(first).includes(root),false);
  assert.equal((await(await get('',tokens.other)).json()).workspaces.length,0);
  assert.equal((await(await get('?workspaceId=foreign')).json()).workspaces.length,0);
  assert.equal((await get('?path=arbitrary')).status,400);
  assert.equal((await get('',tokens.owner,{method:'POST',headers:{origin:'https://fixture.example'}})).status,405);
  assert.equal((await get('',tokens.owner,{headers:{'sec-fetch-site':'cross-site'}})).status,403);
  writeFileSync(file,'{invalid');const invalid=await(await get()).json();assert.equal(invalid.workspaces[0].status,'unavailable');assert.notEqual(invalid.revision,first.revision);
  writeFileSync(file,JSON.stringify(sample()));assert.equal((await(await get()).json()).workspaces[0].status,'ready');
});
