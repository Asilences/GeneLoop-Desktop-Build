import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { cpSync, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { stageRuntime } from './runtime-bundle.mjs';

assert.equal(process.platform, 'win32', '探针仅面向 Windows x64');
assert.equal(process.arch, 'x64');
const app = fileURLToPath(new URL('../', import.meta.url));
const packed = resolve(process.argv[2] || join(app, 'release/win-unpacked'));
const dependencies = resolve(process.argv[3] || app);
const root = mkdtempSync(join(tmpdir(), 'GeneLoop 本机探针 '));
const install = join(root, 'GeneLoop Desktop');
const workspace = join(root, '工作区');
const home = join(root, 'home');
const reports = join(root, '报告');
const outside = join(root, 'outside');
const result = join(root, 'result.json');
const sample = randomUUID();
const modelPending = join(root, 'model-pending');
for (const directory of [workspace, home, outside, reports, join(workspace, '空目录'), join(workspace, '大量文件')]) mkdirSync(directory);
for (let index = 0; index < 201; index++) writeFileSync(join(workspace, '大量文件', index + '.txt'), '');
const report = '# 本机文件盘点\n\n- 来源：资料.txt（第 1 行）\n';
writeFileSync(join(workspace, '资料.txt'), sample);
writeFileSync(join(outside, 'secret.txt'), 'synthetic');
linkSync(join(outside, 'secret.txt'), join(workspace, '硬链接.txt'));
writeFileSync(join(workspace, '超长.txt'), Buffer.alloc(256 * 1024 + 1));
symlinkSync(outside, join(workspace, '越界'), 'junction');
console.log('隔离诊断目录：' + root);
cpSync(packed, install, { recursive: true });

const bundled = join(install, 'resources/geneloop-runtime');
const packagedRuntime = existsSync(join(bundled, 'local-worker.mjs'));
const runtime = packagedRuntime ? bundled : join(install, 'resources/runtime');
const staged = packagedRuntime ? 0 : stageRuntime(app, runtime, dependencies);
const executable = join(install, 'GeneLoop Desktop.exe');
const cli = join(runtime, 'node_modules/@deepseek-ai/dsh/lib/bin.js');
const plugin = join(runtime, 'local-runtime-probe.mjs');
cpSync(join(app, 'test/local-runtime-probe.mjs'), plugin);
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
    assert.deepEqual(body.tools.map(tool => tool.function.name).sort(), ['local_list', 'local_read', 'local_save_report', 'local_search']);
    const toolResult = id => body.messages.find(message => message.role === 'tool' && message.tool_call_id === id)?.content;
    let calls;
    if (fixtureRequests === 1) {
      calls = [
        ['inventory', 'local_list', { path: '' }],
        ['read', 'local_read', { path: '资料.txt' }],
        ['search', 'local_search', { path: '资料.txt', query: sample }],
      ];
    } else if (fixtureRequests === 2) {
      const listing = JSON.parse(toolResult('inventory'));
      assert.ok(listing.entries.some(entry => entry.name === '资料.txt' && entry.kind === 'file'));
      assert.ok(!listing.entries.some(entry => entry.name === '越界'));
      assert.equal(toolResult('read'), sample);
      assert.deepEqual(JSON.parse(toolResult('search')), { path: '资料.txt', matches: [1], truncated: false });
      calls = [['report', 'local_save_report', { markdown: report }]];
    }
    if (calls) {
      const base = { id: 'local-probe-' + fixtureRequests, object: 'chat.completion.chunk', created: 1, model: body.model };
      const tools = calls.map(([id, name, args], index) => ({ index, id, type: 'function', function: { name, arguments: JSON.stringify(args) } }));
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      for (const choices of [
        [{ index: 0, delta: { role: 'assistant', tool_calls: tools }, finish_reason: null }],
        [{ index: 0, delta: {}, finish_reason: 'tool_calls' }],
        [],
      ]) {
        response.write('data: ' + JSON.stringify({ ...base, choices, usage: choices.length ? undefined : { prompt_tokens: 10, completion_tokens: 2, total_tokens: 12 } }) + '\n\n');
      }
      response.end('data: [DONE]\n\n');
      return;
    }
    assert.equal(fixtureRequests, 3);
    const receipt = JSON.parse(toolResult('report'));
    assert.match(receipt.name, /^GeneLoop-[a-f0-9-]+\.md$/);
    assert.equal(receipt.bytes, Buffer.byteLength(report));
    assert.deepEqual(readdirSync(reports), [receipt.name]);
    assert.equal(readFileSync(join(reports, receipt.name), 'utf8'), report);
    assert.equal(readFileSync(join(workspace, '资料.txt'), 'utf8'), sample);
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
    GENELOOP_PROBE_REPORTS: reports, GENELOOP_PROBE_RESULT: result, GENELOOP_PROBE_TEXT: sample, GENELOOP_PROBE_MODEL_PENDING: modelPending,
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
  assert.equal(fixtureRequests, 3);
  assert.equal(streamAborted, true);
  await rpc(2, 'shutdown');
  child.stdin.end();
  assert.deepEqual(await closed, [0, null]);
  console.log(JSON.stringify({ kind: 'packaged_windows_harness_probe', ...outcome, inventorySearchReport: true, initialized: true, gracefulShutdown: true, packagedRuntime, stagedDependencies: staged, fixtureRequests, streamAborted, realModelRequests: 0 }));
} catch (error) {
  if (stderr) console.error(stderr);
  throw error;
} finally {
  clearTimeout(timer);
  fixture.closeAllConnections();
  fixture.close();
  if (child.exitCode === null && child.signalCode === null) child.kill();
}
