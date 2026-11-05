/** Host-selected research policies use original admission evidence and task lifecycle. */
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, renameSync} from 'node:fs';
import {join} from 'node:path';
import {strategyContext, type StrategyFileRef, type StrategySelection} from './capability_strategy.ts';

export type ResearchTaskStrategy = {
  enabled: boolean; scene_id: string; scope: string; snapshot: StrategyFileRef;
  selection: StrategySelection; feedback_directory: string;
};
export type FrozenTaskStrategy = ResearchTaskStrategy & {
  format: 'harless_task_strategy_v1'; owner: string; context_sha256: string;
};
const sha = (value: Uint8Array | string) => createHash('sha256').update(value).digest('hex');
function read(reference: StrategyFileRef) {
  const bytes = readFileSync(reference.path);
  if (sha(bytes) !== reference.sha256) throw Error('task_strategy_snapshot_changed');
  return JSON.parse(bytes.toString('utf8'));
}
export function taskStrategyContext(frozen: FrozenTaskStrategy, owner: string) {
  if (frozen.format !== 'harless_task_strategy_v1' || frozen.owner !== owner || frozen.enabled !== true)
    throw Error('task_strategy_owner_changed');
  const context = strategyContext(frozen.selection, read(frozen.snapshot), {
    owner, target: 'task', scope: frozen.scope, feedbackDirectory: frozen.feedback_directory,
  });
  const visible = Object.fromEntries((['strategy', 'target', 'scope', 'applicability', 'decision_policy',
    'capability_refs', 'authority'] as const).map(key => [key, context[key]]));
  const text = JSON.stringify(visible);
  if (Buffer.byteLength(text) > 12000) throw Error('task_strategy_context_too_large');
  if (frozen.context_sha256 && sha(text) !== frozen.context_sha256) throw Error('task_strategy_context_changed');
  return {context: visible, text, sha256: sha(text)};
}
export function assertTaskStrategyPrompt(frozen: FrozenTaskStrategy, owner: string, request: any) {
  const inherited = taskStrategyContext(frozen, owner);
  const systemMessages = (request.messages ?? []).filter((message: any) => message.role === 'system');
  const latest = systemMessages.at(-1);
  const system = latest ? (typeof latest.content === 'string' ? latest.content :
    (latest.content ?? []).filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n'))
    : request.system ?? '';
  if (typeof system !== 'string' || !system.includes(inherited.text)) throw Error('task_strategy_prompt_missing');
  return {context_sha256: inherited.sha256, system_sha256: sha(system)};
}
export function freezeTaskStrategy(config: ResearchTaskStrategy | undefined,
  task: {owner: string; scene_id: string; mode: string; rsi: boolean}): FrozenTaskStrategy | undefined {
  if (!config?.enabled || task.mode !== 'execute' || !task.rsi || task.scene_id !== config.scene_id) return;
  if (config.enabled !== true || typeof config.scope !== 'string' || !config.scope.trim()
      || typeof config.feedback_directory !== 'string' || !config.feedback_directory)
    throw Error('task_strategy_config_invalid');
  const frozen = {...structuredClone(config), format: 'harless_task_strategy_v1' as const,
    owner: task.owner, context_sha256: ''};
  frozen.context_sha256 = taskStrategyContext(frozen, task.owner).sha256;
  return frozen;
}
export function writeTaskStrategyContext(frozen: FrozenTaskStrategy, owner: string, output: string) {
  const context = taskStrategyContext(frozen, owner);
  const path = join(output, 'strategy-context.json');
  writeFileSync(path, context.text, {mode: 0o600});
  return {path, sha256: context.sha256};
}
export function writeTaskStrategyReceipt(frozen: FrozenTaskStrategy, task: {
  owner: string; task_id: string; session_id: string; scene_id: string; output: string;
  task_status: string; trace_start_index: number; exposure: 'prepared_only' | 'prompt_submitted';
}) {
  const reference = (name: string) => {
    const path = join(task.output, name); return {path, sha256: sha(readFileSync(path))};
  };
  const context = reference('strategy-context.json');
  if (context.sha256 !== frozen.context_sha256) throw Error('task_strategy_context_changed');
  const events = readFileSync(join(task.output, 'events.jsonl'), 'utf8');
  if (events && !events.endsWith('\n')) throw Error('task_strategy_events_incomplete');
  const evidence = ['task.json', 'effective-config.json', 'events.jsonl'].map(reference);
  const value = {format: 'harless_task_strategy_use_v1', owner: task.owner, task_id: task.task_id,
    session_id: task.session_id, scene_id: task.scene_id, scope: frozen.scope,
    selection: frozen.selection, strategy: JSON.parse(readFileSync(context.path, 'utf8')).strategy,
    snapshot: frozen.snapshot, context_ref: context, context_sha256: context.sha256,
    task_status: task.task_status, exposure: task.exposure,
    events_range: {start_index: task.trace_start_index, end_index: events.split('\n').filter(Boolean).length},
    semantic_adoption: null, quality_status: 'unreviewed', evidence};
  const path = join(task.output, 'strategy-use.json');
  writeFileSync(path + '.tmp', JSON.stringify(value, null, 2), {mode: 0o600});
  renameSync(path + '.tmp', path);
  return value;
}
