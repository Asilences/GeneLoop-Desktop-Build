import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

export type LocalTaskUpdate =
  | { kind: 'answer'; text: string }
  | { kind: 'report'; report: { name: string; bytes: number } }
  | { kind: 'done'; status: 'completed' | 'canceled' | 'error'; error?: string };

export function startLocalWorker(options: {
  executable: string; runtime: string; home: string; directory: string;
  endpoint: string; token: string; model: string; prompt: string;
  onUpdate: (event: LocalTaskUpdate) => void;
}) {
  mkdirSync(options.home, { recursive: true });
  const run = mkdtempSync(join(options.home, 'run-'));
  const patch = join(run, 'worker.patch.yml');
  const cli = join(options.runtime, 'node_modules/@deepseek-ai/dsh/lib/bin.js');
  writeFileSync(patch, JSON.stringify([
    { id: 'persistent-pwsh', disabled: true },
    { id: 'persistent-bash', disabled: true },
    { id: 'plugin-package-inventory-deepseek', disabled: true },
    { insert: [{ name: pathToFileURL(join(options.runtime, 'local-worker.mjs')).href }] },
  ]));
  const child = spawn(options.executable, [cli, '--profile', 'sdk-minimal', '--patch', patch], {
    cwd: run, windowsHide: true, stdio: ['pipe', 'ignore', 'ignore', 'ipc'],
    env: {
      SystemRoot: process.env.SystemRoot,
      USERPROFILE: run, HOME: run, LOCALAPPDATA: run, APPDATA: run, TEMP: run, TMP: run,
      DSH_HOME: join(run, 'dsh'), ELECTRON_RUN_AS_NODE: '1',
      DEEPSEEK_BASE_URL: options.endpoint, DEEPSEEK_API_KEY: options.token,
    },
  });
  child.stdin?.on('error', () => {});
  const send = (message: object) => {
    if (child.connected) child.send(message, () => {});
  };
  let ending = false, booted = false, canceled = false;
  let killTimer: NodeJS.Timeout | undefined;
  const timeout = setTimeout(() => stopProcess(child), 30_000);
  function finish(update: Extract<LocalTaskUpdate, { kind: 'done' }>) {
    if (ending) return;
    ending = true;
    clearTimeout(timeout);
    clearTimeout(killTimer);
    if (child.exitCode === null && child.signalCode === null) {
      child.stdin?.end(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'shutdown' }) + '\n');
      killTimer = setTimeout(() => stopProcess(child), 3000);
    }
    options.onUpdate(update);
  }
  const closed = new Promise<void>(resolve => child.once('close', () => {
    finish(canceled ? { kind: 'done', status: 'canceled' } :
      { kind: 'done', status: 'error', error: '本机执行进程已退出。' });
    clearTimeout(killTimer);
    resolve();
  }));
  child.once('error', () => finish({ kind: 'done', status: 'error', error: '无法启动本机执行进程。' }));
  child.on('message', (message: LocalTaskUpdate | { kind: 'ready' }) => {
    if (ending) return;
    if (message.kind === 'ready' && !booted) {
      booted = true;
      clearTimeout(timeout);
      if (canceled) return finish({ kind: 'done', status: 'canceled' });
      send({ kind: 'run', directory: options.directory, model: options.model, prompt: options.prompt });
    } else if (message.kind === 'done') finish(message);
    else if (message.kind === 'answer' || message.kind === 'report') options.onUpdate(message);
  });

  return {
    closed,
    cancel() {
      if (ending || canceled) return;
      canceled = true;
      send({ kind: 'cancel' });
      killTimer = setTimeout(() => stopProcess(child), 5000);
    },
    stop() { stopProcess(child); },
  };
}

function stopProcess(child: ChildProcess): void {
  if (child.exitCode === null && child.signalCode === null) child.kill();
}
