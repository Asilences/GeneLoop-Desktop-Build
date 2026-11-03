/** 固定 DSH 的真实 UI/协议诊断；不发送模型任务，不作为 Agent 效果验收。 */
const { app, session } = require('electron');
const assert = require('node:assert/strict');
const { mkdirSync, readFileSync, writeFileSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { createHash } = require('node:crypto');
const { pathToFileURL } = require('node:url');
const validation = resolve(__dirname, '../.local/validation');
const output = join(validation, process.env.GENELOOP_DESKTOP_DIAGNOSTIC_RUN_ID || require('node:crypto').randomUUID());
mkdirSync(output, { recursive: true });
app.setPath('userData', join(output, 'local-ui-profile'));
app.disableHardwareAcceleration();
const report = { kind: 'desktop-local-ui-diagnostic', model_requests: 0, checks: [] };
report.console_errors = [];
app.on('web-contents-created', (_event, contents) => contents.on('console-message', details => {
  if (details.level === 'error' && report.console_errors.length < 20) report.console_errors.push(details.message.slice(0, 800));
}));
let desktop;
const check = name => { report.checks.push(name); console.log('通过：' + name); };
async function until(fn, label) {
  const end = Date.now() + 20_000;
  while (Date.now() < end) { if (await fn()) return; await new Promise(done => setTimeout(done, 100)); }
  throw Error('等待超时：' + label);
}

app.whenReady().then(async () => {
  const { DesktopWorkspace } = await import(pathToFileURL(resolve(__dirname, '../dist/workspace.js')).href);
  const { readBootDocument } = await import(pathToFileURL(resolve(__dirname, '../dist/boot-request.js')).href);
  const coldRequests = [];
  const coldServer = require('node:http').createServer((request, response) => {
    coldRequests.push(request.url);
    if (request.url === '/pending') return;
    if (request.url === '/cookie') { response.end(request.headers.cookie || 'no-cookie'); return; }
    response.writeHead(303, { location: '/starting?next=%2F' }); response.end();
  });
  coldServer.listen(0, '127.0.0.1'); await require('node:events').once(coldServer, 'listening');
  try {
    const coldSession = session.fromPartition('geneloop-cold-start-diagnostic');
    const coldOrigin = `http://127.0.0.1:${coldServer.address().port}/`;
    const cold = await readBootDocument(coldSession, new Request(coldOrigin));
    assert.equal(cold.status, 303);
    assert.equal(new URL(cold.headers.get('location')).pathname, '/starting');
    assert.deepEqual(coldRequests, ['/']);
    check('原生网络保留冷启动 /starting 跳转，不误判为登录页');
    await coldSession.cookies.set({ url: coldOrigin, name: 'synthetic', value: 'diagnostic', path: '/' });
    assert.match(await (await readBootDocument(coldSession, new Request(coldOrigin + 'cookie'))).text(), /synthetic=diagnostic/);
    assert.equal(await (await readBootDocument(coldSession, new Request(coldOrigin + 'cookie', { credentials: 'omit' }))).text(), 'no-cookie');
    const controller = new AbortController();
    const pending = readBootDocument(coldSession, new Request(coldOrigin + 'pending', { signal: controller.signal }));
    setTimeout(() => controller.abort(), 30);
    await assert.rejects(Promise.race([pending, new Promise((_, reject) => setTimeout(() => reject(Error('cancel timeout')), 2000))]), /取消/);
    check('启动请求尊重 omit，取消会结束 Promise');
  } finally { coldServer.closeAllConnections(); await new Promise(done => coldServer.close(done)); }
  const accessFile = process.env.GENELOOP_DESKTOP_PROBE_ACCESS_FILE;
  if (!accessFile) throw Error('需要隔离的 npm run web 协议诊断服务；设置 GENELOOP_DESKTOP_PROBE_ACCESS_FILE。');
  const access = readFileSync(accessFile, 'utf8').trim();
  const server = new URL(access).origin + '/';
  const runId = process.env.GENELOOP_DESKTOP_DIAGNOSTIC_RUN_ID;
  assert.match(runId || '', /^[a-f0-9]{32}$/);
  assert.equal(resolve(accessFile), resolve(__dirname, '../../../.local/web/runs', runId, 'access-url.txt'));
  assert.equal(new URL(server).hostname, '127.0.0.1', '诊断写入严格限制在本机 fixture');
  assert.equal(new URL(server).protocol, 'http:');
  assert.equal(app.isPackaged, false);
  const effective = JSON.parse(readFileSync(resolve(accessFile, '../effective-config.json'), 'utf8'));
  assert.equal(effective.provider_mode, 'mock');
  assert.equal(effective.real_models_enabled, false);
  const partition = 'persist:geneloop-' + createHash('sha256').update(server).digest('hex').slice(0, 24);
  const remoteSession = session.fromPartition(partition);
  await remoteSession.fetch(access, { credentials: 'include' });
  assert.ok((await remoteSession.cookies.get({ url: server })).length);
  check('原生 DSH 浏览器认证 Cookie 进入隔离桌面会话');
  // 与正式成员环境一样先准备一个服务器工作区；不通过模型创建内容。
  const created = await remoteSession.fetch(server + 'api/harless/workspaces', {
    method: 'POST', credentials: 'include', headers: { 'content-type': 'application/json', origin: new URL(server).origin, 'sec-fetch-site': 'same-origin' },
    body: JSON.stringify({ name: '桌面诊断', request_id: require('node:crypto').randomUUID() }),
  });
  const workspace = await created.json();
  assert.ok(workspace.workspace?.workspaceId, JSON.stringify(workspace));
  const emptySession = await remoteSession.fetch(server + 'api/session/create', {
    method: 'POST', credentials: 'include', headers: { 'content-type': 'application/json', origin: new URL(server).origin, 'sec-fetch-site': 'same-origin' },
    body: JSON.stringify({ type: 'client-request', rpcId: require('node:crypto').randomUUID(), method: 'session/create', payload: { args: { request: { workspaceId: workspace.workspace.workspaceId } } } }),
  });
  const emptySessionResult = await emptySession.json();
  assert.equal(emptySessionResult.result?.ok, true, JSON.stringify(emptySessionResult));
  desktop = new DesktopWorkspace({ settings: { version: 1, server, window: { width: 1280, height: 860, maximized: false } }, settingsFile: join(output, 'local-ui-settings.json'), version: 'diagnostic', downloadsDirectory: output, allowLoopback: true, closeToTray: true });
  await desktop.ready;
  assert.equal(desktop.state().phase, 'connected', desktop.state().message);
  const contents = desktop.workspace.webContents;
  contents.on('console-message', details => {
    if (details.level === 'error') console.log('UI console error: ' + details.message.slice(0, 220));
  });
  await until(async () => contents.executeJavaScript('Boolean(window.__DSH_BOOT__?.entries?.length > 10 && window.__ModuleLoader__)'), '原生客户端图');
  await contents.executeJavaScript(`(() => { const picker = [...document.querySelectorAll('button')].find(button => button.textContent.trim() === '选择工作区'); picker?.click(); })()`);
  await until(async () => contents.executeJavaScript(`Boolean([...document.querySelectorAll('button')].find(button => button.textContent.includes('桌面诊断')))`), '已登记服务器工作区');
  await contents.executeJavaScript(`(() => { const item = [...document.querySelectorAll('button')].find(button => button.textContent.includes('桌面诊断')); item.click(); })()`);
  await until(async () => contents.executeJavaScript('document.body.innerText.includes("GeneLoop") && !Array.from(document.querySelectorAll(".geneloop-page-loader")).some(e=>!e.hidden)'), 'GeneLoop 原生界面初始化');
  report.local = desktop.frontend.served.local;
  report.network = desktop.frontend.served.network;
  assert.ok(desktop.frontend.served.localScripts.some(path => /^\/assets\/index-.*\.js$/.test(path)), '前端入口必须从安装资源加载');
  assert.ok(desktop.frontend.served.localScripts.filter(path => path === '/plugins/').length >= 2, 'bootstrap 和 application 插件批次必须从安装资源加载');
  assert.deepEqual(desktop.frontend.served.networkScripts, [], '不得从服务器加载 UI 脚本或样式');
  report.local_script_requests = desktop.frontend.served.localScripts;
  assert.deepEqual(await contents.executeJavaScript('[typeof require,typeof process,typeof window.geneLoopDesktop]'), ['undefined', 'undefined', 'undefined']);
  check('本地打包的 DSH 原生聊天/设置/场景组件加载，无本地 Node 权限');
  await contents.executeJavaScript(`(() => { const button = [...document.querySelectorAll('button')].find(item => item.textContent.trim() === '新会话'); button?.click(); })()`);
  await until(async () => contents.executeJavaScript('Boolean(document.querySelector(\'[contenteditable="true"]\'))'), '服务器新会话与输入框');
  check('通过原生接口创建服务器空会话并恢复输入框，未发送模型消息');
  const source = 'GeneLoop desktop download diagnostic\n';
  const downloaded = new Promise((resolveDownload, reject) => {
    contents.session.once('will-download', (_event, item) => {
      item.setSavePath(join(output, 'download-diagnostic.txt'));
      item.once('done', (_downloadEvent, state) => state === 'completed' ? resolveDownload() : reject(Error('下载未完成：' + state)));
    });
  });
  await contents.executeJavaScript(`(() => { const anchor = document.createElement('a'); const url = URL.createObjectURL(new Blob([${JSON.stringify(source)}], {type:'text/plain'})); anchor.href=url; anchor.download='download-diagnostic.txt'; anchor.click(); setTimeout(()=>URL.revokeObjectURL(url),5000); })()`);
  await Promise.race([downloaded, new Promise((_, reject) => setTimeout(() => reject(Error('下载超时')), 10_000))]);
  assert.equal(readFileSync(join(output, 'download-diagnostic.txt'), 'utf8'), source);
  check('原生下载实际保存字节与合成来源一致');
  const before = contents.id;
  desktop.showSettings();
  await until(async () => desktop.window.webContents.executeJavaScript('!document.getElementById("settings").hidden'), '桌面连接设置');
  desktop.showWorkspace();
  assert.equal(desktop.workspace.webContents.id, before);
  check('桌面标题栏、连接设置和原工作区切换保留页面');
  desktop.window.close();
  assert.equal(desktop.window.isDestroyed(), false);
  assert.equal(desktop.window.isVisible(), false);
  desktop.window.show();
  check('关闭窗口隐藏到托盘，恢复后保持原工作区');
  const unavailable = require('node:net').createServer();
  unavailable.listen(0, '127.0.0.1'); await require('node:events').once(unavailable, 'listening');
  const unavailableUrl = `http://127.0.0.1:${unavailable.address().port}/`;
  await new Promise(done => unavailable.close(done));
  await desktop.connect(unavailableUrl);
  assert.equal(desktop.state().phase, 'error');
  await desktop.connect(server);
  assert.equal(desktop.state().phase, 'connected');
  await until(async () => desktop.workspace.webContents.executeJavaScript('document.body.innerText.includes("GeneLoop")'), '重连工作区');
  check('连接失败显示恢复页，重连重新读取服务器状态而不重发模型消息');
  try {
    await new Promise(done => setTimeout(done, 300));
    writeFileSync(join(output, 'local-workspace.png'), (await desktop.workspace.webContents.capturePage()).toPNG());
    report.screenshot = 'local-workspace.png';
  } catch (error) { report.screenshot_unavailable = String(error); }
  report.graph_entries = await desktop.workspace.webContents.executeJavaScript('window.__DSH_BOOT__.entries.length');
  if (process.argv.includes('--public')) {
    await desktop.connect('https://geneloop.ai/');
    assert.equal(desktop.state().phase, 'connected', desktop.state().message);
    await until(async () => desktop.workspace.webContents.executeJavaScript('/登录|Sign in|Log in/.test(document.body.innerText)'), '正式服务的本地登录界面');
    report.public_login = true;
    assert.ok(desktop.frontend.served.local > 0);
    check('正式服务认证接入；登录界面仍从本地安装资源加载，未登录或调用模型');
    try { writeFileSync(join(output, 'public-login.png'), (await desktop.workspace.webContents.capturePage()).toPNG()); } catch {}
  }
  desktop.permitClose(); desktop.window.close();
  report.ok = true;
}).catch(async error => {
  report.ok = false; report.error = error.stack; report.resources = desktop?.frontend?.diagnostics;
  try {
    report.body = await desktop.workspace.webContents.executeJavaScript('document.body.innerText');
    writeFileSync(join(output, 'failed-workspace.png'), (await desktop.workspace.webContents.capturePage()).toPNG());
  } catch {}
  console.error(error);
  if (report.console_errors.length) console.error(report.console_errors.join('\n'));
}).finally(() => {
  writeFileSync(join(output, 'local-ui-summary.json'), JSON.stringify(report, null, 2) + '\n');
  writeFileSync(join(validation, 'local-ui-summary.json'), JSON.stringify({ ...report, artifact_directory: output }, null, 2) + '\n');
  if (desktop && !desktop.window.isDestroyed()) desktop.window.destroy();
  app.exit(report.ok ? 0 : 1);
});
