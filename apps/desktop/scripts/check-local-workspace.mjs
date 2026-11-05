import assert from 'node:assert/strict';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { execFileSync, spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createGateway } from '../../../scripts/harless_gateway.mjs';
import { renderHybridVideo } from '../runtime/local-video.mjs';

const app = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(import.meta.url);
const output = join(app, '.local/validation/local-workspace-' + randomUUID());
const source = join(output, '测试工作区'), reports = join(source, 'GeneLoop 输出');
mkdirSync(source, { recursive: true });
const sample = '仅本机资料 ' + randomUUID();
const report = '# 本机报告\n\n来源：资料.txt\n';
writeFileSync(join(source, '资料.txt'), sample);
writeFileSync(join(source, 'sample.csv'), 'group,amount\nA,0.15\nA,0.25\nB,2.10\n');
writeFileSync(join(source, 'paper.tex'), String.raw`Reference \cite{known,missing}`);
writeFileSync(join(source, 'paper.bib'), '@article{known,title={Known}}');
const media = process.env.GENELOOP_FFMPEG_DIRECTORY;
if (!media) throw Error('六场景诊断需要 GENELOOP_FFMPEG_DIRECTORY。');
execFileSync(join(media,'ffmpeg.exe'), ['-v','error','-nostdin','-f','lavfi','-i','color=c=blue:s=320x180:r=30',
  '-t','2','-c:v','libx264','-pix_fmt','yuv420p','-n',join(source,'sample.mp4')], {windowsHide:true});

execFileSync(join(media,'ffmpeg.exe'), ['-v','error','-nostdin','-f','lavfi','-i','color=c=green:s=320x180:r=30',
  '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',
  '-n',join(source,'with-audio.mp4')], {windowsHide:true});
const version = name => createHash('sha256').update(readFileSync(join(source,name))).digest('hex');

// Transport fixture only. The response is a real MP4 produced above, not a
// Remotion render. Verify that consent precedes transfer and output decoding.
const renderedFixture = readFileSync(join(source,'sample.mp4'));
const transfers = [];
const rendererFixture = createServer(async (req,res) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  transfers.push({url:req.url, body:JSON.parse(Buffer.concat(chunks).toString())});
  res.writeHead(200, {'content-type':'video/mp4','content-length':renderedFixture.length,'x-geneloop-sha256':version('sample.mp4')});
  res.end(renderedFixture);
});
rendererFixture.listen(0,'127.0.0.1');
await once(rendererFixture,'listening');
const originalEndpoint = process.env.DEEPSEEK_BASE_URL;
const originalToken = process.env.DEEPSEEK_API_KEY;
process.env.DEEPSEEK_BASE_URL = 'http://127.0.0.1:'+rendererFixture.address().port+'/api/harless/desktop-model/v1';
process.env.DEEPSEEK_API_KEY = 'transport-fixture';
try {
  const phases = [], artifacts = [];
  const result = await renderHybridVideo(
    {readBytes:name=>readFileSync(join(source,name))},
    {writeArtifacts:items=>{artifacts.push(...items);return items.map(item=>({name:'fixture.'+item.extension}));}},
    {ffmpeg:join(media,'ffmpeg.exe'),ffprobe:join(media,'ffprobe.exe')},
    'registerRoot(Entry)', '["sample.mp4"]', new AbortController().signal,
    async request=>{assert.equal(transfers.length,0);assert.deepEqual(request.assets,[{path:'sample.mp4',bytes:renderedFixture.length}]);return true;},
    undefined, phase=>phases.push(phase),
  );
  assert.deepEqual(phases,['remote-render','local']);
  assert.equal(transfers.length,1);
  assert.equal(transfers[0].url,'/api/harless/desktop-model/video/render');
  assert.deepEqual(transfers[0].body.assets,[{name:'asset-1.mp4',bytes:renderedFixture.toString('base64'),sha256:version('sample.mp4')}]);
  assert.deepEqual(artifacts.map(item=>item.extension),['mp4','tsx','json']);
  assert.equal(result.output.fullyDecoded,true);
} finally {
  if (originalEndpoint === undefined) delete process.env.DEEPSEEK_BASE_URL;
  else process.env.DEEPSEEK_BASE_URL = originalEndpoint;
  if (originalToken === undefined) delete process.env.DEEPSEEK_API_KEY;
  else process.env.DEEPSEEK_API_KEY = originalToken;
  rendererFixture.closeAllConnections();
  await new Promise(resolve=>rendererFixture.close(resolve));
}

