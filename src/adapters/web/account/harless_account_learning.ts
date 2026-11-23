import {randomBytes, randomUUID} from 'node:crypto';
import {lstatSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {runPrivacyWorker} from '../../privacy_worker_pool.ts';

const DAY = 86400000;
const terminal = new Set(['completed', 'failed', 'cancelled', 'budget_exhausted']);
const structure = 'rsi-structure.json';
const learningFiles = [structure, 'privacy-learning.json', 'privacy-learning-rejected',
  'rsi-learning-trace.json', 'rsi-learning-trace-rejected', 'ppt-learning-delivery.json'];
const rawFiles = ['events.jsonl', 'native-prefix.json'];
const clearedTaskFiles = ['task.json', 'answer.md', 'effective-config.json', 'session-header.json',
  'motif-audit.jsonl', 'bound-motif-task.json'];
const missing = (error: unknown) => (error as NodeJS.ErrnoException).code === 'ENOENT';

function readOwnedFile(path: string, maxBytes: number) {
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.nlink !== 1 || realpathSync(path) !== path || stat.size > maxBytes) throw Error('rsi_learning_file_invalid');
  return JSON.parse(readFileSync(path, 'utf8'));
}

function write(path: string, data: unknown) {
  const temporary = path + '-' + randomUUID() + '.tmp';
  try {
    writeFileSync(temporary, JSON.stringify(data), {mode: 0o600, flag: 'wx'});
    renameSync(temporary, path);
  } finally { rmSync(temporary, {force: true}); }
}

function retention(value: string | undefined, fallback: number) {
  if (value === undefined) return fallback;
  if (!/^\d{1,4}$/.test(value) || Number(value) < 1 || Number(value) > 3650)
    throw Error('rsi_learning_retention_invalid');
  return Number(value);
}

type Policy = {enabled: boolean; changedAt: number; toolKey: string};
type Task = {output: string; session: string; scene: string; status: string; finished: number; started: number; state: Record<string, any>};

