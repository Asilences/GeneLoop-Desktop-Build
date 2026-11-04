const assert = require('node:assert/strict');
const { app, BrowserWindow, session, webContents } = require('electron');
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
  const local = new LocalWorkspaceWindow({ parent, server: fixture.origin + '/', session: profile });
  try {
    const workspace = { id: 'workspace', name: '本机诊断', directory: fixture.source, updatedAt: Date.now() };
    await local.open(workspace);
    const view = webContents.getAllWebContents().find(contents => contents.getURL().endsWith('/local-workspace.html'));
    assert.ok(view);
    view.setBackgroundThrottling(false);
    const evaluate = code => view.executeJavaScript(code);
    await until(() => evaluate(`document.getElementById('directory').textContent.length>0`), '本机目录展示');
    assert.equal(await evaluate(`document.getElementById('directory').textContent`), fixture.source);
    assert.equal(await evaluate(`document.getElementById('output').textContent`), fixture.reports);
    assert.equal(await evaluate(`!!document.getElementById('choose-output')`), false);
    assert.equal(existsSync(fixture.reports), false, '打开工作区不提前创建输出目录');
    await evaluate(`document.getElementById('prompt').value='读取资料并写报告';document.getElementById('task').requestSubmit()`);
    await until(() => evaluate(`!document.getElementById('send').disabled`), '本机任务结束');
    assert.equal(await evaluate(`document.getElementById('status').textContent`), '任务已完成。');
    assert.match(await evaluate(`document.getElementById('results').innerText`), /报告已保存/);
    assert.ok(await evaluate(`document.querySelector('#results button').textContent.includes('.md')`));
    await evaluate(`document.getElementById('reset-context').click();document.getElementById('prompt').value='等待取消';document.getElementById('task').requestSubmit()`);
    await until(() => existsSync(fixture.waiting), '上游模型处于等待');
    await evaluate(`document.getElementById('cancel').click()`);
    await until(() => evaluate(`document.getElementById('status').textContent==='任务已停止。'`), '取消任务并结算');
    BrowserWindow.fromWebContents(view).destroy();
    await local.open(workspace);
    const reopened = webContents.getAllWebContents().find(contents => contents.getURL().endsWith('/local-workspace.html'));
    assert.ok(reopened && reopened !== view);
    await until(() => reopened.executeJavaScript(`document.querySelectorAll('#history-list li').length===2`), '重新打开工作区后恢复历史任务');
    await reopened.executeJavaScript(`document.querySelector('#history-list li:last-child button').click()`);
    assert.equal(await reopened.executeJavaScript(`document.getElementById('prompt').value`), '读取资料并写报告');
    assert.match(await reopened.executeJavaScript(`document.querySelector('#results button').textContent`), /\.md/);
    await reopened.executeJavaScript("document.querySelector('#history-list li:last-child button:nth-child(2)').click()");
    assert.equal(await reopened.executeJavaScript("document.getElementById('continuation').hidden"), false);
    await reopened.executeJavaScript("document.getElementById('prompt').value='续接测试';document.getElementById('task').requestSubmit()");
    await until(() => reopened.executeJavaScript("document.getElementById('results').innerText.includes('续接成功') && !document.getElementById('send').disabled"), '续接历史任务');

  } finally { local.dispose(); parent.destroy(); }
  app.exit(0);
}).catch(error => { console.error(error); app.exit(1); });
