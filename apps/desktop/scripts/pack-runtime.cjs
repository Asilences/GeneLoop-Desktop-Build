const assert = require('node:assert/strict');
const { accessSync } = require('node:fs');
const { join, normalize } = require('node:path');
const asar = require('@electron/asar');

module.exports = async ({ appOutDir, electronPlatformName }) => {
  if (electronPlatformName !== 'win32') return;
  const source = join(__dirname, '../runtime-bundle');
  const archive = join(appOutDir, 'resources', 'geneloop-runtime.asar');
  await asar.createPackageWithOptions(source, archive, { unpack: '*.{node,dll,exe}' });
  for (const file of ['local-worker.mjs', 'node_modules/@deepseek-ai/dsh/lib/bin.js', 'node_modules/koffi/package.json']) {
    assert.equal(Boolean(asar.statFile(archive, normalize(file)).unpacked), false, '运行时入口必须封进 ASAR：' + file);
  }
  const native = 'node_modules/@koromix/koffi-win32-x64/win32_x64/koffi.node';
  assert.equal(asar.statFile(archive, normalize(native)).unpacked, true, 'Win32 文件权限工具需要实体文件');
  accessSync(join(archive + '.unpacked', native));
};
