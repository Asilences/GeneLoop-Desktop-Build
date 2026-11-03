/** Failure diagnostics are data; certificates and execution guards stay intact. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {scriptWorkerFailure,readScriptWorkerFailure,SCRIPT_FAILURE_FRAME} from '../src/adapters/script_worker_failure.mjs';
import {scriptCodeLocks} from '../src/adapters/script_motif_runtime.ts';
import {buildScriptCapabilities,runScriptCapability} from '../src/adapters/script_capability_runtime.ts';
import {capabilityDigest,capabilityRef} from '../src/adapters/capability_contract.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {bytesSha256 as sha} from '../src/adapters/rsi_protocol.ts';

test('worker diagnostics preserve bounded type/location without private text or host paths',()=>{
 const message='script_sandbox_failed: Traceback (most recent call last):\n  File "/private/input/secrets.py", line 9, in run\nTypeError: private source body must not escape';
 const failure=scriptWorkerFailure(Error(message));
 assert.equal(failure.exception_type,'TypeError');assert.equal(failure.source_file,'secrets.py');assert.equal(failure.source_line,9);
 assert.equal(failure.category,'data_operation_error');assert.ok(!JSON.stringify(failure).includes('private'));
 assert.deepEqual(readScriptWorkerFailure(JSON.stringify(failure)),failure);
 assert.deepEqual(readScriptWorkerFailure('Node module warning\n'+SCRIPT_FAILURE_FRAME+JSON.stringify(failure)+'\n'),failure);
 assert.equal(readScriptWorkerFailure((SCRIPT_FAILURE_FRAME+JSON.stringify(failure)+'\n').repeat(2)),null);
 for(const alter of [v=>v.reason='success',v=>v.source_file='/outside/path',v=>v.source_line=-1,
  v=>v.category='authorized_retry',v=>v.unknown='injected']){
  const value=structuredClone(failure);alter(value);assert.equal(readScriptWorkerFailure(JSON.stringify(value)),null);
 }
 assert.equal(readScriptWorkerFailure('x'.repeat(9000)),null);
 assert.equal(scriptWorkerFailure(Error('script_worker_timeout TypeError: misleading')).category,'unknown');
});

test('actual worker failure emits a checked diagnostic rather than raw exception text',()=>{
 const run=spawnSync(process.execPath,['--experimental-strip-types','scripts/script-capability-worker.mjs'],
  {input:JSON.stringify({workspace:null}),encoding:'utf8'});
 assert.equal(run.status,1);assert.equal(run.stdout,'');
 const failure=readScriptWorkerFailure(run.stderr);assert.ok(failure);assert.equal(failure.category,'unknown');
 assert.equal(failure.source_file,null);assert.equal(failure.exception_type,null);
});

const sandbox=process.platform==='linux'&&existsSync('/usr/bin/bwrap')&&process.env.RUN_SCRIPT_CAPABILITY_SANDBOX==='1';
test('a native data operation failure keeps its receipt and writes scoped diagnostics',{skip:!sandbox},async t=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'script-worker-diagnostic-')));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const work=join(dir,'work');mkdirSync(join(work,'inputs'),{recursive:true});
 const identity={version:1,language:'python',template:"import json\nx=json.load(open('__MOTIF_INPUT_0__'))\nprint(json.dumps({'total':sum(row['amount'] for row in x['items'])}))",
  inputs:[{suffix:'.json',format:'json',shape:{object:{items:'array'}}}]};
 // A deterministic diagnostic library, never a real quality/learning claim.
 const program={...identity,id:'script_'+digest(identity).slice(0,24),description:'Diagnostic summation',certification:{passed:true,cases:2,
  source_equivalent:true,program_sha256:digest(identity),output_schema:{type:'object',properties:{total:{type:'number'}},required:['total'],additionalProperties:false},
  value_binding:{format:'script_json_value_binding_v1',input_schema:{type:'object',properties:{items:{type:'array'}},required:['items'],additionalProperties:false}}}};
 const body={kind:'sandboxed_script_motif_library',version:1,programs:[program],code_locks:Object.fromEntries(scriptCodeLocks.map(path=>[path,sha(readFileSync(path))]))};
 const library=join(dir,'library.json');writeFileSync(library,JSON.stringify({...body,digest:digest(body)}));
 const catalog=buildScriptCapabilities(library,'owner'),leaf=catalog.capabilities.find(c=>c.contract.input_schema.properties.value);
 const args={value:{items:[[{amount:1}]]}},registry=join(dir,'registry.json'),manifest=join(dir,'manifest.json');
 writeFileSync(registry,JSON.stringify(catalog.snapshot));
 writeFileSync(manifest,JSON.stringify({format:'script_capability_task_v1',task_id:'shape-diagnostic',owner:'owner',workspace:work,
  registry_path:registry,libraries:[{path:library,sha256:sha(readFileSync(library))}],inputs:[],
  grant:{id:'shape-grant',task_id:'shape-diagnostic',snapshot_sha256:catalog.snapshot.digest,root:capabilityRef(leaf),
   arguments_sha256:capabilityDigest(args),mode:'execute',effects:['read'],revoked:false}}));
 const trace=await runScriptCapability(manifest,catalog.snapshot,args),receipt=trace.receipts.find(r=>r.dispatched);
 assert.equal(trace.status,'failed');assert.equal(receipt.reason,'script_worker_failed');
 const failure=JSON.parse(readFileSync(join(work,'calls',receipt.call_id,'failure.json'),'utf8'));
 assert.equal(failure.call_id,receipt.call_id);assert.deepEqual(failure.capability,capabilityRef(leaf));
 assert.equal(failure.arguments_sha256,sha(JSON.stringify(args)));
 assert.equal(failure.diagnostic.exception_type,'TypeError');assert.equal(failure.diagnostic.category,'data_operation_error');
 assert.ok(failure.diagnostic.source_line>0);assert.equal(trace.result,null);
});
