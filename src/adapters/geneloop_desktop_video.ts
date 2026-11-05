import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, readFileSync, realpathSync } from 'node:fs';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { videoProjectCommand, type VideoRenderer } from './geneloop_video.ts';

const sourceLimit = 128 * 1024;
const mediaLimit = 16 * 1024 * 1024;
export const desktopVideoRequestLimit = 23 * 1024 * 1024;
const outputLimit = 80 * 1024 * 1024;
const sha256 = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex');
const recipe = (browser: string) => "timeout --kill-after=5s 230s /bin/sh -c '"
  + 'node /runtime/node_modules/@remotion/cli/remotion-cli.js render src/index.tsx Main /tmp/video.mp4 '
  + '--browser-executable=' + browser + ' --bundle-cache=false --concurrency=2 --log=error >&2'
  + ' && ffmpeg -v error -xerror -nostdin -protocol_whitelist file,pipe -f mov -enable_drefs 0 '
  + "-i /tmp/video.mp4 -map 0:v:0 -map 0:a? -f null - && cat /tmp/video.mp4'";

type VideoSandbox = { rootfs: string; runtimeRoot: string; browser: string };
export function desktopVideoSandbox(value: VideoSandbox): VideoSandbox {
  if (process.platform !== 'linux' || !value || Object.keys(value).sort().join(',') !== 'browser,rootfs,runtimeRoot' ||
      typeof value.browser !== 'string' || !/^\/ms-playwright\/[\w-]+\/[\w-]+\/chrome-headless-shell$/.test(value.browser)) {
    throw Error('Invalid desktop render sandbox');
  }
  for (const dir of [value.rootfs,value.runtimeRoot]) {
    if (typeof dir !== 'string' || realpathSync(dir) !== resolve(dir) || !lstatSync(dir).isDirectory()) throw Error('Invalid render resources');
  }
  if (JSON.parse(readFileSync(join(value.runtimeRoot,'node_modules/remotion/package.json'),'utf8')).version !== '4.0.539' ||
      ![join(value.rootfs,value.browser),join(value.rootfs,'usr/bin/node'),
        join(value.runtimeRoot,'node_modules/@ffmpeg-installer/linux-x64/ffmpeg')].every(existsSync)) {
    throw Error('Desktop render dependencies unavailable');
  }
  return value;
}

function sandboxCommand(sandbox: VideoSandbox, project: string, volatile: string) {
  return ['/usr/bin/unshare','--user','--map-root-user','--mount','--propagation','private','/bin/sh','-ec',
    'mount -t tmpfs -o size=512m,nosuid,nodev tmpfs "$1"; shift; exec "$@"','geneloop-render',volatile,
    '/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL',
    '--ro-bind',sandbox.rootfs,'/','--proc','/proc','--dev','/dev','--bind',volatile,'/tmp',
    '--ro-bind',sandbox.runtimeRoot,'/runtime','--ro-bind',project,'/work',
    '--ro-bind',join(sandbox.runtimeRoot,'node_modules'),'/work/node_modules','--chdir','/work',
    '--setenv','HOME','/tmp','--setenv','PATH','/runtime/node_modules/@ffmpeg-installer/linux-x64:/usr/local/bin:/usr/bin:/bin',
    '/bin/sh','-c',recipe(sandbox.browser)];
}

export function desktopVideoInput(raw: Buffer) {
  const input = JSON.parse(raw.toString('utf8'));
  if (!input || Object.keys(input).sort().join(',') !== 'assets,source' ||
      typeof input.source !== 'string' || !input.source.trim() || Buffer.byteLength(input.source) > sourceLimit ||
      !Array.isArray(input.assets) || input.assets.length > 8) throw Error('无效的 Remotion 工程。');
  let remaining = mediaLimit;
  const names = new Set<string>();
  const assets = input.assets.map((asset: { name: string; bytes: string; sha256: string }) => {
    if (!asset || Object.keys(asset).sort().join(',') !== 'bytes,name,sha256' ||
        typeof asset.name !== 'string' || !/^[a-z0-9_-]{1,64}\.(?:mp4|mov|png|jpg|jpeg|mp3|wav)$/i.test(asset.name) ||
        names.has(asset.name.toLowerCase()) || typeof asset.bytes !== 'string' ||
        asset.bytes.length > Math.ceil(remaining / 3) * 4) throw Error('无效的渲染素材。');
    const bytes = Buffer.from(asset.bytes, 'base64');
    remaining -= bytes.length;
    if (!bytes.length || remaining < 0 || bytes.toString('base64') !== asset.bytes ||
        sha256(bytes) !== asset.sha256) throw Error('渲染素材校验失败。');
    names.add(asset.name.toLowerCase());
    return { name: asset.name, bytes };
  });
  return { source: input.source as string, assets };
}

export async function renderDesktopVideo(input: ReturnType<typeof desktopVideoInput>, renderer: VideoRenderer | VideoSandbox, signal: AbortSignal) {
  signal.throwIfAborted();
  const job = await mkdtemp(join(tmpdir(), 'geneloop-desktop-video-'));
  const project = join(job,'project'), volatile = join(job,'volatile');
  try {
    await Promise.all([mkdir(project),mkdir(volatile)]);
    await Promise.all(['src', 'public', 'node_modules'].map(name => mkdir(join(project, name))));
    await writeFile(join(project, 'package.json'), '{"name":"geneloop-desktop-render","version":"1.0.0","private":true}', { flag: 'wx' });
    await writeFile(join(project, 'src/index.tsx'), input.source, { flag: 'wx' });
    for (const { name, bytes } of input.assets) await writeFile(join(project, 'public', name), bytes, { flag: 'wx' });
    signal.throwIfAborted();
    const docker = 'image' in renderer ? videoProjectCommand(project,recipe('/usr/bin/chromium-headless-shell'),renderer) : undefined;
    const [bin, ...args] = docker?.argv ?? sandboxCommand(renderer as VideoSandbox,project,volatile);
    const chunks: Buffer[] = [];
    let size = 0;
    try {
      await new Promise<void>((resolve, reject) => {
        const child = spawn(bin, args, { stdio: ['ignore', 'pipe', 'pipe'], env: {}, signal });
        let failure: Error | undefined;
        let diagnostic = '';
        child.stderr.on('data', (chunk: Buffer) => { diagnostic = (diagnostic + chunk.toString('utf8')).slice(-2048); });
        child.stdout.on('data', (chunk: Buffer) => {
          if (failure) return;
          size += chunk.length;
          if (size > outputLimit) {
            failure = Error('渲染产物超出限制。');
            child.kill();
          } else chunks.push(chunk);
        });
        child.once('error', error => { failure ??= error; });
        child.once('close', code => failure || code !== 0
          ? reject(failure ?? Error('Remotion 渲染或解码失败。', { cause: diagnostic })) : resolve());
      });
    } finally {
      // A disconnected Docker CLI does not by itself stop the container.
      if (docker) await new Promise<void>(resolve => {
        const cleanup = spawn(bin, ['rm', '-f', docker.name], { stdio: 'ignore', env: {}, signal: AbortSignal.timeout(5000) });
        cleanup.on('error', () => {});
        cleanup.once('close', () => resolve());
      });
    }
    signal.throwIfAborted();
    if (!size) throw Error('没有生成视频。');
    const bytes = Buffer.concat(chunks, size);
    return { bytes, digest: sha256(bytes) };
  } finally { await rm(job, { recursive: true, force: true }); }
}
