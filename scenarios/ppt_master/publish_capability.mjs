/** PPT-specific callbacks on the public validate/publish/reload/followup cycle. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {capabilityDigest,capabilityRef} from '../../src/adapters/capability_contract.ts';
import {bytesSha256} from '../../src/adapters/rsi_protocol.ts';
import {runArtifactCapability} from '../../src/adapters/artifact_capability_runtime.ts';
import {completeCapabilityCycle} from '../../src/adapters/capability_cycle.ts';
const root=fileURLToPath(new URL('../../',import.meta.url)),exec=promisify(execFile);
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const save=(path,value)=>writeFileSync(path,JSON.stringify(value,null,2),{flag:'wx',mode:0o600});
const plan=read(process.argv[2]),candidate=read(plan.candidate),selected=capabilityRef(candidate.capability),output=plan.output;
mkdirSync(output,{mode:0o700});save(join(output,'plan.json'),plan);
const controller=new AbortController();process.on('SIGINT',()=>controller.abort());process.on('SIGTERM',()=>controller.abort());
const checker=join(root,'src/adapters/ppt_component_equivalence.py');
const checkerDigest=()=>capabilityDigest(['src/adapters/ppt_component_equivalence.py','src/adapters/ppt_design_preflight.py']
 .map(path=>({path,sha256:bytesSha256(readFileSync(join(root,path)))})));
const code=checkerDigest();
function fixed(ref){const bytes=readFileSync(ref.path);if(bytesSha256(bytes)!==ref.sha256)throw Error('ppt_capability_reference_changed');return bytes;}
try{
 if(!process.env.SSS_PYTHON)throw Error('project_python_required');
 const result=await completeCapabilityCycle({owner:plan.owner,directory:plan.store,candidateSnapshot:candidate.snapshot,root:selected,
  expectedLatest:plan.expected_latest,validation:plan.validation,followup:plan.followup,
  validator:{id:'ppt-visible-text-render-equivalence-v1',sha256:capabilityDigest({code,validation:plan.validation})},
  run:async(snapshot,input,mode,label)=>{
   const task=plan[label],directory=join(output,label);mkdirSync(directory,{mode:0o700});
   const registry=join(directory,'registry.json');save(registry,snapshot);
   const manifest={format:'artifact_capability_task_v1',owner:plan.owner,task_id:task.id,workspace:task.workspace,
    registry_path:registry,libraries:plan.libraries,inputs:task.input_versions,resources:plan.resources,
    evidence:[task.reference_svg,task.reference_png,...(task.sources??[])],
    grant:{id:'ppt-'+task.id,task_id:task.id,root:selected,snapshot_sha256:snapshot.digest,
     arguments_sha256:capabilityDigest(input),effects:['workspace_write'],mode,revoked:false}};
   const path=join(directory,'manifest.json');save(path,manifest);save(join(directory,'args.json'),input);
   const execution=await runArtifactCapability(path,snapshot,input,{signal:controller.signal});save(join(directory,'trace.json'),execution);
   const receipt=execution.result;
   if(execution.status!=='succeeded'||receipt?.kind!=='artifact_program_receipt')throw Error('ppt_capability_page_receipt_required');
   const actual=join(directory,'actual'),reference=join(directory,'reference');
   mkdirSync(actual,{mode:0o700});mkdirSync(reference,{mode:0o700});
   const artifacts=[];
   for(const name of ['page.svg','page.png']){
    const proof=receipt.files.find(file=>file.path===name);
    const bytes=readFileSync(join(task.workspace,'outputs/code',receipt.output_directory.slice('/work/outputs/'.length),name));
    if(!proof||bytesSha256(bytes)!==proof.sha256)throw Error('ppt_capability_output_changed');
    writeFileSync(join(actual,name),bytes,{flag:'wx',mode:0o600});artifacts.push({name,bytes});
    writeFileSync(join(reference,name),fixed(task[name==='page.svg'?'reference_svg':'reference_png']),{flag:'wx',mode:0o600});
   }
   return {execution,artifacts,directory,actual,reference};
  },
  check:async(run,label)=>{
   if(checkerDigest()!==code)throw Error('ppt_capability_validator_changed');
   const {stdout}=await exec(process.env.SSS_PYTHON,[checker,run.reference,run.actual],
    {cwd:root,timeout:30000,maxBuffer:100000,signal:controller.signal});
   const assessment=JSON.parse(stdout);save(join(run.directory,'quality.json'),assessment);
   const checks=['visible_text_exact','page_contract_equal'].map(id=>({id,status:assessment[id]?'passed':'failed',observation:'Independent comparison in quality.json'}));
   checks.push({id:'render_equivalence',status:assessment.passed?'passed':'failed',observation:'Rendered pixel MAE and canvas checked in quality.json'});
   const verdict={passed:assessment.passed,checks,scope:'PPT page visible text, canvas and rendered source equivalence',
    limitations:['Scientific accuracy, new-task suitability and cost benefit require separate review.']};
   save(join(run.directory,'validation.json'),verdict);return verdict;
  },onPublished:publication=>save(join(output,'publication.json'),publication)});
 save(join(output,'result.json'),result);
}catch(error){save(join(output,'result.json'),{status:'failed',error:error.message,efficiency_conclusion:null});process.exitCode=1;}
