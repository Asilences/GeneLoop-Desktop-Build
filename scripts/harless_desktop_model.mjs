import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { localSceneTools } from '../apps/desktop/runtime/local-scenes.mjs';
import { desktopVideoInput, desktopVideoRequestLimit, desktopVideoSandbox, renderDesktopVideo } from '../src/adapters/geneloop_desktop_video.ts';

export const DESKTOP_MODEL_PATH = '/api/harless/desktop-model';
const leaseMs = 10 * 60_000;
const requestFields = new Set(['model', 'messages', 'stream', 'stream_options', 'thinking', 'tools', 'temperature', 'max_tokens', 'stop']);
const roles = new Set(['system', 'user', 'assistant', 'tool']);
const validPayload = (value, model, tools) => {
  const localFunction = entry => entry?.type === 'function' && tools.has(entry.function?.name);
  return value?.model === model && value.stream === true &&
  Object.keys(value).every(key => requestFields.has(key)) &&
  (value.thinking === undefined || value.thinking?.type === 'disabled') &&
  Array.isArray(value.messages) && value.messages.every(message =>
    roles.has(message?.role) && typeof message.content === 'string' &&
    (message.tool_calls === undefined || (Array.isArray(message.tool_calls) && message.tool_calls.every(localFunction)))) &&
  (value.tools === undefined || (Array.isArray(value.tools) && value.tools.every(localFunction)));
};
const hash = value => createHash('sha256').update(value).digest('hex');

