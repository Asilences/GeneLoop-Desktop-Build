import { randomUUID } from 'node:crypto';
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { openReportWriter, openWorkspaceReader } from './local-files.mjs';
import { registerLocalFileTools } from './local-file-tools.mjs';

// Constructed by the trusted desktop worker after native directory approval.
export async function openLocalFileAgent(ctx, { directory, reports, model }) {
  const reader = openWorkspaceReader(directory);
  let writer, handle;
  try {
    if (reports) writer = openReportWriter(reports, directory);
    handle = await ctx.agents.create({
      sessionId: randomUUID(),
      meta: { cwd: directory },
      agentOptions: model,
      setup(scope) { registerLocalFileTools(scope, reader, writer); },
    });
  } catch (error) {
    writer?.close();
    reader.close();
    throw error;
  }
  const { agent } = handle;
  let closing;
  return {
    agent,
    submit(text) {
      if (closing) throw Error('本机会话已关闭。');
      if (agent.status !== 'idle') throw Error('请等待当前本机任务完成。');
      if (typeof text !== 'string' || !text.trim()) throw Error('请输入本机文件任务。');
      agent.followup(createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text', text }] }));
    },
    async cancel() {
      agent.cancel({ kind: 'user' });
      await agent.whenIdle();
    },
    close() {
      // Revoke file capabilities immediately, even if Agent disposal must wait.
      if (!closing) {
        writer?.close();
        reader.close();
        closing = Promise.resolve().then(() => handle.dispose());
      }
      return closing;
    },
  };
}
