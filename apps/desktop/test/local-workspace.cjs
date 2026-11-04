const assert = require('node:assert/strict');
const { app, BrowserWindow, dialog, session, webContents } = require('electron');
const { existsSync } = require('node:fs');
const { join } = require('node:path');
const { pathToFileURL } = require('node:url');

const fixture = JSON.parse(process.env.GENELOOP_LOCAL_WINDOW_FIXTURE);
app.setPath('userData', fixture.profile);
const until = async (predicate, label) => {
  const end = Date.now() + 35_000;
  while (Date.now() < end) {
    if (await predicate()) return;
    await new Promise(done => setTimeout(done, 100));
  }
  throw Error('等待超时：' + label);
};
app.whenReady().then(async () => {
  const { LocalWorkspaceWindow } = await import(pathToFileURL(join(__dirname, '../dist/local-workspace.js')).href);
  const profile = session.fromPartition('local-workspace-test');
  await profile.cookies.set({ url: fixture.origin, name: 'harless_sess', value: fixture.cookie });
  const parent = new BrowserWindow({ show: false });
  // Replace only the operating-system chooser. The renderer, IPC, cookie,
  // worker, file handles, upstream HTTP and final file use production paths.
  dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [fixture.reports] });
  const local = new LocalWorkspaceWindow({ parent, server: fixture.origin + '/', session: profile });
  try {
    await local.open({ id: 'workspace', name: '本机诊断', directory: fixture.source, updatedAt: Date.now() });
    const view = webContents.getAllWebContents().find(contents => contents.getURL().endsWith('/local-workspace.html'));
    assert.ok(view);
    view.setBackgroundThrottling(false);
    const evaluate = code => view.executeJavaScript(code);
    await until(() => evaluate(`document.getElementById('directory').textContent.length>0`), '本机目录展示');
    assert.equal(await evaluate(`document.getElementById('directory').textContent`), fixture.source);
    await evaluate(`document.getElementById('choose-output').click()`);
    await until(() => evaluate(`document.getElementById('output').textContent===${JSON.stringify(fixture.reports)}`), '报告目录展示');
    await evaluate(`document.getElementById('prompt').value='读取资料并写报告';document.getElementById('task').requestSubmit()`);
    await until(() => evaluate(`document.getElementById('status').textContent==='任务已完成。'||!document.getElementById('send').disabled`), '本机任务结束');
    assert.equal(await evaluate(`document.getElementById('status').textContent`), '任务已完成。');
    assert.match(await evaluate(`document.getElementById('results').innerText`), /报告已保存/);
    assert.ok(await evaluate(`document.querySelector('#results button').textContent.includes('.md')`));
    await evaluate(`document.getElementById('prompt').value='等待取消';document.getElementById('task').requestSubmit()`);
    await until(() => existsSync(fixture.waiting), '上游模型处于等待');
    await evaluate(`document.getElementById('cancel').click()`);
    await until(() => evaluate(`document.getElementById('status').textContent==='任务已停止。'`), '取消任务并结算');

  } finally { local.dispose(); parent.destroy(); }
  app.exit(0);
}).catch(error => { console.error(error); app.exit(1); });
