/** Adapter conformance runner. Explicit synthetic tasks, no model or user data. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {completeCapabilityCycle} from '../../../src/adapters/capability_cycle.ts';
import {capabilityRef} from '../../../src/adapters/capability_contract.ts';
import {execute,checkResult,validator} from './runtime.mjs';
const plan=JSON.parse(readFileSync(process.argv[2],'utf8'));
const candidate=JSON.parse(readFileSync(plan.candidate,'utf8')),output=resolve(plan.output);
mkdirSync(output,{mode:0o700});
const save=(path,value)=>writeFileSync(path,JSON.stringify(value,null,2),{mode:0o600,flag:'wx'});
try{
 const result=await completeCapabilityCycle({owner:plan.owner,directory:plan.store,
  candidateSnapshot:candidate.snapshot,root:capabilityRef(candidate.capability),expectedLatest:plan.expected_latest,
  validation:plan.validation,followup:plan.followup,validator,
  run:async(snapshot,input,mode,label)=>{
   const run=await execute(snapshot,capabilityRef(candidate.capability),input,{mode,taskId:plan[label].id});
   const directory=join(output,label);mkdirSync(directory,{mode:0o700});
   save(join(directory,'trace.json'),run.execution);save(join(directory,'args.json'),input);save(join(directory,'snapshot.json'),snapshot);
   return run;
  },
  check:async(run,label)=>{const verdict=await checkResult(plan[label].input,run);save(join(output,label,'validation.json'),verdict);return verdict;},
  onPublished:publication=>save(join(output,'publication.json'),publication)});
 save(join(output,'result.json'),{...result,diagnostic_only:true});
}catch(error){save(join(output,'result.json'),{status:'failed',error:error.message,diagnostic_only:true});process.exitCode=1;}
