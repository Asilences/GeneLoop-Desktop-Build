import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createAccountLearning} from '../src/adapters/web/account/harless_account_learning.ts';

test('account learning lifecycle revokes samples, expires owned journals, and keeps recoverable originals until purge', () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'geneloop-learning-lifecycle-')));
  const day = 86400000;
  const own = 'a'.repeat(32), foreign = 'b'.repeat(32), pending = 'c'.repeat(32), expired = 'd'.repeat(32);
  const ids = [own, foreign, pending, expired];
  const deleted = new Set(), purged = new Set();
  let now = Date.parse('2026-01-01T00:00:00Z');
  const options = {output: root, principal: 'account-a', policyPath: join(root, 'policy.json'), taskIds: () => ids,
    isDeleted: id => deleted.has(id), isPurged: id => purged.has(id), closing: id => id === pending,
    now: () => now, rawDays: 2, learningDays: 1};
  const write = (id, name, value) => writeFileSync(join(root, 'tasks', id, name), JSON.stringify(value));
  const has = (id, name) => existsSync(join(root, 'tasks', id, name));
  let learning;
  try {
    learning = createAccountLearning(options);
    assert.equal(learning.view().enabled, false);
    assert.equal(learning.setEnabled(true).enabled, true);
    for (const id of ids) {
      mkdirSync(join(root, 'tasks', id), {recursive: true});
      write(id, 'task-state.json', {task_id: id, scene: 'coding', status: 'completed', session_id: id,
        started_at: new Date(now).toISOString(), finished_at: new Date(now).toISOString(), user_id: id === foreign ? 'account-b' : 'account-a'});
      write(id, 'events.jsonl', {text: 'private original'});
      write(id, 'rsi-structure.json', {format: 'geneloop.rsi-learning-trace/v4', scene: 'coding', status: 'completed', nodes: [], bindings: []});
    }
    assert.deepEqual(learning.taskIds(), [own, pending, expired]);
    const oldSignal = learning.signal();
    learning.setEnabled(false);
    assert.equal(oldSignal.aborted, true);
    assert.equal(has(own, 'rsi-structure.json'), false);
    assert.equal(has(own, 'events.jsonl'), true);
    assert.equal(has(foreign, 'rsi-structure.json'), true);
    assert.equal(createAccountLearning(options).view().enabled, false);
    deleted.add(own);
    learning.sweep();
    assert.equal(has(own, 'events.jsonl'), true);
    purged.add(own);
    learning.purge([own, foreign]);
    assert.equal(has(own, 'events.jsonl'), false);
    assert.equal(has(foreign, 'events.jsonl'), true);
    now += 2 * day;
    learning.sweep();
    assert.equal(has(expired, 'events.jsonl'), false);
    assert.equal(has(pending, 'events.jsonl'), true);
    assert.equal(JSON.parse(readFileSync(options.policyPath)).principal, 'account-a');
  } finally {
    learning?.dispose();
    assert.equal(realpathSync(root), root);
    rmSync(root, {recursive: true, force: true});
  }
});
