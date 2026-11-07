const assert = require('node:assert/strict');
const { accessSync,existsSync } = require('node:fs');
const { join, normalize } = require('node:path');
const asar = require('@electron/asar');

module.exports = async ({ appOutDir, electronPlatformName }) => {
  assert.ok(['win32','darwin'].includes(electronPlatformName));
  const source = join(__dirname, '../runtime-bundle');
  const resources = electronPlatformName === 'darwin'
    ? join(appOutDir,'GeneLoop Desktop.app','Contents','Resources') : join(appOutDir,'resources');
  if (electronPlatformName === 'win32'&&existsSync(join(resources,'geneloop-tools'))) require('./prune-windows-tools.cjs')(resources);
  const archive = join(resources, 'geneloop-runtime.asar');
  await asar.createPackageWithOptions(source, archive, { unpack: '*.{node,dll,exe,dylib,so}',
    unpackDir:'{node_modules/@remotion/compositor-*,node_modules/@esbuild/*,node_modules/esbuild,node_modules/@vscode/ripgrep*}' });
  for (const file of ['local-worker.mjs', 'node_modules/@deepseek-ai/dsh/lib/bin.js', 'node_modules/koffi/package.json']) {
    assert.equal(Boolean(asar.statFile(archive, normalize(file)).unpacked), false, '运行时入口必须封进 ASAR：' + file);
  }
  const platform = electronPlatformName === 'win32' ? 'win32-x64/win32_x64' : 'darwin-'+process.arch+'/darwin_'+process.arch;
  const native = 'node_modules/@koromix/koffi-'+platform+'/koffi.node';
  assert.equal(asar.statFile(archive, normalize(native)).unpacked, true, '本机文件权限工具需要实体文件');
  accessSync(join(archive + '.unpacked', native));
  const rg = `node_modules/@vscode/ripgrep-${electronPlatformName}-${process.arch}/bin/rg${electronPlatformName === 'win32' ? '.exe' : ''}`;
  assert.equal(asar.statFile(archive, normalize(rg)).unpacked, true, '搜索工具需要实体可执行文件');
  accessSync(join(archive + '.unpacked', rg));
};
