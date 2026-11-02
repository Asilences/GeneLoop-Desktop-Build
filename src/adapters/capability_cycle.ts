/** Shared validation -> publication -> independent consumption lifecycle.
 * Scene callbacks own native execution and task-specific quality, never candidates.
 */
import {realpathSync} from 'node:fs';
import {capabilityDigest,capabilityRef,type CapabilitySnapshot} from './capability_contract.ts';
import {createCapabilityStore,type CapabilityArtifact,type CapabilityValidationExecution,type CapabilityValidationVerdict} from './capability_store.ts';

export type CapabilitySceneRun={execution:CapabilityValidationExecution;artifacts:CapabilityArtifact[];[key:string]:unknown};
export type CapabilitySceneCheck=CapabilityValidationVerdict&{evidence_binding?:Record<string,string>};
type Task={id:string;workspace:string;input:unknown};
export type CapabilityCycleOptions={
 owner:string;directory:string;candidateSnapshot:CapabilitySnapshot;root:ReturnType<typeof capabilityRef>;
 expectedLatest:string|null;validation:Task;followup:Task;
 validator:{id:string;sha256:string};
 run:(snapshot:CapabilitySnapshot,input:unknown,mode:'validate'|'execute',label:'validation'|'followup')=>Promise<CapabilitySceneRun>;
 check:(run:CapabilitySceneRun,label:'validation'|'followup')=>Promise<CapabilitySceneCheck>;
 onPublished?:(publication:unknown)=>void;
};
function check(condition:unknown,reason:string):asserts condition{if(!condition)throw Error('cycle_'+reason);}

/** Explicitly separate transport evidence from the Store's strict quality verdict.
 * Unknown fields remain errors rather than silently discarded claims.
 */
export function publicationVerdict(value:CapabilitySceneCheck):CapabilityValidationVerdict{
 check(value&&typeof value==='object'&&Object.keys(value).every(k=>['passed','checks','scope','limitations','evidence_binding'].includes(k)),'verdict_shape_invalid');
 if(value.evidence_binding!==undefined){
  check(value.evidence_binding&&typeof value.evidence_binding==='object'&&!Array.isArray(value.evidence_binding)&&
   Object.values(value.evidence_binding).every(v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v)),'evidence_binding_invalid');
 }
 const {evidence_binding,...verdict}=value;return structuredClone(verdict);
}

export async function completeCapabilityCycle(options:CapabilityCycleOptions){
 const {owner,directory,expectedLatest}=options;
 const snapshot=structuredClone(options.candidateSnapshot),root=structuredClone(options.root);
 const validation=structuredClone(options.validation),followup=structuredClone(options.followup);
 check(validation.id!==followup.id&&realpathSync(validation.workspace)!==realpathSync(followup.workspace),'followup_must_be_independent');
 // Paths supplied by adapters are canonical, existing directories. Different
 // task IDs alone are insufficient independence; identical inputs are rejected.
 check(capabilityDigest(validation.input)!==capabilityDigest(followup.input),'followup_input_must_differ');
 const run=options.run,verify=options.check;let validationRun:CapabilitySceneRun;
 function binding(value:CapabilitySceneRun,expected:CapabilitySnapshot,task:Task,mode:string){
  const t=value.execution;
  check(t.owner===owner&&t.task_id===task.id&&t.mode===mode&&t.snapshot_sha256===expected.digest&&
   capabilityDigest(t.root)===capabilityDigest(root)&&t.arguments_sha256===capabilityDigest(task.input),'execution_binding_changed');
  check(t.status==='succeeded'&&Array.isArray(t.receipts)&&t.receipts.length>0,'execution_failed');
 }
 const store=createCapabilityStore({directory,owner,validator:{...options.validator,
  check:async()=>publicationVerdict(await verify(validationRun,'validation'))},
  runValidation:async context=>{
   validationRun=await run(context.candidateSnapshot,context.input,'validate','validation');
   binding(validationRun,context.candidateSnapshot,validation,'validate');return validationRun;
  }});
 const publication=await store.publish({candidateSnapshot:snapshot,root,input:validation.input,expectedLatest});
 options.onPublished?.(publication.publication);
 const loaded=store.loadLatest();
 check(loaded?.publication_sha256===publication.publication_sha256,'publication_not_adopted');
 const next=await run(loaded.snapshot,followup.input,'execute','followup');binding(next,loaded.snapshot,followup,'execute');
 const verdict=publicationVerdict(await verify(next,'followup'));
 check(verdict.passed===true&&Array.isArray(verdict.checks)&&verdict.checks.length>0&&verdict.checks.every(c=>c.status==='passed'),'followup_validation_failed');
 return {status:'completed',publication_sha256:publication.publication_sha256,candidate:root,
  validation_task:validationRun!.execution.task_id,followup_task:next.execution.task_id,followup_passed:true,
  scope:'scene_capability_validated_published_and_reused',efficiency_conclusion:null};
}
