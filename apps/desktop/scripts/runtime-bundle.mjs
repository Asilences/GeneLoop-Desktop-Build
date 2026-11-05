import assert from 'node:assert/strict';
import { cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import { join, posix } from 'node:path';

export const pptRendererFiles = ['layout-policy', 'render'].map(name =>
  new URL('../../../scenarios/research_ppt/ts/' + name + '.ts', import.meta.url));

export function stageRuntime(app, destination, dependencies = app) {
  const lock = JSON.parse(readFileSync(join(dependencies, 'package-lock.json'), 'utf8'));
  const staged = new Set();
  function stage(name, requester = '', optional = false) {
    let folder = requester;
    while (true) {
      const key = posix.join(folder, 'node_modules', name);
      const entry = lock.packages[key], source = join(dependencies, key);
      if (entry && existsSync(join(source, 'package.json'))) {
        if (staged.has(key)) return;
        staged.add(key);
        cpSync(source, join(destination, key), {
          recursive: true,
          // The file-only SDK profile does not consume source maps or TypeScript declarations.
          filter: path => {
            if (path === source) return true;
            const parts = path.slice(source.length + 1).split(/[\\/]/);
            if (parts.at(-1) === 'node_modules' || /\.(?:map|d\.(?:ts|cts|mts))$/i.test(path)) return false;
            if (name === 'node-pty' && parts[0] === 'prebuilds' && parts.length === 2) {
              return parts[1] === process.platform + '-' + process.arch;
            }
            if (name === 'node-pty' && parts[0] === 'third_party' && parts.at(-1) === 'win10-arm64') return false;
            return true;
          },
        });
        for (const dep of Object.keys(entry.dependencies || {})) stage(dep, key);
        for (const dep of Object.keys(entry.optionalDependencies || {})) stage(dep, key, true);
        for (const dep of Object.keys(entry.peerDependencies || {})) stage(dep, key, entry.peerDependenciesMeta?.[dep]?.optional);
        return;
      }
      if (!folder) break;
      folder = folder.replace(/(?:^|\/)node_modules\/(@[^/]+\/)?[^/]+$/, '');
    }
    assert.ok(optional, '缺少锁定依赖：' + name + '（' + requester + '）');
  }
  stage('@deepseek-ai/dsh');
  stage('csv-parse');
  stage('pdfjs-dist');
  stage('pptxgenjs');
  for (const name of ['@remotion/renderer', '@remotion/bundler', 'remotion', 'react', 'react-dom']) stage(name);
  for (const file of pptRendererFiles) {
    const name = posix.basename(file.pathname, '.ts');
    const source = readFileSync(file, 'utf8').replace('./layout-policy.js', './local-ppt-layout-policy.mjs');
    writeFileSync(join(destination, 'local-ppt-' + name + '.mjs'), stripTypeScriptTypes(source, { mode: 'transform' }));
  }
  cpSync(join(app, 'runtime'), destination, { recursive: true });
  return staged.size;
}
