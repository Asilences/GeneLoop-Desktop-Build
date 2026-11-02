/** Paper callbacks on the shared lifecycle, with fixed independent validator. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {capabilityDigest,capabilityRef} from '../../src/adapters/capability_contract.ts';
import {bytesSha256} from '../../src/adapters/rsi_protocol.ts';
import {runScriptCapability} from '../../src/adapters/script_capability_runtime.ts';
import {completeCapabilityCycle} from '../../src/adapters/capability_cycle.ts';
const root=fileURLToPath(new URL('../../',import.meta.url)),exec=promisify(execFile);
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const save=(path,value)=>writeFileSync(path,JSON.stringify(value,null,2),{flag:'wx',mode:0o600});
const plan=read(process.argv[2]),output=resolve(plan.output),candidate=read(plan.candidate),selected=capabilityRef(candidate.capability);
mkdirSync(output,{mode:0o700});save(join(output,'plan.json'),plan);
const controller=new AbortController();process.on('SIGINT',()=>controller.abort());process.on('SIGTERM',()=>controller.abort());
const checker=join(root,'scenarios/paper_proofreading/verify_capability_outputs.py');
const checkerFiles=[checker,join(root,'src/adapters/paper_bibliography.py'),join(root,'src/adapters/capability_contract.py')];
const checkerDigest=()=>capabilityDigest(checkerFiles.map(path=>({path,sha256:bytesSha256(readFileSync(path))})));
const code=checkerDigest();
// A path can remain unchanged while its source bytes change. The lifecycle
// binds the host's full input evidence; the native program still gets only args.
const cycleTask=label=>({...plan[label],input_versions:plan[label].manifest.inputs});
try{
 if(!process.env.SSS_PYTHON)throw Error('project_python_required');
 const inputHashes=label=>plan[label].manifest.inputs.map(i=>i.sha256).sort();
 if(capabilityDigest(inputHashes('validation'))===capabilityDigest(inputHashes('followup')))throw Error('paper_followup_bytes_must_differ');
 const result=await completeCapabilityCycle({owner:plan.owner,directory:plan.store,candidateSnapshot:candidate.snapshot,root:selected,
  expectedLatest:plan.expected_latest,validation:cycleTask('validation'),followup:cycleTask('followup'),
  validator:{id:'paper-bibtex-inventory-v1',sha256:capabilityDigest({code,specification:plan.validation.specification})},
  run:async(snapshot,input,mode,label)=>{
   const task=plan[label],directory=join(output,label);mkdirSync(directory,{mode:0o700});
   const manifest={...task.manifest,owner:plan.owner,task_id:task.id,workspace:task.workspace,registry_path:join(directory,'registry.json'),
    grant:{id:'paper-'+task.id,task_id:task.id,root:selected,snapshot_sha256:snapshot.digest,
     arguments_sha256:capabilityDigest(input),effects:['read'],mode,revoked:false}};
   save(manifest.registry_path,snapshot);save(join(directory,'manifest.json'),manifest);
   save(join(directory,'snapshot.json'),snapshot);save(join(directory,'args.json'),input);
   const execution=await runScriptCapability(join(directory,'manifest.json'),snapshot,input,{signal:controller.signal});
   save(join(directory,'trace.json'),execution);
   return {execution,directory,artifacts:[{name:'inventory.json',bytes:Buffer.from(JSON.stringify(execution.result??null))}]};
  },
  check:async(run,label)=>{
   if(code!==checkerDigest())throw Error('paper_validator_changed');
   save(join(run.directory,'specification.json'),plan[label].specification);
   const args=[checker,...['manifest','trace','specification'].flatMap(key=>['--'+key,join(run.directory,key+'.json')])];
   const {stdout}=await exec(process.env.SSS_PYTHON,args,{cwd:root,timeout:30000,maxBuffer:100000,signal:controller.signal});
   const verdict=JSON.parse(stdout);save(join(run.directory,'validation.json'),verdict);return verdict;
  },onPublished:publication=>save(join(output,'publication.json'),publication)});
 save(join(output,'result.json'),result);
}catch(error){save(join(output,'result.json'),{status:'failed',error:error.message,efficiency_conclusion:null});process.exitCode=1;}
