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
  '/api/harless/deliveries',
]);

export function apiPurpose(path: string, diagnostic = false): 'account' | 'task' | 'sharing' | undefined {
  if (path.startsWith('/api/account/') && ACCOUNT.has(path.slice('/api/account/'.length))) return 'account';
  if (TASK.has(path) || diagnostic && path.startsWith('/api/fixture/')) return 'task';
  if (path === '/api/harless/rsi-sharing') return 'sharing';
  return undefined;
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
