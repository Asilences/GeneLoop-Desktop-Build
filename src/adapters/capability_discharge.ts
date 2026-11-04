/** Experimental, host-authorized discharge of declared, independently checkable
 * obligations. This is a handoff around the existing Capability Runtime, not a
 * second executor or a natural-language theorem prover. No production defaults.
 */
import {capabilityDigest, capabilityRef, validateCapability, type CapabilityRef} from './capability_contract.ts';
import {createCapabilityRuntime, type CapabilityRuntimeHost} from './capability_runtime.ts';
import {bytesSha256, validateRsiRecord, type RsiRecord} from './rsi_protocol.ts';

export type DischargeEvidence = {id:string;sha256:string;version:string};
export type DischargeObligation = {
 id:string; task_id:string; owner:string; state_version:string; scope:string;
 /** Host-owned predicate identity. Candidate text/verified=true grants nothing. */
 predicate:DischargeEvidence; description:string;
 dependencies:DischargeEvidence[]; depends_on:string[];
 /** Results of the host's existing binder, frozen for this task state. */
 bindings:{capability:CapabilityRef;arguments:unknown}[];
};
export type DischargeClaim = {
 id:string; capability:CapabilityRef; owner:string; scope:string;
 predicate:DischargeEvidence; verifier:DischargeEvidence;
 training_task_ids:string[]; validation_task_ids:string[];
 validation_evidence:DischargeEvidence[];
};
export type DischargeCheck = {id:string;scope:string;description:string};
export type DischargeVerification = {
 accepted:boolean; evidence:DischargeEvidence;
 receipt_binding:{call_id:string;arguments_sha256:string;result_sha256:string};
 artifact_refs:DischargeEvidence[]; introduced_checks:DischargeCheck[];
};
/** Exact JSON payload whose persisted bytes the verification evidence hashes. */
export function dischargeVerificationPayload(value:Pick<DischargeVerification,'accepted'|'receipt_binding'|'artifact_refs'|'introduced_checks'>){
 return {accepted:value.accepted,receipt_binding:value.receipt_binding,
  artifact_refs:value.artifact_refs,introduced_checks:value.introduced_checks};
}
type RuntimeOutcome = Awaited<ReturnType<ReturnType<typeof createCapabilityRuntime>['execute']>>;
export type CapabilityDischargeHost = {
 enabled?:boolean;
 runtime:CapabilityRuntimeHost;
 /** These readers belong to the authenticated host, not the generated program. */
 readObligations:()=>DischargeObligation[];
 readApprovedClaims:()=>DischargeClaim[];
 readEvidence:(ref:DischargeEvidence)=>RsiRecord|undefined;
 readVerifier:(ref:DischargeEvidence)=>DischargeEvidence|undefined;
 /** The host persists the full result and returns its immutable evidence ref. */
 saveAudit:(value:unknown)=>DischargeEvidence;
 verify:(input:{obligation:DischargeObligation;claim:DischargeClaim;
  arguments:unknown;outcome:RuntimeOutcome;signal?:AbortSignal})=>Promise<DischargeVerification>;
};

const same=(a:unknown,b:unknown)=>capabilityDigest(a)===capabilityDigest(b);
function check(value:unknown,reason:string):asserts value {if(!value)throw Error(reason);}
function text(value:unknown){return typeof value==='string'&&value.trim().length>0&&value.length<=4096;}
function ref(value:DischargeEvidence){
 check(value&&text(value.id)&&text(value.version)&&/^[a-f0-9]{64}$/.test(value.sha256),'discharge_evidence_ref_invalid');
 capabilityDigest(value);
}
function obligation(value:DischargeObligation){
 check(value&&text(value.id)&&text(value.task_id)&&text(value.owner)&&text(value.state_version)&&
  text(value.scope)&&text(value.description)&&Array.isArray(value.dependencies)&&value.dependencies.length>0&&
  Array.isArray(value.depends_on)&&new Set(value.depends_on).size===value.depends_on.length&&
  value.depends_on.every(text)&&!value.depends_on.includes(value.id)&&Array.isArray(value.bindings),'discharge_obligation_invalid');
 ref(value.predicate);for(const item of value.dependencies)ref(item);capabilityDigest(value);
}

/** Returned summary is the model handoff; audit carries full receipts/bindings.
 * The host must carry remaining_frontier (including introduced checks) into its
 * original semantic path. No unknown or undeclared task work is marked solved.
 */
