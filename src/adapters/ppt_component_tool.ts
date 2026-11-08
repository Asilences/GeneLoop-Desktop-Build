/** A discoverable typed entry point for account-local certified page programs. */
import {artifactInvocation} from './artifact_motif_runtime.ts';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {executeArtifactJob} from './artifact_motif_transport.ts';
import type {Scene} from './harless_settings.ts';
import {randomUUID} from 'node:crypto';
import {appendFileSync,existsSync,lstatSync,readdirSync,readFileSync,writeFileSync,renameSync,unlinkSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {pptWorkspacePath} from './ppt_delivery_pipeline.ts';
import {runPptPublicPage} from './ppt_capability_online.ts';
import {admitPptComponent} from './ppt_execution.ts';
import {pptWriteTools} from './ppt_write_tool.ts';
const pageFile=/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,127}\.svg$/u;
const pageJobs=new Set<string>();

export const pptComponentTool={name:'create_ppt_page',
 description:'用本任务已认证页面程序生成当前内容。先用read_ppt_design读取参数契约。parameters传内容对象，复杂内容可先写JSON文件再传parameters_file，两者选一。project传start_ppt返回的完整路径，page传SVG文件名。宿主安装页面并同步字号角色。修订时提供expected_page_sha256，随后finalize_ppt。',
 parameters:{type:'object',properties:{id:{type:'string'},parameters:{type:'object'},parameters_file:{type:'string',description:'本会话/work内的JSON文件，与parameters二选一。'},notes:{type:'string',description:'当前页的讲者备注和来源说明，宿主与页面一起保存。'},output:{type:'string'},project:{type:'string',description:'完整/work/projects/项目名。page与project一起使用。'},page:{type:'string',description:'项目SVG文件名，例如01_conclusion.svg'},expected_page_sha256:{type:'string',description:'参数修订时提供当前项目SVG的SHA256。缺省只允许新建页面。'}},required:['id'],additionalProperties:false}};

export function componentRequest(task:any,args:any){
 if(typeof args==='string'){
  try{args=JSON.parse(args);}catch(error:any){throw Error('component_arguments_json_invalid: '+error.message);}
 }
 if(!args||typeof args!=='object'||Array.isArray(args)||typeof args.id!=='string')throw Error('component_id_required');
 if((args.parameters===undefined)===(args.parameters_file===undefined))
  throw Error('component_parameters_choice_required: provide parameters object OR parameters_file JSON path');
 let parameters=args.parameters;
 if(args.parameters_file!==undefined){
  const path=pptWorkspacePath(task.workspace,args.parameters_file);
  if(!lstatSync(path).isFile()||lstatSync(path).size>1_000_000)throw Error('component_parameters_file_invalid');
  try{parameters=JSON.parse(readFileSync(path,'utf8'));}catch(error:any){throw Error('component_parameters_json_invalid: '+error.message);}
 }
 if(!parameters||typeof parameters!=='object'||Array.isArray(parameters))throw Error('component_parameters_object_required');
 if(args.notes!==undefined&&(typeof args.notes!=='string'||!args.notes.trim()||args.notes.length>100_000))throw Error('component_notes_invalid');
 let project=args.project;
 if(typeof project==='string'&&/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,79}$/u.test(project))project='/work/projects/'+project;
 if(project===undefined&&args.page!==undefined){
  const parent=join(task.workspace,'code/projects');
  const candidates=existsSync(parent)?readdirSync(parent).filter(name=>!lstatSync(join(parent,name)).isSymbolicLink()&&existsSync(join(parent,name,'svg_output'))):[];
  if(candidates.length===1)project='/work/projects/'+candidates[0];
 }
 return {...args,parameters,project,output:args.output??'/work/outputs/component-'+randomUUID()};
}

