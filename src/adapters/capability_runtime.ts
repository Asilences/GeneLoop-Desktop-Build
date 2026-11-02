/** Task-pinned composition runner. Authority and actual execution stay in the
 * existing host/backend lifecycle; this module never evaluates stored source.
 */
import {randomUUID} from 'node:crypto';
import {validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';
import {
 capabilityDigest, capabilityRef, validateCapability, validateCapabilitySnapshot,
 type Capability, type CapabilityRef, type CapabilitySnapshot,
} from './capability_contract.ts';
import {bytesSha256, executeRsiOperation, type AdmissionHost, type RsiRecord} from './rsi_protocol.ts';

type LegacyRef = Extract<Capability['implementation'], {kind:'legacy'}>['legacy_ref'];
type Binding = Extract<Capability['implementation'], {kind:'composition'}>['output'];
export type CapabilityCall = {
 taskId:string; callId:string; parentCallId:string|null; capability:Capability;
 snapshotDigest:string; signal?:AbortSignal;
};
export type NativeCapabilityReceipt = {call_id:string; operation:string; status:'succeeded';
 parent_call_id?:string|null;task_id?:string;native_receipt?:unknown};
export type CapabilityBackend = {
 /** Read and verify the actual immutable library, object and certificate bytes.
  * Returning the supplied reference without reading the backend is not valid.
  */
 inspect:(reference:LegacyRef)=>LegacyRef;
 /** Trusted native adapter, not candidate code. It binds an existing obligation. */
 request:(call:CapabilityCall,args:unknown)=>RsiRecord;
 /** Must await the native tool's execution/completion and forward cancellation.
  * Materialized source and catalog lookup results are not execution receipts.
  */
 execute:(call:CapabilityCall,operation:string,args:unknown)=>Promise<{
  value:unknown; receipt:NativeCapabilityReceipt;
 }>;
};
export type CapabilityReceipt = {
 call_id:string; parent_call_id:string|null; task_id:string;
 capability:CapabilityRef; snapshot_sha256:string; kind:'legacy'|'composition';
 status:'succeeded'|'rejected'|'failed'|'cancelled'|'interrupted'; reason:string|null;
 /** Null when supplied arguments are not representable as valid JSON. */
 arguments_sha256:string|null; result_sha256:string|null; dispatched:boolean;
 /** Inclusive elapsed time; do not sum parent and child durations. */
 duration_ms:number;
 child_call_ids:string[]; backend_receipt:NativeCapabilityReceipt|null;
 events:RsiRecord[];
};
export type CapabilityRuntimeHost = {
 taskId:string; owner:string; snapshot:CapabilitySnapshot;
 readHost:()=>AdmissionHost;
 /** Independent trusted registry: certification/revocation must be current. */
 readCapability:(reference:CapabilityRef)=>unknown;
 backends:Partial<Record<LegacyRef['backend'],CapabilityBackend>>;
 /** An independent validator may execute exactly one candidate root without
  * upgrading its certification. Dependencies still require certification. */
 readValidationGrant?:()=>{id:string;taskId:string;owner:string;snapshotDigest:string;root:CapabilityRef;revoked:boolean};
};

function check(condition:unknown,reason:string):asserts condition {
 if(!condition)throw Error(reason);
}
function same(a:unknown,b:unknown){return capabilityDigest(a)===capabilityDigest(b);}
function jsonHash(value:unknown){
 capabilityDigest(value); // Reject non-JSON/non-finite values before serialization.
 const encoded=JSON.stringify(value);
 check(encoded!==undefined,'capability_non_json_value');
 return bytesSha256(encoded);
}
function at(value:unknown,path:string[]):unknown {
 let cursor:any=value;
 for(const key of path){
  check(cursor!==null&&typeof cursor==='object'&&Object.hasOwn(cursor,key),'capability_binding_path_missing');
  cursor=cursor[key];
 }
 return structuredClone(cursor);
}
function bind(binding:Binding,input:unknown,steps:Map<string,unknown>):unknown {
 switch(binding.kind){
  case 'input': return at(input,binding.path);
  case 'step':
   check(steps.has(binding.step_id),'capability_binding_step_missing');
   return at(steps.get(binding.step_id),binding.path);
  case 'literal': return structuredClone(binding.value);
  case 'array': return binding.items.map(item=>bind(item,input,steps));
  case 'object': return Object.fromEntries(Object.entries(binding.fields).map(([key,item])=>[key,bind(item,input,steps)]));
 }
}

/** Freeze content/component versions once for the task. Each execute() admits
 * one selected root against its current selection eligibility. Promotion or
 * archival after that admission does not interrupt the call; certification,
 * permissions and evidence remain live guards. Latest pointers are never read.
 */
export function createCapabilityRuntime(options:CapabilityRuntimeHost){
 const snapshot=validateCapabilitySnapshot(options.snapshot,options.owner);
 const taskId=options.taskId,owner=options.owner;
 const frozenHost=options.readHost();
 check(frozenHost.taskId===taskId,'capability_task_mismatch');
 const stateVersion=frozenHost.stateVersion,versions=structuredClone(frozenHost.versions);
 const capabilities=new Map(snapshot.capabilities.map(item=>[item.id,item]));
 for(const capability of snapshot.capabilities){
  for(const dependency of capability.dependencies){
   check(capabilities.get(dependency.id)!.contract.effects.every(effect=>capability.contract.effects.includes(effect)),
    'capability_undeclared_dependency_effect');
  }
 }
 // Capture adapter registrations: swapping the options object must not reroute a task.
 const backends=Object.fromEntries(Object.entries(options.backends).map(([key,value])=>[key,{
  inspect:value!.inspect.bind(value),request:value!.request.bind(value),execute:value!.execute.bind(value),
 }])) as CapabilityRuntimeHost['backends'];
 const readHost=options.readHost,readCapability=options.readCapability;
 const readValidationGrant=options.readValidationGrant;

 function guard(signal:AbortSignal|undefined,closure:Capability[],selectedRoot:CapabilityRef,admitting=false){
  check(!signal?.aborted,'capability_cancelled');
  const host=readHost();
  check(host.taskId===taskId,'capability_task_mismatch');
  check(host.stateVersion===stateVersion,'capability_state_changed');
  check(same(host.versions,versions),'capability_component_version_changed');
  check(!host.grant.revoked&&host.grant.taskId===taskId&&host.grant.stateVersion===stateVersion,'capability_permission_denied');
  let validating=false;
  if(readValidationGrant){
   const grant=readValidationGrant();
   check(!grant.revoked&&grant.taskId===taskId&&grant.owner===owner&&grant.snapshotDigest===snapshot.digest&&same(grant.root,selectedRoot),
    'capability_validation_grant_invalid');
   validating=true;
  }
  for(const frozen of closure){
   const current=validateCapability(readCapability(capabilityRef(frozen)),owner);
   check(same(capabilityRef(current),capabilityRef(frozen)),'capability_revision_changed');
   const candidateRoot=validating&&frozen.id===selectedRoot.id&&frozen.certification==='candidate'&&current.certification==='candidate';
   check(candidateRoot||frozen.certification==='certified'&&current.certification==='certified','capability_not_certified');
   // Lifecycle/migration are selection policy, not revocation. Only the initial
   // root admission checks active; retained dependencies may already be archived.
   if(admitting&&frozen.id===selectedRoot.id)check(candidateRoot||frozen.lifecycle==='active'&&current.lifecycle==='active','capability_not_executable');
   check(current.contract.effects.every(effect=>host.grant.effects.includes(effect)),'capability_permission_denied');
   check(!current.contract.effects.includes('external_write'),'capability_external_write_not_enabled');
   check(!current.contract.effects.includes('opaque'),'capability_opaque_not_executable');
   if(frozen.implementation.kind==='legacy'){
    const reference=frozen.implementation.legacy_ref,backend=backends[reference.backend];
    check(backend,'capability_backend_missing');
    check(same(backend.inspect(structuredClone(reference)),reference),'capability_legacy_changed');
   }
  }
  return structuredClone(host);
 }

 async function execute(root:CapabilityRef,input:unknown,{signal}:{signal?:AbortSignal}={}){
  const selectedRoot=structuredClone(root);
  check(snapshot.roots.some(ref=>same(ref,selectedRoot)),'capability_root_not_in_snapshot');
  const selectedIds=new Set<string>(),pending=[selectedRoot.id];
  while(pending.length){
   const id=pending.pop()!;
   if(selectedIds.has(id))continue;
   selectedIds.add(id);
   pending.push(...capabilities.get(id)!.dependencies.map(ref=>ref.id));
  }
  // A snapshot can expose several roots. Unselected capabilities neither grant
  // this call authority nor impose unrelated live availability/IO dependencies.
  const closure=snapshot.capabilities.filter(capability=>selectedIds.has(capability.id));
  const receipts:CapabilityReceipt[]=[];
  async function run(ref:CapabilityRef,args:unknown,parentCallId:string|null):Promise<{ok:boolean;value:unknown;receipt:CapabilityReceipt}>{
   const started=performance.now();
   const capability=capabilities.get(ref.id)!;
   const receipt:CapabilityReceipt={call_id:randomUUID(),parent_call_id:parentCallId,task_id:taskId,
    capability:capabilityRef(capability),snapshot_sha256:snapshot.digest,kind:capability.implementation.kind,
    status:'rejected',reason:null,arguments_sha256:null,result_sha256:null,dispatched:false,duration_ms:0,
    child_call_ids:[],backend_receipt:null,events:[]};
   receipts.push(receipt);
   let value:unknown=null;
   try{
    const bound=structuredClone(args);
    receipt.arguments_sha256=jsonHash(bound);
    guard(signal,closure,selectedRoot,parentCallId===null);
    check(!validateJsonSchemaValue(capability.contract.input_schema,bound).length,'capability_input_schema_invalid');
    const implementation=capability.implementation;
    if(implementation.kind==='composition'){
     const outputs=new Map<string,unknown>();
     for(const step of implementation.steps){
      guard(signal,closure,selectedRoot);
      const child=await run(step.capability,bind(step.arguments,bound,outputs),receipt.call_id);
      receipt.child_call_ids.push(child.receipt.call_id);
      receipt.dispatched ||= child.receipt.dispatched;
      check(child.ok,child.receipt.reason??'capability_child_failed');
      outputs.set(step.id,child.value);
     }
     value=bind(implementation.output,bound,outputs);
    }else{
     const backend=backends[implementation.legacy_ref.backend];
     check(backend,'capability_backend_missing');
     const call:CapabilityCall={taskId,callId:receipt.call_id,parentCallId,
      capability:structuredClone(capability),snapshotDigest:snapshot.digest,signal};
     const request=backend.request(call,structuredClone(bound));
     const outcome=await executeRsiOperation(request,bound,()=>guard(signal,closure,selectedRoot),async(operation,argumentsValue)=>{
      // Recheck after request construction and immediately before native dispatch.
      const current=guard(signal,closure,selectedRoot);
      const operator=current.operators.get(request.payload.operator_id)?.record.payload;
      check(operator&&capability.contract.effects.includes(operator.effect),'capability_effect_mismatch');
      receipt.dispatched=true;
      const native=await backend.execute(call,operation,argumentsValue);
      check(native.receipt?.call_id===call.callId&&native.receipt.operation===operation&&native.receipt.status==='succeeded','capability_backend_receipt_invalid');
      check((native.receipt.parent_call_id===undefined||native.receipt.parent_call_id===parentCallId)&&
       (native.receipt.task_id===undefined||native.receipt.task_id===taskId),'capability_backend_receipt_scope_invalid');
      receipt.backend_receipt=structuredClone(native.receipt);
      receipt.result_sha256=jsonHash(native.value);
      return native.value;
     },{callId:receipt.call_id});
     receipt.events=outcome.events;
     check(outcome.decision.payload.action==='execute'&&outcome.events.at(-1)?.payload.phase==='succeeded',
      outcome.events.at(-1)?.payload.error??outcome.decision.payload.reason);
     value=outcome.result;
    }
    receipt.result_sha256=jsonHash(value);
    check(!validateJsonSchemaValue(capability.contract.output_schema,value).length,'capability_output_schema_invalid');
    guard(signal,closure,selectedRoot);
    receipt.status='succeeded';
    return {ok:true,value,receipt};
   }catch(error){
    receipt.reason=error instanceof Error?error.message:'capability_execution_failed';
    receipt.status=signal?.aborted?(receipt.dispatched?'interrupted':'cancelled'):(receipt.dispatched?'failed':'rejected');
    return {ok:false,value:null,receipt};
   }finally{
    receipt.duration_ms=performance.now()-started;
   }
  }
  const outcome=await run(selectedRoot,input,null);
  return {status:outcome.receipt.status,result:outcome.value,receipts:structuredClone(receipts)};
 }
 return {snapshot:()=>structuredClone(snapshot),execute};
}
