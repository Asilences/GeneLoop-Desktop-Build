/** CLI wiring fixture. Real subprocesses/Runtime/Store, synthetic source tasks. */
import {readFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {join} from 'node:path';
import {createCapability,capabilityRef,createCapabilitySnapshot,capabilityDigest} from '../../src/adapters/capability_contract.ts';
import {bytesSha256} from '../../src/adapters/rsi_protocol.ts';
import {completeCapabilityCycle} from '../../src/adapters/capability_cycle.ts';
import {createCapabilityStore} from '../../src/adapters/capability_store.ts';
import {execute} from './rae_runtime.mjs';

const source=fileURLToPath(new URL('./rae_arithmetic.py',import.meta.url));
const operations=new Map(['increment','double','subtract'].map(name=>[name,{
 inspect:()=>({backend:'artifact_motif',object_id:name,object_sha256:bytesSha256(readFileSync(source)),
  library_sha256:bytesSha256('rae-arithmetic-library'),library_digest:bytesSha256('rae-arithmetic-library'),
  certificate_sha256:bytesSha256('rae-synthetic-diagnostic-certificate')}),
 run:async args=>{
  const result=spawnSync(process.env.SSS_PYTHON??'python3',[source,name],{input:JSON.stringify(args),encoding:'utf8'});
  if(result.status!==0)throw Error('diagnostic_worker_failed:'+result.stderr);
  return JSON.parse(result.stdout);
 },
}]));
const scalar={type:'object',properties:{value:{type:'number'}},required:['value'],additionalProperties:false};
const request=JSON.parse(readFileSync(0,'utf8'));
if(request.action==='seed'){
 const caps=[...operations].map(([name,op])=>createCapability({owner:request.owner,
  contract:{input_schema:scalar,output_schema:scalar,effects:['read']},
  implementation:{kind:'legacy',legacy_ref:op.inspect()},dependencies:[]},
  {lifecycle:'active',certification:'certified',migration:'testing'}));
 process.stdout.write(JSON.stringify(createCapabilitySnapshot(request.owner,caps.map(capabilityRef),caps)));
}else if(request.action==='run'){
 process.stdout.write(JSON.stringify(await execute(request.snapshot,request.root,request.input,
  {taskId:request.task_id,mode:request.mode??'execute',operations})));
}else if(request.action==='publish'){
 const snapshot=request.compiled.snapshot,root=capabilityRef(request.compiled.capability),owner=snapshot.owner;
 const validation={id:request.label+'-validation',workspace:join(request.directory,'validation'),input:request.validation_input};
 const followup={id:request.label+'-followup',workspace:join(request.directory,'followup'),input:request.followup_input};
 mkdirSync(validation.workspace,{recursive:true});mkdirSync(followup.workspace,{recursive:true});
 const directory=join(request.directory,'store'),validator={id:'arithmetic-independent-predicate',sha256:bytesSha256(readFileSync(fileURLToPath(import.meta.url)))};
 const result=await completeCapabilityCycle({owner,directory,candidateSnapshot:snapshot,root,
  expectedLatest:request.expectedLatest??null,validation,followup,validator,
  run:(s,input,mode,label)=>execute(s,root,input,{taskId:label==='validation'?validation.id:followup.id,mode,operations}),
  check:async(run,label)=>{
   const expected=label==='validation'?request.expected_validation:request.expected_followup;
   const passed=capabilityDigest(run.execution.result)===capabilityDigest(expected);
   return {passed,checks:[{id:'independent-result',status:passed?'passed':'failed',observation:'fixed diagnostic predicate'}],
    scope:'synthetic_arithmetic_wiring_not_model_quality'};
  }});
 const store=createCapabilityStore({directory,owner,validator:{...validator,check:async()=>{throw Error('read_only');}},
  runValidation:async()=>{throw Error('read_only');}});
 process.stdout.write(JSON.stringify({result,publication:store.loadLatest(),library:store.constructionLibrary(request.seed)}));
}else throw Error('unknown_diagnostic_action');
