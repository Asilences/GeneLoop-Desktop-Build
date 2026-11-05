const assert = require('node:assert/strict');
const { app, session } = require('electron');
const { randomUUID } = require('node:crypto');
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
  const { LocalWorkspaceConversation } = await import(pathToFileURL(join(__dirname, '../dist/local-workspace.js')).href);
  const profile = session.fromPartition('local-workspace-test');
  await profile.cookies.set({ url: fixture.origin, name: 'harless_sess', value: fixture.cookie });
  const create = () => new LocalWorkspaceConversation({ server: fixture.origin + '/', session: profile });
  const local = create();
  const workspace = { id: 'workspace', name: '本机诊断', directory: fixture.source, updatedAt: Date.now() };
  const threadId = randomUUID();
  try {
    assert.deepEqual(local.history(workspace), []);
    assert.equal(existsSync(fixture.reports), false, '打开工作区不提前创建输出目录');
    await assert.rejects(local.start(workspace, { scene: 'unknown', threadId, prompt: '禁止发送' }, () => {}), /暂不支持本机/);
    await local.start(workspace, { scene: 'files', threadId, prompt: '读取资料并写报告' }, () => {});
    const [first] = local.history(workspace);
    assert.equal(first.updates.at(-1).status, 'completed');
    assert.match(first.updates.find(event => event.kind === 'answer').text, /报告已保存/);
    assert.match(first.updates.find(event => event.kind === 'report').report.name, /\.md/);
    const cancelThread = randomUUID();
    const pending = local.start(workspace, { scene: 'files', threadId: cancelThread, prompt: '等待取消' }, () => {});
    await until(() => existsSync(fixture.waiting), '上游模型处于等待');
    local.cancel(workspace.id, cancelThread);
    await pending;
    assert.equal(local.history(workspace)[0].updates.at(-1).status, 'canceled');
    const reopened = create();
    try {
      assert.equal(reopened.history(workspace)[1].prompt, '读取资料并写报告');
      await reopened.start(workspace, { scene: 'files', threadId, prompt: '续接测试' }, () => {});
      const [next] = reopened.history(workspace);
      assert.equal(next.sessionId, first.sessionId);
      assert.match(next.updates.find(event => event.kind === 'answer').text, /续接成功/);
    } finally { reopened.dispose(); }
    for (const scene of ['chat','data','paper','ppt','video']) {
      const updates=[];
      await local.start(workspace, {scene,threadId:randomUUID(),prompt:'诊断-'+scene}, update=>updates.push(update));
      assert.equal(updates.at(-1)?.status,'completed',scene+' '+JSON.stringify(updates.at(-1)));
      const answers = updates.filter(update=>update.kind==='answer');
      assert.match(answers.at(-1)?.text ?? '',new RegExp('诊断完成 '+scene));
      if (scene==='ppt'||scene==='video') {
        const extension=scene==='ppt'?'.pptx':'.mp4';
        assert.ok(updates.some(update=>update.kind==='report'&&update.report.name.endsWith(extension)),scene);
      }
    }
  } finally { local.dispose(); }
  app.exit(0);
}).catch(error => { console.error(error); app.exit(1); });
