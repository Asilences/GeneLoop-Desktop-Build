import {lstatSync, readdirSync, realpathSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {digest} from '../../../motif_core/runtime/online_skill_runtime.mjs';
import {createAccountLearning} from './harless_account_learning.ts';
import {purgeNativeHistory} from '../sessions/harless_native_history.ts';
import {clearedSessions, readSessionTrash} from '../sessions/harless_session_trash.ts';

function ownedDirectory(path: string) {
  try { return lstatSync(path).isDirectory() && realpathSync(path) === path; }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false; throw error; }
}

/** The gateway calls this only while a member has no running or starting host.
 * Resolve the same policy and tombstones the member host sees in its sandbox. */
export async function sweepDormantMemberPrivacy(members: string, id: string, prefix: string, standardLayout: boolean) {
  if (!/^[A-Za-z0-9_-]{22}$/.test(id) || !/^[0-9a-f]{8}$/.test(prefix)) return;
  const root = resolve(members), member = join(root, id), home = join(member, 'dsh');
  if (![root, member, home].every(ownedDirectory)) return;
  const principal = 'member-' + prefix;
  const scope = digest({home: '/user/dsh', principal});
  const base = join(home, 'harless-web-ownership-' + scope);
  const {entries} = readSessionTrash(base + '-trash.json', principal);
  const purged = new Set(clearedSessions(entries));
  const deleted = new Set(entries.flatMap(row => [row.session_id, ...row.private_session_ids]));
  const output = join(member, 'tasks');
  if (ownedDirectory(output) && ownedDirectory(join(output, 'tasks'))) {
    const ids = readdirSync(join(output, 'tasks'), {withFileTypes: true})
      .filter(row => row.isDirectory() && /^[a-f0-9]{32}$/.test(row.name)).map(row => row.name);
    const learning = createAccountLearning({output, principal, policyPath: base + '-rsi-learning.json',
      taskIds: () => ids, isDeleted: session => deleted.has(session), isPurged: session => purged.has(session), closing: () => false});
    try { learning.sweep(); } finally { learning.dispose(); }
  }
  await purgeNativeHistory(home, [...purged], {standardLayout});
}
