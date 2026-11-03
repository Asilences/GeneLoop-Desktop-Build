import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import sharp from 'sharp';

const require = createRequire(import.meta.url);
const app = fileURLToPath(new URL('../', import.meta.url));
const repo = fileURLToPath(new URL('../../../', import.meta.url));
const assets = join(app, 'assets');
mkdirSync(join(assets, 'clients'), { recursive: true });
const manifest = { format: 1, dshVersion: '0.1.5-rc.3', sourceCommit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim(), clients: {}, staticFiles: [], scenes: [] };
const frontend = dirname(require.resolve('@deepseek-ai/dsh-web-frontend/package.json'));
cpSync(join(frontend, 'dist'), join(assets, 'frontend'), { recursive: true });
function inventory(directory, prefix = '') {
  for (const row of readdirSync(directory, { withFileTypes: true })) {
    if (row.isDirectory()) inventory(join(directory, row.name), prefix + row.name + '/');
    else manifest.staticFiles.push('/' + prefix + row.name);
  }
}
inventory(join(frontend, 'dist'));
const scope = dirname(dirname(require.resolve('@deepseek-ai/dsh/package.json')));
const licenses = [];
function client(pkg, base) {
  if (!pkg.dsh?.client) return;
  const entry = pkg.exports?.['./client'];
  const relative = typeof entry === 'string' ? entry : entry?.default;
  if (typeof relative !== 'string') throw Error('Missing client export: ' + pkg.name);
  const file = 'clients/' + pkg.name.replaceAll(/[^a-zA-Z0-9_-]/g, '_') + '.js';
  copyFileSync(join(base, relative), join(assets, file));
  manifest.clients[pkg.name] = { file, version: pkg.version, declaration: pkg.dsh.client };
  const licensePath = ['LICENSE', 'LICENSE.md', 'LICENSE.txt'].map(name => join(base, name)).find(existsSync);
  licenses.push(`## ${pkg.name} ${pkg.version}\n\n${licensePath ? readFileSync(licensePath, 'utf8') : 'License: ' + (pkg.license || 'See upstream package')}\n`);
}
for (const row of readdirSync(scope, { withFileTypes: true })) {
  const base = join(scope, row.name), file = join(base, 'package.json');
  if (existsSync(file)) client(JSON.parse(readFileSync(file, 'utf8')), base);
}
const custom = join(repo, 'src/adapters/harless_web_client');
client(JSON.parse(readFileSync(join(custom, 'package.json'), 'utf8')), custom);
for (const name of ['geneloop_brand.js', 'geneloop_workspaces.js', 'harless_account_link.js', 'geneloop_theme.css', 'harless_account.html']) copyFileSync(join(repo, 'src/adapters', name), join(assets, name));
copyFileSync(join(repo, 'src/adapters/brand/geneloop-spiral.svg'), join(assets, 'geneloop-spiral.svg'));
manifest.scenes = JSON.parse(readFileSync(join(repo, 'config/harless-scenes.json'), 'utf8')).scenes.map(({ id, label }) => ({ id, label }));
writeFileSync(join(assets, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
writeFileSync(join(assets, 'THIRD_PARTY_NOTICES.md'), '# GeneLoop Desktop bundled client packages\n\n' + licenses.join('\n'));
// 图标保持 SVG 的透明背景；非正方形 viewBox 的补边也必须透明。
const iconResize = { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } };
await sharp(join(assets, 'geneloop-spiral.svg')).resize(512, 512, iconResize).png().toFile(join(assets, 'icon.png'));
// Windows 原生 ICO 使用同一品牌 SVG 的多尺寸 PNG 帧，避免构建时再下载转换程序。
const sizes = [16, 32, 48, 64, 128, 256];
const frames = await Promise.all(sizes.map(size => sharp(join(assets, 'geneloop-spiral.svg')).resize(size, size, iconResize).png().toBuffer()));
const header = Buffer.alloc(6 + frames.length * 16);
header.writeUInt16LE(1, 2); header.writeUInt16LE(frames.length, 4);
let offset = header.length;
frames.forEach((frame, i) => {
  const at = 6 + i * 16;
  header[at] = sizes[i] === 256 ? 0 : sizes[i]; header[at + 1] = header[at];
  header.writeUInt16LE(1, at + 4); header.writeUInt16LE(32, at + 6);
  header.writeUInt32LE(frame.length, at + 8); header.writeUInt32LE(offset, at + 12);
  offset += frame.length;
});
writeFileSync(join(assets, 'icon.ico'), Buffer.concat([header, ...frames]));
console.log(`Bundled ${Object.keys(manifest.clients).length} client modules and ${manifest.staticFiles.length} frontend files from ${manifest.sourceCommit.slice(0, 7)}.`);
