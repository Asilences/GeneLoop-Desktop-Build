import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,readdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
const supported={skip:!process.features?.typescript};

test('File judgement claim survives pre-admission failure and blocks paid cold restart across hosts',supported,async t=>{
  const {createDesktopDecisions}=await import('../scripts/harless_desktop_decisions.mjs');
  const {DECISION_FORMAT}=await import('../src/adapters/typed_decisions.ts');
  const root=mkdtempSync(join(tmpdir(),'gl-jev-host-'));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  const context=join(root,'meter.json');
  writeFileSync(context,JSON.stringify({format:'geneloop-decision-account-v1',owner:'fixture-owner'}));
  // A deliberately invalid Python executable and absent provider config ensure
  // admission fails before any network call, even if a developer has credentials.
  const settings={accounts:{'fixture-owner':{config:join(root,'absent-provider.env'),meterContext:context,python:process.execPath}}};
  const api=createDesktopDecisions(settings),hash=x=>createHash('sha256').update(x).digest('hex');
  const packet={format:DECISION_FORMAT,scene:'files',owner:'client-cannot-set-owner',task_id:randomUUID(),
    parent_call_id:'synthetic-test',contract:hash('contract'),evidence:[{id:'fixture.txt',sha256:hash('fixture'),scope:'synthetic'}],
    request:{state:'Synthetic fixture only',questions:{type:{type:'choice',instructions:'Classify',
      criteria:{document:'Document',unknown:'Insufficient evidence'}}}}};
  const input={packet,request_id:hash('stable-client-request')};
  assert.equal(api.available('another-account'),false);
  const first=api.judge('fixture-owner',input);
  await assert.rejects(api.judge('fixture-owner',input),e=>e.status===409);
  await assert.rejects(first,/CLI did not complete/);
  const [scope]=readdirSync(join(root,'desktop-decisions'));
  const folder=join(root,'desktop-decisions',scope),stateFile=join(folder,'state.json');
  const original=readFileSync(stateFile,'utf8'),runs=readdirSync(join(folder,'runs'));
  assert.equal(runs.length,1);
  await assert.rejects(createDesktopDecisions(settings).judge('fixture-owner',input),e=>e.status===409);
  assert.deepEqual(readdirSync(join(folder,'runs')),runs,'no second potentially paid operation');
  assert.equal(readFileSync(stateFile,'utf8'),original);
  await assert.rejects(api.judge('fixture-owner',{...input,packet:{...packet,request:{...packet.request,state:'Changed evidence'}}}),/changed/);
});

test('File judgement rejects account context mismatch before launching the existing CLI',supported,async t=>{
  const {createDesktopDecisions}=await import('../scripts/harless_desktop_decisions.mjs');
  const root=mkdtempSync(join(tmpdir(),'gl-jev-owner-'));t.after(()=>rmSync(root,{recursive:true,force:true}));
  const file=join(root,'meter.json');writeFileSync(file,JSON.stringify({format:'geneloop-decision-account-v1',owner:'someone-else'}));
  const api=createDesktopDecisions({accounts:{fixture:{config:join(root,'provider.env'),meterContext:file,python:process.execPath}}});
  assert.throws(()=>api.available('fixture'),/account differs/);
  assert.deepEqual(readdirSync(root),['meter.json']);
});
