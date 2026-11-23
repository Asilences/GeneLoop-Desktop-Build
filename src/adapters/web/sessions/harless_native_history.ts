import {constants} from 'node:fs';
import {lstat, open, readdir, realpath, unlink} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {join, resolve} from 'node:path';
import {tryLockExclusive} from '@deepseek-ai/node-addon-system/flock';
import {parseSessionFormatLogFilename} from '@deepseek-ai/dsh-session-format';

const require = createRequire(import.meta.url);
const supported = require('@deepseek-ai/dsh-session-persistence-jsonl/package.json').version === '0.1.5-rc.3';
const missing = (error: unknown) => (error as NodeJS.ErrnoException).code === 'ENOENT';
export const sessionIdPattern = /^[A-Za-z0-9_-]{1,200}$/;

async function directory(path: string) {
  try {
    if (!(await lstat(path)).isDirectory() || await realpath(path) !== path) throw Error('rsi_native_directory_invalid');
    return true;
  } catch (error) { if (missing(error)) return false; throw error; }
}

async function eraseFile(path: string) {
  try {
    const state = await lstat(path);
    if (!state.isFile() || state.nlink !== 1) throw Error('rsi_native_artifact_invalid');
    await unlink(path);
  } catch (error) { if (!missing(error)) throw error; }
}

function isJournal(name: string) {
  const raw = name.replace(/\.zstd$/, '');
  if (parseSessionFormatLogFilename(raw) !== undefined) return true;
  const staging = name.replace(/\.[a-f0-9]{12}\.tmp$/, '').replace(/\.zstd$/, '');
  return staging !== raw && parseSessionFormatLogFilename(staging) !== undefined ||
    /^session\.migration\.[a-f0-9]+\.jsonl(?:\.zstd)?\.tmp$/.test(name);
}

async function eraseJournals(path: string, id: string, live: (id: string) => boolean) {
  const lockPath = join(path, 'session.lock');
  const lock = await open(lockPath, constants.O_RDWR | constants.O_CREAT | constants.O_NOFOLLOW, 0o600);
  try {
    await tryLockExclusive(lock.fd);
    const held = await lock.stat({bigint: true}), current = await lstat(lockPath, {bigint: true});
    if (!held.isFile() || held.nlink !== 1n || held.ino !== current.ino || held.dev !== current.dev ||
        !await directory(path) || live(id)) throw Error('rsi_native_writer_active');
    for (const name of await readdir(path)) if (isJournal(name)) await eraseFile(join(path, name));
    const parent = await open(path, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
    try { await parent.sync(); } finally { await parent.close(); }
    // Keep the lock inode. DSH can still have contenders holding this descriptor.
  } finally { await lock.close(); }
}

/** DSH documents pruning as out-of-band maintenance. Only clear tombstones
 * enter here. The pinned provider's public filename parser and POSIX lock
 * protect all generations while retaining the provider's stable lock inode. */
export async function purgeNativeHistory(home: string | null, ids: readonly string[], options: {
  live?: (id: string) => boolean; deleteCheckpoint?: (id: string) => Promise<unknown>;
  standardLayout?: boolean;
} = {}) {
  const unique = [...new Set(ids)];
  if (!unique.length) return 0;
  if (!home || !supported || process.platform !== 'linux' || options.standardLayout === false) return unique.length;
  const root = resolve(home), sessions = join(root, 'sessions');
  const live = options.live ?? (() => false);
  let projects: string[], cache: string | undefined;
  try {
    if (!await directory(root)) return unique.length;
    projects = await directory(sessions) ? (await readdir(sessions, {withFileTypes: true}))
      .filter(entry => entry.isDirectory()).map(entry => join(sessions, entry.name)) : [];
    for (const path of ['storages', 'storages/session_projcache', 'storages/session_projcache/sessions']) {
      if (!await directory(join(root, path))) break;
      if (path.endsWith('/sessions')) cache = join(root, path);
    }
  } catch { return unique.length; }
  let pending = 0;
  for (const id of unique) {
    try {
      if (!sessionIdPattern.test(id) || live(id)) throw Error('rsi_native_writer_active');
      let located: string | undefined;
      for (const project of projects) {
        // The pinned provider refuses this old flat layout as well.
        for (const suffix of ['.jsonl', '.jsonl.zstd']) {
          try { await lstat(join(project, id + suffix)); throw Error('rsi_native_legacy_layout'); }
          catch (error) { if (!missing(error)) throw error; }
        }
        const path = join(project, id);
        if (!await directory(path)) continue;
        if (located) throw Error('rsi_native_duplicate_session');
        located = path;
      }
      if (located) await eraseJournals(located, id, live);
      if (live(id)) throw Error('rsi_native_writer_active');
      await options.deleteCheckpoint?.(id);
      if (cache) for (const name of await readdir(cache)) {
        if (name === id + '.json' || name.startsWith(id + '.json.bak.') && /^\d{12}$/.test(name.slice(id.length + 10)))
          await eraseFile(join(cache, name));
      }
    } catch { pending++; }
  }
  return pending;
}

export function nativeHistoryMaintenance(ctx: any, home: string | null) {
  return (ids: readonly string[]) => {
    const persistence = ctx.get?.('sessionPersistence') ?? ctx.sessionPersistence;
    const query = ctx.get?.('sessionQuery') ?? ctx.sessionQuery;
    const store = ctx.get?.('storageDomain') ?? ctx.storageDomain;
    return purgeNativeHistory(home, ids, {
      live: id => Boolean(ctx.sessions?.get?.(id) || ctx.agents?.get?.(id)),
      deleteCheckpoint: id => store?.get('session_projcache')?.table('sessions').delete(id),
      standardLayout: (!persistence?.config?.root || home !== null &&
        resolve(persistence.config.root) === resolve(home, 'sessions')) &&
        (!query?.config?.path || query.config.openAt === 'never' || query.config.path === ':memory:'),
    });
  };
}

export async function nativePrivateChildren(ctx: any, parent: string) {
  const persistence = ctx.get?.('sessionPersistence') ?? ctx.sessionPersistence;
  if (!persistence?.list) return [];
  const children = new Map<string, string[]>();
  for (const {header} of await persistence.list()) {
    if (header.origin !== 'subagent' || !header.parentSession || !sessionIdPattern.test(header.id)) continue;
    const siblings = children.get(header.parentSession) ?? [];
    siblings.push(header.id);
    children.set(header.parentSession, siblings);
  }
  const seen = new Set([parent]);
  for (const id of seen) for (const child of children.get(id) ?? []) seen.add(child);
  seen.delete(parent);
  return [...seen];
}
