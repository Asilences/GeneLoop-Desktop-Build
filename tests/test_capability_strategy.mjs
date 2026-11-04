/** Python admission -> TypeScript inheritance diagnostics, with no model calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, realpathSync, readFileSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {capabilityDigest, createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {validateStrategy, strategyContext} from '../src/adapters/capability_strategy.ts';

const python = process.env.SSS_PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3');
function fixture(t) {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), 'strategy-wire-')));
  t.after(() => rmSync(directory, {recursive: true, force: true}));
  const run = spawnSync(python, ['-c', `import json,sys
from pathlib import Path
from tests.test_capability_contract import leaf,compose
from src.adapters.capability_contract import capability_ref,create_capability_snapshot
from src.adapters.capability_feedback import CapabilityFeedback,file_ref
from src.adapters.capability_strategy import create_strategy,admit_strategy,strategy_context
root=Path(sys.argv[1])
def put(name,value):
 p=root/name;p.write_text(json.dumps(value),encoding='utf-8');return file_ref(p)
a=leaf();b=compose([a])
for cap in (a,b):cap.update(certification='certified',lifecycle='active')
snapshot=create_capability_snapshot('owner',[capability_ref(b)],[a,b])
training=put('training.json',{'source':'first'});heldout=put('heldout.json',{'source':'second'})
definition={'owner':'owner','target':'task','scope':'research','applicability':'When intent needs clarification.',
 'decision_policy':'先检查上下文，再判断是否需要询问。','capability_refs':[snapshot['roots'][0]],'evidence':[training],'parent':None}
parent=create_strategy(definition,snapshot);definition['parent']=put('parent.json',parent)
definition['decision_policy']+=' Apply an existing certified operation when intent is clear.'
strategy=create_strategy(definition,snapshot);reference=put('candidate.json',strategy)
feedback=CapabilityFeedback(root/'feedback','owner')
verdict={'passed':True,'checks':[{'id':'diagnostic-host','status':'passed'}],
 'training_sources':[training],'heldout_sources':[heldout],'evidence':[heldout]}
selection=admit_strategy(reference,snapshot,target='task',scope='research',evaluate=lambda c:verdict,directory=root/'admit',feedback=feedback)
context=strategy_context(selection,snapshot,target='task',scope='research',feedback=feedback)
print(json.dumps({'snapshot':snapshot,'strategy':strategy,'selection':selection,'context':context,
 'feedbackDirectory':str(root/'feedback'),'feedbackFile':str(feedback.path),'leaf':capability_ref(a)}))`, directory], {encoding: 'utf8'});
  assert.equal(run.status, 0, run.stderr);
  return JSON.parse(run.stdout);
}
function options(data) {
  return {owner: 'owner', target: 'task', scope: 'research', feedbackDirectory: data.feedbackDirectory};
}
function put(path, value) {
  const bytes = Buffer.from(JSON.stringify(value));
  writeFileSync(path, bytes);
  return {path, sha256: createHash('sha256').update(bytes).digest('hex')};
}
function identity(value) {
  const {format, id, revision_sha256, ...definition} = value;
  const revision = capabilityDigest(definition);
  return {...definition, format, id: 'strategy_' + revision.slice(0, 24), revision_sha256: revision};
}

test('Python independently admitted Unicode strategy has identical TypeScript context', t => {
  const data = fixture(t);
  assert.deepEqual(validateStrategy(data.strategy, data.snapshot, options(data)), data.strategy);
  assert.deepEqual(strategyContext(data.selection, data.snapshot, options(data)), data.context);
});

test('identity, owner, target and scope are rechecked at inheritance', t => {
  const data = fixture(t);
  for (const change of [{owner: 'other'}, {target: 'construction'}, {scope: 'other'}]) {
    assert.throws(() => strategyContext(data.selection, data.snapshot, {...options(data), ...change}));
  }
  const candidate = structuredClone(data.strategy);
  candidate.decision_policy = 'changed';
  assert.throws(() => validateStrategy(candidate, data.snapshot), /identity_changed/);
  candidate.certification = 'certified';
  assert.throws(() => validateStrategy(candidate, data.snapshot), /shape_invalid/);
});

test('current transitive certification and feedback withdrawal both block use', t => {
  const data = fixture(t);
  const caps = structuredClone(data.snapshot.capabilities);
  caps.find(cap => cap.id === data.leaf.id).certification = 'rejected';
  const current = createCapabilitySnapshot('owner', data.snapshot.roots, caps);
  assert.throws(() => strategyContext(data.selection, current, options(data)), /dependency_unavailable/);
  const state = JSON.parse(readFileSync(data.feedbackFile, 'utf8'));
  state.blocked[data.leaf.id] = {capability: data.leaf, reason: 'revoked', evidence: data.selection.evaluation};
  writeFileSync(data.feedbackFile, JSON.stringify(state));
  assert.throws(() => strategyContext(data.selection, data.snapshot, options(data)), /dependency_withdrawn/);
});

test('original strategy withdrawal is checked on every context read', t => {
  const data = fixture(t);
  strategyContext(data.selection, data.snapshot, options(data));
  const state = JSON.parse(readFileSync(data.feedbackFile, 'utf8'));
  const subject = data.context.strategy;
  state.blocked[subject.id] = {capability: subject, reason: 'counterexample', evidence: data.selection.evaluation};
  writeFileSync(data.feedbackFile, JSON.stringify(state));
  assert.throws(() => strategyContext(data.selection, data.snapshot, options(data)), /strategy_withdrawn/);
});

test('selection without host feedback admission fails and every feedback evidence is verified', t => {
  const data = fixture(t);
  const state = JSON.parse(readFileSync(data.feedbackFile, 'utf8'));
  writeFileSync(data.feedbackFile, JSON.stringify({...state, facts: {}}));
  assert.throws(() => strategyContext(data.selection, data.snapshot, options(data)), /host_admission_required/);
  state.facts.unrelated = {evidence: [{path: data.selection.strategy.path, sha256: '0'.repeat(64)}]};
  writeFileSync(data.feedbackFile, JSON.stringify(state));
  assert.throws(() => strategyContext(data.selection, data.snapshot, options(data)), /evidence_changed/);
});

test('changed heldout input and parent bytes are rejected', t => {
  const data = fixture(t);
  const receipt = JSON.parse(readFileSync(data.selection.evaluation.path, 'utf8'));
  const heldout = receipt.verdict.heldout_sources[0];
  const original = readFileSync(heldout.path);
  writeFileSync(heldout.path, '{}');
  assert.throws(() => strategyContext(data.selection, data.snapshot, options(data)), /evidence_changed/);
  writeFileSync(heldout.path, original);
  writeFileSync(data.strategy.parent.path, '{}');
  assert.throws(() => validateStrategy(data.strategy, data.snapshot), /evidence_changed/);
});

test('same-content training and heldout paths cannot become independent evaluation', t => {
  const data = fixture(t);
  const receipt = JSON.parse(readFileSync(data.selection.evaluation.path, 'utf8'));
  const training = receipt.verdict.training_sources[0];
  const alias = join(data.feedbackDirectory, 'renamed-heldout.json');
  writeFileSync(alias, readFileSync(training.path));
  receipt.verdict.heldout_sources = [{path: alias, sha256: training.sha256}];
  const evaluation = put(data.selection.evaluation.path, receipt);
  assert.throws(() => strategyContext({...data.selection, evaluation}, data.snapshot, options(data)), /heldout_overlap/);
});

test('UTF-8 limits count bytes and certified inventory may grow without changing referenced dependencies', t => {
  const data = fixture(t);
  const exact = identity({...data.strategy, decision_policy: '😀'.repeat(1024)});
  assert.equal(validateStrategy(exact, data.snapshot).decision_policy, exact.decision_policy);
  for (const whitespace of ['\u0085', '\u001c']) {
    assert.throws(() => validateStrategy(identity({...data.strategy, decision_policy: whitespace}), data.snapshot), /policy_invalid/);
  }
  const over = identity({...data.strategy, decision_policy: '中'.repeat(1366)});
  assert.throws(() => validateStrategy(over, data.snapshot), /policy_invalid/);
  const expanded = createCapabilitySnapshot('owner', [...data.snapshot.roots, data.leaf], data.snapshot.capabilities);
  assert.deepEqual(strategyContext(data.selection, expanded, options(data)), data.context);
});
