import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync} from 'node:fs';
import {once} from 'node:events';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import {SESSION_FORMAT_VERSION} from '@deepseek-ai/dsh-session';
import JsonlPersistence from '@deepseek-ai/dsh-session-persistence-jsonl';
import {createGateway} from '../scripts/harless_gateway.mjs';
import {digest} from '../src/motif_core/runtime/online_skill_runtime.mjs';
import {purgeNativeHistory} from '../src/adapters/web/sessions/harless_native_history.ts';
import {createSessionTrash} from '../src/adapters/web/sessions/harless_session_trash.ts';

const linux = {skip: process.platform !== 'linux'};
function temporary() { return realpathSync(mkdtempSync(join(tmpdir(), 'geneloop-native-erase-'))); }
function seed(storage, id) {
  return storage.create({id, version: SESSION_FORMAT_VERSION, createdAt: Date.now(), isSeeded: false, delegationDepth: 0});
}
function removeFixture(path) {
  assert.equal(realpathSync(path), path);
  assert.ok(path.startsWith(join(realpathSync(tmpdir()), 'geneloop-native-erase-')));
  rmSync(path, {recursive: true, force: true});
}

test('DSH writer lease defers physical purge and a clear retry erases all generations', linux, async () => {
  const root = temporary(), ctx = new Context();
  try {
    const storage = new JsonlPersistence(ctx, {root: join(root, 'sessions')});
    const writer = await seed(storage, 'erase-me');
    await writer.flush();
    const sibling = await seed(storage, 'keep-me');
    await sibling.flush(); await sibling.close();
    const tombstone = join(root, 'trash.json');
    const host = {owns: async () => {}, isPrivate: () => false, privateChildren: () => [], busy: () => false,
      describe: async () => ({title: 'synthetic history'}), purged: ids => purgeNativeHistory(root, ids)};
    const trash = createSessionTrash(tombstone, 'owner', host);
    await trash.mutate('delete', 'erase-me');
    assert.deepEqual(await trash.clear(trash.list().revision), {cleared: 1, native_pending: 1});
    assert.ok(await storage.stat('erase-me'));
    assert.throws(() => trash.assertVisible('erase-me'), {code: 'session_deleted'});
    await writer.close();
    const directory = join(root, 'sessions', '_no-cwd', 'erase-me');
    const cache = join(root, 'storages', 'session_projcache', 'sessions');
    mkdirSync(cache, {recursive: true});
    writeFileSync(join(cache, 'erase-me.json'), 'checkpoint');
    writeFileSync(join(cache, 'erase-me.json.bak.202601010000'), 'older checkpoint');
    writeFileSync(join(cache, 'keep-me.json'), 'unrelated');
    writeFileSync(join(directory, 'session.jsonl.zstd'), 'older generation');
    writeFileSync(join(directory, 'session.v3.jsonl.zstd.001122334455.tmp'), 'interrupted materialization');
    const restarted = createSessionTrash(tombstone, 'owner', host);
    assert.deepEqual(await restarted.clear(restarted.list().revision), {cleared: 0, native_pending: 0});
    assert.deepEqual(readdirSync(directory), ['session.lock']);
    assert.deepEqual(readdirSync(cache), ['keep-me.json']);
    assert.equal(await storage.stat('erase-me'), undefined);
    assert.ok(await storage.stat('keep-me'));
  } finally { await ctx.fiber.dispose(); removeFixture(root); }
});

test('gateway startup cleans a dormant member without launching its DSH host', linux, async () => {
  const root = temporary(), ctx = new Context();
  let gateway;
  try {
    const id = 'a'.repeat(22), foreign = 'b'.repeat(22);
    const principal = 'member-' + createHash('sha256').update(id).digest('hex').slice(0, 8);
    const membersDir = join(root, 'members'), home = join(membersDir, id, 'dsh');
    const db = join(root, 'db'), scope = digest({home: '/user/dsh', principal});
    mkdirSync(db, {recursive: true});
    mkdirSync(home, {recursive: true});
    writeFileSync(join(db, 'accounts.json'), JSON.stringify({version: 1, users: [{id, role:'member'}], invites: [], sessions: []}));
    const storage = new JsonlPersistence(ctx, {root: join(home, 'sessions')});
    const writer = await seed(storage, 'deleted-native');
    await writer.flush(); await writer.close();
    writeFileSync(join(home, `harless-web-ownership-${scope}-trash.json`), JSON.stringify({version: 1, principal,
      entries: [{session_id: 'deleted-native', title: '', deleted_at: '2026-01-01', purged_at: '2026-01-02', private_session_ids: []}]}));
    for (const [owner, task, session, expired] of [[id, '1'.repeat(32), 'deleted-native', false],
      [id, '2'.repeat(32), 'visible-native', true], [foreign, '3'.repeat(32), 'deleted-native', true]]) {
      const path = join(membersDir, owner, 'tasks', 'tasks', task);
      mkdirSync(path, {recursive:true});
      const timestamp = new Date(Date.now() - (expired ? 100 : 0) * 86400000).toISOString();
      writeFileSync(join(path, 'task-state.json'), JSON.stringify({task_id: task, session_id: session, user_id: principal,
        status: 'completed', scene: 'coding', started_at: timestamp, finished_at: timestamp, messages: ['private']}));
      for (const name of ['events.jsonl', 'rsi-structure.json', 'task.json', 'answer.md', 'ledger.jsonl'])
        writeFileSync(join(path, name), 'synthetic marker');
    }
    gateway = createGateway({dataDir: db, membersDir, publicOrigin: 'https://app.example.test',
      sourceDir: fileURLToPath(new URL('../src', import.meta.url)), memberPatch: []});
    gateway.server.listen(0, '127.0.0.1');
    await once(gateway.server, 'listening');
    const removed = join(membersDir, id, 'tasks', 'tasks', '1'.repeat(32));
    const expired = join(membersDir, id, 'tasks', 'tasks', '2'.repeat(32));
    for (let i = 0; i < 200 && await storage.stat('deleted-native'); i++) await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(await storage.stat('deleted-native'), undefined);
    assert.equal(gateway.backends.size, 0);
    for (const name of ['events.jsonl', 'rsi-structure.json', 'task.json', 'answer.md']) assert.equal(existsSync(join(removed,name)),false);
    assert.equal(JSON.parse(readFileSync(join(removed,'task-state.json'))).messages,undefined);
    assert.equal(existsSync(join(removed,'ledger.jsonl')),true);
    assert.equal(existsSync(join(expired,'events.jsonl')),false);
    assert.equal(existsSync(join(expired,'rsi-structure.json')),false);
    assert.equal(existsSync(join(expired,'task.json')),true);
    assert.equal(existsSync(join(membersDir, foreign, 'tasks', 'tasks', '3'.repeat(32), 'events.jsonl')),true);
  } finally {
    if (gateway?.server.listening) { const closed = once(gateway.server, 'close'); gateway.close(); await closed; }
    await ctx.fiber.dispose(); removeFixture(root);
  }
});
