/** Offline transport diagnostics, not evidence of real model quality. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, chmodSync, readdirSync, readFileSync, rmSync, realpathSync, symlinkSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
const enabled = { skip: !process.features?.typescript };
const credentials = { skip: enabled.skip || process.platform === 'win32' };
const request = { state: '请按正文归档附件', questions: {
  certain: { type: 'noul', instructions: '资料的归属是否明确？' },
  category: { type: 'choice', instructions: '文件属于哪一类？', criteria: { invoice: '发票', other: '其他' } } } };
const reply = { model: 'jev-1.14.0', answers: {
  certain: { type: 'noul', noul: 0.8 }, category: { type: 'choice', choice: 'invoice', confidence: 1,
    probabilities: { invoice: 1, other: 0 } } }, usage: { input_tokens: 100, output_tokens: 10, cost: 0.0001 } };
const api = () => import('../src/adapters/kouri_jev.ts');
function fixture() {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'jev-test-'))), config = join(root,'private.env');
  writeFileSync(config, 'KOURI_API_KEY="test-key-not-real"\nKOURI_BASE_URL=https://api.kourichat.com/v1\n', { mode: 0o600 });
  return { root, config, recordRoot: join(root,'runs'), close: () => rmSync(root, { recursive: true, force: true }) };
}
test('JEV uses private Kouri config without exporting the key', credentials, async () => {
  const {loadJevCredential} = await api(), f = fixture();
  try {
    const before = process.env.KOURI_API_KEY;
    assert.equal(loadJevCredential(f.config), 'test-key-not-real');
    assert.equal(process.env.KOURI_API_KEY, before);
    chmodSync(f.config, 0o644); assert.throws(() => loadJevCredential(f.config), /private_config_required/);
  } finally { f.close(); }
});
test('JEV rejects symlinks and alternative credential origins', credentials, async () => {
  const {loadJevCredential} = await api(), f = fixture();
  try {
    symlinkSync(f.config, join(f.root, 'link.env'));
    assert.throws(() => loadJevCredential(join(f.root, 'link.env')), /private_config/);
    for (const origin of ['http://api.kourichat.com/v1','https://api.kourichat.com.evil/v1','https://evil.example']) {
      writeFileSync(f.config, `KOURI_API_KEY=test\nKOURI_BASE_URL=${origin}\n`);
      assert.throws(() => loadJevCredential(f.config), /invalid_kouri_origin/);
    }
  } finally { f.close(); }
});
test('JEV request supports supplied noul/choice contract and rejects unknown fields', enabled, async () => {
  const {validateJevRequest} = await api();
  assert.equal(validateJevRequest(request).model,'jev');
  for (const v of [{...request,model:'deepseek-flash'}, {...request,questions:{}}, {...request,state:''},
    {...request,tools:[]}, {...request,questions:{x:{type:'choice',instructions:'x',criteria:{}}}},
    {...request,questions:{x:{type:'noul',instructions:'x',criteria:{a:'a'}}}}])
    assert.throws(() => validateJevRequest(v), /invalid_/);
});
test('JEV verifies answer identity/types and allowed choices; missing answers never pass', enabled, async () => {
  const {validateJevResponse} = await api();
  assert.deepEqual(validateJevResponse(reply,request),reply);
  for (const change of [r => delete r.answers.certain, r => r.answers.category.choice='unknown',
    r => r.answers.certain.noul='0.8', r => r.answers.category.type='noul', r => r.answers.category.confidence=2,
    r => r.answers.category.probabilities.other=-1]) {
    const r = structuredClone(reply); change(r); assert.throws(() => validateJevResponse(r,request), /invalid_/);
  }
});
test('JEV real-shaped success keeps raw usage, private evidence and explicit unverified currency', credentials, async t => {
  const {judgeWithJev,JEV_ENDPOINT} = await api(), f = fixture(); let calls=0;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls++; assert.equal(url,JEV_ENDPOINT); assert.equal(options.redirect,'error');
    assert.equal(options.headers.Authorization,'Bearer test-key-not-real');
    assert.equal(JSON.parse(options.body).model,'jev');
    return new Response(JSON.stringify(reply), { status:200, headers:{'x-request-id':'test-request'} });
  });
  try {
    const r = await judgeWithJev(request,f); assert.equal(calls,1);
    assert.deepEqual(r.result,reply); assert.equal(r.accounting.reported_cost,0.0001);
    assert.equal(r.accounting.currency,null); assert.equal(r.accounting.invoice_verified,false);
    const records = readdirSync(r.record_directory).map(name => readFileSync(join(r.record_directory,name),'utf8')).join('');
    assert(!records.includes('test-key-not-real'));
    assert.equal(JSON.parse(readFileSync(join(r.record_directory,'http.json'))).request_id,'test-request');
  } finally { f.close(); }
});
for (const [name,response,code] of [
  ['HTTP failure',()=>new Response('{"error":"unavailable"}',{status:503}),'http_503'],
  ['invalid JSON',()=>new Response('not json'),'invalid_json'],
  ['partial answers',()=>new Response(JSON.stringify({...reply,answers:{}})),'invalid_response'],
]) test(`JEV ${name} preserves raw failure without retry`, credentials, async t => {
  const {judgeWithJev} = await api(), f=fixture(); let calls=0;
  t.mock.method(globalThis,'fetch',async()=>{calls++;return response();});
  try {
    await assert.rejects(judgeWithJev(request,f),new RegExp(code)); assert.equal(calls,1);
    const dir=join(f.recordRoot,readdirSync(f.recordRoot)[0]), failure=JSON.parse(readFileSync(join(dir,'failed.json')));
    assert.equal(failure.code,code); assert.equal(failure.charge_unknown,true);
    assert(readFileSync(join(dir,'response.txt'),'utf8').length>0);
  } finally {f.close();}
});
test('JEV transport error never leaks error text/credentials or silently retries', credentials, async t => {
  const {judgeWithJev}=await api(), f=fixture(); let calls=0;
  t.mock.method(globalThis,'fetch',async()=>{calls++;throw Error('test-key-not-real');});
  try {
    await assert.rejects(judgeWithJev(request,f),/transport_error/); assert.equal(calls,1);
    const dir=join(f.recordRoot,readdirSync(f.recordRoot)[0]);
    assert(!readFileSync(join(dir,'failed.json'),'utf8').includes('test-key-not-real'));
  } finally {f.close();}
});
test('JEV pre-cancelled call records zero attempts and never sends', credentials, async t => {
  const {judgeWithJev}=await api(), f=fixture(); const controller=new AbortController(); controller.abort();
  t.mock.method(globalThis,'fetch',()=>{assert.fail('must not call');});
  try {
    await assert.rejects(judgeWithJev(request,{...f,signal:controller.signal}),/cancelled/);
    const dir=join(f.recordRoot,readdirSync(f.recordRoot)[0]);
    const failure=JSON.parse(readFileSync(join(dir,'failed.json')));
    assert.equal(failure.upstream_attempts,0); assert.equal(failure.charge_unknown,false);
  } finally {f.close();}
});
test('JEV absent usage stays unknown rather than inventing zero cost', credentials, async t => {
  const {judgeWithJev}=await api(), f=fixture(); const r=structuredClone(reply); delete r.usage;
  t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(r)));
  try {
    const result=await judgeWithJev(request,f);
    assert.equal(result.accounting.reported_cost,null); assert.equal(result.accounting.cost_basis,'not_reported');
  } finally {f.close();}
});
