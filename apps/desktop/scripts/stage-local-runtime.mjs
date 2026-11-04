import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stageRuntime } from './runtime-bundle.mjs';

assert.equal(process.platform, 'win32', '本机执行预览当前仅构建 Windows x64');
assert.equal(process.arch, 'x64');
const app = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
const destination = resolve(app, 'runtime-bundle');
const marker = join(destination, '.geneloop-runtime');
const fingerprint = createHash('sha256');
fingerprint.update(readFileSync(join(app, 'package-lock.json')));
fingerprint.update(readFileSync(new URL('./runtime-bundle.mjs', import.meta.url)));
for (const file of readdirSync(join(app, 'runtime')).sort()) fingerprint.update(readFileSync(join(app, 'runtime', file)));
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
writeFileSync(marker, digest);
console.log('本机运行时已准备，锁定软件包数量：' + count);