export function createDesktopModelRoute({ config, json, requireOrigin, sessionHash, isSessionActive, readBounded, forward, videoRenderer }) {
  if (config.desktopLocalModel == null || config.desktopLocalModel === false) return null;
  const accountIds = config.desktopLocalModel.accountIds;
  if (!Array.isArray(accountIds) || !accountIds.length || accountIds.some(id => typeof id !== 'string' || !id.trim())) {
    throw Error('Desktop model pilot requires explicit account IDs');
  }
  const allowed = new Set(accountIds);
  if (!config.apiKey || !config.memberPolicy?.control_token ||
      !config.upstreamControlPort || !config.upstreamBrokerPort) {
    throw Error('Desktop model pilot requires the existing budget control and broker');
  }

  const model = 'deepseek-flash';
  const video = config.desktopLocalModel.videoRendering === true
    ? config.desktopLocalModel.videoSandbox ? desktopVideoSandbox(config.desktopLocalModel.videoSandbox) : videoRenderer
    : undefined;
  if (config.desktopLocalModel.videoRendering === true && !video) throw Error('Desktop video requires the configured Remotion renderer');
  const byToken = new Map(), byAccount = new Map();
  let stopping = false, rendering = false;

  async function control(port, path, body) {
    const response = await fetch('http://127.0.0.1:' + port + path, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
      headers: { 'content-type': 'application/json', 'x-sss-control-token': config.memberPolicy.control_token },
      body: JSON.stringify(body),
    });
    await response.body?.cancel();
    if (!response.ok) throw Error('Budget control rejected ' + path);
  }

  function close(lease) {
    if (lease.settlement) return lease.settlement;
    clearTimeout(lease.timer);
    byToken.delete(lease.tokenHash);
    lease.abort?.();
    lease.render?.abort();
    lease.settlement = (async () => {
      await lease.admission.catch(() => {});
      const operations = [];
      if (lease.bindingAttempted) operations.push(control(config.upstreamBrokerPort, '/unbind', lease.binding));
      if (lease.registrationAttempted) operations.push(control(config.upstreamControlPort, '/tasks/cancel', { session_id: lease.binding.budget_session_id }));
      const outcomes = await Promise.allSettled(operations);
      if (outcomes.some(outcome => outcome.status === 'rejected')) {
        console.error('Desktop model lease settlement failed for task ' + lease.task);
      }
      if (byAccount.get(lease.userId) === lease) byAccount.delete(lease.userId);
    })();
    return lease.settlement;
  }

  const valid = lease => lease && !lease.settlement && lease.expiresAt > Date.now() && isSessionActive(lease.session, lease.userId);

  async function issue(req, res, user, tools) {
    const session = sessionHash(req);
    const existing = byAccount.get(user.id);
    if (existing && !valid(existing)) await close(existing);
    if (stopping || !isSessionActive(session, user.id)) return json(res, 401, { error: '请重新登录。' });
    if (byAccount.has(user.id)) return json(res, 409, { error: '已有本机任务，请先结束该任务。' });

    const token = randomBytes(32).toString('base64url');
    const task = hash(user.id).slice(0, 8) + randomBytes(12).toString('hex');
    const lease = {
      tokenHash: hash(token), task, session, userId: user.id, tools, expiresAt: Date.now() + leaseMs,
      binding: { session_id: 'session-' + randomUUID(), budget_session_id: 'turn-' + task },
    };
    byAccount.set(user.id, lease);
    lease.admission = (async () => {
      lease.registrationAttempted = true;
      await control(config.upstreamControlPort, '/tasks/register', {
        task_id: task, session_id: lease.binding.budget_session_id, model,
        budget_usd: config.memberPolicy.budget_usd ?? null,
      });
      await control(config.upstreamControlPort, '/tasks/activate', { session_id: lease.binding.budget_session_id });
      lease.bindingAttempted = true;
      await control(config.upstreamBrokerPort, '/bind', lease.binding);
    })();
    try {
      await lease.admission;
      if (!valid(lease) || res.destroyed) {
        await close(lease);
        if (!res.destroyed) return json(res, 401, { error: '本机任务授权已结束。' });
        return;
      }
      byToken.set(lease.tokenHash, lease);
      lease.timer = setTimeout(() => void close(lease), lease.expiresAt - Date.now()).unref();
      return json(res, 200, { token, model, expiresAt: lease.expiresAt,
        ...(video && tools.has('hybrid_video_render') ? { videoRendering: true } : {}),
      });
    } catch {
      await close(lease);
      return json(res, 503, { error: '模型计量服务暂不可用。' });
    }
  }

  return {
    async handle(req, res, path, user) {
      if (path === DESKTOP_MODEL_PATH + '/lease' && req.method === 'POST') {
        if (!user || !allowed.has(user.id) || !requireOrigin(req)) return json(res, 403, { error: '请先登录已获授权的试用账号。' });
        const body = await readBounded(req);
        let input;
        try { input = JSON.parse(body.toString('utf8')); } catch { return json(res, 400, { error: '无效的本机任务授权请求。' }); }
        const tools = input && !Array.isArray(input) && typeof input === 'object' &&
          Object.keys(input).every(key => key === 'scene') && localSceneTools(Object.hasOwn(input, 'scene') ? input.scene : 'files');
        if (!tools) return json(res, 400, { error: '无效的本机场景授权请求。' });
        return issue(req, res, user, new Set(tools));
      }
      const authorization = req.headers.authorization;
      const token = typeof authorization === 'string' ? /^Bearer ([A-Za-z0-9_-]{43})$/.exec(authorization)?.[1] : undefined;
      const lease = token ? byToken.get(hash(token)) : undefined;
      if (path === DESKTOP_MODEL_PATH + '/lease' && req.method === 'DELETE') {
        if (lease) await close(lease);
        return json(res, 200, { ok: true });
      }
      if (path === DESKTOP_MODEL_PATH + '/video/render' && req.method === 'POST') {
        if (!video) return json(res, 404, { error: '服务器未启用桌面 Remotion 渲染。' });
        if (!valid(lease) || !lease.tools.has('hybrid_video_render')) return json(res, 403, { error: '该任务未获视频渲染授权。' });
        if (rendering) return json(res, 409, { error: '服务器正在渲染，请稍后重试。' });
        const abort = new AbortController();
        const cancel = () => abort.abort();
        rendering = true;
        lease.render = abort;
        res.once('close', cancel);
        try {
          const body = await readBounded(req, desktopVideoRequestLimit);
          if (!valid(lease) || abort.signal.aborted) return json(res, 401, { error: '本机任务授权已结束。' });
          const input = desktopVideoInput(body);
          const result = await renderDesktopVideo(input, video, AbortSignal.any([abort.signal, AbortSignal.timeout(240_000)]));
          if (!valid(lease) || res.destroyed) return;
          res.writeHead(200, { 'content-type': 'video/mp4', 'content-length': result.bytes.length,
            'x-geneloop-sha256': result.digest, 'cache-control': 'no-store' });
          res.end(result.bytes);
        } catch (error) {
          if (error?.status === 413) throw error;
          if (!res.destroyed) return json(res, 422, { error: 'Remotion 渲染未完成。请检查工程、素材和渲染时长。' });
        } finally {
          res.off('close', cancel);
          lease.render = undefined;
          rendering = false;
        }
        return;
      }
      if (path !== DESKTOP_MODEL_PATH + '/v1/chat/completions' || req.method !== 'POST') return json(res, 404, { error: '未知本机模型接口。' });
      if (!valid(lease)) {
        if (lease) void close(lease);
        return json(res, 401, { error: '本机任务授权无效或已过期。' });
      }
      const body = await readBounded(req, undefined, true);
      if (!valid(lease)) return json(res, 401, { error: '本机任务授权已结束。' });
      if (lease.abort) return json(res, 409, { error: '该任务已有模型请求。' });
      let payload;
      try { payload = JSON.parse(body.toString('utf8')); } catch { return json(res, 400, { error: '模型请求格式无效。' }); }
      if (!validPayload(payload, model, lease.tools)) return json(res, 400, { error: '模型请求超出本机场景授权。' });
      const upstream = forward(config.upstreamBrokerPort, '/v1/chat/completions', 'POST', {
        'content-type': 'application/json', authorization: 'Bearer ' + config.apiKey,
        'x-api-key': config.apiKey, 'x-deepseek-harness-session-id': lease.binding.session_id,
      }, body, res);
      lease.abort = () => { upstream.destroy(); res.destroy(); };
      upstream.once('timeout', () => upstream.destroy(Error('Desktop model relay timed out')));
      res.once('close', () => { lease.abort = undefined; });
    },
    revokeSession(session) {
      for (const lease of byAccount.values()) if (lease.session === session) void close(lease);
    },
    close() {
      stopping = true;
      for (const lease of byAccount.values()) void close(lease);
    },
  };
}
