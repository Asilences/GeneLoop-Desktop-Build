/** Electron / HTTP 桌面诊断，不调用模型，不替代真实场景验收。 */
const { app } = require('electron');
const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const { once } = require('node:events');
const { mkdirSync, readFileSync, writeFileSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { createHash } = require('node:crypto');
const { pathToFileURL } = require('node:url');

const output = resolve(__dirname, '../.local/validation');
mkdirSync(output, { recursive: true });
app.setPath('userData', join(output, 'diagnostic-profile'));
const report = { kind: 'desktop-transport-diagnostic', model_requests: 0, checks: [] };
let desktop, server;
const check = name => { report.checks.push(name); console.log('通过：' + name); };

app.whenReady().then(async () => {
  const { DesktopWorkspace } = await import(pathToFileURL(resolve(__dirname, '../dist/workspace.js')).href);
  const source = 'GeneLoop synthetic download\n';
  server = createServer((request, response) => {
    if (request.url === '/') { response.writeHead(303, { Location: '/workspace', 'Set-Cookie': 'desktop_fixture=synthetic; HttpOnly; SameSite=Lax' }); response.end(); }
    else if (request.url === '/identity') {
      response.writeHead(request.headers.cookie?.includes('desktop_fixture=synthetic') ? 200 : 401, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ fixture: true }));
    } else if (request.url === '/download') {
      response.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename="diagnostic.txt"' }); response.end(source);
    } else {
      response.writeHead(200, { 'Content-Type': 'text/html;charset=utf-8' });
      response.end('<!doctype html><html lang="zh-CN"><title>GeneLoop 桌面传输诊断</title><body><h1>GeneLoop 桌面传输诊断</h1><p>合成页面，不调用模型。</p><a id="download" href="/download" download>下载诊断文件</a><button id="blob">下载 Blob</button><script>document.getElementById("blob").onclick=()=>{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["synthetic blob"],{type:"text/plain"}));a.download="blob.txt";a.click();};</script></body></html>');
    }
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const address = `http://127.0.0.1:${server.address().port}/`;
  const settingsFile = join(output, 'diagnostic-settings.json');
  desktop = new DesktopWorkspace({ settings: { version: 1, server: address, window: { width: 1280, height: 860, maximized: false } }, settingsFile, version: 'diagnostic', downloadsDirectory: output, allowLoopback: true });
  await desktop.ready;
  assert.equal(desktop.state().phase, 'connected');
  assert.equal(new URL(desktop.workspace.webContents.getURL()).pathname, '/workspace');
  assert.equal(await desktop.workspace.webContents.executeJavaScript('fetch("/identity", {credentials:"same-origin"}).then(r=>r.status)'), 200);
  check('同源重定向、HttpOnly Cookie 与带认证 HTTP 请求');
  assert.deepEqual(await desktop.workspace.webContents.executeJavaScript('[typeof require,typeof process,typeof window.geneLoopDesktop]'), ['undefined', 'undefined', 'undefined']);
  assert.equal(desktop.workspace.webContents.getLastWebPreferences().sandbox, true);
  check('工作区无 Node、preload 或本地连接页面 IPC 桥接');

  async function download(id, name, expected) {
    const remoteSession = desktop.workspace.webContents.session;
    const done = new Promise((resolveDone, reject) => {
      remoteSession.once('will-download', (_event, item) => {
        item.setSavePath(join(output, name));
        item.once('done', (_downloadEvent, status) => status === 'completed' ? resolveDone() : reject(new Error('download: ' + status)));
      });
    });
    await desktop.workspace.webContents.executeJavaScript(`document.getElementById(${JSON.stringify(id)}).click()`);
    await Promise.race([done, new Promise((_, reject) => setTimeout(() => reject(new Error('下载超时')), 10_000))]);
    assert.equal(createHash('sha256').update(readFileSync(join(output, name))).digest('hex'), createHash('sha256').update(expected).digest('hex'));
  }
  await download('download', 'download.txt', source);
  await download('blob', 'blob.txt', 'synthetic blob');
  check('HTTP 与 Blob 下载的实际文件及 SHA256 一致');

  const original = desktop.workspace.webContents.id;
  desktop.showSettings();
  assert.equal(await desktop.window.webContents.executeJavaScript('document.getElementById("settings").hidden'), false);
  assert.equal(await desktop.window.webContents.executeJavaScript('window.geneLoopDesktop.state().then(s=>s.phase)'), 'settings');
  writeFileSync(join(output, 'connection-page.png'), (await desktop.window.webContents.capturePage()).toPNG());
  desktop.showWorkspace();
  assert.equal(desktop.workspace.webContents.id, original);
  check('连接设置与工作区切换保留现有页面');

  const rejected = await desktop.window.webContents.executeJavaScript('window.geneLoopDesktop.connect("https://user:private@example.org/")');
  assert.equal(rejected.ok, false);
  assert.equal(desktop.state().server, address);
  check('令牌或凭据地址在连接前拒绝');

  const offline = createServer(); offline.listen(0, '127.0.0.1'); await once(offline, 'listening');
  const unavailable = `http://127.0.0.1:${offline.address().port}/`;
  await new Promise(done => offline.close(done));
  await desktop.connect(unavailable);
  assert.equal(desktop.state().phase, 'error');
  assert.equal(await desktop.window.webContents.executeJavaScript('document.getElementById("retry").hidden'), false);
  await desktop.connect(address);
  assert.equal(desktop.state().phase, 'connected');
  check('连接拒绝显示恢复页面，重连后重新读取工作区');

  if (process.argv.includes('--public')) {
    await desktop.connect('https://geneloop.ai/');
    assert.equal(desktop.state().phase, 'connected');
    const page = await desktop.workspace.webContents.executeJavaScript('document.body.innerText');
    assert.match(page, /登录|Sign in|Log in/i);
    writeFileSync(join(output, 'public-login.png'), (await desktop.workspace.webContents.capturePage()).toPNG());
    report.public_login = true;
    check('正式 GeneLoop 登录页在真实 Electron 工作区加载（未登录、未调用模型）');
  }
  desktop.window.close();
  assert.equal(JSON.parse(readFileSync(settingsFile, 'utf8')).version, 1);
  check('窗口正常关闭并保存设置，不发送任务取消或服务运维请求');
  report.ok = true;
}).catch(error => {
  report.ok = false; report.error = error.stack;
  console.error(error);
}).finally(() => {
  writeFileSync(join(output, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
  if (desktop && !desktop.window.isDestroyed()) desktop.window.destroy();
  server?.closeAllConnections(); server?.close();
  app.exit(report.ok ? 0 : 1);
});
