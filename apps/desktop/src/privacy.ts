import {sameServer} from './policy.ts';

const ACCOUNT = new Set(['me', 'login', 'register', 'logout', 'profile', 'password']);
const TASK = new Set([
  '/api/workspace/ready', '/api/workspace/follow', '/api/workspace/rename', '/api/workspace/delete',
  '/api/session/list', '/api/session/create', '/api/session/page', '/api/session/follow',
  '/api/session/control', '/api/session/prompt', '/api/session/cancel', '/api/session/rename',
  '/api/session/selectModel', '/api/session/uploadFileBinary', '/api/remote.mux', '/api/$events',
  '/api/$events/result', '/api/harless/settings', '/api/harless/models', '/api/harless/file-scene',
  '/api/harless/questions', '/api/harless/session-trash', '/api/harless/workspaces',
  '/api/harless/workspaces/preferences', '/api/harless/tasks', '/api/harless/comparisons',
  '/api/harless/deliveries', '/api/harless/motif-library',
]);

export function apiPurpose(path: string, diagnostic = false): 'account' | 'task' | 'sharing' | undefined {
  if (path.startsWith('/api/account/') && ACCOUNT.has(path.slice('/api/account/'.length))) return 'account';
  if (TASK.has(path) || diagnostic && path.startsWith('/api/fixture/')) return 'task';
  if (path === '/api/harless/rsi-sharing') return 'sharing';
  return undefined;
}

export async function sharingControlAllowed(request: Request): Promise<boolean> {
  const query = new URL(request.url).searchParams;
  if ([...query.keys()].some(key => key !== 'preview_id') || query.getAll('preview_id').length > 1) return false;
  if (query.has('preview_id') && !/^[a-f0-9-]{36}$/.test(query.get('preview_id')!)) return false;
  if (request.method === 'GET') return true;
  if (query.size) return false;
  if (request.method !== 'POST' || !request.headers.get('content-type')?.startsWith('application/json')) return false;
  try {
    const raw = await request.clone().text();
    if (Buffer.byteLength(raw) > 4096) return false;
    const body = JSON.parse(raw);
    const fields: Record<string, string[]> = {preview: ['action','task_id'],
      send: ['action','preview_id','sha256','consent'], cancel: ['action','preview_id']};
    const allowed = fields[body?.action];
    if (!allowed || Object.keys(body).some(key => !allowed.includes(key))) return false;
    if (body.action === 'preview') return typeof body.task_id === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(body.task_id);
    if (typeof body.preview_id !== 'string' || !/^[a-f0-9-]{36}$/.test(body.preview_id)) return false;
    return body.action === 'cancel' ||
      body.consent === true && typeof body.sha256 === 'string' && /^[a-f0-9]{64}$/.test(body.sha256);
  } catch {return false;}
}

/** Covers HTTP and WebSocket egress, including requests outside the local protocol handler. */
export function desktopNetworkAllowed(candidate: string, server: string, diagnostic = false): boolean {
  let url: URL;
  try {url = new URL(candidate);} catch {return false;}
  if (url.protocol === 'wss:') url.protocol = 'https:';
  else if (url.protocol === 'ws:') url.protocol = 'http:';
  if (!sameServer(url.href, server)) return false;
  const path = url.pathname;
  if (['ws:', 'wss:'].includes(new URL(candidate).protocol)) return path === '/api/remote.mux';
  return !!apiPurpose(path, diagnostic) || ['/','/login','/register','/account','/starting'].includes(path) ||
    path.startsWith('/desktop/') || path === '/assets/geneloop-spiral.svg';
}
