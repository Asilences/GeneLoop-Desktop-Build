import { net } from 'electron';
import type { Session } from 'electron';

/** 启动文档必须保留 303 /starting、/login 等真实跳转；Chromium fetch 的
 * manual redirect 会以 Redirect was cancelled 拒绝，因此使用原生 request。 */
export function readBootDocument(session: Session, input: Request): Promise<Response> {
  return new Promise((resolve, reject) => {
    const credentials = input.credentials === 'omit' ? 'omit' : 'include';
    const request = net.request({ url: input.url, method: 'GET', session, credentials, useSessionCookies: credentials !== 'omit', redirect: 'manual', bypassCustomProtocolHandlers: true });
    let settled = false;
    const fail = (error: Error) => { if (!settled) { settled = true; input.signal.removeEventListener('abort', abort); reject(error); } };
    const finish = (response: Response) => { if (!settled) { settled = true; input.signal.removeEventListener('abort', abort); resolve(response); } };
    const abort = () => { fail(new Error('启动连接已取消。')); request.abort(); };
    input.signal.addEventListener('abort', abort, { once: true });
    request.on('redirect', (status, _method, location) => { finish(new Response(null, { status, headers: { location } })); request.abort(); });
    request.on('response', response => {
      const chunks: Buffer[] = [];
      response.on('data', chunk => chunks.push(Buffer.from(chunk)));
      response.on('end', () => finish(new Response(response.statusCode === 204 || response.statusCode === 304 ? null : new Uint8Array(Buffer.concat(chunks)), { status: response.statusCode })));
      response.on('error', fail);
    });
    request.on('error', fail);
    request.on('abort', () => fail(new Error('启动连接已取消。')));
    if (input.signal.aborted) { abort(); return; }
    request.end();
  });
}