const scenarioSteps = {
  chat: [],
  data: [['local_data_summarize',{path:'sample.csv',column:'amount',group_by:'group'}]],
  paper: [['local_paper_check_citations',{manuscript:'paper.tex',bibliography:'paper.bib'}]],
  ppt: [['local_ppt_create',{plan:JSON.stringify({title:'科研诊断',slides:[{
    title:'单页验证',bullets:['文字可编辑，来源见讲稿。'],sources:['合成诊断数据'],notes:'本页是本机工程诊断。'
  }]})}]],
  video: [['local_video_probe',{path:'sample.mp4'}],['local_video_render',{plan:JSON.stringify([
    {path:'sample.mp4',sha256:version('sample.mp4'),start:0,end:0.5},
    {path:'with-audio.mp4',sha256:version('with-audio.mp4'),start:1,end:1.5},
  ])}]],
};
const paths = [];
let canceledUpstream = false;
const upstream = createServer(async (req, res) => {
  const chunks = [];
  for await (const part of req) chunks.push(part);
  const body = JSON.parse(Buffer.concat(chunks).toString());
  paths.push({ path: req.url, body, headers: req.headers });
  if (req.url !== '/v1/chat/completions') {
    res.writeHead(200, { 'content-type': 'application/json' }); return res.end('{}');
  }
  const calls = paths.filter(row => row.path === '/v1/chat/completions').length;
  if (calls === 4) {
    res.once('close', () => { canceledUpstream = !res.writableEnded; });
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    res.write(': wait for cancellation\n\n');
    writeFileSync(join(output, 'waiting'), 'ready');
    return;
  }
  const usage = { prompt_tokens: 100, completion_tokens: 12, total_tokens: 112 };
  const probe = body.messages.find(message => message.role === 'user' && /^诊断-(chat|data|paper|ppt|video)$/.test(message.content));
  const scene = probe?.content.slice(3);
  const step = scene && scenarioSteps[scene][body.messages.filter(message => message.role === 'tool').length];
  const delta = scene ? step ? {tool_calls:[{index:0,id:'fixture-'+calls,type:'function',
    function:{name:step[0],arguments:JSON.stringify(step[1])}}]} : {content:'诊断完成 '+scene} : calls === 1 ? { tool_calls: [{ index: 0, id: 'fixture-read', type: 'function', function: {
    name: 'local_read', arguments: JSON.stringify({ path: '资料.txt' }),
  }}] } : calls === 2 ? { tool_calls: [{ index: 0, id: 'fixture-save', type: 'function', function: {
    name: 'local_save_report', arguments: JSON.stringify({ markdown: report }),
  }}] } : { content: calls === 5 ? '续接成功。' : '报告已保存。' };
  const base = { id: 'local-check-' + calls, object: 'chat.completion.chunk', created: 1, model: body.model };
  res.writeHead(200, { 'content-type': 'text/event-stream' });
  for (const choices of [
    [{ index: 0, delta: { role: 'assistant', ...delta }, finish_reason: null }],
    [{ index: 0, delta: {}, finish_reason: delta.tool_calls ? 'tool_calls' : 'stop' }],
    [],
  ]) res.write('data: ' + JSON.stringify({ ...base, choices, usage: choices.length ? undefined : usage }) + '\n\n');
  res.end('data: [DONE]\n\n');
});
upstream.listen(0, '127.0.0.1');
await once(upstream, 'listening');
const reservation = createServer().listen(0, '127.0.0.1');
await once(reservation, 'listening');
const port = reservation.address().port;
await new Promise(done => reservation.close(done));
const origin = 'http://127.0.0.1:' + port;
const accountHtml = join(output, 'account.html');
writeFileSync(accountHtml, '<title>本机联调</title>');
const gateway = createGateway({
  publicOrigin: origin, accountHtml, dataDir: join(output, 'accounts'),
  desktopLocalModel: { accountIds: ['desktop-probe'] }, upstreamBrokerPort: upstream.address().port, upstreamControlPort: upstream.address().port,
  apiKey: 'synthetic-model-only', memberPolicy: { control_token: 'synthetic-budget-only', budget_usd: null },
});
const cookie = randomBytes(32).toString('base64url');
const otherCookie = randomBytes(32).toString('base64url');
gateway.db.users.push({ id: 'desktop-probe', role: 'owner' }, { id: 'unapproved-probe', role: 'member' });
gateway.db.sessions.push({ userId: 'desktop-probe', hash: createHash('sha256').update(cookie).digest('hex'), expiresAt: Date.now() + 60_000 });
gateway.db.sessions.push({ userId: 'unapproved-probe', hash: createHash('sha256').update(otherCookie).digest('hex'), expiresAt: Date.now() + 60_000 });
gateway.server.listen(port, '127.0.0.1');
await once(gateway.server, 'listening');

