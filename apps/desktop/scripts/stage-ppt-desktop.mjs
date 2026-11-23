/** Materialize the complete PPT resources at desktop build time. */
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { stagePptDeck } from './stage-ppt-deck.mjs';

const hash = bytes => createHash('sha256').update(bytes).digest('hex');

export function stageDesktopPpt(sourceRoot, destination) {
  const assets = join(sourceRoot, 'scenarios/ppt_master/third_party/ppt-master-desktop');
  const provenanceBytes = readFileSync(join(assets, 'PROVENANCE.json'));
  const provenance = JSON.parse(provenanceBytes);
  const archive = readFileSync(join(assets, 'ppt-master-presentation.zip'));
  if (provenance.schema_version !== 1 || hash(archive) !== provenance.archive_sha256) {
    throw Error('Desktop PPT resource archive digest mismatch');
  }

  const staged = stagePptDeck(sourceRoot, destination);
  const thirdParty = join(staged.root, 'scenarios/ppt_master/third_party');
  const require = createRequire(join(thirdParty, 'dsh-ppt/package.json'));
  const entries = Object.entries(require('fflate').unzipSync(archive))
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0);
  const caseFolded = new Set();
  const files = Object.create(null);
  for (const [name, bytes] of entries) {
    const key = name.toLowerCase();
    if (/[\\:\u0000-\u001f]/.test(name) || name.split('/').some(part => !part || part === '.' || part === '..') ||
        caseFolded.has(key)) {
      throw Error('Unsafe or duplicate desktop PPT resource path');
    }
    caseFolded.add(key);
    files[name] = hash(bytes);
  }
  const serialized = JSON.stringify(files).replace(/[\u007f-\uffff]/g, char =>
    '\\u' + char.charCodeAt(0).toString(16).padStart(4, '0'));
  if (entries.length !== provenance.file_count || hash(serialized) !== provenance.bundle_sha256) {
    throw Error('Desktop PPT resource tree digest mismatch');
  }

  const root = join(thirdParty, 'ppt-master');
  for (const [name, bytes] of entries) {
    const target = join(root, ...name.split('/'));
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, bytes, { flag: 'wx' });
  }
  writeFileSync(join(thirdParty, 'ppt-master-provenance.json'), provenanceBytes, { flag: 'wx' });
  writeFileSync(join(thirdParty, 'ppt-master-desktop-lock.json'), JSON.stringify({
    schema_version: 1, version: provenance.upstream_version_label,
    package_sha256: provenance.bundle_sha256, files,
  }) + '\n', { flag: 'wx' });
  return { ...staged, ppt_master: { root, sha256: provenance.bundle_sha256, files: entries.length } };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  if (process.argv.length !== 3) throw Error('A fresh desktop PPT bundle destination is required');
  const source = fileURLToPath(new URL('../../../', import.meta.url));
  console.log(JSON.stringify(stageDesktopPpt(source, resolve(process.argv[2]))));
}
