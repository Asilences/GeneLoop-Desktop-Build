/** 启动实际 Windows 安装资源；仅只读检查公开登录页，不登录或发送模型消息。 */
import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';

assert.equal(process.platform, 'win32', '当前只验收 Windows x64 产物');
const app = fileURLToPath(new URL('../', import.meta.url));
const output = join(app, '.local/validation/packaged-' + randomUUID());
mkdirSync(output, { recursive: true });
const require = createRequire(import.meta.url);
const asar = require('@electron/asar');
const archive = join(app, 'release/win-unpacked/resources/app.asar');
const files = asar.listPackage(archive).map(file => file.replaceAll('\\', '/'));
assert.ok(files.includes('/dist/boot-request.js'));
assert.deepEqual(files.filter(file => /^\/(?:\.local|test|src)\//.test(file) || /^\/\.env/.test(file)), []);
const manifest = JSON.parse(asar.extractFile(archive, 'assets/manifest.json'));
const report = { kind: 'desktop-packaged-readonly-diagnostic', model_requests: 0, source_commit: manifest.sourceCommit, clients: Object.keys(manifest.clients).length, frontend_files: manifest.staticFiles.length, checks: ['ASAR 含启动修复与本地资源，不含私有目录或源测试夹具'] };
const listener = createServer().listen(0, '127.0.0.1');
await once(listener, 'listening');
const port = listener.address().port;
await new Promise(done => listener.close(done));
const executable = join(app, 'release/win-unpacked/GeneLoop Desktop.exe');
const child = spawn(executable, [`--remote-debugging-port=${port}`, `--user-data-dir=${join(output, 'profile')}`], {
  cwd: dirname(executable), windowsHide: true, stdio: 'ignore',
  env: { ...process.env, GENELOOP_DESKTOP_URL: 'https://geneloop.ai/' },
});
let launchError;
child.once('error', error => { launchError = error; });
const sockets = [];
async function cdp(url) {
  const socket = new WebSocket(url); sockets.push(socket);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
  let id = 0;
  const pending = new Map();
  socket.addEventListener('message', event => {
    const value = JSON.parse(event.data);
    if (!value.id || !pending.has(value.id)) return;
    const request = pending.get(value.id); pending.delete(value.id); clearTimeout(request.timer);
    if (value.error) request.reject(Error(value.error.message)); else request.resolve(value.result);
  });
  socket.addEventListener('close', () => { for (const request of pending.values()) { clearTimeout(request.timer); request.reject(Error('CDP closed')); } pending.clear(); });
  return (method, params = {}) => new Promise((resolve, reject) => {
    const next = ++id;
    const timer = setTimeout(() => { pending.delete(next); reject(Error('CDP timeout: ' + method)); }, 10_000);
    pending.set(next, { resolve, reject, timer }); socket.send(JSON.stringify({ id: next, method, params }));
  });
}
async function until(check, label) {
  const deadline = Date.now() + 35_000;
  while (Date.now() < deadline) {
    if (launchError) throw launchError;
    if (child.exitCode !== null) throw Error('打包程序提前退出：' + child.exitCode);
    const result = await check(); if (result) return result;
    await new Promise(done => setTimeout(done, 200));
  }
  throw Error('等待超时：' + label);
}
const endpoint = `http://127.0.0.1:${port}`;
let command;
try {
  const target = await until(async () => {
    try { return (await (await fetch(endpoint + '/json/list', { signal: AbortSignal.timeout(1000) })).json()).find(page => page.type === 'page' && page.url.startsWith('https://geneloop.ai/')); } catch { return false; }
  }, '打包程序登录工作区');
  command = await cdp(target.webSocketDebuggerUrl);
  const evaluate = async expression => {
    const value = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (value.exceptionDetails) throw Error(value.exceptionDetails.text);
    return value.result.value;
  };
  await until(() => evaluate('/登录|Sign in|Log in/.test(document.body.innerText)'), '本地登录界面');
  assert.deepEqual(await evaluate('[typeof require,typeof process,typeof window.geneLoopDesktop]'), ['undefined', 'undefined', 'undefined']);
  assert.equal(await evaluate("fetch('/login', {credentials:'omit'}).then(response => response.headers.get('x-geneloop-desktop-resource'))"), 'local');
  report.checks.push('实际打包程序从 ASAR 启动并加载本地登录页，无 Node 或桌面 IPC 暴露');
  report.checks.push('公开服务器仅只读接入，未登录、创建会话或调用模型');
  try {
    const screenshot = await command('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(output, 'packaged-login.png'), Buffer.from(screenshot.data, 'base64'));
    report.screenshot = 'packaged-login.png';
  } catch (error) { report.screenshot_unavailable = String(error); }
  report.ok = true;
} catch (error) { report.ok = false; report.error = String(error.stack || error); }
finally {
  if (command) await command('Browser.close').catch(() => {});
  for (const socket of sockets) socket.close();
  if (child.pid && child.exitCode === null) {
    await Promise.race([once(child, 'exit').catch(() => {}), new Promise(done => setTimeout(done, 2000))]);
    if (child.exitCode === null) await new Promise(done => execFile('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true }, () => done()));
  }
  writeFileSync(join(output, 'packaged-summary.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ ...report, artifact_directory: output }, null, 2));
  process.exitCode = report.ok ? 0 : 1;
}
