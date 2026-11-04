const { accessSync } = require('node:fs');
const { join } = require('node:path');

module.exports = ({ appOutDir, electronPlatformName }) => {
  if (electronPlatformName !== 'win32') return;
  const runtime = join(appOutDir, 'resources', 'geneloop-runtime');
  for (const file of ['local-worker.mjs', 'node_modules/@deepseek-ai/dsh/lib/bin.js', 'node_modules/koffi/package.json']) {
    try { accessSync(join(runtime, file)); }
    catch (cause) { throw Error('安装资源缺少本机运行时文件：' + file, { cause }); }
  }
};
