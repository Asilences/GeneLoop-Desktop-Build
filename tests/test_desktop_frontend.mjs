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
    const host = new module.LocalFrontendHost({ server: 'https://fixture.example/', assets: directory, fail: message => failures.push(message), session: {
      fetch: async request => { network.push(new URL(request.url).pathname); return new Response(new URL(request.url).pathname === '/' ? remote : 'API_STREAM', { headers: { 'content-encoding': 'gzip', 'content-type': 'text/plain' } }); },
    } });
    const fetchPath = path => host.fetch(new Request('https://fixture.example' + path));
    const root = await fetchPath('/');
    assert.equal(root.status, 200);
    assert.equal(root.headers.get('x-geneloop-desktop-resource'), 'local');
    assert.doesNotMatch(await root.text(), /REMOTE_EXECUTABLE_CODE/);
    assert.equal(await (await fetchPath('/assets/index-fixture.js')).text(), 'LOCAL_FRONTEND');
    assert.equal(await (await fetchPath('/plugins/bootstrap.js')).text(), 'LOCAL_PLUGIN');
    assert.equal(await (await fetchPath('/login')).text(), '<html><head><style></style></head><body>LOCAL_LOGIN</body></html>');
    const api = await fetchPath('/api/result');
    assert.equal(await api.text(), 'API_STREAM');
    assert.equal(api.headers.get('content-encoding'), null);
    assert.deepEqual(network, ['/', '/api/result']);
    assert.equal((await fetchPath('/assets/unknown.js')).status, 503);
    assert.equal((await fetchPath('/plugins/unknown.js')).status, 503);
    assert.equal(failures.length, 2);
    assert.deepEqual(network, ['/', '/api/result']);
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
