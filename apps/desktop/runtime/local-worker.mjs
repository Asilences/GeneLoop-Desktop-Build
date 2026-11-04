import { openLocalFileAgent } from './local-agent.mjs';

export const name = 'geneloop-desktop-file-worker';
export const inject = ['agents', 'agentLoop', 'tools'];

export function apply(ctx) {
  if (!process.send) throw Error('Desktop worker requires a private parent IPC channel');
  const send = message => { if (process.connected) process.send(message, () => {}); };
  const cancellation = new AbortController();
  let started = false, local;

  async function run(task) {
    let off, end;
    try {
      local = await openLocalFileAgent(ctx, {
        directory: task.directory, reports: task.reports, signal: cancellation.signal,
        model: { provider: 'deepseek-official', model: task.model, reasoningEffort: 'off' },
        onReport: report => send({ kind: 'report', report }),
      });
      cancellation.signal.throwIfAborted();
      off = ctx.on('session/event', (session, event) => {
        if (session.id !== local.agent.session.id) return;
        if (event.type === 'assistant/message') {
          const text = event.data.message.content.filter(block => block.type === 'text').map(block => block.text).join('');
          if (text) send({ kind: 'answer', text });
        }
        if (event.type === 'turn/end') end = event.data.reason?.kind;
      });
      local.submit(task.prompt);
      await local.agent.whenIdle();
      await local.close();
      if (cancellation.signal.aborted || end === 'aborted') send({ kind: 'done', status: 'canceled' });
      else if (end === 'completed') send({ kind: 'done', status: 'completed' });
      else send({ kind: 'done', status: 'error', error: '本机任务未正常完成。' });
    } catch {
      await local?.close().catch(() => {});
      send(cancellation.signal.aborted
        ? { kind: 'done', status: 'canceled' }
        : { kind: 'done', status: 'error', error: '无法运行本机任务，请检查目录权限和模型连接。' });
    } finally { off?.(); }
  }

  process.on('message', message => {
    if (message?.kind === 'run' && !started) {
      started = true;
      void run(message);
    } else if (message?.kind === 'cancel') {
      cancellation.abort();
      void local?.cancel().catch(() => {});
    }
  });
  process.once('disconnect', () => {
    cancellation.abort();
    void local?.close().catch(() => {});
  });
  send({ kind: 'ready' });
}
