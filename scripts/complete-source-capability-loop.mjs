/** Trusted pilot controller: validate, publish, then consume in a new task.
 * The model supplies a candidate only. This file and the independent checker
 * own validation/publication; no callback or checker path comes from a proposal.
 */
import {readFileSync,writeFileSync,mkdirSync,realpathSync,existsSync} from 'node:fs';
import {dirname,resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {capabilityDigest,capabilityRef} from '../src/adapters/capability_contract.ts';
import {completeCapabilityCycle} from '../src/adapters/capability_cycle.ts';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const save=(path,value)=>writeFileSync(path,JSON.stringify(value,null,2),{mode:0o600,flag:'wx'});
function command(program,args,stdoutFile,stderrFile){
 return new Promise((resolvePromise,reject)=>{
  const child=spawn(program,args,{cwd:root,env:process.env,stdio:['ignore','pipe','pipe']});
  let output='',error='';child.stdout.on('data',data=>output+=data);child.stderr.on('data',data=>error+=data);
  child.once('error',reject);child.once('close',code=>{
   writeFileSync(stdoutFile,output,{mode:0o600});writeFileSync(stderrFile,error,{mode:0o600});
   resolvePromise({code,output});
  });
 });
}
async function main(){
 const planPath=process.argv[2];if(!planPath)throw Error('usage: node complete-source-capability-loop.mjs PLAN.json');
 const plan=read(planPath),output=resolve(plan.output);
 const firstTask=read(plan.validation_manifest),nextTask=read(plan.followup_manifest);
 if(firstTask.task_id===nextTask.task_id||realpathSync(firstTask.workspace)===realpathSync(nextTask.workspace))throw Error('loop_followup_must_be_independent_task');
 if(existsSync(output))throw Error('loop_output_must_be_new');mkdirSync(output,{recursive:true,mode:0o700});
 const candidate=read(plan.candidate),candidateSnapshot=candidate.snapshot;
 const selected=capabilityRef(candidate.capability);
 const validatorPath=resolve(root,'scenarios/remotion_edit/structured/verify_capability_outputs.py');
 const checkerBytes=readFileSync(validatorPath);
 const python=process.env.SSS_PYTHON;if(!python)throw Error('project_python_required');
 save(resolve(output,'plan.json'),plan);
 async function run(snapshot,input,manifestPath,mode,label,specification){
  const directory=resolve(output,label);mkdirSync(directory,{mode:0o700});
  const manifest=read(manifestPath);
  if(manifest.owner!==plan.owner)throw Error('loop_owner_mismatch');
  manifest.grant={...manifest.grant,task_id:manifest.task_id,mode,root:selected,
   snapshot_sha256:snapshot.digest,arguments_sha256:capabilityDigest(input)};
  manifest.registry_path=resolve(directory,'registry.json');
  const snapshotPath=resolve(directory,'snapshot.json'),argsPath=resolve(directory,'args.json'),manifestFile=resolve(directory,'manifest.json');
  save(snapshotPath,snapshot);save(manifest.registry_path,snapshot);save(argsPath,input);save(manifestFile,manifest);
  const result=await command(process.execPath,['--experimental-strip-types','scripts/run-source-capability.mjs',
   '--manifest',manifestFile,'--snapshot',snapshotPath,'--args',argsPath],resolve(directory,'stdout.json'),resolve(directory,'stderr.log'));
  let execution;try{execution=JSON.parse(result.output);}catch{throw Error('loop_runtime_no_trace');}
  save(resolve(directory,'trace.json'),execution);
  if(result.code!==0||execution.status!=='succeeded')throw Error('loop_native_execution_failed');
  const scope=realpathSync(manifest.workspace),artifacts=[];
  const videos=specification.outputs.map((spec,index)=>{
   const path=spec.result_path??['videos',index];
   if(!Array.isArray(path)||!path.length||path.some(key=>!(typeof key==='string'||Number.isSafeInteger(key)&&key>=0)||['__proto__','prototype','constructor'].includes(key)))throw Error('loop_result_path_invalid');
   return path.reduce((value,key)=>value&&Object.hasOwn(value,key)?value[key]:undefined,execution.result);
  });
  for(const [index,video] of videos.entries()){
   if(!video||typeof video.video_path!=='string')throw Error('loop_video_result_missing');
   const path=realpathSync(video.video_path),part=relative(scope,path);
   if(!part||part.startsWith('..')||isAbsolute(part))throw Error('loop_artifact_outside_task');
   const bytes=readFileSync(path);if(hash(bytes)!==video.video_sha256)throw Error('loop_artifact_changed');
   artifacts.push({name:`video-${index}.mp4`,bytes});
  }
  if(!artifacts.length)throw Error('loop_missing_videos');
  return {execution,artifacts,directory,manifestFile};
 }
 async function check(run,specification){
  if(hash(readFileSync(validatorPath))!==hash(checkerBytes))throw Error('loop_validator_changed');
  const specificationPath=resolve(run.directory,'specification.json');save(specificationPath,specification);
  const result=await command(python,[validatorPath,'--manifest',run.manifestFile,'--trace',resolve(run.directory,'trace.json'),
   '--specification',specificationPath,'--output',resolve(run.directory,'qa')],resolve(run.directory,'validation.json'),resolve(run.directory,'validation-stderr.log'));
  if(result.code!==0)throw Error('loop_independent_validation_failed');
  return JSON.parse(result.output);
 }
 const validationSpec=read(plan.validation_specification),followupSpec=read(plan.followup_specification);
 try{
  const result=await completeCapabilityCycle({owner:plan.owner,directory:plan.store,candidateSnapshot,root:selected,
   expectedLatest:plan.expected_latest??null,
   validation:{id:firstTask.task_id,workspace:realpathSync(firstTask.workspace),input:read(plan.validation_args)},
   followup:{id:nextTask.task_id,workspace:realpathSync(nextTask.workspace),input:read(plan.followup_args)},
   validator:{id:'source-mechanical-v1',sha256:capabilityDigest({code:hash(checkerBytes),specification:validationSpec})},
   run:(snapshot,input,mode,label)=>run(snapshot,input,label==='validation'?plan.validation_manifest:plan.followup_manifest,
    mode,label,label==='validation'?validationSpec:followupSpec),
   check:(run,label)=>check(run,label==='validation'?validationSpec:followupSpec),
   onPublished:publication=>save(resolve(output,'publication.json'),publication)});
  save(resolve(output,'result.json'),result);
  process.stdout.write(JSON.stringify({status:'completed',output,publication_sha256:result.publication_sha256}));
 }catch(error){
  save(resolve(output,'result.json'),{status:'failed',error:error.message,efficiency_conclusion:null});throw error;
 }
}
main().catch(error=>{process.stderr.write(error.message+'\n');process.exitCode=1;});
