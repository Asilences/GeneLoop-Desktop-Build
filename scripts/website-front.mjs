#!/usr/bin/env node
// Static website and gateway front for the GeneLoop service.
// Usage: node front.mjs LISTEN_PORT UPSTREAM_PORT SITE_DIR
// Typed or external visits to "/" get the website; same-origin navigations to "/" (the old login
// and account pages redirect there) reach the gateway, which shows the chat to signed-in users.
import http from 'node:http';
import net from 'node:net';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';

const [listenPort, upstreamPort] = process.argv.slice(2, 4).map(Number);
if (!(listenPort > 0 && upstreamPort > 0 && process.argv[4])) {
  console.error('Usage: node front.mjs LISTEN_PORT UPSTREAM_PORT SITE_DIR');
  process.exit(2);
}
const siteRoot = resolve(process.argv[4]);

const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml',
  '.jpg': 'image/jpeg', '.mp4': 'video/mp4', '.ttf': 'font/ttf', '.txt': 'text/plain; charset=utf-8' };
const CSP = "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; media-src 'self'; " +
  "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";
const HOP = new Set(['connection', 'keep-alive', 'proxy-connection', 'te', 'trailer', 'transfer-encoding', 'upgrade']);

const files = new Map();
for (const entry of readdirSync(siteRoot, { recursive: true })) {
  const name = String(entry).split('\\').join('/');
  if (extname(name) in TYPES && statSync(join(siteRoot, name)).isFile())
    files.set('/' + name, { body: readFileSync(join(siteRoot, name)), type: TYPES[extname(name)] });
}
const home = files.get('/index.html');
if (!home) throw Error('SITE_DIR has no index.html');
// The chat app owns /index.html; the website home answers only at "/".
files.delete('/index.html');

const agent = new http.Agent({ keepAlive: true, maxSockets: 256 });

function sendSite(req, res, file, isHome) {
  let body = file.body;
  let status = 200;
  const headers = {
    'content-type': file.type,
    'content-security-policy': CSP,
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    'cache-control': isHome ? 'no-store' : 'public, max-age=3600'
  };
  if (file.type === 'video/mp4') {
    headers['accept-ranges'] = 'bytes';
    const range = req.method === 'GET' && !req.headers['if-range'] &&
      /^bytes=(\d*)-(\d*)$/i.exec(req.headers.range ?? '');
    if (range && (range[1] || range[2])) {
      const [, first, last] = range;
      const length = body.length;
      const start = first ? Number(first) : Math.max(0, length - Number(last));
      const end = first && last ? Math.min(Number(last), length - 1) : length - 1;
      if (start > end) {
        res.writeHead(416, { ...headers, 'content-range': `bytes */${length}`, 'content-length': '0' });
        return res.end();
      }
      status = 206;
      headers['content-range'] = `bytes ${start}-${end}/${length}`;
      body = body.subarray(start, end + 1);
    }
  }
  headers['content-length'] = String(body.length);
  res.writeHead(status, headers);
  res.end(req.method === 'HEAD' ? undefined : body);
}

function upstreamHeaders(req) {
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) if (!HOP.has(name)) headers[name] = value;
  return headers;
}

const isLoginRedirect = response => response.statusCode === 303 &&
  new URL(String(response.headers.location ?? ''), 'http://x').pathname === '/login';

function proxy(req, res, homeWhenSignedOut) {
  const upstream = http.request({ host: '127.0.0.1', port: upstreamPort, method: req.method, path: req.url,
    headers: upstreamHeaders(req), agent }, response => {
    if (homeWhenSignedOut && isLoginRedirect(response)) {
      response.resume();
      return sendSite(req, res, home, true);
    }
    for (const [name, value] of Object.entries(response.headers)) if (!HOP.has(name)) res.setHeader(name, value);
    res.writeHead(response.statusCode ?? 502, response.statusMessage);
    response.on('error', () => res.destroy());
    response.pipe(res);
  });
  upstream.on('error', () => {
    if (res.headersSent) return res.destroy();
    res.writeHead(502, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' });
    res.end('工作区暂时不可用，请刷新重试。');
  });
  // Live SSE and long downloads end when the browser leaves; stop the upstream request with them.
  res.on('close', () => { if (!res.writableFinished) upstream.destroy(); });
  req.pipe(upstream);
}

const server = http.createServer((req, res) => {
  let url;
  try { url = new URL(req.url, 'http://front'); } catch { res.writeHead(400); return res.end(); }
  if (req.method === 'GET' || req.method === 'HEAD') {
    if (url.pathname === '/') {
      if (url.searchParams.has('home')) return sendSite(req, res, home, true);
      const site = req.headers['sec-fetch-site'];
      // Browsers without Fetch Metadata keep the old behaviour so signed-in users can still reach the chat.
      if (site === undefined || site === 'same-origin') return proxy(req, res, true);
      return sendSite(req, res, home, true);
    }
    const file = files.get(url.pathname);
    if (file) return sendSite(req, res, file, false);
  }
  proxy(req, res, false);
});
server.requestTimeout = 0;
server.timeout = 0;
server.keepAliveTimeout = 75_000;
server.headersTimeout = 80_000;

server.on('upgrade', (req, socket, head) => {
  const upstream = net.connect(upstreamPort, '127.0.0.1', () => {
    let request = `${req.method} ${req.url} HTTP/1.1\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) request += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    upstream.write(request + '\r\n');
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on('error', () => socket.destroy());
  socket.on('error', () => upstream.destroy());
  upstream.once('close', () => socket.destroy());
  socket.once('close', () => upstream.destroy());
});

server.listen(listenPort, '127.0.0.1', () =>
  console.log(`${new Date().toISOString()} front listening on 127.0.0.1:${listenPort}, upstream ${upstreamPort}, ${files.size + 1} site files`));
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => { server.close(); process.exit(0); });
