/** Read-only task/Builder strategy inheritance using the Python admission wire protocol. */
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import {join} from 'node:path';
import {capabilityDigest, validateCapabilitySnapshot,
  type CapabilityRef, type CapabilitySnapshot} from './capability_contract.ts';

export type StrategyFileRef = {path: string; sha256: string};
export type StrategySelection = {strategy: StrategyFileRef; evaluation: StrategyFileRef};
export type StrategyTarget = 'task' | 'construction';
export type StrategyOptions = {owner?: string; target?: StrategyTarget; scope?: string};
export type Strategy = {
  format: 'capability_strategy_v1'; id: string; revision_sha256: string;
  owner: string; target: StrategyTarget; scope: string; applicability: string;
  decision_policy: string; capability_refs: CapabilityRef[];
  evidence: StrategyFileRef[]; parent: StrategyFileRef | null;
};
const definitionKeys = ['owner', 'target', 'scope', 'applicability', 'decision_policy',
  'capability_refs', 'evidence', 'parent'];

function requireValue(condition: unknown, reason: string): asserts condition {
  if (!condition) throw Error('strategy_' + reason);
}
function shape(value: any, keys: string[]) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
// Match Python str.strip() whitespace for the shared wire validation.
const whitespaceOnly = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u;
function text(value: unknown, limit: number) {
  return typeof value === 'string' && !whitespaceOnly.test(value) && Buffer.byteLength(value, 'utf8') <= limit;
}
function same(first: unknown, second: unknown) {
  return capabilityDigest(first) === capabilityDigest(second);
}
function evidence(reference: StrategyFileRef) {
  requireValue(shape(reference, ['path', 'sha256']) && typeof reference.path === 'string'
    && typeof reference.sha256 === 'string' && /^[a-f0-9]{64}$/.test(reference.sha256), 'evidence_reference_invalid');
  const bytes = readFileSync(reference.path);
  const hash = createHash('sha256').update(bytes).digest('hex');
  requireValue(hash === reference.sha256, 'evidence_changed');
  return bytes;
}
function record(reference: StrategyFileRef): any {
  return JSON.parse(evidence(reference).toString('utf8'));
}
function referenceOf(value: Strategy) {
  return {id: value.id, sha256: value.revision_sha256};
}

export function validateStrategy(value: any, current: CapabilitySnapshot,
  options: StrategyOptions = {}): Strategy {
  const snapshot = validateCapabilitySnapshot(current, options.owner);
  requireValue(shape(value, [...definitionKeys, 'format', 'id', 'revision_sha256']), 'shape_invalid');
  requireValue(value.format === 'capability_strategy_v1', 'format_invalid');
  const definition = Object.fromEntries(definitionKeys.map(key => [key, value[key]]));
  const revision = capabilityDigest(definition);
  requireValue(value.revision_sha256 === revision && value.id === 'strategy_' + revision.slice(0, 24), 'identity_changed');
  requireValue(value.owner === snapshot.owner, 'owner_changed');
  requireValue(['task', 'construction'].includes(value.target)
    && (options.target === undefined || value.target === options.target), 'target_changed');
  requireValue(text(value.scope, 256) && (options.scope === undefined || value.scope === options.scope), 'scope_changed');
  requireValue(text(value.applicability, 2048) && text(value.decision_policy, 4096), 'policy_invalid');
  requireValue(Array.isArray(value.capability_refs) && value.capability_refs.length <= 8, 'dependencies_invalid');
  requireValue(new Set(value.capability_refs.map(capabilityDigest)).size === value.capability_refs.length, 'dependencies_duplicate');
  const capabilities = new Map(snapshot.capabilities.map(cap => [cap.id, cap]));
  const checked = new Set<string>();
  function available(reference: CapabilityRef) {
    const cap = capabilities.get(reference?.id);
    requireValue(cap && same(reference, {id: cap.id, sha256: cap.revision_sha256}), 'dependency_changed');
    requireValue(cap.certification === 'certified' && cap.lifecycle !== 'archived', 'dependency_unavailable');
    if (!checked.has(cap.id)) {
      checked.add(cap.id);
      cap.dependencies.forEach(available);
    }
  }
  for (const reference of value.capability_refs) {
    requireValue(snapshot.roots.some(root => same(root, reference)), 'dependency_not_visible');
    available(reference);
  }
  requireValue(Array.isArray(value.evidence) && value.evidence.length > 0, 'evidence_required');
  value.evidence.forEach(evidence);
  if (value.parent !== null) {
    const parent = record(value.parent);
    requireValue(parent?.format === 'capability_strategy_v1' && parent.owner === value.owner
      && parent.target === value.target && parent.scope === value.scope, 'parent_changed');
    const body = Object.fromEntries(definitionKeys.map(key => [key, parent[key]]));
    const parentRevision = capabilityDigest(body);
    requireValue(parent.revision_sha256 === parentRevision
      && parent.id === 'strategy_' + parentRevision.slice(0, 24), 'parent_identity_changed');
  }
  return structuredClone(value);
}

