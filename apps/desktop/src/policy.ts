/** 桌面连接策略独立于执行端；当前只连接远程 GeneLoop。 */
export const DEFAULT_SERVER = 'https://geneloop.ai/';

export function serverOrigin(input: unknown, allowLoopback = false): string {
  if (typeof input !== 'string' || input.length > 2048 || /[\s\\\u0000-\u001f\u007f]/u.test(input)) {
    throw new Error('请输入完整的 GeneLoop HTTPS 地址。');
  }
  let url: URL;
  try { url = new URL(input); } catch { throw new Error('请输入完整的 GeneLoop HTTPS 地址。'); }
  const loopback = ['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(allowLoopback && loopback && url.protocol === 'http:')) {
    throw new Error('服务器地址必须使用 HTTPS。');
  }
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('只填写服务器根地址，不包含登录令牌、路径或参数。');
  }
  return url.origin + '/';
}

export function sameServer(candidate: string, server: string): boolean {
  try {
    const url = new URL(candidate);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password &&
      url.origin === new URL(server).origin;
  } catch { return false; }
}

export function externalWebUrl(candidate: string): string | null {
  try {
    const url = new URL(candidate);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function ownedDownload(urls: string[], server: string): boolean {
  if (!urls.length) return false;
  return urls.every(candidate => {
    if (sameServer(candidate, server)) return true;
    try {
      const url = new URL(candidate);
      return url.protocol === 'blob:' && sameServer(candidate.slice(5), server);
    } catch { return false; }
  });
}

export function downloadName(input: string): string {
  const name = input.split(/[\\/]/u).pop()?.replace(/[<>:"|?*\u0000-\u001f]/gu, '_').replace(/[. ]+$/u, '') || 'GeneLoop-file';
  return /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/iu.test(name) ? '_' + name : name;
}

export function windowSize(input: unknown): { width: number; height: number; maximized: boolean } {
  const value = input && typeof input === 'object' ? input as Record<string, unknown> : {};
  const dimension = (name: string, fallback: number, min: number, max: number) => {
    const raw = value[name];
    return typeof raw === 'number' && Number.isFinite(raw) ? Math.round(Math.min(max, Math.max(min, raw))) : fallback;
  };
  return { width: dimension('width', 1280, 800, 3840), height: dimension('height', 860, 600, 2160), maximized: value.maximized === true };
}
