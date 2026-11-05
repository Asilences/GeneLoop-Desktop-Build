import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { pptRendererFiles, stageRuntime } from './runtime-bundle.mjs';

assert.ok(['win32', 'darwin'].includes(process.platform), '请在目标 Windows 或 macOS 平台原生构建。');
assert.ok(process.arch === 'x64' || process.platform === 'darwin' && process.arch === 'arm64');
const app = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
const destination = resolve(app, 'runtime-bundle');
const marker = join(destination, '.geneloop-runtime');
const fingerprint = createHash('sha256');
fingerprint.update(process.platform + '/' + process.arch);
fingerprint.update(readFileSync(join(app, 'package-lock.json')));
fingerprint.update(readFileSync(new URL('./runtime-bundle.mjs', import.meta.url)));
fingerprint.update(readFileSync(new URL('./stage-local-runtime.mjs', import.meta.url)));
if (process.platform === 'win32') fingerprint.update(readFileSync(join(app,'native/RemotionBrowser.cs')));
for (const file of readdirSync(join(app, 'runtime')).sort()) fingerprint.update(readFileSync(join(app, 'runtime', file)));
for (const source of pptRendererFiles) fingerprint.update(readFileSync(source));
const digest = fingerprint.digest('hex');
if (existsSync(destination)) {
  assert.equal(realpathSync(destination).toLowerCase(), destination.toLowerCase(), '运行时目录不得是链接');
  assert.ok(existsSync(marker), '保留现有目录，无法覆盖未识别的运行时目录');
  if (readFileSync(marker, 'utf8') === digest) process.exit(0);
  rmSync(destination, { recursive: true });
}
mkdirSync(destination);
writeFileSync(marker, 'building');
const count = stageRuntime(app, destination);
if (process.platform === 'win32') {
  const output = join(destination,'native');mkdirSync(output);
  const compiler = join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/csc.exe');
  const result = spawnSync(compiler,['/nologo','/target:exe','/reference:System.Web.Extensions.dll',
    '/out:'+join(output,'remotion-browser.exe'),join(app,'native/RemotionBrowser.cs')],{encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,'浏览器沙箱入口编译失败：'+result.stdout+result.stderr);
}
writeFileSync(marker, digest);
console.log('本机运行时已准备，锁定软件包数量：' + count);
