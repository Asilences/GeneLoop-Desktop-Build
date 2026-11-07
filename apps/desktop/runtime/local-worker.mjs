import { openLocalFileAgent } from './local-agent.mjs';
import { randomUUID } from 'node:crypto';
import {LocalAttachmentStore} from '@deepseek-ai/dsh-attachment-local';

export const name = 'geneloop-desktop-file-worker';
export const inject = ['agents', 'agentLoop', 'tools', 'sandbox', 'subprocess'];

export function apply(ctx) {
  if (!process.send) throw Error('Desktop worker requires a private parent IPC channel');
  if(!ctx.get('attachments'))new LocalAttachmentStore(ctx,{dshHome:process.env.DSH_HOME});
  const send = message => { if (process.connected) process.send(message, () => {}); };
  const cancellation = new AbortController();
  let started = false, local, videoDenied = false;
  const approvals = new Map();
  const questions = new Map();
  cancellation.signal.addEventListener('abort', () => {
    for (const resolve of approvals.values()) resolve(false);
    approvals.clear();
    for(const pending of questions.values())pending.reject(Error('问题已取消'));
    questions.clear();
  }, { once: true });
  const approveVideo = request => new Promise(resolve => {
    if (videoDenied || approvals.size || cancellation.signal.aborted || !process.connected) return resolve(false);
    const id = randomUUID();
    approvals.set(id, resolve);
    send({ kind: 'video-approval', id, request });
  });
  const approveFilePlan=request=>new Promise(resolve=>{
    if(approvals.size||cancellation.signal.aborted||!process.connected)return resolve(false);
    const id=randomUUID();approvals.set(id,resolve);send({kind:'file-approval',id,request});
  });
  const askUser=request=>new Promise((resolve,reject)=>{
    if(cancellation.signal.aborted||request.signal?.aborted||!process.connected)return reject(Error('本机问题已取消'));
    const id=randomUUID(),cleanup=()=>request.signal?.removeEventListener('abort',aborted);
    const pending={resolve:value=>{cleanup();resolve(value);},reject:error=>{cleanup();reject(error);}};
    const aborted=()=>{if(!questions.delete(id))return;pending.reject(Error('本机问题已取消'));send({kind:'question-cleared',id});};
    questions.set(id,pending);request.signal?.addEventListener('abort',aborted,{once:true});
    send({kind:'question',id,questions:request.questions});
  });

  async function run(task) {
    let off, end;
    try {
      local = await openLocalFileAgent(ctx, {
        directory: task.directory, signal: cancellation.signal, sessionId: task.sessionId, resume: task.resume, scene: task.scene, media: task.media,legacyTools:task.legacyTools===true,fullWorkflows:task.fullWorkflows===true,commonCapabilities:task.commonCapabilities===true,approveFilePlan,askUser,
        model: { provider: 'deepseek-official', model: task.model, reasoningEffort: 'off' },
        onReport: report => send({ kind: 'report', report }),
        approveVideo: task.videoRendering === true ? approveVideo : undefined, ppt: task.ppt,
        onVideoPhase: phase => send({ kind: 'progress', phase }),
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
    } else if(message?.kind==='question-answered') {
      const pending=questions.get(message.id);if(!pending)return;
      questions.delete(message.id);pending.resolve({answers:message.answers});
    } else if(message?.kind==='file-approved') {
      const resolve=approvals.get(message.id);if(!resolve)return;
      approvals.delete(message.id);resolve(message.allowed===true);
    } else if (message?.kind === 'video-approved') {
      const resolve = approvals.get(message.id);
      if (!resolve) return;
      approvals.delete(message.id);
      videoDenied = message.allowed !== true;
      resolve(!videoDenied);
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
