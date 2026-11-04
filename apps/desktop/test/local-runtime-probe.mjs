import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { rename, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { openWorkspaceReader } from './local-files.mjs';

export const name = 'geneloop-local-runtime-probe';
export const inject = ['agents', 'agentLoop', 'tools'];

async function probe(ctx, reader) {
  const root = process.cwd();
  const { agent } = await ctx.agents.create({
    sessionId: randomUUID(),
    meta: { cwd: root },
    agentOptions: { provider: 'deepseek-official', model: 'deepseek-flash', reasoningEffort: 'off' },
    setup(scope) {
      scope.tools.guard(call => call.name === 'probe_read' ? undefined : 'Tool outside Windows probe');
      scope.tools.register(defineTool({
        name: 'probe_read',
        description: 'Read a synthetic workspace file for the Windows diagnostic',
        parameters: { path: { type: 'string', required: true } },
        output: { schema: { type: 'string' }, render: (_args, text) => [{ type: 'text', text }] },
        async execute({ path }) { return reader.readText(path); },
      }));
    },
  });
  const call = (name, path) => agent.ctx.tools.execute({
    name, callId: randomUUID(), agent, arguments: { path }, signal: new AbortController().signal,
  });
  const read = await call('probe_read', '资料.txt');
  assert.equal(read.isError, false, JSON.stringify(read.error));
  assert.equal(read.value, process.env.GENELOOP_PROBE_TEXT);
  for (const path of ['../outside/secret.txt', resolve(root, '../outside/secret.txt'), '越界/secret.txt', '硬链接.txt', '超长.txt', '资料.txt:alternate', 'NUL']) {
    assert.equal((await call('probe_read', path)).isError, true, path);
  }
  assert.equal((await call('pwsh', '资料.txt')).isError, true);

  agent.followup(createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text', text: 'Windows runtime transport diagnostic' }] }));
  const deadline = Date.now() + 10_000;
  while (!existsSync(process.env.GENELOOP_PROBE_MODEL_PENDING)) {
    assert.ok(Date.now() < deadline, 'Loopback stream never entered waiting state');
    await delay(20);
  }
  assert.equal(agent.status, 'running');
  agent.cancel({ kind: 'user' });
  await agent.whenIdle();
  assert.equal(agent.status, 'idle');
  reader.close();
  assert.throws(() => reader.readText('资料.txt'), /授权已关闭/);
  return {
    pid: process.pid, localRead: true, rejectedTraversalAndJunction: true,
    rejectedHardlinkOversizeAndDevice: true, revocation: true, shellUnavailable: true,
    turnCanceled: true, realModelRequests: 0,
  };
}

export function apply(ctx) {
  void (async () => {
    let reader;
    let outcome;
    try {
      reader = openWorkspaceReader(process.cwd());
      outcome = await probe(ctx, reader);
    } catch (error) {
      outcome = { error: error.stack };
    } finally {
      reader?.close();
    }
    const destination = process.env.GENELOOP_PROBE_RESULT;
    await writeFile(destination + '.tmp', JSON.stringify(outcome));
    await rename(destination + '.tmp', destination);
  })();
}