export function createCapabilityDischarge(options:CapabilityDischargeHost){
 const enabled=options.enabled===true;
 // Snapshot the callbacks; mutating options must not swap authority mid-call.
 const {readObligations,readApprovedClaims,readEvidence,readVerifier,saveAudit,verify}=options;
 const runtimeOptions=options.runtime;
 const taskId=runtimeOptions.taskId,owner=runtimeOptions.owner,readHost=runtimeOptions.readHost;
 const runtime=enabled?createCapabilityRuntime(runtimeOptions):null;
 const versions=enabled?structuredClone(readHost().versions):null;
 const readCapability=runtimeOptions.readCapability;

 function evidence(reference:DischargeEvidence,roles:string[],taskIds?:string[],callId?:string){
  ref(reference);const value=readEvidence(structuredClone(reference));
  check(value,'discharge_evidence_missing');const record=validateRsiRecord(value);
  const e=record.payload;
  check(record.record_type==='evidence'&&e.id===reference.id&&e.sha256===reference.sha256&&
   e.version===reference.version&&e.status==='valid'&&roles.includes(e.role)&&
   (!taskIds||taskIds.includes(e.task_id))&&(!callId||e.observation_id===callId),'discharge_evidence_invalidated');
 }
 function active(item:DischargeObligation,claim:DischargeClaim,signal?:AbortSignal){
  check(!signal?.aborted,'discharge_cancelled');
  const host=readHost();
  check(host.taskId===taskId&&item.task_id===taskId&&item.owner===owner&&
   item.state_version===host.stateVersion,'discharge_task_state_changed');
  check(same(host.versions,versions),'discharge_component_version_changed');
  check(!host.grant.revoked&&host.grant.taskId===taskId&&host.grant.stateVersion===host.stateVersion,
   'discharge_permission_denied');
  const current=readObligations().find(row=>row.id===item.id);
  check(current&&same(current,item),'discharge_obligation_changed');
  check(readApprovedClaims().some(row=>same(row,claim)),'discharge_claim_changed');
  check(claim.owner===owner&&claim.scope===item.scope&&same(claim.predicate,item.predicate),
   'discharge_claim_scope_mismatch');
  ref(claim.verifier);check(same(readVerifier(claim.verifier)??null,claim.verifier),'discharge_verifier_changed');
  const capabilities=new Map(runtime!.snapshot().capabilities.map(cap=>[cap.id,cap]));
  const pending=[claim.capability],seen=new Set<string>();
  while(pending.length){
   const reference=pending.pop()!;if(seen.has(reference.id))continue;seen.add(reference.id);
   const frozen=capabilities.get(reference.id);
   check(frozen&&same(capabilityRef(frozen),reference),'discharge_capability_unavailable');
   const current=validateCapability(readCapability(reference),owner);
   check(same(capabilityRef(current),reference)&&current.certification==='certified',
    'discharge_capability_not_certified');
   check(current.contract.effects.every(effect=>host.grant.effects.includes(effect)),'discharge_permission_denied');
   pending.push(...frozen.dependencies);
  }
  check(Array.isArray(claim.training_task_ids)&&Array.isArray(claim.validation_task_ids)&&
   claim.validation_task_ids.length>0&&new Set(claim.validation_task_ids).size===claim.validation_task_ids.length&&
   claim.validation_task_ids.every(id=>text(id)&&!claim.training_task_ids.includes(id))&&
   Array.isArray(claim.validation_evidence)&&claim.validation_evidence.length>0,'discharge_claim_validation_invalid');
  for(const reference of claim.validation_evidence)evidence(reference,['validation'],claim.validation_task_ids);
  check(claim.validation_task_ids.every(id=>claim.validation_evidence.some(reference=>
   readEvidence(reference)?.payload.task_id===id)),'discharge_claim_validation_unwitnessed');
  for(const reference of item.dependencies)evidence(reference,['current'],[taskId]);
 }

 async function run({signal}:{signal?:AbortSignal}={}){
  const declared=structuredClone(readObligations());
  for(const item of declared)obligation(item);
  check(new Set(declared.map(item=>item.id)).size===declared.length,'discharge_duplicate_obligation');
  const ids=new Set(declared.map(item=>item.id));
  check(declared.every(item=>item.depends_on.every(id=>ids.has(id))),'discharge_dependency_missing');
  const summary:{status:string;solved:any[];remaining_frontier:any[]}={status:enabled?'completed':'disabled',solved:[],
   remaining_frontier:declared.map(item=>({id:item.id,kind:'obligation',scope:item.scope,description:item.description,reason:enabled?'unresolved':'disabled'}))};
  const audit:any[]=[];
  if(!enabled)return {summary,audit};
  const solved=new Set<string>();
  for(const item of declared){
   const row=summary.remaining_frontier.find(entry=>entry.id===item.id);
   if(signal?.aborted){summary.status='cancelled';row.reason='cancelled';break;}
   if(item.depends_on.some(id=>!solved.has(id))){row.reason='dependency_unresolved';continue;}
   // Retrieve only host-approved claims matching the current bounded predicate.
   const selection=item.bindings.flatMap(binding=>readApprovedClaims().filter(claim=>
    claim.owner===owner&&claim.scope===item.scope&&same(claim.predicate,item.predicate)&&
    same(claim.capability,binding.capability)).map(claim=>({binding,claim})))[0];
   if(!selection){row.reason='no_verified_cover';continue;}
   const {binding,claim}=structuredClone(selection);
   const attempt:any={obligation:structuredClone(item),claim,arguments:binding.arguments,outcome:null,verification:null,reason:null};
   audit.push(attempt);
   try{
    active(item,claim,signal);
    const snapshot=runtime!.snapshot();
    const cap=snapshot.capabilities.find(value=>same(capabilityRef(value),binding.capability));
    check(cap&&cap.certification==='certified'&&snapshot.roots.some(root=>same(root,binding.capability)),
     'discharge_capability_not_certified');
    // MVP is read-only. A failed independent check must not replay external writes.
    check(cap.contract.effects.every(effect=>effect==='read'),'discharge_read_only_required');
    const outcome=await runtime!.execute(binding.capability,binding.arguments,{signal});attempt.outcome=outcome;
    if(outcome.status==='cancelled'||outcome.status==='interrupted'){
     summary.status=outcome.status;row.reason=outcome.status;attempt.reason=outcome.status;break;
    }
    check(outcome.status==='succeeded','discharge_execution_'+outcome.status);
    const root=outcome.receipts[0];
    check(root&&root.parent_call_id===null&&root.task_id===taskId&&same(root.capability,binding.capability)&&
     root.arguments_sha256===bytesSha256(JSON.stringify(binding.arguments))&&
     root.result_sha256===bytesSha256(JSON.stringify(outcome.result)),'discharge_receipt_mismatch');
    active(item,claim,signal);
    const verified=await verify({obligation:structuredClone(item),claim:structuredClone(claim),
     arguments:structuredClone(binding.arguments),outcome:structuredClone(outcome),signal});
    attempt.verification=structuredClone(verified);
    active(item,claim,signal);
    check(verified&&typeof verified.accepted==='boolean'&&Array.isArray(verified.artifact_refs)&&
     Array.isArray(verified.introduced_checks),'discharge_verification_invalid');
    check(same(verified.receipt_binding,{call_id:root.call_id,arguments_sha256:root.arguments_sha256,
     result_sha256:root.result_sha256}),'discharge_verification_receipt_mismatch');
    check(verified.evidence.sha256===bytesSha256(JSON.stringify(dischargeVerificationPayload(verified))),
     'discharge_verification_digest_mismatch');
    evidence(verified.evidence,['validation'],[taskId],root.call_id);
    for(const artifact of verified.artifact_refs)evidence(artifact,['current','validation'],[taskId],root.call_id);
    check(verified.introduced_checks.every(check=>check&&text(check.id)&&text(check.scope)&&text(check.description))&&
     new Set(verified.introduced_checks.map(check=>check.id)).size===verified.introduced_checks.length,'discharge_new_checks_invalid');
    for(const next of verified.introduced_checks)summary.remaining_frontier.push({
     id:item.id+'/check/'+next.id,kind:'composition_check',scope:next.scope,description:next.description,
     reason:'independent_composition_check_required',origin_obligation:item.id});
    check(verified.accepted,'discharge_verifier_rejected');
    check(verified.artifact_refs.length>0,'discharge_artifact_evidence_missing');
    // Persist complete linked receipts before giving the model a solved claim.
    const auditRef=saveAudit(structuredClone(attempt));ref(auditRef);
    check(auditRef.sha256===bytesSha256(JSON.stringify(attempt)),'discharge_audit_digest_mismatch');
    active(item,claim,signal);
    attempt.audit_ref=auditRef;
    summary.solved.push({obligation_id:item.id,capability:binding.capability,scope:claim.scope,
     artifact_refs:structuredClone(verified.artifact_refs),receipt_ref:{audit:auditRef,call_id:root.call_id},
     verification_ref:structuredClone(verified.evidence)});
    summary.remaining_frontier=summary.remaining_frontier.filter(entry=>entry!==row);
    solved.add(item.id);
   }catch(error){
    const reason=error instanceof Error?error.message:'discharge_failed';attempt.reason=reason;row.reason=reason;
    if(signal?.aborted){summary.status=attempt.outcome?'interrupted':'cancelled';break;}
   }finally{
    if(!attempt.audit_ref){
     try{const auditRef=saveAudit(structuredClone(attempt));ref(auditRef);
      check(auditRef.sha256===bytesSha256(JSON.stringify(attempt)),'discharge_audit_digest_mismatch');attempt.audit_ref=auditRef;
     }catch{attempt.audit_error='discharge_audit_persistence_failed';}
    }
   }
  }
  // A later call/verifier can revoke evidence supporting an earlier answer.
  // Recheck before the single handoff; never keep a stale solved item in it.
  summary.solved=summary.solved.filter(solution=>{
   const attempt=audit.find(row=>row.obligation.id===solution.obligation_id);
   try{active(attempt.obligation,attempt.claim,signal);
    evidence(solution.verification_ref,['validation'],[taskId],solution.receipt_ref.call_id);
    for(const artifact of solution.artifact_refs)evidence(artifact,['current','validation'],[taskId],solution.receipt_ref.call_id);
    return true;
   }catch(error){summary.remaining_frontier.push({id:attempt.obligation.id,kind:'obligation',scope:attempt.obligation.scope,
    description:attempt.obligation.description,reason:error instanceof Error?error.message:'discharge_handoff_invalidated'});return false;}
  });
  return {summary,audit};
 }
 return {run};
}
