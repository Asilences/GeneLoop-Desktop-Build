import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from 'node:fs';
import { rm, chmod, lstat, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';

export type LocalTaskUpdate =
  | { kind: 'ready' }
  | { kind: 'answer'; text: string }
  | { kind: 'progress'; phase: 'remote-render' | 'local' }
  | { kind: 'report'; report: { name: string; bytes: number } }
  | { kind: 'done'; status: 'completed' | 'canceled' | 'error'; error?: string };
export type LocalScene = 'chat' | 'files' | 'data' | 'paper' | 'ppt' | 'video';
export type LocalMediaTools = { ffmpeg: string; ffprobe: string; remotion?: {browser:string; binaries:string} };
export type VideoApproval = { sourceBytes: number; assets: { path: string; bytes: number }[] };
export type LocalPptTools = { python: string; sourceRoot: string; skill: string; soffice: string };

export function startLocalWorker(options: {
  executable: string; runtime: string; home: string; directory: string;
  endpoint: string; token: string; model: string; prompt: string;
  sessionId?: string; resume?: boolean; scene?: LocalScene; media?: LocalMediaTools;
  ppt?: LocalPptTools; legacyTools?: boolean;
  approveVideo?: (request: VideoApproval) => Promise<boolean>;
  onUpdate: (event: LocalTaskUpdate) => void;
}) {
  mkdirSync(options.home, { recursive: true });
  const temp = realpathSync(tmpdir());
  const run = mkdtempSync(join(temp, 'geneloop-agent-'));
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
      USERPROFILE: run, HOME: run, LOCALAPPDATA: run, APPDATA: run, TEMP: run, TMP: run, TMPDIR: run,
      DSH_HOME: options.sessionId ? join(options.home, 'dsh') : join(run, 'dsh'), ELECTRON_RUN_AS_NODE: '1',
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
  const closed = new Promise<void>(resolve => child.once('close', async () => {
    finish(canceled ? { kind: 'done', status: 'canceled' } :
      { kind: 'done', status: 'error', error: '本机执行进程已退出。' });
    clearTimeout(killTimer);
    await cleanRunDirectory(temp, run);
    resolve();
  }));
  child.once('error', () => finish({ kind: 'done', status: 'error', error: '无法启动本机执行进程。' }));
  child.on('message', (message: LocalTaskUpdate | { kind: 'video-approval'; id: string; request: VideoApproval }) => {
    if (ending) return;
    if (message.kind === 'ready' && !booted) {
      booted = true;
      clearTimeout(timeout);
      if (canceled) return finish({ kind: 'done', status: 'canceled' });
      options.onUpdate({ kind: 'ready' });
      send({ kind: 'run', directory: options.directory, model: options.model, prompt: options.prompt,
        sessionId: options.sessionId, resume: options.resume, scene: options.scene, media: options.media,
        ppt: options.ppt, legacyTools:options.legacyTools===true,videoRendering: !!options.approveVideo });
    } else if (message.kind === 'video-approval') {
      const answer = (allowed: boolean) => send({ kind: 'video-approved', id: message.id, allowed: allowed && !canceled && !ending });
      if (canceled || !options.approveVideo) answer(false);
      else void options.approveVideo(message.request).then(answer, () => answer(false));
    } else if (message.kind === 'done') finish(message);
    else if (message.kind === 'answer' || message.kind === 'report' || message.kind === 'progress') options.onUpdate(message);
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

async function cleanRunDirectory(temp: string, run: string): Promise<void> {
  try {
    if (dirname(run) === temp && realpathSync(run) === run) {
      if (process.platform === 'win32') {
        const walk = async (path: string): Promise<void> => {
          const info=await lstat(path);
          if (!info.isDirectory() || info.isSymbolicLink()) return;
          await chmod(path,0o700);
          for (const item of await readdir(path,{withFileTypes:true})) {
            if (item.isDirectory() && !item.isSymbolicLink()) await walk(join(path,item.name));
          }
        };
        await walk(run);
      }
      await rm(run, { recursive: true, force: true, maxRetries: 8, retryDelay: 250 });
    }
  } catch { /* The directory was removed or replaced. */ }
}
