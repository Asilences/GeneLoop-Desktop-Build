/** Synthetic Script-shaped native evidence, actual Capability Runtime dispatch.
 * This tests projection/guards, not Script sandbox admission or real paper quality.
 */
import {readFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createCapability,capabilityRef,createCapabilitySnapshot,capabilityDigest} from '../../src/adapters/capability_contract.ts';
import {completeCapabilityCycle} from '../../src/adapters/capability_cycle.ts';
import {createCapabilityStore} from '../../src/adapters/capability_store.ts';
import {bytesSha256} from '../../src/adapters/rsi_protocol.ts';
import {execute} from './rae_runtime.mjs';
const object=properties=>({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
const report=object({name:{type:'string'},records:{type:'array'}});
const output=object({same:{type:'boolean'},records:{type:'array'}});
const reference=name=>({backend:'script_motif',object_id:name,
 object_sha256:bytesSha256(readFileSync(fileURLToPath(import.meta.url))),
 library_sha256:bytesSha256('synthetic-script-library'),library_digest:bytesSha256('synthetic-script-library'),
 certificate_sha256:bytesSha256('synthetic-script-certificate')});
const operations=new Map(['audit','compare'].map(name=>[name,{
 inspect:()=>reference(name),
 run:async args=>{
  const value=name==='audit'?{name:args.project,records:args.project==='empty'?[]:[{text:args.project,groups:[['x'],[]]}]}:
   {same:args.value.before.name===args.value.after.name,records:[args.value.before.records,args.value.after.records]};
  return {stdout:JSON.stringify(value),value};
 },
 nativeReceipt:(result,call)=>({kind:'script_motif_receipt',nonce:'synthetic-native-witness',program_id:name,
  versions:[],output:result.stdout,output_sha256:bytesSha256(result.stdout),network_evidence:[],
  elapsed_ms:0,script_version:call.capability.implementation.legacy_ref}),
}]));
const request=JSON.parse(readFileSync(0,'utf8'));
if(request.action==='seed'){
 const caps=[...operations].map(([name,op])=>createCapability({owner:'nested-diagnostic',
  contract:{input_schema:name==='audit'?object({project:{type:'string'}}):object({value:object({before:report,after:report})}),
   output_schema:object({stdout:{type:'string'},value:name==='audit'?report:output}),effects:['read']},
  implementation:{kind:'legacy',legacy_ref:op.inspect()},dependencies:[]},
  {lifecycle:'active',certification:'certified',migration:'testing'}));
 process.stdout.write(JSON.stringify(createCapabilitySnapshot('nested-diagnostic',caps.map(capabilityRef),caps)));
}else if(request.action==='publish'){
 const snapshot=request.compiled.snapshot,root=capabilityRef(request.compiled.capability),owner=snapshot.owner;
 const directory=join(request.directory,'store');
 const tasks=Object.fromEntries(['validation','followup'].map(label=>{
  const workspace=join(request.directory,label);mkdirSync(workspace,{recursive:true});
  return [label,{id:'builder-material-'+label,input:request[label+'_input'],workspace}];
 }));
 const validator={id:'builder-material-conformance',sha256:bytesSha256(readFileSync(fileURLToPath(import.meta.url)))};
 const result=await completeCapabilityCycle({owner,directory,candidateSnapshot:snapshot,root,expectedLatest:null,
  validation:tasks.validation,followup:tasks.followup,validator,
  run:(s,input,mode,label)=>execute(s,root,input,{taskId:tasks[label].id,mode,operations}),
  check:async(run,label)=>{
   const passed=capabilityDigest(run.execution.result)===capabilityDigest(request['expected_'+label]);
   return {passed,checks:[{id:'host-frozen-output',status:passed?'passed':'failed',observation:'independent synthetic material values'}],
    scope:'diagnostic_native_authority_not_paper_quality'};
  }});
 const store=createCapabilityStore({directory,owner,validator:{...validator,check:async()=>{throw Error('read_only');}},
  runValidation:async()=>{throw Error('read_only');}});
 process.stdout.write(JSON.stringify({result,library:store.constructionLibrary(request.seed)}));
}else{
 process.stdout.write(JSON.stringify(await execute(request.snapshot,request.root,request.input,
  {taskId:request.task_id,mode:request.mode??'execute',operations})));
}
