import assert from 'node:assert/strict';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createGateway } from '../../../scripts/harless_gateway.mjs';

const app = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(import.meta.url);
const output = join(app, '.local/validation/local-workspace-' + randomUUID());
const source = join(output, '测试工作区'), reports = join(source, 'GeneLoop 输出');
mkdirSync(source, { recursive: true });
const sample = '仅本机资料 ' + randomUUID();
const report = '# 本机报告\n\n来源：资料.txt\n';
writeFileSync(join(source, '资料.txt'), sample);
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
  const delta = calls === 1 ? { tool_calls: [{ index: 0, id: 'fixture-read', type: 'function', function: {
    name: 'local_read', arguments: JSON.stringify({ path: '资料.txt' }),
  }}] } : calls === 2 ? { tool_calls: [{ index: 0, id: 'fixture-save', type: 'function', function: {
    name: 'local_save_report', arguments: JSON.stringify({ markdown: report }),
  }}] } : { content: calls === 5 ? '续接成功。' : '报告已保存。' };
  const base = { id: 'local-check-' + calls, object: 'chat.completion.chunk', created: 1, model: body.model };
  res.writeHead(200, { 'content-type': 'text/event-stream' });
  for (const choices of [
    [{ index: 0, delta: { role: 'assistant', ...delta }, finish_reason: null }],
    [{ index: 0, delta: {}, finish_reason: calls < 3 ? 'tool_calls' : 'stop' }],
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
    env: { ...process.env, GENELOOP_LOCAL_WINDOW_FIXTURE: JSON.stringify({ origin, cookie, source, reports, profile: join(output, 'desktop'), waiting: join(output, 'waiting') }) },
  });
  timer = setTimeout(() => child.kill(), 90_000);
  const [code] = await once(child, 'exit');
  assert.equal(code, 0);
  assert.deepEqual(paths.map(row => row.path).slice(0, 6), ['/tasks/register', '/tasks/activate', '/bind', '/v1/chat/completions', '/v1/chat/completions', '/v1/chat/completions']);
  assert.deepEqual(paths.map(row => row.path).slice(6, 8).sort(), ['/tasks/cancel', '/unbind']);
  assert.deepEqual(paths.map(row => row.path).slice(8, 12), ['/tasks/register', '/tasks/activate', '/bind', '/v1/chat/completions']);
  assert.deepEqual(paths.map(row => row.path).slice(12, 14).sort(), ['/tasks/cancel', '/unbind']);
  assert.deepEqual(paths.map(row => row.path).slice(14, 18), ['/tasks/register', '/tasks/activate', '/bind', '/v1/chat/completions']);
  assert.deepEqual(paths.map(row => row.path).slice(18).sort(), ['/tasks/cancel', '/unbind']);
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
  assert.equal(names.length, 1);
  assert.equal(readFileSync(join(reports, names[0]), 'utf8'), report);
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
  assert.equal(paths.filter(row => row.path === '/v1/chat/completions').length, 5);
  console.log(JSON.stringify({ kind: 'desktop_local_workspace_electron_gateway_diagnostic', modelRequests: 0, syntheticRequests: 5, canceledUpstream, report: join(reports, names[0]), settled: true }));
} finally {
  clearTimeout(timer);
  gateway.close();
  upstream.closeAllConnections();
  upstream.close();
}
