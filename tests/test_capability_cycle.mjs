/** Cross-scene lifecycle conformance. Real fixed subprocesses, synthetic authority. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createCapability,capabilityRef,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {completeCapabilityCycle,publicationVerdict} from '../src/adapters/capability_cycle.ts';
import {createCapabilityStore} from '../src/adapters/capability_store.ts';
import {seed,contract,execute,checkResult,validator} from '../examples/capability-scenes/counts/runtime.mjs';

function fixture(t){
 const base=mkdtempSync(join(tmpdir(),'scene-cycle-'));t.after(()=>rmSync(base,{recursive:true,force:true}));
 const owner='count-scene',snapshot=seed(owner),leaf=snapshot.roots[0];
 const cap=createCapability({owner,contract,implementation:{kind:'composition',
  steps:[{id:'count',capability:leaf,arguments:{kind:'input',path:[]}}],output:{kind:'step',step_id:'count',path:[]}},dependencies:[leaf]});
 const root=capabilityRef(cap),candidateSnapshot=createCapabilitySnapshot(owner,[root],[...snapshot.capabilities,cap]);
 const validation={id:'validation-count',workspace:join(base,'validation'),input:{rows:[{group:'A'},{group:'A'}]}};
 const followup={id:'followup-count',workspace:join(base,'followup'),input:{rows:[{group:'B'},{group:'A'},{group:'B'}]}};
 mkdirSync(validation.workspace);mkdirSync(followup.workspace);
 const options={owner,directory:join(base,'store'),candidateSnapshot,root,expectedLatest:null,validation,followup,validator,
  run:async(snapshot,input,mode,label)=>execute(snapshot,root,input,{mode,taskId:label==='validation'?validation.id:followup.id}),
  check:async(run,label)=>checkResult(label==='validation'?validation.input:followup.input,run)};
 return options;
}

test('extra QA binding survives scene evidence but strict Store receives a valid verdict',async t=>{
 const options=fixture(t);let committed;
 options.onPublished=value=>committed=value;
 const result=await completeCapabilityCycle(options);
 assert.equal(result.status,'completed');assert.equal(result.followup_passed,true);
 assert.equal(committed.root.id,options.root.id);
 const store=createCapabilityStore({directory:options.directory,owner:options.owner,
  runValidation:async()=>{throw Error('read_only');},validator:{...validator,check:async()=>{throw Error('read_only');}}});
 assert.equal(store.loadLatest().publication_sha256,result.publication_sha256);
 assert.ok(store.constructionLibrary(seed(options.owner)).snapshot.roots.some(r=>r.id===options.root.id));
});

test('a failing independent followup stays committed and never auto-replays',async t=>{
 const options=fixture(t),original=options.check;let committed=false,calls=0;
 options.onPublished=()=>committed=true;
 options.check=async(run,label)=>{calls++;return label==='validation'?original(run,label):{passed:false,checks:[{id:'bad',status:'failed',observation:'diagnostic rejection'}]};};
 await assert.rejects(completeCapabilityCycle(options),/followup_validation_failed/);
 assert.equal(committed,true);assert.equal(calls,2);
});

test('independent task and input bindings are enforced by the common lifecycle',async t=>{
 const options=fixture(t);options.followup.input=options.validation.input;
 await assert.rejects(completeCapabilityCycle(options),/followup_input_must_differ/);
 options.followup.input={rows:[]};const run=options.run;
 options.run=async(...args)=>{const value=await run(...args);value.execution.task_id='another-task';return value;};
 await assert.rejects(completeCapabilityCycle(options),/execution_binding_changed/);
});

test('unknown or malformed QA transport fields are not silently accepted',()=>{
 const verdict={passed:true,checks:[{id:'x',status:'passed',observation:'diagnostic'}]};
 assert.deepEqual(publicationVerdict({...verdict,evidence_binding:{trace_sha256:'a'.repeat(64)}}),verdict);
 assert.throws(()=>publicationVerdict({...verdict,evidence_binding:{trace_sha256:'bad'}}),/binding_invalid/);
 assert.throws(()=>publicationVerdict({...verdict,model_certificate:true}),/shape_invalid/);
});

test('same file arguments accept different pinned bytes and bind native versions',async t=>{
 const options=fixture(t),run=options.run;
 options.followup.input=structuredClone(options.validation.input);
 options.validation.input_versions=[{path:'/work/inputs/references.bib',sha256:'a'.repeat(64)}];
 options.followup.input_versions=[{path:'/work/inputs/references.bib',sha256:'b'.repeat(64)}];
 options.run=async(...args)=>{const value=await run(...args);value.execution.input_versions=structuredClone(options[args[3]].input_versions);return value;};
 assert.equal((await completeCapabilityCycle(options)).followup_passed,true);
});

test('renaming identical bytes, missing versions and changed execution versions are rejected',async t=>{
 const options=fixture(t),run=options.run;
 options.validation.input_versions=[{path:'/work/inputs/one.bib',sha256:'a'.repeat(64)}];
 await assert.rejects(completeCapabilityCycle(options),/input_versions_invalid/);
 options.followup.input_versions=[{path:'/work/inputs/two.bib',sha256:'a'.repeat(64)}];
 await assert.rejects(completeCapabilityCycle(options),/followup_input_must_differ/);
 options.followup.input_versions=[{path:'/work/inputs/two.bib',sha256:'b'.repeat(64)}];
 options.run=async(...args)=>{const value=await run(...args);value.execution.input_versions=[{path:'/work/inputs/wrong.bib',sha256:'c'.repeat(64)}];return value;};
 await assert.rejects(completeCapabilityCycle(options),/execution_input_versions_changed/);
});
