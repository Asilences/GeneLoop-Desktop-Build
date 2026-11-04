/** Reuse public published roots through the existing create_ppt_page entry. */
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {capabilityDigest,capabilityRef,validateCapabilitySnapshot} from './capability_contract.ts';
import {bytesSha256} from './rsi_protocol.ts';
import {runArtifactCapability} from './artifact_capability_runtime.ts';

export function pptPublicCapabilities(selection:any){
 const selected=selection.public_capabilities;
 if(!selected)return null;
 const raw=readFileSync(selected.snapshot.path);
 if(bytesSha256(raw)!==selected.snapshot.sha256)throw Error('ppt_public_snapshot_changed');
 const snapshot=validateCapabilitySnapshot(JSON.parse(raw.toString('utf8')),selection.user);
 const roots=selected.roots.map((ref:any)=>{
  const value=snapshot.capabilities.find(cap=>cap.id===ref.id);
  if(!value||!snapshot.roots.some(root=>capabilityDigest(root)===capabilityDigest(ref))||
     value.certification!=='certified'||value.implementation.kind!=='composition')throw Error('ppt_public_root_not_published');
  return value;
 }).filter((value:any)=>capabilityDigest(Object.keys(value.contract.input_schema.properties??{}).sort())===capabilityDigest(['parameters']));
 return {selection:selected,snapshot,roots};
}

export async function runPptPublicPage(value:any,args:any,execution:any){
 const publicState=value.publicCapabilities,task=value.task;
 const selected=publicState?.roots.find((cap:any)=>cap.id===args.id);
 if(!selected)throw Error('ppt_public_capability_not_available');
 const id='public-ppt-'+randomUUID(),registry=join(task.output,id+'-registry.json'),manifestPath=join(task.output,id+'-manifest.json');
 writeFileSync(registry,JSON.stringify(publicState.snapshot),{mode:0o600,flag:'wx'});
 const parameters={parameters:args.parameters};
 const manifest={format:'artifact_capability_task_v1',owner:publicState.snapshot.owner,task_id:task.request.task_id,
  workspace:task.workspace,session_id:execution.agent.session.id,registry_path:registry,
  libraries:[{path:value.selection.library,sha256:value.selection.library_sha256}],resources:value.context.resources,
  evidence:[publicState.selection.snapshot,...publicState.selection.evidence],inputs:[],
  grant:{id,task_id:task.request.task_id,root:capabilityRef(selected),snapshot_sha256:publicState.snapshot.digest,
   arguments_sha256:capabilityDigest(parameters),effects:['workspace_write'],mode:'execute',revoked:false}};
 writeFileSync(manifestPath,JSON.stringify(manifest),{mode:0o600,flag:'wx'});
 const trace=await runArtifactCapability(manifestPath,publicState.snapshot,parameters,{signal:execution.signal});
 writeFileSync(join(task.output,id+'-trace.json'),JSON.stringify(trace),{mode:0o600,flag:'wx'});
 value.context.audit({kind:'ppt_public_capability_executed',capability_id:selected.id,status:trace.status,
  task_id:task.request.task_id,snapshot_sha256:publicState.snapshot.digest,receipts:trace.receipts.length});
 if(trace.status!=='succeeded')throw Error('ppt_public_capability_failed: '+trace.receipts.find((row:any)=>row.reason)?.reason);
 if(trace.result?.kind!=='artifact_program_receipt')throw Error('ppt_public_page_result_required');
 return {receipt:trace.result,capability_trace:trace};
}
