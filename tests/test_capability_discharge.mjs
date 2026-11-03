/** T1/T2 wiring diagnostics: real Capability Runtime + existing Python tool.
 * Authority and predicates are synthetic independent host fixtures, not model
 * output. These tests claim no autonomous learning or efficiency improvement.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createCapability,capabilityRef,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {createCapabilityDischarge,dischargeVerificationPayload} from '../src/adapters/capability_discharge.ts';
import {bytesSha256,validateRsiRecord} from '../src/adapters/rsi_protocol.ts';
import {diagnosticHost,fixtureRecord} from '../examples/rsi-protocol-v1/host.mjs';

const clone=structuredClone,sha=bytesSha256;
function setup(){
 const {host,request,args}=diagnosticHost();
 const owner='rae-discharge-diagnostic',program=fileURLToPath(new URL('../examples/rsi-protocol-v1/group_count.py',import.meta.url));
 const native={backend:'artifact_motif',library_sha256:sha('diagnostic-registry'),library_digest:sha('diagnostic-library'),
  object_id:'group-count',object_sha256:sha(readFileSync(program)),certificate_sha256:sha('diagnostic-independent-certificate')};
 const cap=createCapability({owner,contract:{input_schema:{type:'object'},output_schema:{type:'object'},effects:['read']},
  implementation:{kind:'legacy',legacy_ref:native},dependencies:[]},
  {lifecycle:'active',certification:'certified',migration:'testing'});
 const snapshot=createCapabilitySnapshot(owner,[capabilityRef(cap)],[cap]);
 const registry=new Map([[cap.id,cap]]),evidence=new Map(host.currentEvidence),audits=new Map(),calls=[];
 const predicate={id:'counts-exact',sha256:sha('host-counts-predicate-v1'),version:'1'};
 const verifier={id:'count-verifier',sha256:sha('independent-count-verifier-v1'),version:'1'};
 const evidenceRef=record=>({id:record.payload.id,sha256:record.payload.sha256,version:record.payload.version});
 function putEvidence(id,role,taskId,value,observation=id){
  const record=fixtureRecord('evidence');Object.assign(record.payload,{id,role,task_id:taskId,sha256:sha(JSON.stringify(value)),observation_id:observation});
  validateRsiRecord(record);evidence.set(id,record);return evidenceRef(record);
 }
 const claim={id:'host-reviewed-count-claim',owner,scope:'count-groups',capability:capabilityRef(cap),predicate,verifier,
  training_task_ids:['train-1'],validation_task_ids:['heldout-1'],
  validation_evidence:[putEvidence('heldout-count-check','validation','heldout-1',{passed:true})]};
 const obligation={id:'count-current-table',task_id:host.taskId,owner,state_version:host.stateVersion,scope:'count-groups',
  predicate,description:'Count the groups in the current table',dependencies:clone(request.payload.dependencies),depends_on:[],
  bindings:[{capability:capabilityRef(cap),arguments:args}]};
 const state={claim,claims:[claim],obligations:[obligation],verifier,evidence,host,cap,registry,args,audits,calls,putEvidence,verifyCalls:0};
 state.seal=proof=>({...proof,evidence:putEvidence('verification-'+proof.receipt_binding.call_id,'validation',host.taskId,
  dischargeVerificationPayload(proof),proof.receipt_binding.call_id)});
 const backend={
  inspect(reference){return {...native,object_sha256:sha(readFileSync(program))};},
  request(call,bound){
   const next=clone(request);Object.assign(next.payload,{id:call.callId,obligation_ref:'runtime-'+call.callId,
    arguments_sha256:sha(JSON.stringify(bound))});
   host.obligations.set(next.payload.obligation_ref,{taskId:host.taskId,operation:next.payload.operation,
    argumentsSha256:next.payload.arguments_sha256,stateVersion:host.stateVersion,dependencies:clone(next.payload.dependencies)});
   return next;
  },
  async execute(call,operation,bound){
   const result=spawnSync(process.env.SSS_PYTHON??'python3',[program],{input:JSON.stringify(bound),encoding:'utf8'});
   assert.equal(result.status,0,result.stderr);calls.push({call,operation,bound});
   return {value:JSON.parse(result.stdout),receipt:{call_id:call.callId,task_id:host.taskId,operation,status:'succeeded'}};
  },
 };
 const options={enabled:true,runtime:{taskId:host.taskId,owner,snapshot,readHost:()=>host,
  readCapability:ref=>registry.get(ref.id),backends:{artifact_motif:backend}},
  readObligations:()=>state.obligations,readApprovedClaims:()=>state.claims,
  readEvidence:ref=>evidence.get(ref.id),readVerifier:()=>state.verifier,
  saveAudit(value){const hash=sha(JSON.stringify(value)),ref={id:'audit-'+hash.slice(0,24),sha256:hash,version:'1'};audits.set(ref.id,clone(value));return ref;},
  async verify({outcome}){
   state.verifyCalls++;
   const accepted=JSON.stringify(outcome.result)===JSON.stringify({counts:{poster:1,workshop:2}});
   const root=outcome.receipts[0];
   return state.seal({accepted,receipt_binding:{call_id:root.call_id,arguments_sha256:root.arguments_sha256,result_sha256:root.result_sha256},
    artifact_refs:[putEvidence('counts-artifact-'+root.call_id,'current',host.taskId,outcome.result,root.call_id)],introduced_checks:[]});
  },
 };
 state.options=options;state.backend=backend;state.obligation=obligation;return state;
}

test('T1/T2 actual Runtime call discharges a bounded predicate and returns only evidence to the model',async()=>{
 const s=setup();const result=await createCapabilityDischarge(s.options).run();
 assert.equal(s.calls.length,1);assert.equal(s.verifyCalls,1);assert.equal(result.summary.status,'completed');
 assert.equal(result.summary.solved.length,1);assert.deepEqual(result.summary.remaining_frontier,[]);
 const solved=result.summary.solved[0],audit=s.audits.get(solved.receipt_ref.audit.id);
 assert.equal(audit.outcome.status,'succeeded');assert.equal(audit.outcome.receipts[0].call_id,solved.receipt_ref.call_id);
 assert.deepEqual(audit.arguments,s.args);assert.deepEqual(audit.outcome.result,{counts:{poster:1,workshop:2}});
 assert.equal(audit.outcome.receipts[0].backend_receipt.call_id,solved.receipt_ref.call_id);
 assert.deepEqual(audit.outcome.receipts[0].events.map(e=>e.payload.phase),['started','succeeded']);
 const handoff=JSON.stringify(result.summary);assert.equal(handoff.includes('implementation'),false);
 assert.equal(handoff.includes('counts'),true); // predicate/artifact identity only
 assert.equal(handoff.includes('"workshop":2'),false);assert.equal(handoff.includes('child_call_ids'),false);
});

for(const enabled of [undefined,false])test('default/off preserves the full frontier without executing or verifying: '+enabled,async()=>{
 const s=setup();s.options.enabled=enabled;
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.status,'disabled');assert.equal(result.summary.remaining_frontier.length,1);
 assert.equal(s.calls.length,0);assert.equal(s.verifyCalls,0);assert.equal(s.audits.size,0);
});

for(const [name,change,reason] of [
 ['no host claim',s=>{s.claims=[];},'no_verified_cover'],
 ['predicate mismatch',s=>{s.claim.predicate={...s.claim.predicate,sha256:sha('another-predicate')};},'no_verified_cover'],
 ['scope mismatch',s=>{s.claim.scope='another-task-scope';},'no_verified_cover'],
 ['foreign claim',s=>{s.claim.owner='another-owner';},'no_verified_cover'],
 ['expired validation',s=>{s.evidence.get('heldout-count-check').payload.status='invalidated';},'discharge_evidence_invalidated'],
 ['validation overlaps training',s=>{s.claim.training_task_ids=['heldout-1'];},'discharge_claim_validation_invalid'],
 ['unwitnessed validation task',s=>{s.claim.validation_task_ids.push('heldout-2');},'discharge_claim_validation_unwitnessed'],
 ['verifier changed',s=>{s.verifier={...s.verifier,sha256:sha('new-verifier')};},'discharge_verifier_changed'],
 ['permission revoked',s=>{s.host.grant.revoked=true;},'discharge_permission_denied'],
 ['permission effect removed',s=>{s.host.grant.effects=[];},'discharge_permission_denied'],
 ['current evidence invalidated',s=>{s.evidence.get('current-table').payload.status='invalidated';},'discharge_evidence_invalidated'],
 ['uncertified capability',s=>{s.registry.get(s.cap.id).certification='candidate';},'discharge_capability_not_certified'],
 ['task changed',s=>{s.obligation.task_id='other-task';},'discharge_task_state_changed'],
])test(name+' stays unresolved and does not dispatch',async()=>{
 const s=setup();change(s);const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);assert.equal(s.calls.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,reason);
});

test('successful Runtime execution cannot override independent verifier rejection',async()=>{
 const s=setup(),original=s.options.verify;
 s.options.verify=async input=>s.seal({...await original(input),accepted:false});
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(s.calls.length,1);assert.equal(result.summary.solved.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,'discharge_verifier_rejected');
 assert.ok(result.audit[0].audit_ref);assert.equal(s.audits.size,1);
});

test('candidate-like verified=true does not create a host-approved claim',async()=>{
 const s=setup();s.claims=[];s.obligation.verified=true;
 s.obligation.bindings[0].verified=true;
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);assert.equal(s.calls.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,'no_verified_cover');
});

test('native operation permission remains enforced by the original Runtime',async()=>{
 const s=setup();s.host.grant.operations=[];
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);assert.equal(s.calls.length,0);
 assert.equal(result.audit[0].outcome.receipts[0].reason,'permission_denied');
});

test('a request for a changed input version cannot discharge the old obligation',async()=>{
 const s=setup(),discharge=createCapabilityDischarge(s.options);
 s.host.stateVersion='new-input-state';
 const result=await discharge.run();
 assert.equal(result.summary.solved.length,0);assert.equal(s.calls.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,'discharge_task_state_changed');
});

test('new composition/conflict checks remain explicit even after local acceptance',async()=>{
 const s=setup(),original=s.options.verify;
 s.options.verify=async input=>s.seal({...await original(input),introduced_checks:[{id:'join-scope',scope:'joined-report',description:'Check cross-source consistency'}]});
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,1);assert.equal(result.summary.remaining_frontier.length,1);
 assert.equal(result.summary.remaining_frontier[0].kind,'composition_check');
 assert.match(result.summary.remaining_frontier[0].description,/cross-source/);
});

test('an unresolved prerequisite retains the dependent and unrelated open work',async()=>{
 const s=setup();s.claims=[];
 s.obligations.push({...clone(s.obligation),id:'compose-report',depends_on:[s.obligation.id],description:'Interpret this table',bindings:[]});
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.remaining_frontier.length,2);assert.equal(s.calls.length,0);
 assert.equal(result.summary.remaining_frontier[1].reason,'dependency_unresolved');
});

for(const [name,change,reason] of [
 ['obligation arguments',s=>{s.obligation.bindings[0].arguments={rows:[]};},'discharge_obligation_changed'],
 ['current input evidence',s=>{s.evidence.get('current-table').payload.sha256=sha('new-input');},'discharge_evidence_invalidated'],
 ['claim registry',s=>{s.claims=[];},'discharge_claim_changed'],
 ['component version',s=>{s.host.versions.motif.sha256=sha('new-version');},'discharge_component_version_changed'],
 ['certificate',s=>{s.registry.get(s.cap.id).certification='rejected';},'discharge_capability_not_certified'],
])test('change during independent verification cannot yield solved: '+name,async()=>{
 const s=setup(),original=s.options.verify;
 s.options.verify=async input=>{const result=await original(input);change(s);return result;};
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(s.calls.length,1);assert.equal(result.summary.solved.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,reason);
});

test('cancel before dispatch and interrupt after native execution preserve unresolved work',async()=>{
 const s=setup(),cancel=new AbortController();cancel.abort();
 const before=await createCapabilityDischarge(s.options).run({signal:cancel.signal});
 assert.equal(before.summary.status,'cancelled');assert.equal(s.calls.length,0);
 const t=setup(),during=new AbortController(),original=t.backend.execute;
 t.backend.execute=async(...args)=>{const result=await original(...args);during.abort();return result;};
 const after=await createCapabilityDischarge(t.options).run({signal:during.signal});
 assert.equal(after.summary.status,'interrupted');assert.equal(after.summary.solved.length,0);
 assert.equal(after.audit[0].outcome.receipts[0].status,'interrupted');assert.equal(t.verifyCalls,0);
});

test('native timeout/failure falls back without accepting a missing receipt',async()=>{
 const s=setup();s.backend.execute=async()=>{throw Error('native-timeout');};
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);assert.equal(s.verifyCalls,0);
 assert.equal(result.audit[0].outcome.receipts[0].status,'failed');
 assert.equal(result.summary.remaining_frontier[0].reason,'discharge_execution_failed');
});

test('fake or failed audit persistence cannot produce a solved handoff',async()=>{
 const s=setup();s.options.saveAudit=()=>({id:'fake',sha256:'0'.repeat(64),version:'1'});
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);assert.equal(result.summary.remaining_frontier[0].reason,'discharge_audit_digest_mismatch');
 assert.equal(result.audit[0].audit_error,'discharge_audit_persistence_failed');
});

test('a later obligation invalidating prior evidence retracts the earlier solved claim',async()=>{
 const s=setup(),original=s.options.verify;
 s.obligations.push({...clone(s.obligation),id:'second-count',depends_on:[s.obligation.id]});
 s.options.verify=async input=>{
  const result=await original(input);
  if(input.obligation.id==='second-count')s.host.grant.revoked=true;
  return result;
 };
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(s.calls.length,2);assert.equal(result.summary.solved.length,0);
 assert.equal(result.summary.remaining_frontier.length,2);
 assert.ok(result.summary.remaining_frontier.every(item=>item.reason==='discharge_permission_denied'));
});

test('duplicate declared obligation IDs reject before any execution',async()=>{
 const s=setup();s.obligations.push(clone(s.obligation));
 await assert.rejects(createCapabilityDischarge(s.options).run(),/discharge_duplicate_obligation/);
 assert.equal(s.calls.length,0);
});

test('verification from another actual call cannot discharge this invocation',async()=>{
 const s=setup(),original=s.options.verify;
 s.options.verify=async input=>{const proof=await original(input);proof.receipt_binding.call_id='another-call';return s.seal(proof);};
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,'discharge_verification_receipt_mismatch');
});

test('artifact evidence from a different call remains unresolved even with a correct verifier receipt',async()=>{
 const s=setup(),original=s.options.verify;
 s.options.verify=async input=>{const proof=await original(input);
  s.evidence.get(proof.artifact_refs[0].id).payload.observation_id='unrelated-call';return proof;};
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,'discharge_evidence_invalidated');
});

test('verification evidence hash must cover the acceptance, receipt, artifacts and new checks',async()=>{
 const s=setup(),original=s.options.verify;
 s.options.verify=async input=>{const proof=await original(input);
  proof.introduced_checks.push({id:'new',scope:'new-scope',description:'A further check'});return proof;};
 const result=await createCapabilityDischarge(s.options).run();
 assert.equal(result.summary.solved.length,0);
 assert.equal(result.summary.remaining_frontier[0].reason,'discharge_verification_digest_mismatch');
});
