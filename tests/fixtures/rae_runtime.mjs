/** Actual Runtime execution with explicitly synthetic diagnostic authority.
 * Host operations must inspect their fixed executable bytes and run for real.
 * This fixture is never a production authorization or model-behavior claim.
 */
import {createCapabilityRuntime} from '../../src/adapters/capability_runtime.ts';
import {capabilityDigest,capabilityRef} from '../../src/adapters/capability_contract.ts';
import {bytesSha256} from '../../src/adapters/rsi_protocol.ts';
import {diagnosticHost} from '../../examples/rsi-protocol-v1/host.mjs';

export async function execute(snapshot,root,input,{taskId,mode='execute',operations}){
 const {host,request:template}=diagnosticHost();
 host.taskId=taskId;host.stateVersion='rae-state-'+taskId;
 Object.assign(host.grant,{taskId,stateVersion:host.stateVersion});
 Object.assign(template.payload,{task_id:taskId,state_version:host.stateVersion});
 for(const value of host.currentEvidence.values())value.payload.task_id=taskId;
 const operatorTemplate=structuredClone(host.operators.get('group-count').record);
 host.operators.clear();host.currentCodeSha256.clear();host.obligations.clear();
 for(const [name,operation] of operations){
  const reference=operation.inspect();
  const operator=structuredClone(operatorTemplate);
  Object.assign(operator.payload,{id:name,operation:name,code_sha256:reference.object_sha256,
   input_schema:{type:'object'},output_schema:{type:'object'}});
  host.operators.set(name,{record:operator,certified:true});
  host.currentCodeSha256.set(name,reference.object_sha256);
 }
 host.grant.operations=[...operations.keys()];
 const backend={
  inspect(reference){
   const operation=operations.get(reference.object_id);
   if(!operation)throw Error('diagnostic_operation_missing');
   return operation.inspect();
  },
  request(call,args){
   const operation=call.capability.implementation.legacy_ref.object_id;
   const request=structuredClone(template);
   Object.assign(request.payload,{id:call.callId,operation,operator_id:operation,
    arguments_sha256:bytesSha256(JSON.stringify(args)),obligation_ref:'rae-call-'+call.callId});
   host.obligations.set(request.payload.obligation_ref,{taskId,operation,stateVersion:host.stateVersion,
    argumentsSha256:request.payload.arguments_sha256,dependencies:structuredClone(request.payload.dependencies)});
   return request;
  },
  async execute(call,operation,args){
   const value=await operations.get(operation).run(structuredClone(args));
   return {value,receipt:{call_id:call.callId,parent_call_id:call.parentCallId,task_id:taskId,
    operation,status:'succeeded',...(operations.get(operation).nativeReceipt?
      {native_receipt:operations.get(operation).nativeReceipt(value,call)}:{})}};
  },
 };
 const runtime=createCapabilityRuntime({taskId,owner:snapshot.owner,snapshot,readHost:()=>host,
  readCapability:ref=>snapshot.capabilities.find(c=>c.id===ref.id),
  ...(mode==='validate'?{readValidationGrant:()=>({id:'rae-validation-'+taskId,taskId,
   owner:snapshot.owner,snapshotDigest:snapshot.digest,root,revoked:false})}:{}),
  backends:Object.fromEntries([...new Set([...operations.values()].map(op=>op.inspect().backend))].map(name=>[name,backend]))});
 const result=await runtime.execute(root,input);
 const execution={format:'capability_diagnostic_execution_v1',owner:snapshot.owner,task_id:taskId,
  mode,grant_id:host.grant.id,snapshot_sha256:snapshot.digest,root,
  arguments_sha256:capabilityDigest(input),...result};
 return {execution,artifacts:[{name:'output.json',bytes:Buffer.from(JSON.stringify(result.result))}]};
}
