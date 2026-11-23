import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const app = fileURLToPath(new URL('../',import.meta.url));
const complete = process.argv.includes('--complete'), lightweight = process.argv.includes('--lightweight');
if (complete && lightweight) throw Error('完整安装与轻量安装只能选择一种。');
// The normal product installer is complete. Keep the previous environment-only
// entry for explicit CI tooling, while npm run dist always selects --complete.
if (complete) delete process.env.GENELOOP_DESKTOP_TOOL_PACKS;
if (lightweight) process.env.GENELOOP_DESKTOP_TOOL_PACKS = '1';
process.argv = process.argv.filter(arg => arg !== '--complete' && arg !== '--lightweight');
if (process.platform === 'win32') await import('./wrap-installer.mjs');
else if (process.platform === 'darwin') {
  const cli = join(app,'node_modules/electron-builder/cli.js');
  const result = spawnSync(process.execPath,[cli,'--config',join(app,'electron-builder.config.cjs'),'--mac',process.arch === 'arm64'?'--arm64':'--x64','--publish','never'],
    {cwd:app,stdio:'inherit'});
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} else throw Error('请在 Windows 或 Mac 原生构建安装包。');
