/** Host-side typed program jobs for member namespaces that cannot nest bwrap.
 * The request supplies an opaque account-local job, never executable source.
 * Reconstruct execution from the task's frozen certified library and current IO.
 */
import {readFileSync,lstatSync,realpathSync,mkdirSync,writeFileSync} from 'node:fs';
import {join,resolve,relative,isAbsolute,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {commandLayout} from './geneloop_shell.ts';
import {artifactInvocation,loadArtifactLibrary,registerArtifactContext,hash} from './artifact_motif_runtime.ts';
import {publicPptValidationTask} from './ppt_capability_broker.ts';
const root=fileURLToPath(new URL('../../',import.meta.url));
const inside=(base:string,path:string)=>{const rel=relative(base,path);return rel!==''&&!rel.startsWith('..')&&!isAbsolute(rel);};

export function preparePptProgramJob(options:any,value:any){
 const output=realpathSync(options.output);
 const map=(name:string)=>{
  if(typeof name!=='string')throw Error('program path missing');
  const path=resolve(name.startsWith('/app/.local/web/')?join(output,name.slice('/app/.local/web/'.length)):name);
  if(!inside(output,path)||realpathSync(path)!==path)throw Error('program path outside owning account');
  return path;
 };
 const json=(path:string)=>{
  const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size>4_000_000)throw Error('program job is not a bounded private file');
  return JSON.parse(readFileSync(path,'utf8'));
 };
 if(value?.operation==='workflow-certify'){
  if(Object.keys(value).sort().join(',')!=='file,operation')throw Error('invalid workflow certification request');
  const path=map(value.file),rel=relative(output,path).split('\\').join('/');
  if(!/^learning\/ppt-[a-f0-9]{64}\/workflows\/certification\/[a-f0-9]{64}\/plan\.json$/.test(rel))throw Error('workflow certification outside owning learner');
  const plan=json(path),request=json(map(join(dirname(dirname(dirname(dirname(path)))),'request.json')));
  if(plan.kind!=='ppt_native_workflow_certification'||plan.user!==request.user||plan.scope!==request.scope||
    'ppt-'+hash(Buffer.from(plan.user+'\0'+plan.scope))!==rel.split('/')[1])throw Error('workflow certification owner changed');
  return {argv:[options.node,'--experimental-strip-types',join(root,'scripts/certify-ppt-workflow.mjs'),path],
   env:{SSS_PYTHON:options.python,GENELOOP_ARTIFACT_RESOURCES:JSON.stringify(options.resources??{})}};
 }
 if(value?.operation==='capability'){
  if(Object.keys(value).sort().join(',')!=='file,operation')throw Error('invalid public validation request');
  const task=publicPptValidationTask(output,value.file,options.python);
  return {argv:[options.node,'--experimental-strip-types',join(root,'scripts/run-artifact-capability.mjs'),
   '--member-public',task.manifestPath,output],
   env:{SSS_PYTHON:options.python,GENELOOP_ARTIFACT_RESOURCES:JSON.stringify(options.resources??{})}};
 }
 if(value?.operation==='run'){
  if(Object.keys(value).sort().join(',')!=='file,operation,session'||!/^session-[a-f0-9-]{36}$/.test(value.session))throw Error('invalid program owner');
  const layout=commandLayout(output,value.session),jobPath=map(value.file);
  if(!inside(layout.temp,jobPath)||!/^artifact-job-[a-zA-Z0-9]+\/job\.json$/.test(relative(layout.temp,jobPath).split('\\').join('/')))throw Error('program job outside owning Session');
  const supplied=json(jobPath),taskId=supplied.taskId;
  if(!/^[a-f0-9]{32}$/.test(taskId))throw Error('program task missing');
  const task=join(output,'tasks',taskId),state=json(map(join(task,'task-state.json'))),effective=json(map(join(task,'effective-config.json')));
  if(state.task_id!==taskId||state.session_id!==value.session||state.status!=='running'||state.scene!=='ppt'||
    state.mode!=='execute'||state.rsi!==true||effective.rsi!==true||effective.provider_mode!=='real'||effective.session_id!==value.session||effective.user_id!==state.user_id||
    effective.scene_options?.allow_output!==true||map(effective.workspace)!==layout.work)throw Error('program task no longer authorized');
  const snapshot=json(map(join(task,'ppt-program-snapshot.json'))),libraryPath=map(snapshot.library);
  if(!inside(join(output,'learning'),libraryPath)||hash(readFileSync(libraryPath))!==snapshot.library_sha256)throw Error('program library changed');
  const library=loadArtifactLibrary(libraryPath);
  if(library.scene!=='ppt'||library.digest!==snapshot.library_digest||supplied.library?.digest!==library.digest)throw Error('program snapshot changed');
  const inputs=supplied.bound?.map((b:any)=>b.path);
  if(!Array.isArray(inputs)||inputs.some((p:any)=>typeof p!=='string'))throw Error('program explicit bindings missing');
  const auditPath=join(task,'artifact-motif-audit.jsonl');
  let job:any;
  try{
   // The scoped recipe interpreter repeats type, origin, source version,
   // fresh-output and execution-authority checks outside the member namespace.
   registerArtifactContext(value.session,{library,workspace:layout.work,allowOutput:true,cacheRoot:join(dirname(libraryPath),'page-cache'),resources:options.resources??{},auditPath,audit(){}});
   job=artifactInvocation(value.session,'geneloop-recipe '+JSON.stringify({id:supplied.program?.id,inputs,output:supplied.output}));
   if(job.bound.some((b:any,i:number)=>b.sha256!==supplied.bound[i].sha256))throw Error('program input changed in transport');
  }finally{registerArtifactContext(value.session,null);}
  const {audit,...body}=job;
  const directory=join(task,'program-jobs');mkdirSync(directory,{recursive:true,mode:0o700});
  const path=join(directory,randomUUID()+'.json');
  writeFileSync(path,JSON.stringify({...body,bound:body.bound.map((b:any)=>({...b,data:b.data.toString('base64')}))}),{mode:0o600,flag:'wx'});
  return {argv:[options.node,join(root,'scripts/run-artifact-motif.mjs'),path],env:{SSS_PYTHON:options.python}};
 }
 if(value?.operation==='certify'){
  if(Object.keys(value).sort().join(',')!=='file,operation')throw Error('invalid program certification request');
  const path=map(value.file),rel=relative(output,path).split('\\').join('/');
  if(/^learning\/ppt-[a-f0-9]{64}\/program-[a-f0-9]{24}\/candidate\/candidates\.json$/.test(rel)){
   const generation=dirname(dirname(path)),proof=json(map(join(generation,'learning-evidence.json')));
   if(!Array.isArray(proof.sources)||proof.sources.length!==2||new Set(proof.sources.map((row:any)=>row.task_id)).size!==2||
      !proof.sources[0].source_signature||proof.sources[0].source_signature===proof.sources[1].source_signature)
    throw Error('independent page evidence required');
   for(const row of proof.sources){
    if(!/^[a-f0-9]{32}$/.test(row.task_id))throw Error('page task missing');
    const task=join(output,'tasks',row.task_id),state=json(map(join(task,'task-state.json')));
    if(state.scene!=='ppt'||state.status!=='completed'||state.failure)throw Error('completed normal page required');
    const svg=map(row.svg),receipt=map(row.delivered?.receipt);
    if(!inside(join(output,'learning'),svg)||hash(readFileSync(svg))!==row.svg_sha256||
       !inside(task,receipt)||hash(readFileSync(receipt))!==row.delivered.receipt_sha256)
     throw Error('page source evidence changed');
    const delivery=json(receipt);
    if(delivery.mechanical_status!=='passed'||!delivery.page_receipts?.some((page:any)=>page.source_sha256===row.svg_sha256)||
       !delivery.artifacts?.some((file:any)=>file.sha256===row.delivered.deck_sha256&&file.path.endsWith('.pptx')))
     throw Error('page delivery receipt changed');
   }
   const rows=json(path);
   if(!Array.isArray(rows)||rows.length!==2||rows.some((row:any)=>!proof.sources.some((source:any)=>source.task_id===row.task_id)))
    throw Error('page candidate tasks changed');
   const mapped=rows.map((row:any)=>{
    const workspace=map(row.workspace);
    if(!inside(join(generation,'candidate'),workspace))throw Error('page candidate workspace changed');
    return {...row,workspace,candidates:row.candidates.map((program:any)=>{
     const witness=program.witness;
     const input_paths=Object.fromEntries(Object.entries(witness.input_paths).map(([i,name]:any)=>{
      const file=map(name);if(!inside(workspace,file)||hash(readFileSync(file))!==witness.input_sha256[i])throw Error('page input changed');
      return [i,file];
     }));
     const original=map(witness.original_output);
     if(!inside(workspace,original))throw Error('page reference changed');
     return {...program,witness:{...witness,input_paths,original_output:original}};
    })};
   });
   const hostInput=join(dirname(path),'host-candidates-'+randomUUID()+'.json');
   writeFileSync(hostInput,JSON.stringify(mapped),{mode:0o600,flag:'wx'});
   return {argv:[options.node,'--experimental-strip-types',join(root,'scripts/certify-artifact-motifs.mjs'),hostInput,dirname(path)],
    env:{SSS_PYTHON:options.python,GENELOOP_ARTIFACT_RESOURCES:JSON.stringify(options.resources??{})}};
  }
  if(!/^learning\/ppt-[a-f0-9]{64}\/program-[a-f0-9]{24}\/candidates\.json$/.test(rel))throw Error('program certification outside owning learner');
  const rows=json(path);
  if(!Array.isArray(rows)||rows.length!==2||new Set(rows.map((r:any)=>r.task_id)).size!==2)throw Error('independent program tasks required');
  const mapped=rows.map((row:any)=>{
   if(!/^[a-f0-9]{32}$/.test(row.task_id)||row.scene!=='ppt')throw Error('program certification task missing');
   const task=join(output,'tasks',row.task_id),state=json(map(join(task,'task-state.json'))),effective=json(map(join(task,'effective-config.json')));
   if(state.status!=='completed'||!['baseline','execute'].includes(state.mode)||state.failure||state.scene!=='ppt'||effective.provider_mode!=='real'||
     effective.task_id!==row.task_id||effective.user_id!==state.user_id)throw Error('settled ordinary program witness required');
   if(state.mode==='execute'){
    const receipt=json(map(join(task,'ppt-learning-delivery.json')));
    if(receipt.kind!=='ppt_single_delivery_v1'||receipt.schema_version!==1||receipt.mode!=='execute'||
      receipt.task_id!==row.task_id||receipt.session_id!==state.session_id||receipt.user!==state.user_id||
      receipt.status!=='completed'||row.source_task_mode!=='execute')throw Error('settled ordinary program witness requires owning single-task receipt');
   }
   const work=map(effective.workspace);
   if(work!==commandLayout(output,state.session_id).work||map(row.workspace)!==work)throw Error('program certification workspace changed');
   return {...row,workspace:work,candidates:row.candidates.map((p:any)=>{
    const witness=p.witness;
    const input_paths=Object.fromEntries(Object.entries(witness.input_paths).map(([i,name]:any)=>{
     const input=map(name);if(!inside(work,input)||hash(readFileSync(input))!==witness.input_sha256[i])throw Error('program certification input changed');
     return [i,input];
    }));
    const original=map(witness.original_output);
    if(!inside(join(work,'outputs/code'),original))throw Error('program historical output outside current workspace');
    return {...p,witness:{...witness,input_paths,original_output:original}};
   })};
  });
  const hostInput=join(dirname(path),'host-candidates-'+randomUUID()+'.json');
  writeFileSync(hostInput,JSON.stringify(mapped),{mode:0o600,flag:'wx'});
  return {argv:[options.node,'--experimental-strip-types',join(root,'scripts/certify-artifact-motifs.mjs'),hostInput,dirname(path)],
   env:{SSS_PYTHON:options.python,GENELOOP_ARTIFACT_RESOURCES:JSON.stringify(options.resources??{})}};
 }
 throw Error('unsupported program operation');
}
