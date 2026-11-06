/** Original Store and native Script Runtime bridge for benchmark compositions. */
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {capabilityDigest, validateCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {createCapabilityStore} from '../src/adapters/capability_store.ts';
import {runScriptCapability} from '../src/adapters/script_capability_runtime.ts';

const sha = value => createHash('sha256').update(value).digest('hex');
const read = reference => {
  const bytes = readFileSync(reference.path);
  if (sha(bytes) !== reference.sha256) throw Error('benchmark_store_evidence_changed');
  return JSON.parse(bytes.toString('utf8'));
};
const save = (path, value) => writeFileSync(path, JSON.stringify(value), {flag: 'wx', mode: 0o600});
let input = '';
for await (const chunk of process.stdin) input += chunk;
const plan = JSON.parse(input);
try {
  const owner = plan.owner;
  const seed = validateCapabilitySnapshot(plan.seed, owner);
  const code = sha(readFileSync(fileURLToPath(import.meta.url)));
  let caseValue;
  let candidate;
  if (plan.action === 'publish') {
    candidate = read(plan.candidate);
    caseValue = read(plan.source_case);
    read(caseValue.source_trace);
    for (const reference of caseValue.source_executions) read(reference);
    mkdirSync(plan.output, {recursive: true, mode: 0o700});
  } else if (plan.action !== 'catalog') {
    throw Error('benchmark_store_action_invalid');
  }
  const validator = {id: 'benchmark-heldout-source-equivalence-v1',
    sha256: capabilityDigest({code, source_case: plan.source_case ?? null}),
    async check(context) {
      if (!caseValue) throw Error('benchmark_store_catalog_has_no_validator');
      read(plan.source_case);
      read(caseValue.source_trace);
      for (const reference of caseValue.source_executions) read(reference);
      const equal = capabilityDigest(context.execution.result) === capabilityDigest(caseValue.expected_result);
      return {passed: equal, scope: 'heldout_native_source_equivalence',
        limitations: ['Benchmark semantic quality and future consumption are evaluated separately.'],
        checks: [{id: 'witnessed_input_binding', status: 'passed', observation: 'Inputs reconstructed from original learner bindings.'},
          {id: 'heldout_source_equivalence', status: equal ? 'passed' : 'failed',
            observation: 'Fresh native execution compared with the frozen original heldout Runtime result.'}]};
    }};
  const store = createCapabilityStore({directory: plan.store_directory, owner, validator,
    async runValidation(context) {
      if (!caseValue) throw Error('benchmark_store_catalog_has_no_execution');
      const taskId = caseValue.source_task_id + '-publication-' + context.root.id.slice(-16);
      const workspace = join(plan.output, 'work');
      mkdirSync(join(workspace, 'inputs'), {recursive: true, mode: 0o700});
      const registry = join(plan.output, 'snapshot.json');
      save(registry, context.candidateSnapshot);
      const manifest = {format: 'script_capability_task_v1', owner, task_id: taskId,
        workspace, registry_path: registry, libraries: plan.libraries, inputs: [],
        grant: {id: 'benchmark-publication-' + context.root.id.slice(-16), task_id: taskId,
          snapshot_sha256: context.candidateSnapshot.digest, root: context.root,
          arguments_sha256: capabilityDigest(context.input), mode: 'validate', effects: ['read'], revoked: false}};
      const manifestPath = join(plan.output, 'manifest.json');
      save(manifestPath, manifest);
      save(join(plan.output, 'input.json'), context.input);
      const execution = await runScriptCapability(manifestPath, context.candidateSnapshot, context.input);
      save(join(plan.output, 'execution.json'), execution);
      const bytes = Buffer.from(JSON.stringify({source_case: plan.source_case,
        source_executions: caseValue.source_executions, result: execution.result}));
      return {execution, artifacts: [{name: 'source-equivalence.json', bytes}]};
    }});
  if (plan.action === 'publish') {
    const published = await store.publish({candidateSnapshot: candidate.snapshot,
      root: candidate.snapshot.roots[0], input: caseValue.input, expectedLatest: plan.expected_latest});
    process.stdout.write(JSON.stringify({...published, library: store.constructionLibrary(seed)}));
  } else {
    const latest = store.loadLatest();
    const catalog = latest || seed.roots.length ? store.constructionLibrary(seed) : {
      snapshot: seed, head: null, catalog: []};
    process.stdout.write(JSON.stringify({...catalog, status: 'loaded'}));
  }
} catch (error) {
  process.stdout.write(JSON.stringify({status: 'failed', error: error.message}));
  process.exitCode = 1;
}
