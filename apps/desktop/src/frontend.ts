import { readFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import type { Session } from 'electron';
import { bootInjections } from '@deepseek-ai/dsh-client-modules';
import { renderIndexInjections } from '@deepseek-ai/dsh-host-webserver';
import { sameServer } from './policy.ts';

type Graph = Parameters<typeof bootInjections>[0];
type Manifest = { format: number; dshVersion: string; sourceCommit: string; staticFiles: string[]; clients: Record<string, { file: string; version: string }> };
type FrontendOptions = { session: Session; server: string; assets: string; fail: (message: string) => void };
const MIME: Record<string, string> = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.json': 'application/json', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.webmanifest': 'application/manifest+json' };

/** 只读取上游结构化 JSON 注入；服务器页面中的脚本和样式不执行。 */
export function bootGlobals(html: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const match of html.matchAll(/<script>globalThis\[("__DSH_[A-Z_]+__")\]\s*=\s*([\s\S]*?)<\/script>/g)) {
    const name = JSON.parse(match[1]);
    if (name === '__DSH_BOOT__' || name === '__DSH_CONNECTION_RECOVERY__') result[name] = JSON.parse(match[2]);
  }
  return result;
}

function responseHeaders(input: Headers): Headers {
  const headers = new Headers(input);
  // fetch 返回解码后的流，不能把原压缩传输头交给第二层 Chromium。
  for (const key of ['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'keep-alive']) headers.delete(key);
  return headers;
}

/** 本地界面资源 + 原生 boot 元数据；网络承载认证/会话/API/事件及用户文件。 */
export class LocalFrontendHost {
  readonly manifest: Manifest;
  readonly served = { local: 0, network: 0, localScripts: [] as string[], networkScripts: [] as string[] };
  readonly diagnostics: { unsupported: string[]; bundleKeys: string[] } = { unsupported: [], bundleKeys: [] };
  private bundles = new Map<string, string[]>();
  private installed = false;
  private readonly scheme: string;
  private options: FrontendOptions;

  constructor(options: FrontendOptions) {
    this.options = options;
    this.manifest = JSON.parse(readFileSync(join(options.assets, 'manifest.json'), 'utf8'));
    if (this.manifest.format !== 1) throw Error('桌面界面资源无法识别，请重新安装。');
    this.scheme = new URL(options.server).protocol.slice(0, -1);
  }

  install(): void {
    // 保留真实 HTTPS origin，使原 Cookie、WebSocket 和服务器来源检查继续生效。
    this.options.session.protocol.handle(this.scheme, request => this.fetch(request));
    this.installed = true;
  }

  dispose(): void {
    if (this.installed) this.options.session.protocol.unhandle(this.scheme);
    this.installed = false;
  }

  private local(body: BodyInit | null, type: string, method: string): Response {
    this.served.local++;
    return new Response(method === 'HEAD' ? null : body, { headers: { 'content-type': type, 'cache-control': 'no-store', 'x-geneloop-desktop-resource': 'local', 'x-content-type-options': 'nosniff' } });
  }

  private async network(request: Request): Promise<Response> {
    this.served.network++;
    if (/^\/(?:plugins\/\?\?|assets\/.*\.(?:js|css))/.test(new URL(request.url).pathname + new URL(request.url).search)) this.served.networkScripts.push(new URL(request.url).pathname);
    return this.options.session.fetch(request, { bypassCustomProtocolHandlers: true, credentials: 'include' });
  }

  private compose(html: string): string {
    const { server, assets } = this.options;
    const globals = bootGlobals(html), graph = globals.__DSH_BOOT__ as Graph;
    if (!graph || !Array.isArray(graph.entries) || !Array.isArray(graph.batches)) throw Error('服务器未提供兼容的工作区启动信息。');
    const index = readFileSync(join(assets, 'frontend/index.html'), 'utf8');
    const entry = /src="\.\/(assets\/index-[^" ]+\.js)"/.exec(index)?.[1];
    if (!entry || !html.includes(entry)) throw Error('服务器和桌面界面版本不同，请更新 GeneLoop Desktop。');
    this.bundles.clear();
    for (const row of graph.entries) {
      const client = this.manifest.clients[row.id];
      if (!client || !sameServer(new URL(row.url, server).href, server)) throw Error('服务器使用了桌面尚未包含的客户端插件，请更新应用。');
      const url = new URL(row.url, server);
      this.bundles.set(url.pathname + url.search, [client.file]);
    }
    for (const batch of graph.batches) {
      if (!sameServer(new URL(batch.url, server).href, server)) throw Error('服务器客户端资源地址不兼容。');
      const paths = batch.entries.map(id => this.manifest.clients[id]?.file);
      if (paths.some(path => !path)) throw Error('服务器客户端插件不完整。');
      const url = new URL(batch.url, server);
      this.bundles.set(url.pathname + url.search, paths);
    }
    const rows = bootInjections(graph);
    this.diagnostics.bundleKeys = [...this.bundles.keys()];
    if (globals.__DSH_CONNECTION_RECOVERY__ !== undefined) rows.push({ kind: 'global', name: '__DSH_CONNECTION_RECOVERY__', value: globals.__DSH_CONNECTION_RECOVERY__ });
    rows.push({ kind: 'style', text: readFileSync(join(assets, 'geneloop_theme.css'), 'utf8') });
    rows.push({ kind: 'script', placement: 'head', text: readFileSync(join(assets, 'geneloop_brand.js'), 'utf8') });
    rows.push({ kind: 'script', placement: 'head', text: readFileSync(join(assets, 'geneloop_workspaces.js'), 'utf8') });
    rows.push({ kind: 'script', placement: 'body', text: readFileSync(join(assets, 'harless_account_link.js'), 'utf8') });
    return renderIndexInjections(index, rows).replace('<title>DeepSeek Harness</title>', '<title>GeneLoop Desktop</title>').replace('<head>', '<head><base href="/">');
  }

  async fetch(request: Request): Promise<Response> {
    const { server, assets } = this.options;
    if (!sameServer(request.url, server)) return this.network(request);
    const url = new URL(request.url), key = url.pathname + url.search;
    try {
      if (request.method === 'GET' || request.method === 'HEAD') {
        if (this.manifest.staticFiles.includes(url.pathname) && url.pathname !== '/index.html') {
          if (/\.(?:js|css)$/.test(url.pathname)) this.served.localScripts.push(url.pathname);
          return this.local(new Uint8Array(readFileSync(join(assets, 'frontend', url.pathname.slice(1)))), MIME[extname(url.pathname)] || 'application/octet-stream', request.method);
        }
        if (url.pathname === '/assets/geneloop-spiral.svg') return this.local(new Uint8Array(readFileSync(join(assets, 'geneloop-spiral.svg'))), 'image/svg+xml', request.method);
        if (/^\/assets\/.*\.(?:js|css)$/.test(url.pathname)) throw Error('服务器界面资源已变化，请更新 GeneLoop Desktop。');
        if (['/login', '/register', '/claim', '/account', '/starting'].includes(url.pathname)) {
          const html = readFileSync(join(assets, 'harless_account.html'), 'utf8').replace('</head>', '<style>' + readFileSync(join(assets, 'geneloop_theme.css'), 'utf8') + '</style></head>');
          return this.local(html, MIME['.html'], request.method);
        }
        const files = this.bundles.get(key);
        if (files) {
          this.served.localScripts.push(url.pathname);
          return this.local(files.map(file => readFileSync(join(assets, file), 'utf8')).join('\n'), MIME['.js'], request.method);
        }
        if (url.pathname.startsWith('/plugins') && url.pathname !== '/plugins/events') {
          this.diagnostics.unsupported.push(key);
          throw Error('服务器客户端插件已变化，请更新 GeneLoop Desktop 后重试。');
        }
        if (url.pathname === '/' || url.pathname === '/index.html') {
          const remote = await this.network(request.method === 'HEAD' ? new Request(request, { method: 'GET' }) : request);
          if (remote.status >= 300 && remote.status < 400) {
            const target = remote.headers.get('location');
            if (!target || !sameServer(new URL(target, server).href, server)) throw Error('服务器跳转到了其他地址，请检查连接设置。');
            return new Response(null, { status: remote.status, headers: { location: target } });
          }
          if (!remote.ok) throw Error('服务器工作区暂时无法启动，请稍后重试。');
          const html = await remote.text();
          if (!bootGlobals(html).__DSH_BOOT__ && /id=["']login-form["']/.test(html)) {
            return new Response(null, { status: 303, headers: { location: '/login' } });
          }
          return this.local(this.compose(html), MIME['.html'], request.method);
        }
      }
      const remote = await this.network(request);
      return new Response(remote.body, { status: remote.status, statusText: remote.statusText, headers: responseHeaders(remote.headers) });
    } catch (error) {
      this.options.fail(error instanceof Error && error.message.startsWith('服务器') ? error.message : '桌面资源或网络暂时不可用，请重试。');
      return new Response('GeneLoop Desktop connection unavailable', { status: 503 });
    }
  }
}