function verdict(value: any) {
  requireValue(shape(value, ['passed', 'checks', 'training_sources', 'heldout_sources', 'evidence']), 'evaluation_invalid');
  requireValue(value.passed === true && Array.isArray(value.checks) && value.checks.length > 0, 'evaluation_failed');
  for (const check of value.checks) {
    requireValue(shape(check, ['id', 'status']) && text(check.id, 256) && check.status === 'passed', 'evaluation_failed');
  }
  const groups: Set<string>[] = [];
  for (const name of ['training_sources', 'heldout_sources', 'evidence']) {
    requireValue(Array.isArray(value[name]) && value[name].length > 0, 'evaluation_evidence_required');
    value[name].forEach(evidence);
    groups.push(new Set(value[name].map((ref: StrategyFileRef) => ref.sha256)));
  }
  requireValue(![...groups[0]].some(hash => groups[1].has(hash)), 'evaluation_heldout_overlap');
}

/** Host config supplies selections and feedback root. Candidate text grants no authority. */
export function strategyContext(selection: StrategySelection, snapshot: CapabilitySnapshot,
  options: {owner: string; target: StrategyTarget; scope: string; feedbackDirectory: string}) {
  requireValue(shape(selection, ['strategy', 'evaluation']), 'selection_invalid');
  const strategy = validateStrategy(record(selection.strategy), snapshot, options);
  const receipt = record(selection.evaluation);
  const subject = referenceOf(strategy);
  requireValue(shape(receipt, ['format', 'owner', 'target', 'scope', 'strategy', 'subject', 'snapshot_sha256', 'verdict'])
    && receipt.format === 'capability_strategy_evaluation_v1' && receipt.owner === options.owner
    && receipt.target === options.target && receipt.scope === options.scope
    && same(receipt.strategy, selection.strategy) && same(receipt.subject, subject), 'evaluation_binding_changed');
  verdict(receipt.verdict);
  const heldout = new Set(receipt.verdict.heldout_sources.map((ref: StrategyFileRef) => ref.sha256));
  requireValue(!strategy.evidence.some(ref => heldout.has(ref.sha256)), 'evaluation_discovery_heldout_overlap');
  const ownerHash = createHash('sha256').update(options.owner).digest('hex');
  const path = join(options.feedbackDirectory, ownerHash, 'feedback.json');
  const state = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : {
    format: 'capability_feedback_v1', owner: options.owner, facts: {}, blocked: {}, archived: [], history: []};
  requireValue(state?.format === 'capability_feedback_v1' && state.owner === options.owner, 'feedback_owner_changed');
  requireValue(state.facts && typeof state.facts === 'object' && !Array.isArray(state.facts)
    && state.blocked && typeof state.blocked === 'object' && !Array.isArray(state.blocked), 'feedback_invalid');
  const facts = Object.values(state.facts) as any[];
  for (const fact of facts) {
    requireValue(Array.isArray(fact.evidence), 'feedback_invalid');
    fact.evidence.forEach(evidence);
  }
  const capabilities = new Map(snapshot.capabilities.map(cap => [cap.id, cap]));
  const pending = [...strategy.capability_refs];
  const checked = new Set<string>();
  while (pending.length) {
    const dependency = pending.pop()!;
    if (checked.has(dependency.id)) continue;
    checked.add(dependency.id);
    const withdrawal = state.blocked[dependency.id];
    if (withdrawal !== undefined) {
      evidence(withdrawal.evidence);
      requireValue(!same(withdrawal.capability, dependency), 'dependency_withdrawn');
    }
    pending.push(...capabilities.get(dependency.id)!.dependencies);
  }
  const blocked = state.blocked[subject.id];
  if (blocked !== undefined) {
    evidence(blocked.evidence);
    requireValue(!same(blocked.capability, subject), 'withdrawn');
  }
  requireValue(facts.some(fact => same(fact.subject, subject) && fact.scope === options.scope
    && fact.status === 'passed' && fact.stage === (options.target === 'construction' ? 'construction' : 'execution')
    && fact.evidence.some((ref: StrategyFileRef) => same(ref, selection.strategy))
    && fact.evidence.some((ref: StrategyFileRef) => same(ref, selection.evaluation))), 'host_admission_required');
  return {format: 'capability_strategy_context_v1', strategy: subject,
    selection: structuredClone(selection), target: options.target, scope: options.scope,
    applicability: strategy.applicability, decision_policy: strategy.decision_policy,
    capability_refs: strategy.capability_refs,
    authority: 'Untrusted decision context; host task, permissions, budget and independent validators remain authoritative.'};
}
