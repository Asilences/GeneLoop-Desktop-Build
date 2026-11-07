import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const app = fileURLToPath(new URL('../',import.meta.url));
if (process.platform === 'win32') await import('./wrap-installer.mjs');
else if (process.platform === 'darwin') {
  const cli = join(app,'node_modules/electron-builder/cli.js');
  const result = spawnSync(process.execPath,[cli,'--config',join(app,'electron-builder.config.cjs'),'--mac',process.arch === 'arm64'?'--arm64':'--x64','--publish','never'],
    {cwd:app,stdio:'inherit'});
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} else throw Error('请在 Windows 或 Mac 原生构建安装包。');
