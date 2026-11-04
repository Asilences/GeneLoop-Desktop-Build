import assert from 'node:assert/strict';
import { cpSync, existsSync, readFileSync } from 'node:fs';
import { join, posix } from 'node:path';

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
          filter: path => path === source || path.split(/[\\/]/).at(-1) !== 'node_modules',
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
  cpSync(join(app, 'runtime'), destination, { recursive: true });
  return staged.size;
}
