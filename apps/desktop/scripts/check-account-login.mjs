/** 使用原账号网关与临时合成账号验证桌面登录；只监听127.0.0.1，不调用模型。 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomUUID, scryptSync } from 'node:crypto';
import { once } from 'node:events';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createServer } from 'node:net';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createGateway } from '../../../scripts/harless_gateway.mjs';

const require = createRequire(import.meta.url);
const app = fileURLToPath(new URL('../', import.meta.url));
const repo = fileURLToPath(new URL('../../../', import.meta.url));
const output = join(app, '.local/validation/account-' + randomUUID());
mkdirSync(output, { recursive: true });
const reservation = createServer().listen(0, '127.0.0.1');
await once(reservation, 'listening');
const port = reservation.address().port;
await new Promise(done => reservation.close(done));
const server = `http://127.0.0.1:${port}`;
const username = 'desktop-diagnostic', password = 'Diagnostic-' + randomUUID(), salt = randomUUID();
const gateway = createGateway({ dataDir: join(output, 'db'), publicOrigin: server, accountHtml: join(repo, 'src/adapters/harless_account.html') });
gateway.db.users.push({ id: 'owner', username, displayName: '桌面合成账号', role: 'owner', createdAt: new Date().toISOString(), passwordHash: 'scrypt-v1$' + salt + '$' + scryptSync(password, salt, 64, { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 }).toString('hex') });
gateway.save();
const requests = [];
gateway.server.prependListener('request', request => requests.push({ path: request.url, method: request.method, origin: request.headers.origin, fetchSite: request.headers['sec-fetch-site'] }));
gateway.server.listen(port, '127.0.0.1');
await once(gateway.server, 'listening');
let result = 1;
try {
  for (const origin of [undefined, 'https://foreign.example']) {
    const response = await fetch(server + '/api/account/login', { method: 'POST', headers: { 'content-type': 'application/json', ...(origin ? { origin } : {}) }, body: JSON.stringify({ username, password }) });
    assert.equal(response.status, 403, '原网关仍须拒绝缺失或跨源的请求');
  }
  const fixture = join(output, 'fixture.json');
  writeFileSync(fixture, JSON.stringify({ diagnostic: true, server, username, password, output }) + '\n');
  const environment = { ...process.env, GENELOOP_DESKTOP_ACCOUNT_FIXTURE: fixture };
  delete environment.ELECTRON_RUN_AS_NODE;
  const child = spawn(require('electron'), ['test/account-login.cjs'], { cwd: app, env: environment, stdio: 'inherit', windowsHide: true });
  const [code] = await once(child, 'exit');
  result = code ?? 1;
} finally {
  const closed = once(gateway.server, 'close');
  gateway.close(); await closed;
  writeFileSync(join(output, 'gateway-requests.json'), JSON.stringify({ model_requests: 0, requests }, null, 2) + '\n');
  console.log('账号网关诊断结束；仅本机临时账号，原来源校验未改，真实模型请求0。');
}
process.exitCode = result;
