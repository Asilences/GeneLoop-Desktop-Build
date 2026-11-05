import {createHash, randomUUID} from 'node:crypto';

export const PRIVATE_DEFAULTS = Object.freeze({
  trajectory_sharing: false, source_sharing: false, optional_telemetry: false,
});
const MAX_BYTES = 256 * 1024;
const EXPIRY_MS = 10 * 60 * 1000;
type State = 'preview' | 'sending' | 'sent' | 'cancelled' | 'unknown';
type Preview = {id: string; body: string; sha256: string; bytes: number; expires: number; state: State; abort?: AbortController};
type Audit = {event: 'preview' | 'rejected' | 'sending' | 'sent' | 'cancelled' | 'unknown' | 'expired'};
type Options = {
  prepare: (taskId: string) => Promise<string>;
  endpoint?: string;
  allowLoopback?: boolean;
  audit: (event: Audit) => void;
};

function sharingEndpoint(input: string | undefined, allowLoopback: boolean): string | undefined {
  if (input === undefined || input === '') return undefined;
  let url: URL;
  try {url = new URL(input);} catch {return undefined;}
  const local = allowLoopback && ['127.0.0.1', '[::1]'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !(local && url.protocol === 'http:')) ||
      url.username || url.password || url.search || url.hash) return undefined;
  return url.href;
}

/** Account-scoped, expiring consent. Restart and disposal discard every grant. */
export function createRsiSharing(options: Options) {
  const endpoint = sharingEndpoint(options.endpoint, options.allowLoopback === true);
  const previews = new Map<string, Preview>();
  let disposed = false;
  let preparing = 0;
  const record = (event: Audit['event']) => options.audit({event});
  const view = (row: Preview) => ({preview_id: row.id, payload: row.body, sha256: row.sha256,
    bytes: row.bytes, expires_at: new Date(row.expires).toISOString(), state: row.state, target: endpoint ?? null});
  const response = (value: unknown, status = 200) => Response.json(value, {status, headers: {'Cache-Control': 'no-store'}});
  const rejected = (code: string, status = 409) => response({error: {code, message: {
    rsi_sharing_disabled: '当前部署未配置共享接收端，可继续使用当前账号内的学习。',
    rsi_sharing_unavailable: '共享对象不可用，请重新生成预览。',
    rsi_sharing_rejected: '共享对象未通过隐私检查。',
    rsi_sharing_confirmation: '请核对预览后明确确认共享。',
    rsi_sharing_unknown: '接收状态尚未确认，请核对接收端记录。',
  }[code] ?? '共享请求未通过检查。'}}, status);
  const find = (id: unknown) => {
    const row = typeof id === 'string' ? previews.get(id) : undefined;
    if (!row) return undefined;
    if (Date.now() >= row.expires && row.state === 'preview') {
      previews.delete(row.id); record('expired'); return undefined;
    }
    return row;
  };

  return {
    async handle(request: Request): Promise<Response> {
      if (disposed) return rejected('rsi_sharing_unavailable', 410);
      if (request.method === 'GET') {
        const id = new URL(request.url).searchParams.get('preview_id');
        if (id) {
          const row = find(id);
          return row ? response(view(row)) : rejected('rsi_sharing_unavailable', 410);
        }
        return response({defaults: PRIVATE_DEFAULTS, enabled: !!endpoint, target: endpoint ?? null,
          allowed_objects: ['tool_flow'], semantic_sharing: false});
      }
      try {
        const raw = await request.text();
        if (Buffer.byteLength(raw) > 4096) return rejected('rsi_sharing_rejected', 400);
        const body = JSON.parse(raw);
        const commands: Record<string, string[]> = {
          preview: ['action', 'task_id'], send: ['action', 'preview_id', 'sha256', 'consent'],
          cancel: ['action', 'preview_id'],
        };
        const keys = commands[body?.action];
        if (!keys || Object.keys(body).some(key => !keys.includes(key))) return rejected('rsi_sharing_rejected', 400);
        if (body.action === 'preview') {
          if (typeof body.task_id !== 'string' || !body.task_id || body.task_id.length > 128)
            return rejected('rsi_sharing_rejected', 400);
          for (const row of previews.values()) if (Date.now() >= row.expires && row.state !== 'sending') previews.delete(row.id);
          if (previews.size + preparing >= 20) return rejected('rsi_sharing_unavailable', 429);
          preparing++;
          let payload: string;
          try {payload = await options.prepare(body.task_id);} finally {preparing--;}
          if (disposed || request.signal.aborted) return rejected('rsi_sharing_unavailable', 410);
          const value = JSON.parse(payload), bytes = Buffer.byteLength(payload);
          if (value.format !== 'geneloop.rsi-shared-object/v1' || value.kind !== 'tool_flow' ||
              value.trace?.format !== 'geneloop.rsi-learning-trace/v2' || bytes > MAX_BYTES)
            throw Error('invalid_projected_sharing_object');
          const row: Preview = {id: randomUUID(), body: payload, bytes,
            sha256: createHash('sha256').update(payload).digest('hex'), expires: Date.now() + EXPIRY_MS, state: 'preview'};
          previews.set(row.id, row); record('preview');
          return response(view(row));
        }
        const row = find(body.preview_id);
        if (!row) return rejected('rsi_sharing_unavailable', 410);
        if (body.action === 'cancel') {
          if (row.state === 'preview') {row.state = 'cancelled'; record('cancelled');}
          else if (row.state === 'sending') {row.abort?.abort(); row.state = 'unknown'; record('unknown');}
          return response(view(row));
        }
        if (!endpoint) return rejected('rsi_sharing_disabled', 403);
        if (body.consent !== true || body.sha256 !== row.sha256 || row.state !== 'preview')
          return rejected('rsi_sharing_confirmation');
        row.abort = new AbortController(); row.state = 'sending'; record('sending');
        try {
          const uploaded = await fetch(endpoint, {method: 'POST', body: row.body,
            headers: {'Content-Type': 'application/json', 'X-GeneLoop-Sharing-Id': row.id},
            credentials: 'omit', redirect: 'error',
            signal: AbortSignal.any([row.abort.signal, request.signal, AbortSignal.timeout(15000)])});
          await uploaded.body?.cancel();
          if (!uploaded.ok || row.abort.signal.aborted || request.signal.aborted || disposed) throw Error('delivery_unknown');
          row.state = 'sent'; record('sent');
          return response(view(row));
        } catch {
          row.state = 'unknown'; record('unknown');
          return rejected('rsi_sharing_unknown', 502);
        }
      } catch {
        record('rejected');
        return rejected('rsi_sharing_rejected');
      }
    },
    dispose() {
      disposed = true;
      for (const row of previews.values()) {
        if (row.state === 'sending') record('unknown');
        row.abort?.abort();
      }
      previews.clear();
    },
  };
}
