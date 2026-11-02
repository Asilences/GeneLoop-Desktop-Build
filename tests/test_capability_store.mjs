/** Store mechanics with actual fixed subprocess execution and independent checking.
 * Synthetic tasks/authority only: these are not model or scientific gain results.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync,writeFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createCapability,capabilityRef,capabilityDigest,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {createCapabilityRuntime} from '../src/adapters/capability_runtime.ts';
import {createCapabilityStore} from '../src/adapters/capability_store.ts';
import {diagnosticHost} from '../examples/rsi-protocol-v1/host.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const python=process.env.SSS_PYTHON??'python3',owner='local-experiment-owner';
const countPath=fileURLToPath(new URL('../examples/rsi-protocol-v1/group_count.py',import.meta.url));
const checkerPath=fileURLToPath(new URL('./fixtures/capability_count_validator.py',import.meta.url));
const contract={input_schema:{type:'object',properties:{rows:{type:'array',items:{type:'object',properties:{group:{type:'string'}},required:['group'],additionalProperties:false}}},required:['rows'],additionalProperties:false},output_schema:{type:'object'},effects:['read']};
const legacy={backend:'artifact_motif',object_id:'group-count',library_sha256:hash('diagnostic-library'),library_digest:hash('diagnostic-manifest'),object_sha256:hash(readFileSync(countPath)),certificate_sha256:hash('diagnostic-certificate')};
function candidate(stepId='count'){
 const leaf=createCapability({owner,contract,implementation:{kind:'legacy',legacy_ref:legacy},dependencies:[]},{certification:'certified',lifecycle:'active'});
 const root=createCapability({owner,contract,implementation:{kind:'composition',steps:[{id:stepId,capability:capabilityRef(leaf),arguments:{kind:'input',path:[]}}],output:{kind:'step',step_id:stepId,path:[]}},dependencies:[capabilityRef(leaf)]});
 return {root:capabilityRef(root),candidateSnapshot:createCapabilitySnapshot(owner,[capabilityRef(root)],[root,leaf])};
}
const input={rows:[{group:'A'},{group:'B'},{group:'A'}]};
async function execute(snapshot,root,args,validation=true){
 const {host,request}=diagnosticHost(validation?'B':'C');
 const registry=new Map(snapshot.capabilities.map(c=>[c.id,c]));
 const backend={inspect:()=>structuredClone(legacy),request(call,argumentsValue){
  const result=structuredClone(request);Object.assign(result.payload,{id:call.callId,arguments_sha256:hash(JSON.stringify(argumentsValue)),obligation_ref:'obligation-'+call.callId});
  host.obligations.set(result.payload.obligation_ref,{taskId:host.taskId,operation:result.payload.operation,argumentsSha256:result.payload.arguments_sha256,stateVersion:host.stateVersion,dependencies:result.payload.dependencies});return result;
 },async execute(call,operation,argumentsValue){
  const result=spawnSync(python,[countPath],{input:JSON.stringify(argumentsValue),encoding:'utf8'});assert.equal(result.status,0,result.stderr);
  return {value:JSON.parse(result.stdout),receipt:{call_id:call.callId,operation,status:'succeeded'}};
 }};
 const grant={id:'independent-validation-grant',taskId:host.taskId,owner,snapshotDigest:snapshot.digest,root,revoked:false};
 const runtime=createCapabilityRuntime({taskId:host.taskId,owner,snapshot,readHost:()=>host,readCapability:ref=>registry.get(ref.id),backends:{artifact_motif:backend},...(validation?{readValidationGrant:()=>grant}:{})});
 const result=await runtime.execute(root,args);
 return {format:'diagnostic_capability_trace_v1',task_id:host.taskId,owner,mode:validation?'validate':'execute',grant_id:grant.id,
  snapshot_sha256:snapshot.digest,root,arguments_sha256:capabilityDigest(args),...result};
}
function setup(t,overrides={}){
 const directory=mkdtempSync(join(tmpdir(),'capability-store-'));t.after(()=>rmSync(directory,{recursive:true,force:true}));
 const calls={execution:0,validation:0};
 const options={directory,owner,runValidation:async({candidateSnapshot,root,input})=>{
  calls.execution++;const execution=await execute(candidateSnapshot,root,input);return {execution,artifacts:[{name:'counts.json',bytes:Buffer.from(JSON.stringify(execution.result))}]};
 },validator:{id:'count-validator-v1',sha256:hash(readFileSync(checkerPath)),check:async context=>{
  calls.validation++;const result=spawnSync(python,[checkerPath],{input:JSON.stringify({input:context.input,artifact:Buffer.from(context.artifacts[0].bytes).toString('utf8')}),encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout);
 }},...overrides};
 return {directory,calls,options,store:createCapabilityStore(options)};
}

test('actual validation, independent check, immutable publish and next-task execution',async t=>{
 const s=setup(t),request={...candidate(),input,expectedLatest:null};assert.equal(s.store.loadLatest(),null);
 const published=await s.store.publish(request);
 assert.deepEqual(s.calls,{execution:1,validation:1});assert.equal(published.status,'published');
 assert.equal(published.publication.format,'capability_publication_v1');assert.equal(published.publication.scope,'local_experiment');
 assert.equal(published.publication.candidate_snapshot_sha256,request.candidateSnapshot.digest);
 const cap=published.snapshot.capabilities.find(c=>c.id===request.root.id);
 assert.equal(cap.certification,'certified');assert.equal(cap.lifecycle,'active');assert.equal(cap.migration,'promoted');
 assert.equal(request.candidateSnapshot.capabilities.find(c=>c.id===request.root.id).certification,'candidate');
 const reopened=createCapabilityStore(s.options),next=reopened.loadLatest();assert.equal(next.publication_sha256,published.publication_sha256);
 const ordinary=await execute(next.snapshot,request.root,input,false);assert.equal(ordinary.mode,'execute');assert.equal(ordinary.status,'succeeded');assert.deepEqual(ordinary.result,{counts:{A:2,B:1}});
 assert.notEqual(ordinary.task_id,published.publication.task_id);
 const nextPublish=await s.store.publish({...candidate('second'),input,expectedLatest:published.publication_sha256});
 assert.equal(nextPublish.publication.previous_publication_sha256,published.publication_sha256);
 assert.equal(s.store.loadVersion(published.publication_sha256).snapshot.digest,published.snapshot.digest);
 await assert.rejects(s.store.publish({...candidate('stale'),input,expectedLatest:published.publication_sha256}),/cas_conflict/);
 assert.deepEqual(s.calls,{execution:2,validation:2});
});

test('failed independent check and ordinary execution never issue a certificate',async t=>{
 const s=setup(t);s.options.validator.check=async()=>({passed:false,checks:[{id:'quality',status:'failed',observation:'Rejected.'}]});
 const failed=createCapabilityStore(s.options);await assert.rejects(failed.publish({...candidate(),input,expectedLatest:null}),/validation_failed/);assert.equal(failed.loadLatest(),null);
 const ordinary=createCapabilityStore({...s.options,runValidation:async({candidateSnapshot,root,input})=>({execution:await execute(candidateSnapshot,root,input,false),artifacts:[{name:'result',bytes:Buffer.from('bad')}]})});
 await assert.rejects(ordinary.publish({...candidate(),input,expectedLatest:null}),/validation_context_changed/);assert.equal(ordinary.loadLatest(),null);
});

test('wrong trace bindings, unknown checks, and owner mismatch fail closed',async t=>{
 const s=setup(t),original=s.options.runValidation;
 const changed=createCapabilityStore({...s.options,runValidation:async context=>{const r=await original(context);r.execution.arguments_sha256='0'.repeat(64);return r;}});
 await assert.rejects(changed.publish({...candidate(),input,expectedLatest:null}),/validation_binding_changed/);assert.equal(s.calls.validation,0);
 const unknown=createCapabilityStore({...s.options,validator:{...s.options.validator,check:async()=>({passed:true,checks:[{id:'check',status:'unknown',observation:'Unknown.'}]})}});
 await assert.rejects(unknown.publish({...candidate(),input,expectedLatest:null}),/validation_failed/);
 const other=createCapabilityStore({...s.options,owner:'other-owner'});assert.equal(other.loadLatest(),null);
 await assert.rejects(other.publish({...candidate(),input,expectedLatest:null}),/foreign_owner/);
});

test('stored evidence tampering is detected and another owner cannot load the version',async t=>{
 const s=setup(t),published=await s.store.publish({...candidate(),input,expectedLatest:null});
 const other=createCapabilityStore({...s.options,owner:'other-owner'});assert.throws(()=>other.loadVersion(published.publication_sha256));
 const artifact=join(s.directory,hash(owner),'versions',published.publication_sha256,'artifacts','0000.bin');writeFileSync(artifact,'changed');
 assert.throws(()=>s.store.loadLatest(),/evidence_changed/);
});

test('concurrent validated publications use compare-and-swap without deleting either prior version',async t=>{
 const s=setup(t),pending=[];const original=s.options.runValidation;
 const concurrent=createCapabilityStore({...s.options,runValidation:async context=>{const result=await original(context);await new Promise(resolve=>pending.push(resolve));return result;}});
 const a=concurrent.publish({...candidate('one'),input,expectedLatest:null});const b=concurrent.publish({...candidate('two'),input,expectedLatest:null});
 while(pending.length<2)await new Promise(resolve=>setTimeout(resolve,1));pending.splice(0).forEach(resolve=>resolve());
 const results=await Promise.allSettled([a,b]);assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.match(results.find(r=>r.status==='rejected').reason.message,/cas_conflict/);
 const current=concurrent.loadLatest();assert.ok(current);assert.equal(existsSync(join(s.directory,hash(owner),'.publish.lock')),false);
});

test('validator scope and limitations are retained with multiple artifact bytes',async t=>{
 const s=setup(t),originalRun=s.options.runValidation,originalCheck=s.options.validator.check;
 const store=createCapabilityStore({...s.options,runValidation:async ctx=>{
  const result=await originalRun(ctx);result.artifacts.push({name:'counts-copy.json',bytes:Buffer.from(result.artifacts[0].bytes)});return result;
 },validator:{...s.options.validator,check:async ctx=>{
  const verdict=await originalCheck(ctx);assert.equal(ctx.artifacts.length,2);assert.deepEqual(ctx.artifacts[0].bytes,ctx.artifacts[1].bytes);
  return {...verdict,scope:'exact synthetic count only',limitations:['No real model or media quality evidence']};
 }}});
 const result=await store.publish({...candidate(),input,expectedLatest:null});
 assert.equal(result.publication.files.artifacts.length,2);
 const stored=JSON.parse(readFileSync(join(s.directory,hash(owner),'versions',result.publication_sha256,'validation.json'),'utf8'));
 assert.equal(stored.scope,'exact synthetic count only');assert.deepEqual(stored.limitations,['No real model or media quality evidence']);
 assert.equal(store.loadLatest().publication_sha256,result.publication_sha256);
});

test('a proposal cannot replace validation with self-certified metadata',async t=>{
 const s=setup(t),value=candidate();
 const changed=value.candidateSnapshot.capabilities.map(cap=>cap.id===value.root.id?{...cap,certification:'certified',lifecycle:'active'}:cap);
 value.candidateSnapshot=createCapabilitySnapshot(owner,[value.root],changed);
 await assert.rejects(s.store.publish({...value,input,expectedLatest:null,certificate:{passed:true}}),/candidate_required/);
 assert.deepEqual(s.calls,{execution:0,validation:0});assert.equal(s.store.loadLatest(),null);
});
