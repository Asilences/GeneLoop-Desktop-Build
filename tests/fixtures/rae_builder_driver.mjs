/** Real Builder compiler operations through Runtime/Store; diagnostic authority.
 * The Python operations parse and freeze actual construction source. No model
 * output, generated algorithm, or independent quality verdict is fabricated.
 */
import {readFileSync,mkdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createCapability,capabilityRef,createCapabilitySnapshot,capabilityDigest} from '../../src/adapters/capability_contract.ts';
import {bytesSha256} from '../../src/adapters/rsi_protocol.ts';
import {completeCapabilityCycle} from '../../src/adapters/capability_cycle.ts';
import {createCapabilityStore} from '../../src/adapters/capability_store.ts';
import {execute} from './rae_runtime.mjs';

const files=['capability_builder_application.py','capability_source_authoring.py','capability_program_encoding.py'];
const source=()=>Buffer.concat(files.map(f=>readFileSync(new URL('../../src/adapters/'+f,import.meta.url))));
const schema=name=>({type:'object',properties:{[name]:{type:'string'}},required:[name],additionalProperties:false});
const signatures={builder_parse:['context_json','prepared_json'],builder_freeze:['prepared_json','result_json']};
const operations=new Map(Object.keys(signatures).map(name=>[name,{
 inspect:()=>({backend:'artifact_motif',object_id:name,object_sha256:bytesSha256(source()),
  library_sha256:bytesSha256('rae-builder-host-operations'),library_digest:bytesSha256('rae-builder-host-operations'),
  certificate_sha256:bytesSha256('rae-builder-diagnostic-host-authority')}),
 run:async args=>{
  const run=spawnSync(process.env.SSS_PYTHON??'python3',['-m','src.adapters.capability_builder_application'],
   {input:JSON.stringify({operation:name,arguments:args}),encoding:'utf8'});
  if(run.status!==0)throw Error('builder_operation_failed:'+run.stderr);
  return JSON.parse(run.stdout);
 },
}]));
const request=JSON.parse(readFileSync(0,'utf8'));
if(request.action==='seed'){
 const caps=[...operations].map(([name,op])=>createCapability({owner:request.owner,
  contract:{input_schema:schema(signatures[name][0]),output_schema:schema(signatures[name][1]),effects:['read']},
  implementation:{kind:'legacy',legacy_ref:op.inspect()},dependencies:[]},
  {lifecycle:'active',certification:'certified',migration:'testing'}));
 process.stdout.write(JSON.stringify(createCapabilitySnapshot(request.owner,caps.map(capabilityRef),caps)));
}else if(request.action==='run'){
 process.stdout.write(JSON.stringify(await execute(request.snapshot,request.root,request.input,
  {taskId:request.task_id,mode:request.mode??'execute',operations})));
}else if(request.action==='publish'){
 const snapshot=request.compiled.snapshot,root=capabilityRef(request.compiled.capability),owner=snapshot.owner;
 const validation={id:'builder-validation',workspace:join(request.directory,'validation'),input:request.validation_input};
 const followup={id:'builder-followup',workspace:join(request.directory,'followup'),input:request.followup_input};
 mkdirSync(validation.workspace,{recursive:true});mkdirSync(followup.workspace,{recursive:true});
 const directory=join(request.directory,'store');
 const validator={id:'builder-frozen-intent-conformance',sha256:bytesSha256(readFileSync(fileURLToPath(import.meta.url)))};
 const result=await completeCapabilityCycle({owner,directory,candidateSnapshot:snapshot,root,expectedLatest:null,
  validation,followup,validator,
  run:(s,input,mode,label)=>execute(s,root,input,{taskId:label==='validation'?validation.id:followup.id,mode,operations}),
  check:async(run,label)=>{
   const expected=label==='validation'?request.expected_validation:request.expected_followup;
   const passed=capabilityDigest(run.execution.result)===capabilityDigest(expected);
   return {passed,checks:[{id:'original-builder-equivalence',status:passed?'passed':'failed',observation:'frozen independent original Builder output'}],
    scope:'builder_structural_conformance_not_creation_efficiency'};
  }});
 const store=createCapabilityStore({directory,owner,validator:{...validator,check:async()=>{throw Error('read_only');}},
  runValidation:async()=>{throw Error('read_only');}});
 process.stdout.write(JSON.stringify({result,publication:store.loadLatest(),library:store.constructionLibrary(request.seed)}));
}else throw Error('unknown_builder_action');
