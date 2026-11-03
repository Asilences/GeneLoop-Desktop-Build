/** 启动实际 Windows 安装资源；仅只读检查公开登录页，不登录或发送模型消息。 */
import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createServer } from 'node:net';
import { basename, dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
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
assert.ok(files.includes('/ui/desktop/app.js'));
assert.equal(files.some(file=>file.startsWith('/node_modules/')),false,'独立桌面无DSH或其他生产运行时依赖');
assert.equal(files.some(file=>/^\/assets\/(frontend|clients)\//.test(file)||file==='/dist/boot-request.js'),false,'独立桌面不打包网页、网页插件或启动图解析器');
assert.deepEqual(files.filter(file => /^\/(?:\.local|test|src)\//.test(file) || /^\/\.env/.test(file)), []);
const manifest = JSON.parse(asar.extractFile(archive, 'assets/manifest.json'));
assert.equal(manifest.frontend,'geneloop-independent-desktop');
const report = { kind: 'independent-desktop-packaged-readonly-diagnostic', model_requests: 0, source_commit: manifest.sourceCommit, renderer_files: manifest.rendererFiles, checks: ['ASAR仅包含独立桌面与品牌资源，不含DSH网页、插件模块、生产Node依赖或私有文件'] };
const listener = createServer().listen(0, '127.0.0.1');
await once(listener, 'listening');
const port = listener.address().port;
await new Promise(done => listener.close(done));
// 源码目录中的祖先 node_modules 会掩盖安装包缺失依赖。使用系统临时目录的
// 完整独立副本，模拟安装后的目录布局；不执行NSIS，不改用户的安装或注册表。
const temporary = realpathSync(tmpdir());
const isolatedRoot = mkdtempSync(join(temporary, 'geneloop-desktop-'));
for (let ancestor = isolatedRoot; ; ancestor = dirname(ancestor)) {
  assert.equal(existsSync(join(ancestor, 'node_modules')), false, '隔离目录祖先不能提供开发依赖：' + ancestor);
  if (ancestor === dirname(ancestor)) break;
}
const isolatedApp = join(isolatedRoot, 'GeneLoop Desktop');
cpSync(join(app, 'release/win-unpacked'), isolatedApp, { recursive: true, dereference: true });
report.checks.push('独立目录包含完整安装布局，祖先无 node_modules，不借用源码依赖');
const executable = join(isolatedApp, 'GeneLoop Desktop.exe');
const environment = { ...process.env, GENELOOP_DESKTOP_URL: 'https://geneloop.ai/' };
delete environment.NODE_PATH;
delete environment.NODE_OPTIONS;
delete environment.ELECTRON_RUN_AS_NODE;
const child = spawn(executable, [`--remote-debugging-port=${port}`, `--user-data-dir=${join(output, 'profile')}`], {
  cwd: dirname(executable), windowsHide: true, stdio: 'ignore',
  env: environment,
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
    if (value.exceptionDetails) throw Error(value.exceptionDetails.exception?.description || value.exceptionDetails.text);
    return value.result.value;
  };
  await until(() => evaluate('Boolean(document.body && /登录|Sign in|Log in/.test(document.body.innerText))'), '本地登录界面');
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
    if (child.exitCode === null) { report.ok=false;report.error='打包程序正常退出超时，清理本次诊断子进程。';await new Promise(done => execFile('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true }, () => done())); }
  }
  report.process_exit_code=child.exitCode;
  if(child.exitCode!==0){report.ok=false;report.error??='打包程序未正常退出。';}
  writeFileSync(join(output, 'packaged-summary.json'), JSON.stringify(report, null, 2) + '\n');
  // 只删除本脚本刚创建的临时副本，先核对绝对目标与临时根目录。
  const target = realpathSync(isolatedRoot);
  assert.equal(dirname(target).toLowerCase(), resolve(temporary).toLowerCase());
  assert.ok(basename(target).startsWith('geneloop-desktop-'));
  rmSync(target, { recursive: true, force: true, maxRetries: 3, retryDelay: 300 });
  console.log(JSON.stringify({ ...report, artifact_directory: output }, null, 2));
  process.exitCode = report.ok ? 0 : 1;
}
