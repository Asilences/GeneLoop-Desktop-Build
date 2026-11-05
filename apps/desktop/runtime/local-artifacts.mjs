import { mkdtempSync, realpathSync, rmSync, lstatSync, readdirSync, chmodSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';
const remove = process.versions.electron ? createRequire(import.meta.url)('original-fs').rmSync : rmSync;

export function removeScratchDirectory(path, parent) {
  if (dirname(path) !== parent || realpathSync(path) !== path) throw Error('临时目录位置已变化，保留现场。');
  // Office and Chromium may create read-only Documents/profile directories.
  // Normalize only plain directories in our private tree, never link targets.
  if (process.platform === 'win32') {
    const walk = directory => {
      const info=lstatSync(directory);
      if (!info.isDirectory() || info.isSymbolicLink()) return;
      chmodSync(directory,0o700);
      for (const item of readdirSync(directory,{withFileTypes:true})) {
        if (item.isDirectory() && !item.isSymbolicLink()) walk(join(directory,item.name));
      }
    };
    walk(path);
  }
  remove(path,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}

export async function inSceneScratch(run) {
  // The main process starts the worker in its own per-turn directory.
  const root = realpathSync(process.cwd());
  const path = mkdtempSync(join(root, 'scene-'));
  try { return await run(path); }
  finally {
    try {
      removeScratchDirectory(path,root);
    } catch (error) {
      // Office can hold temporary files briefly. The parent cleans the run directory after exit.
      if (!['EPERM', 'EBUSY', 'ENOTEMPTY', 'ENOENT'].includes(error.code)) throw error;
    }
  }
}

export function publishArtifacts(writer, onReport, signal, items) {
  signal.throwIfAborted();
  const artifacts = writer.writeArtifacts(items);
  for (const artifact of artifacts) onReport?.(artifact);
  return artifacts;
}
