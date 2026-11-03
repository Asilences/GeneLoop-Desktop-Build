import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
const [major, minor] = process.versions.node.split('.').map(Number);
const available = major > 22 || major === 22 && minor >= 18;
const module = available ? await import('../apps/desktop/src/frontend.ts') : undefined;

test('桌面只解析结构化启动 JSON，不执行或复制远程页面代码', { skip: !available }, () => {
  const html = '<script>globalThis.attack=true</script><script>globalThis["__DSH_BOOT__"] = {"rev":"fixture","entries":[],"batches":[]}</script>';
  assert.equal(module.bootGlobals(html).__DSH_BOOT__.rev, 'fixture');
  assert.equal(globalThis.attack, undefined);
  assert.deepEqual(module.bootGlobals('<script>globalThis["UNRELATED"] = {"secret":1}</script>'), {});
  assert.throws(() => module.bootGlobals('<script>globalThis["__DSH_BOOT__"] = execute()</script>'));
});

test('桌面仅根据 Chromium 可信同源发起信息恢复 Origin，拒绝跨源和不透明请求', { skip: !available }, async () => {
  const directory = mkdtempSync(join(tmpdir(), 'geneloop-origin-'));
  const forwarded = [];
  try {
    writeFileSync(join(directory, 'manifest.json'), JSON.stringify({ format: 1 }));
    const host = new module.LocalFrontendHost({ server: 'https://fixture.example/', assets: directory, fail: assert.fail, readBoot: assert.fail, session: {
      fetch: async (request, options) => {
        forwarded.push({ url: request.url, origin: options.headers.get('origin'), credentials: options.credentials, body: await request.text() });
        return Response.json({ ok: true });
      },
    } });
    const request = (initiator, headers = {}, url = 'https://fixture.example/api/account/login') => {
      const value = new Request(url, { method: 'POST', credentials: 'omit', headers, body: '{"diagnostic":true}' });
      if (initiator !== undefined) Object.defineProperty(value, 'initiatorOrigin', { value: initiator });
      return value;
    };
    assert.equal((await host.fetch(request('https://fixture.example'))).status, 200);
    assert.deepEqual(forwarded[0], { url: 'https://fixture.example/api/account/login', origin: 'https://fixture.example', credentials: 'omit', body: '{"diagnostic":true}' });
    for (const value of [request('https://external.example'), request('null'), request(undefined), request('https://fixture.example', { origin: 'https://external.example' }), request('https://fixture.example', { 'sec-fetch-site': 'cross-site' })]) {
      assert.equal((await host.fetch(value)).status, 403);
    }
    assert.equal(forwarded.length, 1);
    await host.fetch(request('https://fixture.example', {}, 'https://external.example/resource'));
    assert.equal(forwarded[1].origin, null, '不把服务器身份套给外域请求');
    assert.equal(forwarded[1].credentials, 'omit');
  } finally { rmSync(directory, { recursive: true, force: true }); }
});

test('安装资源与服务器执行接口分离；未知 UI 不回退远程加载', { skip: !available }, async () => {
  const directory = mkdtempSync(join(tmpdir(), 'geneloop-frontend-'));
  const network = [], failures = [];
  const graph = { rev: 'diagnostic', entries: [{ id: 'fixture-ui', url: '/plugins/ui.js', rev: 'diagnostic', inject: [] }], batches: [{ phase: 'bootstrap', url: '/plugins/bootstrap.js', rev: 'diagnostic', entries: ['fixture-ui'] }] };
  const index = '<html><head><script type="module" src="./assets/index-fixture.js"></script></head><body><div id="root"></div></body></html>';
  const remote = index.replace('</head>', '<script>globalThis["__DSH_BOOT__"] = ' + JSON.stringify(graph) + '</script><script>REMOTE_EXECUTABLE_CODE()</script></head>');
  try {
    mkdirSync(join(directory, 'frontend/assets'), { recursive: true });
    mkdirSync(join(directory, 'clients'));
    writeFileSync(join(directory, 'manifest.json'), JSON.stringify({ format: 1, staticFiles: ['/assets/index-fixture.js'], clients: { 'fixture-ui': { file: 'clients/fixture.js', version: 'diagnostic' } } }));
    writeFileSync(join(directory, 'frontend/index.html'), index);
    writeFileSync(join(directory, 'frontend/assets/index-fixture.js'), 'LOCAL_FRONTEND');
    writeFileSync(join(directory, 'clients/fixture.js'), 'LOCAL_PLUGIN');
    for (const file of ['geneloop_theme.css', 'geneloop_brand.js', 'geneloop_workspaces.js', 'harless_account_link.js']) writeFileSync(join(directory, file), '');
    writeFileSync(join(directory, 'harless_account.html'), '<html><head></head><body>LOCAL_LOGIN</body></html>');
    const host = new module.LocalFrontendHost({ server: 'https://fixture.example/', assets: directory, fail: message => failures.push(message), readBoot: async () => { network.push('/'); return new Response(remote); }, session: {
      fetch: async (request, options) => { network.push(new URL(request.url).pathname); if (new URL(request.url).hostname === 'external.example') assert.equal(options.credentials, 'omit'); return new Response('API_STREAM', { headers: { 'content-encoding': 'gzip', 'content-type': 'text/plain' } }); },
    } });
    const fetchPath = path => host.fetch(new Request('https://fixture.example' + path));
    const root = await fetchPath('/');
    assert.equal(root.status, 200);
    assert.equal(root.headers.get('x-geneloop-desktop-resource'), 'local');
    assert.doesNotMatch(await root.text(), /REMOTE_EXECUTABLE_CODE/);
    assert.equal(await (await fetchPath('/assets/index-fixture.js')).text(), 'LOCAL_FRONTEND');
    assert.equal(await (await fetchPath('/plugins/bootstrap.js')).text(), 'LOCAL_PLUGIN');
    const login = await fetchPath('/login');
    assert.match(login.headers.get('content-security-policy'), /form-action 'self'/);
    assert.equal(await login.text(), '<html><head><style></style></head><body>LOCAL_LOGIN</body></html>');
    for (const alias of ['/harless', '/tasks', '/sss']) { const aliasResponse = await fetchPath(alias); assert.equal(aliasResponse.status, 302); assert.equal(aliasResponse.headers.get('location'), '/'); }
    const api = await fetchPath('/api/result');
    assert.equal(await api.text(), 'API_STREAM');
    assert.equal(api.headers.get('content-encoding'), null);
    assert.deepEqual(network, ['/', '/api/result']);
    await host.fetch(new Request('https://external.example/resource', { credentials: 'omit' }));
    assert.equal((await fetchPath('/assets/unknown.js')).status, 503);
    assert.equal((await fetchPath('/plugins/unknown.js')).status, 503);
    assert.equal(failures.length, 2);
    assert.deepEqual(network, ['/', '/api/result', '/resource']);
    const cold = new module.LocalFrontendHost({ server: 'https://fixture.example/', assets: directory, session: {}, fail: message => assert.fail(message), readBoot: async () => new Response(null, { status: 303, headers: { location: '/starting?next=%2F' } }) });
    const coldResponse = await cold.fetch(new Request('https://fixture.example/'));
    assert.equal(coldResponse.status, 303);
    assert.equal(coldResponse.headers.get('location'), '/starting?next=%2F');
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
