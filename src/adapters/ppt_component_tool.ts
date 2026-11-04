/** A discoverable typed entry point for account-local certified page programs. */
import {artifactInvocation} from './artifact_motif_runtime.ts';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {executeArtifactJob} from './artifact_motif_transport.ts';
import type {Scene} from './harless_settings.ts';
import {randomUUID} from 'node:crypto';
import {appendFileSync,existsSync,readFileSync,writeFileSync,renameSync,unlinkSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {pptWorkspacePath} from './ppt_delivery_pipeline.ts';
const pageFile=/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,127}\.svg$/u;
const pageJobs=new Set<string>();

export const pptComponentTool={name:'create_ppt_page',
 description:'用本任务目录中的已认证页面程序生成当前内容。传入id和符合parameters_schema的内容参数，输出目录默认自动分配。project/page可安装页面。修订已安装页时调整内容参数，并传当前页面expected_page_sha256，版本一致才替换。随后使用finalize_ppt导出并查看实际Office渲染。',
 parameters:{type:'object',properties:{id:{type:'string'},parameters:{type:'object'},output:{type:'string'},project:{type:'string'},page:{type:'string',description:'项目SVG文件名，例如01_conclusion.svg'},expected_page_sha256:{type:'string',description:'参数修订时提供当前项目SVG的SHA256。缺省只允许新建页面。'}},required:['id','parameters'],additionalProperties:false}};

function pageTarget(task:any,args:any){
 if(args.project===undefined&&args.page===undefined&&args.expected_page_sha256===undefined)return null;
 if(typeof args.project!=='string'||!args.project.startsWith('/work/projects/')||typeof args.page!=='string'||!pageFile.test(args.page))
  throw Error('component_project_and_page_required');
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
 return row;
}

export function pptComponentScene(scene:Scene,mode:string,available:boolean):Scene{
 if(scene.id!=='ppt'||scene.ppt_execution_strategy!=='ppt_master'||mode!=='execute'||!available)return scene;
 return {...scene,allowed_tools:[...new Set([...scene.allowed_tools,pptComponentTool.name])]};
}

/** Graph certificates still cover their original MCP surface. The new native
 * tool has its own frozen implementation, typed parameters and Artifact proof. */
export function pptComponentGraphTools(scene:Scene,tools:any[]){
 const rows=tools.filter(row=>row.name===pptComponentTool.name);
 if(!rows.length)return tools;
 if(scene.id!=='ppt'||!scene.allowed_tools.includes(pptComponentTool.name)||rows.length!==1||
  digest(rows[0].parameters)!==digest(pptComponentTool.parameters))throw Error('component_native_schema_changed');
 return tools.filter(row=>row.name!==pptComponentTool.name);
}

export function registerPptComponentTool(ctx:any,current:(session:string)=>any){
 ctx.tools.register({...pptComponentTool,
  output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any,execution:any){
   const session=execution?.agent?.session?.id;
   const value=typeof session==='string'?current(session):null,task=value?.task;
   if(!value?.context||task?.status!=='running'||task.request.mode!=='execute'||task.selection.rsi!==true||task.scene_options.allow_output!==true)
    throw Error('component_task_not_authorized');
   const request={...args,output:args.output??'/work/outputs/component-'+randomUUID()};
   const audit=(row:any)=>value.context.audit({task_id:task.request.task_id,...row});
   audit({kind:'component_attempted',program_id:args.id});
   let target:string|null=null,locked=false;
   try{
    target=pageTarget(task,args);
    if(target){if(pageJobs.has(target))throw Error('component_page_revision_running');pageJobs.add(target);locked=true;}
    const job=artifactInvocation(session,'geneloop-component '+JSON.stringify({id:request.id,parameters:request.parameters,output:request.output}));
    const result=await executeArtifactJob(job,session,execution?.signal);
    const installed=installComponentPage(task,{...request,original_arguments:args},result,execution.callId);
    audit({kind:'component_executed',program_id:args.id,output_directory:request.output,receipt:result.receipt??result});
    return {...result,installed_page:installed?.native_path??null,installed_page_sha256:installed?.sha256??null,
     next_action:installed?'write_page_notes_then_finalize_ppt':'install_svg_and_write_page_notes_then_finalize_ppt'};
   }catch(error:any){
    audit({kind:'component_rejected',program_id:args.id,reason:error.message});
    throw error;
   }finally{if(locked&&target)pageJobs.delete(target);}
  }});
}
