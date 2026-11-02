/** Scenario callbacks on the shared Store, Runtime and publication lifecycle. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {capabilityDigest,capabilityRef} from '../../../src/adapters/capability_contract.ts';
import {bytesSha256} from '../../../src/adapters/rsi_protocol.ts';
import {runScriptCapability} from '../../../src/adapters/script_capability_runtime.ts';
import {completeCapabilityCycle} from '../../../src/adapters/capability_cycle.ts';
const root=fileURLToPath(new URL('../../../',import.meta.url)),exec=promisify(execFile);
const read=p=>JSON.parse(readFileSync(p,'utf8')),save=(p,v)=>writeFileSync(p,JSON.stringify(v,null,2),{flag:'wx',mode:0o600});
const plan=read(process.argv[2]),candidate=read(plan.candidate),selected=capabilityRef(candidate.capability),out=resolve(plan.output);
mkdirSync(out,{mode:0o700});save(join(out,'plan.json'),plan);
const abort=new AbortController();process.on('SIGTERM',()=>abort.abort());process.on('SIGINT',()=>abort.abort());
const files=['scenarios/paper_proofreading/frontier/check.py','scenarios/paper_proofreading/frontier/oracle.py','src/adapters/paper_bibliography.py','src/adapters/capability_contract.py'];
const evaluatorDigest=()=>capabilityDigest(files.map(path=>({path,sha256:bytesSha256(readFileSync(join(root,path)))})));
const frozen=evaluatorDigest();
try{
 if(!process.env.SSS_PYTHON)throw Error('frontier_project_python_required');
 const task=label=>({...plan[label],input_versions:plan[label].manifest.inputs});
 const result=await completeCapabilityCycle({owner:plan.owner,directory:plan.store,candidateSnapshot:candidate.snapshot,root:selected,
  expectedLatest:plan.expected_latest,validation:task('validation'),followup:task('followup'),
  validator:{id:'frontier-literal-consistency-v1',sha256:capabilityDigest({code:frozen,specification:plan.validation.specification})},
  run:async(snapshot,input,mode,label)=>{
   const task=plan[label],directory=join(out,label);mkdirSync(directory,{mode:0o700});
   const manifest={...task.manifest,owner:plan.owner,task_id:task.id,workspace:task.workspace,registry_path:join(directory,'registry.json'),
    grant:{id:'frontier-'+task.id,task_id:task.id,snapshot_sha256:snapshot.digest,root:selected,arguments_sha256:capabilityDigest(input),effects:['read'],mode,revoked:false}};
   save(manifest.registry_path,snapshot);save(join(directory,'manifest.json'),manifest);save(join(directory,'snapshot.json'),snapshot);save(join(directory,'args.json'),input);
   const execution=await runScriptCapability(join(directory,'manifest.json'),snapshot,input,{signal:abort.signal});save(join(directory,'trace.json'),execution);
   return {execution,directory,artifacts:[{name:'report.json',bytes:Buffer.from(JSON.stringify(execution.result??null))}]};
  },check:async(run,label)=>{
   if(frozen!==evaluatorDigest())throw Error('frontier_evaluator_changed');
   save(join(run.directory,'specification.json'),plan[label].specification);
   const args=[join(root,files[0]),...['manifest','trace','specification'].flatMap(k=>['--'+k,join(run.directory,k+'.json')])];
   const {stdout}=await exec(process.env.SSS_PYTHON,args,{cwd:root,timeout:45000,maxBuffer:500000,signal:abort.signal});
   const verdict=JSON.parse(stdout);save(join(run.directory,'validation.json'),verdict);return verdict;
  },onPublished:value=>save(join(out,'publication.json'),value)});
 save(join(out,'result.json'),result);
}catch(error){save(join(out,'result.json'),{status:'failed',error:error.message,efficiency_conclusion:null});process.exitCode=1;}