let timer;
try {
  const endpoint = origin + '/api/harless/desktop-model';
  const denied = await fetch(endpoint + '/lease', {
    method: 'POST', headers: { cookie: 'harless_sess=' + cookie, origin: 'https://untrusted.invalid', 'content-type': 'application/json' }, body: '{}',
  });
  assert.equal(denied.status, 403); await denied.body.cancel();
  const unapproved = await fetch(endpoint + '/lease', {
    method: 'POST', headers: { cookie: 'harless_sess=' + otherCookie, origin, 'content-type': 'application/json' }, body: '{}',
  });
  assert.equal(unapproved.status, 403); await unapproved.body.cancel();
  const unauthorized = await fetch(endpoint + '/v1/chat/completions', { method: 'POST', body: '{}' });
  assert.equal(unauthorized.status, 401); await unauthorized.body.cancel();
  assert.deepEqual(paths, []);

  const child = spawn(require('electron'), ['test/local-workspace.cjs'], {
    cwd: app, stdio: 'inherit', windowsHide: true,
    env: { ...process.env, GENELOOP_LOCAL_WINDOW_FIXTURE: JSON.stringify({ origin, cookie, source, reports, profile: join(tmpdir(), 'geneloop-smoke-' + randomUUID().slice(0, 8)), waiting: join(output, 'waiting') }) },
  });
  timer = setTimeout(() => child.kill(), 90_000);
  const [code] = await once(child, 'exit');
  assert.equal(code, 0);
  assert.deepEqual(paths.map(row => row.path).slice(0, 6), ['/tasks/register', '/tasks/activate', '/bind', '/v1/chat/completions', '/v1/chat/completions', '/v1/chat/completions']);
  assert.deepEqual(paths.map(row => row.path).slice(6, 8).sort(), ['/tasks/cancel', '/unbind']);
  assert.deepEqual(paths.map(row => row.path).slice(8, 12), ['/tasks/register', '/tasks/activate', '/bind', '/v1/chat/completions']);
  assert.deepEqual(paths.map(row => row.path).slice(12, 14).sort(), ['/tasks/cancel', '/unbind']);
  assert.deepEqual(paths.map(row => row.path).slice(14, 18), ['/tasks/register', '/tasks/activate', '/bind', '/v1/chat/completions']);
  assert.deepEqual(paths.map(row => row.path).slice(18,20).sort(), ['/tasks/cancel', '/unbind']);
  const history = paths[17].body.messages;
  assert.ok(history.some(message => message.role === 'user' && message.content.includes('读取资料并写报告')));
  assert.ok(history.some(message => message.role === 'assistant' && message.content?.includes('报告已保存。')));
  assert.ok(history.some(message => message.role === 'tool' && message.content === sample));
  assert.equal(canceledUpstream, true);
  const bindings = paths.filter(row => row.path === '/bind').map(row => row.body);
  assert.notEqual(bindings[0].session_id, bindings[1].session_id);
  for (const request of paths.filter(row => row.path === '/v1/chat/completions')) {
    assert.ok(bindings.some(binding => binding.session_id === request.headers['x-deepseek-harness-session-id']));
    assert.equal(request.headers.authorization, 'Bearer synthetic-model-only');
    assert.equal(request.headers.cookie, undefined);
  }
  assert.ok(paths[4].body.messages.some(message => message.role === 'tool' && message.content === sample));
  const names = readdirSync(reports);
  const expectedFiles = {md:1,pptx:1,mp4:1,json:2};
  for (const [ext,count] of Object.entries(expectedFiles)) assert.equal(names.filter(name=>name.endsWith('.'+ext)).length,count,ext);
  const file = ext => join(reports,names.find(name=>name.endsWith('.'+ext)));
  assert.equal(readFileSync(file('md'), 'utf8'), report);
  assert.equal(readFileSync(file('pptx')).readUInt32LE(0), 0x04034b50);
  const receipts = names.filter(name=>name.endsWith('.json')).map(name=>JSON.parse(readFileSync(join(reports,name),'utf8')));
  const slides = receipts.find(row=>row.renderer_version);
  assert.equal(slides.checks.pixel_render_verified,false);
  assert.equal(slides.pptx_sha256,createHash('sha256').update(readFileSync(file('pptx'))).digest('hex'));
  const rendered = receipts.find(row=>row.output?.fullyDecoded);
  assert.ok(rendered);
  assert.equal(rendered.sources.length,2);
  assert.equal(rendered.output.sha256,createHash('sha256').update(readFileSync(file('mp4'))).digest('hex'));
  assert.ok(Math.abs(rendered.output.duration-1)<0.25);
  const scenarioRequests = paths.filter(row=>row.path==='/v1/chat/completions').slice(5);
  for (const [name,steps] of Object.entries(scenarioSteps)) {
    const requests = scenarioRequests.filter(row=>row.body.messages.some(m=>m.role==='user' && m.content==='诊断-'+name));
    assert.equal(requests.length,steps.length+1,name);
    for (const [tool] of steps) assert.ok(requests[0].body.tools.some(row=>row.function?.name===tool),tool);
    assert.equal(requests.at(-1).body.messages.filter(m=>m.role==='tool').length,steps.length);
  }
  const toolResult = scene => JSON.parse(scenarioRequests.find(row=>
    row.body.messages.some(message=>message.role==='user' && message.content==='诊断-'+scene) &&
    row.body.messages.some(message=>message.role==='tool')).body.messages.find(message=>message.role==='tool').content);
  assert.deepEqual(toolResult('data').groups.map(group=>[group.group, group.sum]), [['A','0.4'],['B','2.1']]);
  assert.deepEqual(toolResult('paper').citations.map(row=>[row.key,row.status]), [['known','matched'],['missing','missing']]);
  assert.equal(readFileSync(join(source, '资料.txt'), 'utf8'), sample);
  const sessionHeaders = { cookie: 'harless_sess=' + cookie, origin, 'content-type': 'application/json' };
  const lease = await fetch(endpoint + '/lease', { method: 'POST', headers: sessionHeaders, body: '{}' }).then(response => response.json());
  assert.ok(lease.token);
  const modelHeaders = { authorization: 'Bearer ' + lease.token, 'content-type': 'application/json' };
  const request = { model: lease.model, messages: [{ role: 'user', content: 'test' }], stream: true };
  const response = await fetch(endpoint + '/v1/chat/completions', {
    method: 'POST', headers: modelHeaders, body: JSON.stringify({ ...request, tools: [{ type: 'web_search' }] }),
  });
  assert.equal(response.status, 400); await response.body.cancel();
  const wrongScene = await fetch(endpoint + '/v1/chat/completions', {
    method: 'POST', headers: modelHeaders,
    body: JSON.stringify({ ...request, tools: [{ type: 'function', function: { name: 'local_data_summarize' } }] }),
  });
  assert.equal(wrongScene.status, 400); await wrongScene.body.cancel();
  const logout = await fetch(origin + '/api/account/logout', { method: 'POST', headers: sessionHeaders, body: '{}' });
  assert.equal(logout.status, 200); await logout.body.cancel();
  const revoked = await fetch(endpoint + '/v1/chat/completions', { method: 'POST', headers: modelHeaders, body: JSON.stringify(request) });
  assert.equal(revoked.status, 401); await revoked.body.cancel();
  assert.equal(paths.filter(row => row.path === '/v1/chat/completions').length, 15);
  console.log(JSON.stringify({kind:'desktop_local_workspace_electron_gateway_diagnostic', realModelRequests:0,
    syntheticRequests:15, scenes:['files',...Object.keys(scenarioSteps)], canceledUpstream, remoteVideoTransportFixture:true, output:reports, settled:true}));
} finally {
  clearTimeout(timer);
  gateway.close();
  upstream.closeAllConnections();
  upstream.close();
}
