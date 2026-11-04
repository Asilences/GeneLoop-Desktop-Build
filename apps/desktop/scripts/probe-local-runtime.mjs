import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { cpSync, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, posix, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';

assert.equal(process.platform, 'win32', '探针仅面向 Windows x64');
assert.equal(process.arch, 'x64');
const app = fileURLToPath(new URL('../', import.meta.url));
const packed = resolve(process.argv[2] || join(app, 'release/win-unpacked'));
const dependencies = resolve(process.argv[3] || app);
const lock = JSON.parse(readFileSync(join(dependencies, 'package-lock.json'), 'utf8'));
const root = mkdtempSync(join(tmpdir(), 'GeneLoop 本机探针 '));
const install = join(root, 'GeneLoop Desktop');
const workspace = join(root, '工作区');
const home = join(root, 'home');
const outside = join(root, 'outside');
const result = join(root, 'result.json');
const sample = randomUUID();
const modelPending = join(root, 'model-pending');
for (const directory of [workspace, home, outside]) mkdirSync(directory);
writeFileSync(join(workspace, '资料.txt'), sample);
writeFileSync(join(outside, 'secret.txt'), 'synthetic');
linkSync(join(outside, 'secret.txt'), join(workspace, '硬链接.txt'));
writeFileSync(join(workspace, '超长.txt'), Buffer.alloc(256 * 1024 + 1));
symlinkSync(outside, join(workspace, '越界'), 'junction');
console.log('隔离诊断目录：' + root);
cpSync(packed, install, { recursive: true });

// 依赖按锁文件的 Node 解析位置复制到安装目录，不能借用源码树或全局模块。
const staged = new Set();
function stage(name, requester = '', optional = false) {
  let folder = requester;
  while (true) {
    const key = posix.join(folder, 'node_modules', name);
    const entry = lock.packages[key];
    if (entry && existsSync(join(dependencies, key, 'package.json'))) {
      if (staged.has(key)) return;
      staged.add(key);
      cpSync(join(dependencies, key), join(install, 'resources/runtime', key), {
        recursive: true,
        filter: path => path === join(dependencies, key) || path.split(/[\\/]/).at(-1) !== 'node_modules',
      });
      for (const dep of Object.keys(entry.dependencies || {})) stage(dep, key);
      for (const dep of Object.keys(entry.optionalDependencies || {})) stage(dep, key, true);
      for (const dep of Object.keys(entry.peerDependencies || {})) stage(dep, key, entry.peerDependenciesMeta?.[dep]?.optional);
      return;
    }
    if (!folder) break;
    folder = folder.replace(/(?:^|\/)node_modules\/(@[^/]+\/)?[^/]+$/, '');
  }
  assert.ok(optional, '缺少锁定依赖：' + name + '（' + requester + '）');
}
stage('@deepseek-ai/dsh');
const executable = join(install, 'GeneLoop Desktop.exe');
const cli = join(install, 'resources/runtime/node_modules/@deepseek-ai/dsh/lib/bin.js');
const plugin = join(install, 'resources/runtime/local-runtime-probe.mjs');
cpSync(join(app, 'test/local-runtime-probe.mjs'), plugin);
cpSync(join(app, 'runtime/local-files.mjs'), join(install, 'resources/runtime/local-files.mjs'));
const patch = join(root, 'probe.patch.yml');
writeFileSync(patch, JSON.stringify([
  { id: 'persistent-pwsh', disabled: true },
  { id: 'persistent-bash', disabled: true },
  { insert: [{ name: pathToFileURL(plugin).href }] },
]));
// Loopback fault injection exercises the real turn loop without a paid request.
let fixtureRequests = 0;
let fixtureFailure;
let streamAborted = false;
const fixture = createServer(async (request, response) => {
  try {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    assert.match(request.url, /chat\/completions$/);
    fixtureRequests++;
    if (fixtureRequests === 1) {
      assert.deepEqual(body.tools.map(tool => tool.function.name), ['probe_read']);
      const base = { id: 'local-probe', object: 'chat.completion.chunk', created: 1, model: body.model };
      const tool = { index: 0, id: 'fixture-read', type: 'function', function: { name: 'probe_read', arguments: JSON.stringify({ path: '资料.txt' }) } };
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      for (const choices of [
        [{ index: 0, delta: { role: 'assistant', tool_calls: [tool] }, finish_reason: null }],
        [{ index: 0, delta: {}, finish_reason: 'tool_calls' }],
        [],
      ]) {
        response.write('data: ' + JSON.stringify({ ...base, choices, usage: choices.length ? undefined : { prompt_tokens: 10, completion_tokens: 2, total_tokens: 12 } }) + '\n\n');
      }
      response.end('data: [DONE]\n\n');
      return;
    }
    assert.equal(fixtureRequests, 2);
    assert.ok(body.messages.some(message => message.role === 'tool' && JSON.stringify(message.content).includes(sample)));
    response.on('close', () => { streamAborted = !response.writableEnded; });
    response.writeHead(200, { 'Content-Type': 'text/event-stream' });
    response.write(': waiting for cancellation\n\n');
    writeFileSync(modelPending, 'pending');
  } catch (error) {
    fixtureFailure = error;
    response.destroy();
  }
});
fixture.listen(0, '127.0.0.1');
await once(fixture, 'listening');
const child = spawn(executable, [cli, '--profile', 'sdk-minimal', '--patch', patch], {
  cwd: workspace, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
  env: {
    SystemRoot: process.env.SystemRoot,
    TEMP: root, TMP: root, USERPROFILE: home, HOME: home, APPDATA: home, LOCALAPPDATA: home,
    DSH_HOME: join(home, 'dsh'),
    ELECTRON_RUN_AS_NODE: '1',
    GENELOOP_PROBE_RESULT: result, GENELOOP_PROBE_TEXT: sample, GENELOOP_PROBE_MODEL_PENDING: modelPending,
    DEEPSEEK_BASE_URL: 'http://127.0.0.1:' + fixture.address().port,
    DEEPSEEK_API_KEY: 'geneloop-probe-offline',
  },
});
const closed = once(child, 'close');
let stderr = '';
child.stderr.setEncoding('utf8');
child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-6000); });
const lines = createInterface({ input: child.stdout });
async function rpc(id, method, params) {
  const reply = new Promise((resolve, reject) => {
    const onLine = line => {
      try {
        const value = JSON.parse(line);
        if (value.id !== id) return;
        if (value.error) reject(Error(value.error.message));
        else resolve(value.result);
      } catch (error) { reject(error); }
    };
    lines.on('line', onLine);
    child.once('close', code => reject(Error('Harness 提前退出：' + code)));
  });
  child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  return reply;
}
const timer = setTimeout(() => child.kill(), 30_000);
try {
  const response = await rpc(1, 'initialize', { cwd: workspace, provider: 'deepseek-official', model: 'deepseek-flash', reasoningEffort: 'off' });
  assert.equal(response.serverInfo.name, 'deepseek-harness-sdk-runtime');
  while (!existsSync(result)) {
    if (fixtureFailure) throw fixtureFailure;
    if (child.exitCode !== null || child.signalCode !== null) throw Error('探针未产生结果');
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  const outcome = JSON.parse(readFileSync(result, 'utf8'));
  assert.ok(!outcome.error, outcome.error);
  assert.equal(outcome.pid, child.pid);
  assert.equal(outcome.localRead && outcome.rejectedTraversalAndJunction && outcome.turnCanceled, true);
  assert.equal(fixtureRequests, 2);
  assert.equal(streamAborted, true);
  await rpc(2, 'shutdown');
  child.stdin.end();
  assert.deepEqual(await closed, [0, null]);
  console.log(JSON.stringify({ kind: 'packaged_windows_harness_probe', ...outcome, initialized: true, gracefulShutdown: true, dependencies: staged.size, fixtureRequests, streamAborted, realModelRequests: 0 }));
} catch (error) {
  if (stderr) console.error(stderr);
  throw error;
} finally {
  clearTimeout(timer);
  fixture.closeAllConnections();
  fixture.close();
  if (child.exitCode === null && child.signalCode === null) child.kill();
}