/** Size declarations bind generated pages to the project's existing visual contract. */
function declareComponentRoles(task:any,project:string|undefined,raw:Buffer){
 if(!project)return;
 const sizes=[...new Set([...raw.toString('utf8').matchAll(/font-size\s*(?:=\s*["']|:\s*)(\d+(?:\.\d+)?)(?:px|pt)?/g)].map(match=>Number(match[1])))];
 if(!sizes.length)return;
 const spec=pptWorkspacePath(task.workspace,project+'/spec_lock.md');
 const design=pptWorkspacePath(task.workspace,project+'/design_spec.md');
 const lock=readFileSync(spec,'utf8'),plan=readFileSync(design,'utf8');
 const section=/^##\s+typography\s*\r?\n([\s\S]*?)(?=^##\s|$(?![\s\S]))/im.exec(lock);
 if(!section)throw Error('component_project_typography_section_required');
 const declared=new Set([...section[1].matchAll(/^-\s+[a-zA-Z0-9_]+:\s*(\d+(?:\.\d+)?)\s*$/gm)].map(match=>Number(match[1])));
 const extra=sizes.filter(size=>!declared.has(size));
 if(sizes.some(size=>!Number.isFinite(size)||size<=0||size>200))throw Error('component_font_size_invalid');
 const missingDesign=sizes.filter(size=>!new RegExp('^-\\s+[a-zA-Z0-9_]+:\\s*'+String(size).replace('.','\\.')+'(?:\\s|$)','m').test(plan));
 if(!extra.length&&!missingDesign.length)return;
 const additions=extra.map(size=>'- component_'+String(size).replace('.','_')+': '+size).join('\n')+'\n';
 const updates=[
  {path:spec,changed:extra.length>0,text:lock.slice(0,section.index+section[0].length)+additions+lock.slice(section.index+section[0].length)},
  {path:design,changed:missingDesign.length>0,text:plan+'\n## Certified component typography\n'+missingDesign.map(size=>'- component_'+String(size).replace('.','_')+': '+size+' pt, inherited project font family').join('\n')+'\n'},
 ];
 // Each file is atomic. A retry also repairs a missing design declaration if
 // the process stopped after publishing the matching spec declaration.
 for(const update of updates){
  if(!update.changed)continue;
  const pending=update.path+'.'+randomUUID()+'.pending';
  try{writeFileSync(pending,update.text,{mode:0o600,flag:'wx'});renameSync(pending,update.path);}
  finally{if(existsSync(pending))unlinkSync(pending);}
 }
}

function pageTarget(task:any,args:any){
 if(args.project===undefined&&args.page===undefined&&args.expected_page_sha256===undefined)return null;
 if(typeof args.project!=='string'||!args.project.startsWith('/work/projects/')||typeof args.page!=='string'||!pageFile.test(args.page))
  throw Error('component_project_and_page_required: project=/work/projects/name and page=slide_01.svg must be supplied together');
 const folder=pptWorkspacePath(task.workspace,args.project+'/svg_output'),target=join(folder,args.page);
 if(args.expected_page_sha256!==undefined){
  if(!/^[a-f0-9]{64}$/.test(args.expected_page_sha256)||!existsSync(target)||
     createHash('sha256').update(readFileSync(pptWorkspacePath(task.workspace,args.project+'/svg_output/'+args.page))).digest('hex')!==args.expected_page_sha256)
   throw Error('component_page_version_changed');
 }else if(existsSync(target))throw Error('component_page_already_exists_use_explicit_revision');
 return target;
}

export function installComponentPage(task:any,args:any,result:any,callId:string){
 const target=pageTarget(task,args);
 if(!target)return null;
 const receipt=result.receipt??result;
 const proof=receipt.files?.find((file:any)=>file.path==='page.svg');
 if(!proof)throw Error('component_svg_receipt_missing');
 const raw=readFileSync(pptWorkspacePath(task.workspace,args.output+'/page.svg'));
 const sha256=createHash('sha256').update(raw).digest('hex');
 if(sha256!==proof.sha256)throw Error('component_svg_bytes_changed');
 declareComponentRoles(task,args.project,raw);
 if(args.expected_page_sha256===undefined)writeFileSync(target,raw,{mode:0o600,flag:'wx'});
 else{
  const pending=target+'.'+randomUUID()+'.pending';
  writeFileSync(pending,raw,{mode:0o600,flag:'wx'});
  try{pageTarget(task,args);renameSync(pending,target);}
  finally{if(existsSync(pending))unlinkSync(pending);}
 }
 const row={call_id:callId,arguments_sha256:digest(args.original_arguments),program_id:args.id,
  native_path:args.project+'/svg_output/'+args.page,sha256,mode:'native_component_install',previous_sha256:args.expected_page_sha256??null};
 appendFileSync(join(task.output,'ppt-native-pages.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});
 if(args.notes!==undefined){
  const name=args.page.replace(/\.svg$/,'.md');
  const notes=join(pptWorkspacePath(task.workspace,args.project+'/notes'),name);
  if(existsSync(notes))pptWorkspacePath(task.workspace,args.project+'/notes/'+name);
  const pending=notes+'.'+randomUUID()+'.pending';
  try{writeFileSync(pending,args.notes,{mode:0o600,flag:'wx'});renameSync(pending,notes);}
  finally{if(existsSync(pending))unlinkSync(pending);}
 }
 return row;
}

export function pptComponentScene(scene:Scene,mode:string,available:boolean,writingAvailable=false):Scene{
 if(scene.id!=='ppt'||scene.ppt_execution_strategy!=='ppt_master'||mode!=='execute'||!available&&!writingAvailable)return scene;
 const admitted=[...(available?[pptComponentTool.name]:[]),...(writingAvailable?pptWriteTools.map(tool=>tool.name):[])];
 return {...scene,allowed_tools:[...new Set([...scene.allowed_tools,...admitted])]};
}

/** Graph certificates still cover their original MCP surface. The new native
 * tool has its own frozen implementation, typed parameters and Artifact proof. */
export function pptComponentGraphTools(scene:Scene,tools:any[]){
 const native=[pptComponentTool,...pptWriteTools];
 const rows=tools.filter(row=>native.some(tool=>tool.name===row.name));
 if(!rows.length)return tools;
 if(scene.id!=='ppt'||rows.some(row=>!scene.allowed_tools.includes(row.name)||rows.filter(other=>other.name===row.name).length!==1||
  digest(row.parameters)!==digest(native.find(tool=>tool.name===row.name)!.parameters)))throw Error('component_native_schema_changed');
 return tools.filter(row=>!native.some(tool=>tool.name===row.name));
}

export function registerPptComponentTool(ctx:any,current:(session:string)=>any){
 ctx.tools.register({...pptComponentTool,
  output:{schema:{type:'object'},render:(_args:any,value:any)=>{
   const receipt=value.receipt??value;
   return [{type:'text',text:JSON.stringify({program_id:receipt.program_id,output_directory:receipt.output_directory,
    files:receipt.files,...(value.continued_by?{continued_by:value.continued_by,workflow_program_id:value.workflow_program_id,delivery:value.delivery,error_details:value.error_details,execution_status:value.execution_status,failure:value.failure}:{}),installed_page:value.installed_page,installed_page_sha256:value.installed_page_sha256,notes_saved:value.notes_saved,next_action:value.next_action})}];
  }},
  async execute(args:any,execution:any){
   const session=execution?.agent?.session?.id;
   const value=typeof session==='string'?current(session):null,task=value?.task;
   if(!value?.context||task?.status!=='running'||task.request.mode!=='execute'||task.selection.rsi!==true||task.scene_options.allow_output!==true)
    throw Error('component_task_not_authorized');
   const request=componentRequest(task,args);
   const audit=(row:any)=>value.context.audit({task_id:task.request.task_id,...row});
   const native=value.context.library?.programs.find((program:any)=>program.id===request.id&&program.component);
   if(native){
    try{request.parameters=admitPptComponent(native,request.parameters).parameters;}
    catch(error:any){audit({kind:'component_admission_rejected',program_id:args.id,reason:error.message});throw error;}
   }
   const attempt=digest({library:value.context.library.digest,id:request.id,parameters:request.parameters,project:request.project,page:request.page,
    expected_page_sha256:request.expected_page_sha256??null,requested_output:args.output??null});
   if(value.componentFailures?.has(attempt))throw Error('component_unchanged_failed_input: '+value.componentFailures.get(attempt));
   audit({kind:'component_attempted',program_id:args.id});
   let target:string|null=null,locked=false;
   try{
    target=pageTarget(task,request);
    if(target){if(pageJobs.has(target))throw Error('component_page_revision_running');pageJobs.add(target);locked=true;}
    const publicRoot=value.publicCapabilities?.roots.some((cap:any)=>cap.id===request.id);
    const result=publicRoot?await runPptPublicPage(value,request,execution):await executeArtifactJob(
     artifactInvocation(session,'geneloop-component '+JSON.stringify({id:request.id,parameters:request.parameters,output:request.output})),session,execution?.signal);
    const receipt=result.receipt??result;
    const delivered=publicRoot?{...request,id:receipt.program_id,output:receipt.output_directory}:request;
    const installed=installComponentPage(task,{...delivered,original_arguments:args},result,execution.callId);
    audit({kind:'component_executed',program_id:args.id,output_directory:request.output,receipt:result.receipt??result});
    if(installed)value.managePptSelection?.(request.project,request.id,request.expected_page_sha256?'revision':'new');
    return {...result,installed_page:installed?.native_path??null,installed_page_sha256:installed?.sha256??null,notes_saved:installed?request.notes!==undefined:false,
     next_action:installed?(request.notes!==undefined?'compose_remaining_pages_then_finalize_ppt':'write_page_notes_then_finalize_ppt'):'install_svg_and_write_page_notes_then_finalize_ppt'};
   }catch(error:any){
    if(!execution.signal?.aborted&&/component_design_preflight_failed|component_parameters_invalid|component_self_contained|component_viewbox_invalid|component_svg_root_required/.test(error.message)){
     value.componentFailures??=new Map();value.componentFailures.set(attempt,error.message);
    }
    audit({kind:'component_rejected',program_id:args.id,reason:error.message});
    throw error;
   }finally{if(locked&&target)pageJobs.delete(target);}
  }});
}
