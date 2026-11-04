import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
import { rename, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { openReportWriter, openWorkspaceReader } from './local-files.mjs';
import { openLocalFileAgent } from './local-agent.mjs';

export const name = 'geneloop-local-runtime-probe';
export const inject = ['agents', 'agentLoop', 'tools'];

async function probe(local) {
  const root = process.cwd();
  const { agent } = local;
  const call = (name, path) => agent.ctx.tools.execute({
    name, callId: randomUUID(), agent, arguments: { path }, signal: new AbortController().signal,
  });
  const read = await call('local_read', '资料.txt');
  assert.equal(read.isError, false, JSON.stringify(read.error));
  assert.equal(read.value, process.env.GENELOOP_PROBE_TEXT);
  for (const path of ['../outside/secret.txt', resolve(root, '../outside/secret.txt'), '越界/secret.txt', '硬链接.txt', '超长.txt', '资料.txt:alternate', 'NUL']) {
    assert.equal((await call('local_read', path)).isError, true, path);
  }
  assert.equal((await call('pwsh', '资料.txt')).isError, true);

  local.submit('Windows runtime transport diagnostic');
  const deadline = Date.now() + 10_000;
  while (!existsSync(process.env.GENELOOP_PROBE_MODEL_PENDING)) {
    assert.ok(Date.now() < deadline, 'Loopback stream never entered waiting state');
    await delay(20);
  }
  assert.equal(agent.status, 'running');
  await local.cancel();
  assert.equal(agent.status, 'idle');
  const disposed = local.close();
  assert.equal(local.close(), disposed);
  await disposed;
  assert.throws(() => local.submit('已关闭'), /本机会话已关闭/);
  return {
    pid: process.pid, localRead: true, rejectedTraversalAndJunction: true,
    rejectedHardlinkOversizeAndDevice: true, revocation: true, shellUnavailable: true,
    reportOutputJunctionRejected: true, enumerationBounded: true, turnCanceled: true, realModelRequests: 0,
  };
}

export function apply(ctx) {
  void (async () => {
    let local;
    let outcome;
    try {
      const directory = process.cwd();
      const reader = openWorkspaceReader(directory);
      try {
        assert.deepEqual(reader.list('空目录'), { entries: [], truncated: false });
        const large = reader.list('大量文件');
        assert.equal(large.entries.length, 200);
        assert.equal(large.truncated, true);
        assert.throws(() => reader.list('越界'));
      } finally {
        reader.close();
      }
      assert.throws(() => reader.readText('资料.txt'), /授权已关闭/);
      const blocked = openReportWriter(resolve(directory, '../重解析测试'));
      try { assert.throws(() => blocked.writeMarkdown('禁止越界写入'), /重解析点/); }
      finally { blocked.close(); }
      const writer = openReportWriter(directory);
      writer.close();
      assert.throws(() => writer.writeMarkdown('已撤销'), /授权已关闭/);

      local = await openLocalFileAgent(ctx, {
        directory,
        model: { provider: 'deepseek-official', model: 'deepseek-flash', reasoningEffort: 'off' },
      });
      outcome = await probe(local);
    } catch (error) {
      outcome = { error: error.stack };
    } finally {
      await local?.close().catch(error => { outcome = { error: error.stack }; });
    }
    const destination = process.env.GENELOOP_PROBE_RESULT;
    await writeFile(destination + '.tmp', JSON.stringify(outcome));
    await rename(destination + '.tmp', destination);
  })();
}