export function createAccountLearning(config: {
  output: string; policyPath: string; principal: string; taskIds: () => readonly string[];
  isDeleted: (session: string) => boolean; isPurged: (session: string) => boolean;
  closing: (task: string) => boolean; python?: string;
  now?: () => number; rawDays?: number; learningDays?: number;
}) {
  const rawDays = config.rawDays ?? retention(process.env.GENELOOP_RSI_RAW_RETENTION_DAYS, 90);
  const learningDays = Math.min(rawDays, config.learningDays ?? retention(process.env.GENELOOP_RSI_LEARNING_RETENTION_DAYS, 30));
  const now = config.now ?? Date.now;
  const root = realpathSync(config.output);
  let policy: Policy = {enabled: false, changedAt: now(), toolKey: randomBytes(32).toString('hex')};
  let controller = new AbortController();
  const invalidate = () => {controller.abort(); controller = new AbortController();};
  try {
    const saved = readOwnedFile(config.policyPath, 4096);
    if (saved.version !== 1 || saved.principal !== config.principal || typeof saved.enabled !== 'boolean' ||
        !Number.isSafeInteger(saved.changedAt) || !/^[a-f0-9]{64}$/.test(saved.toolKey)) throw Error('rsi_learning_policy_invalid');
    policy = {enabled: saved.enabled, changedAt: saved.changedAt, toolKey: saved.toolKey};
  } catch (error) { if (!missing(error)) throw error; }

  function ownedTask(id: string): Task | undefined {
    if (!/^[a-f0-9]{32}$/.test(id)) return;
    const output = join(root, 'tasks', id);
    try {
      if (realpathSync(output) !== output) return;
      const state = readOwnedFile(join(output, 'task-state.json'), 32 * 1024 * 1024);
      if (state.user_id !== config.principal || state.task_id !== id || typeof state.session_id !== 'string' ||
          typeof state.scene !== 'string' || typeof state.status !== 'string') return;
      const started = Date.parse(state.started_at), finished = Date.parse(state.finished_at);
      return {output, session: state.session_id, scene: state.scene, status: state.status, finished, started, state};
    } catch (error) { if (!missing(error)) throw error; }
  }

  function eligible(task: Task) {
    return policy.enabled && terminal.has(task.status) && task.started >= policy.changedAt && Number.isFinite(task.finished) &&
      task.finished + learningDays * DAY > now() && !config.isDeleted(task.session);
  }

  function remove(output: string, names: string[]) {
    for (const name of names) rmSync(join(output, name), {force: true});
  }

  function sweep(onlySessions?: Set<string>) {
    for (const id of config.taskIds()) {
      if (config.closing(id)) continue;
      const task = ownedTask(id);
      if (!task || onlySessions && !onlySessions.has(task.session)) continue;
      const purged = config.isPurged(task.session);
      if (!eligible(task) || purged) {
        const temporary = readdirSync(task.output).filter(name => /^(?:rsi-structure\.json-|\.privacy-learning-)[a-f0-9-]+\.tmp$/.test(name));
        remove(task.output, [...learningFiles, ...temporary]);
      }
      if (purged || terminal.has(task.status) && task.finished + rawDays * DAY <= now()) {
        remove(task.output, rawFiles);
        const directory = join(task.output, 'native-sessions');
        try {
          if (realpathSync(directory) === directory) remove(directory,
            readdirSync(directory).filter(name => /^[a-z0-9-]+\.jsonl$/i.test(name)));
        } catch (error) { if (!missing(error)) throw error; }
      }
      if (purged) {
        remove(task.output, clearedTaskFiles);
        if (task.state.history_purged !== true) {
          const {task_id, user_id, session_id, scene, status, started_at, finished_at, created_at} = task.state;
          write(join(task.output, 'task-state.json'), {task_id, user_id, session_id, scene, status,
            started_at, finished_at, created_at, history_purged: true});
        }
      }
    }
  }

  function admitted(id: string) {
    const task = ownedTask(id);
    if (!task || !eligible(task)) return false;
    try {
      const view = readOwnedFile(join(task.output, structure), 4 * 1024 * 1024);
      return view.format === 'geneloop.rsi-learning-trace/v4' && view.status === task.status &&
        Object.keys(view).sort().join(',') === 'bindings,format,nodes,scene,status' &&
        Array.isArray(view.bindings) && view.bindings.length === 0 && Array.isArray(view.nodes) &&
        view.nodes.every((node: any) => node && Object.keys(node).sort().join(',') === 'outcome,tool' &&
          (node.tool === null ? node.outcome === 'unapproved_tool' : /^tool-[0-9a-f]{64}$/.test(node.tool) &&
            ['observed_success', 'missing_or_failed_result'].includes(node.outcome)));
    } catch { return false; }
  }

  const view = () => ({enabled: policy.enabled, raw_retention_days: rawDays, learning_retention_days: learningDays,
    scope: 'account_structure', native_history_retention: 'managed_by_session_host'});
  return {
    view,
    signal: () => controller.signal,
    invalidate,
    taskIds: () => policy.enabled ? config.taskIds().filter(admitted) : [],
    sweep,
    purge: (sessions: string[]) => sweep(new Set(sessions)),
    setEnabled(enabled: boolean) {
      if (policy.enabled !== enabled) {
        const next = {...policy, enabled, changedAt: now()};
        write(config.policyPath, {version: 1, principal: config.principal, ...next});
        policy = next;
        invalidate();
      }
      sweep();
      return view();
    },
    async capture(id: string, start: number | undefined) {
      if (!config.python || !Number.isSafeInteger(start)) return;
      const task = ownedTask(id);
      if (!task || !eligible(task)) return;
      const signal = controller.signal;
      try {
        const result = await runPrivacyWorker(config.python, 'structure', {input: join(task.output, 'events.jsonl'),
          scene: task.scene, status: task.status, start, catalog: join(task.output, 'effective-config.json'), tool_key: policy.toolKey}, signal);
        // No await between the final policy/ownership check and publication.
        if (!signal.aborted && eligible(task)) write(join(task.output, structure), result);
      } catch { /* A rejected sample cannot turn into a raw fallback. */ }
    },
    dispose() { controller.abort(); },
  };
}

export function mountAccountLearning(ctx: any, learning: ReturnType<typeof createAccountLearning>,
  serialize: <T>(operation: () => Promise<T>) => Promise<T>, changed?: () => void,
  sweepHistory?: () => Promise<unknown>) {
  ctx.effect(() => {
    const sweep = () => void serialize(async () => {
      learning.sweep();
      await sweepHistory?.();
    }).catch(() => console.warn('rsi_learning_retention_failed'));
    const interval = setInterval(sweep, 10 * 60 * 1000);
    interval.unref();
    sweep();
    return () => {clearInterval(interval); learning.dispose();};
  }, 'harless-account-learning-retention');
  ctx.effect(() => ctx.connection.fetch.register({path: '/api/harless/rsi-learning', methods: ['GET', 'POST'], requestBody: 'buffered',
    async fetch(request: Request) {
      const rejected = ctx.connection.requestRejection(request);
      if (rejected) return new Response('Unauthorized', {status: rejected});
      const headers = {'Cache-Control': 'no-store'};
      if (new URL(request.url).search) return Response.json({error: {code: 'invalid_learning_settings'}}, {status: 400, headers});
      if (request.method === 'GET') return Response.json(learning.view(), {headers});
      let body: any;
      try {
        if (!request.headers.get('content-type')?.startsWith('application/json')) throw Error();
        const text = await request.text();
        if (text.length > 128) throw Error();
        body = JSON.parse(text);
        if (!body || Object.keys(body).join(',') !== 'enabled' || typeof body.enabled !== 'boolean') throw Error();
      } catch { return Response.json({error: {code: 'invalid_learning_settings'}}, {status: 400, headers}); }
      try {
        const result = await serialize(async () => learning.setEnabled(body.enabled));
        changed?.();
        return Response.json(result, {headers});
      } catch { return Response.json({error: {code: 'learning_settings_unavailable'}}, {status: 503, headers}); }
    },
  }), 'harless-account-learning-api');
}
