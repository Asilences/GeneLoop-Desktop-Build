/** 只通过现有开发入口启动隔离 Host，诊断结束按 RUN_ID 停止。 */
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import { closeSync, existsSync, mkdirSync, openSync } from 'node:fs';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const app = fileURLToPath(new URL('../', import.meta.url));
const repo = fileURLToPath(new URL('../../../', import.meta.url));
const runId = randomUUID().replaceAll('-', '');
const output = join(app, '.local/validation', runId);
mkdirSync(output, { recursive: true });
const log = openSync(join(output, 'host-launch.log'), 'w');
const reservation = createServer();
reservation.listen(0, '127.0.0.1'); await once(reservation, 'listening');
const port = reservation.address().port;
await new Promise(done => reservation.close(done));
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
const host = spawn(process.execPath, ['scripts/project.mjs', 'web', '--port', String(port), '--run-id', runId], { cwd: repo, env, stdio: ['ignore', log, log], windowsHide: true });
const access = join(repo, '.local/web/runs', runId, 'access-url.txt');
let result = 1;
try {
  const deadline = Date.now() + 60_000;
  while (!existsSync(access)) {
    if (host.exitCode !== null || host.signalCode !== null) throw Error('隔离 Host 启动失败，详见 apps/desktop/.local/validation/host-launch.log');
    if (Date.now() > deadline) throw Error('隔离 Host 启动超时，详见 apps/desktop/.local/validation/host-launch.log');
    await new Promise(done => setTimeout(done, 200));
  }
  console.log('隔离协议诊断 Host 已准备；不发送模型任务。');
  const electron = spawn(require('electron'), ['test/local-ui.cjs', ...process.argv.slice(2)], { cwd: app, env: { ...env, GENELOOP_DESKTOP_PROBE_ACCESS_FILE: access, GENELOOP_DESKTOP_DIAGNOSTIC_RUN_ID: runId }, stdio: 'inherit', windowsHide: false });
  const [code] = await once(electron, 'exit');
  result = code ?? 1;
} catch (error) { console.error(error.message); }
finally {
  // Windows 的旧 stop 脚本只识别 /proc。这里只清理本测试持有的子进程树，
  // 不扫描或停止其他 Host，也不用于正式服务生命周期。
  const stopped = host.exitCode !== null ? { status: 0 } : process.platform === 'win32'
    ? spawnSync('taskkill.exe', ['/PID', String(host.pid), '/T', '/F'], { stdio: 'pipe', windowsHide: true, timeout: 20_000 })
    : spawnSync(process.execPath, ['scripts/project.mjs', 'python', 'scripts/stop-harness-web.py', runId], { cwd: repo, env, stdio: 'pipe', windowsHide: true, timeout: 20_000 });
  if (stopped.status !== 0) { console.error('诊断服务未正常停止，保留运行目录和 RUN_ID：' + runId); result = 1; }
  closeSync(log);
}
process.exitCode = result;
