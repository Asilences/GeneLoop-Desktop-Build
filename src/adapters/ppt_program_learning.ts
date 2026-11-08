/** PPT-only product wiring for the existing Artifact compiler/runtime.
 * The model selects applicability; a reused program is not a verified LLM skip.
 */
import {appendFileSync,existsSync,readFileSync,writeFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {createArtifactTrace} from './artifact_motif_trace.ts';
import {artifactProgramPath,loadArtifactLibrary,provideArtifactPrograms,registerArtifactContext} from './artifact_motif_runtime.ts';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
import {registerPptComponentTool} from './ppt_component_tool.ts';
import {registerPptDeliveryTool,pptWorkspacePath} from './ppt_delivery_pipeline.ts';
import {registerPptWriteTool} from './ppt_write_tool.ts';
import {pptPublicCapabilities,pptPublicCatalog} from './ppt_capability_online.ts';
import {registerPptDesignTools} from './ppt_design.ts';
import {registerPptWorkflowContinuation} from './ppt_workflow_runtime.ts';
import {pptWorkflowHost} from './ppt_workflow_host.ts';

export function pptWriteCatalog(programs:any[]){
 return '\n下列程序只覆盖各自已认证的mode和page_count，不是通用整稿生成器。revision只用于已有页并提供当前SHA；page_count=1每次只传一页。初稿仍用create_ppt_page写页后finalize_ppt。修订选定组件时直接调用create_ppt_page，宿主会自动续接适用程序，无需再调用execute_ppt_program。output是宿主临时目录，不要填写。失败只按返回的具体findings修复，不能无变化重试。\n'+JSON.stringify(programs.map((program:any)=>({id:program.id,mode:program.ir.mode,
  writer:program.ir.writer.tool,page_count:program.ir.writer.repeated_page_run?'multiple':1,
  page_fields:program.ir.writer.argument_names.filter((name:string)=>![program.ir.writer.resource_argument,'output'].includes(name)),
  required_page_fields:program.ir.writer.required_arguments.filter((name:string)=>name!==program.ir.writer.resource_argument),
  delivery_fields:program.ir.delivery.argument_names.filter((name:string)=>name!==program.ir.delivery.resource_argument)})))+'\n';
}

export function installPptProgramLearning(ctx:any,host:{current:(session:string)=>any;resolve:()=>any;resources:any;reused:(task:any,count:number)=>void;deliveryFontRules?:()=>any[];workflow?:()=>any}){
 const tasks=new Map<string,any>();
 function current(session:string):any{
  const task=host.current(session);
  if(!task||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||!['awaiting_confirmation','queued','running'].includes(task.status))return null;
  const key=task.request.task_id;
  if(tasks.has(key)){
   const saved=tasks.get(key);if(saved.context&&task.status==='running')registerArtifactContext(session,provideArtifactPrograms(saved.context));
   return saved;
  }
  const value:any={task,trace:createArtifactTrace(task.workspace,task.output),catalog:'',verified:new Set(),
   fontRules:task.request.mode==='execute'&&task.selection.rsi===true?(host.deliveryFontRules?.()??[]):[]};
  // Freeze even a cold result. A moving background pointer cannot alter an
  // already admitted task, and Baseline cannot consume the learned library.
  if(task.request.mode==='execute'&&task.selection.rsi===true){
   const auditPath=join(task.output,'artifact-motif-audit.jsonl');
   const audit=(row:any)=>appendFileSync(auditPath,JSON.stringify({...row,task_id:key})+'\n',{mode:0o600});
   value.workflow=host.workflow?.()??null;
   value.workflowValid=()=>{
    const selected=host.workflow?.();
    return !!selected&&selected.environment_sha256===value.workflow.environment_sha256&&
      value.workflow.programs.every((program:any)=>selected.programs.some((next:any)=>next.id===program.id&&next.status==='certified'));
   };
   value.workflowAudit=audit;
   try{
    const selected=host.resolve();
    if(selected){
     const library=loadArtifactLibrary(selected.library);
     if(library.scene!=='ppt'||library.digest!==selected.library_digest)throw Error('PPT program library changed');
     value.context=provideArtifactPrograms({library,workspace:task.workspace,taskId:key,allowOutput:task.scene_options.allow_output===true,
      cacheRoot:join(dirname(selected.library),'page-cache'),
      resources:host.resources??{},audit,auditPath});
     registerArtifactContext(session,value.context);
     value.catalog='\n本任务的认证程序如下。规划时先按结构说明判断适用页，匹配的页面优先复用，避免重写相同版式。read_ppt_design读取页面参数；使用create_ppt_page安装并写备注，随后共同finalize_ppt交付。若有写入程序，严格遵守其mode和page_count；宿主自动续接适用的修订。不适用时在design_spec.md简短记录具体原因，继续普通制作。其他程序按argv_order执行。\n'+
      JSON.stringify(library.programs.map((p:any)=>p.component?{id:p.id,
       component:{description:(p.component.description??p.component.summary??'').slice(0,1200),summary:p.component.summary,contract_tool:'read_ppt_design',fields:Object.keys(p.component.parameters_schema.properties??{})}}:({id:p.id,program_path:artifactProgramPath(library,p),interface:p.interface,inputs:p.inputs,
       argv_order:Array.from({length:p.argument_count},(_,i)=>i===p.output_argument_index?'new_output_directory':'input['+p.input_argument_indices.indexOf(i)+']'),
       outputs:p.certification.output_extensions})))+'\n';
     writeFileSync(join(task.output,'ppt-program-snapshot.json'),JSON.stringify(selected),{mode:0o600,flag:'wx'});
     audit({kind:'ppt_program_library_loaded',library_digest:library.digest,phase:selected.phase});
     value.selection=selected;
     try{
      value.publicCapabilities=pptPublicCapabilities(selected);
      if(value.publicCapabilities?.roots.length){
       value.catalog+='\n公共RSI已独立发布的页面能力，通过同一create_ppt_page传入id与parameters调用。parameters_from_program沿用前面对应程序的参数schema。\n'+
        JSON.stringify(pptPublicCatalog(value.publicCapabilities,library))+'\n';
       audit({kind:'ppt_public_capability_loaded',snapshot_sha256:value.publicCapabilities.snapshot.digest,
        roots:value.publicCapabilities.roots.map((cap:any)=>cap.id)});
      }
     }catch(error:any){value.publicCapabilities=null;audit({kind:'ppt_public_capability_fallback',reason:error.message});}
    }
   }catch(error:any){registerArtifactContext(session,null);value.context=null;value.catalog='';audit({kind:'ppt_program_fallback',reason:error.message});}
  }
  const writing=value.workflow?.programs.filter((program:any)=>program.ir.kind==='observed_page_write_delivery')??[];
  if(writing.length)value.catalog+=pptWriteCatalog(writing);
  tasks.set(key,value);return value;
 }
 registerPptDesignTools(ctx,current,host.resources??{});
 registerPptComponentTool(ctx,current);
 registerPptDeliveryTool(ctx,current,host.resources??{});
 registerPptWriteTool(ctx,current,pptWorkspacePath,host.resources??{});
 registerPptWorkflowContinuation(ctx,current,pptWorkflowHost);
 ctx.on('agent/created',({agent}:any)=>{
  agent.ctx.systemPrompt.variable('ppt_program_catalog',()=>current(agent.session.id)?.catalog??'');
  agent.ctx.systemPrompt.section({name:'ppt-program-catalog',order:10230,text:'{{ppt_program_catalog}}'});
  agent.ctx.tools.guard((execution:any)=>{
   const value=current(agent.session.id);if(!value||value.task.status!=='running')return;
   if(execution.name==='bash')value.trace.before(execution);
   if(value.catalog&&!value.noticeSent&&!value.seenInModel){
    value.noticeSent=true;
    agent.inject(createUserMessage({source:{kind:'plugin',plugin:'ppt-program-library',form:'notice',summary:'本任务可用的内部程序'},content:[{type:'text',text:value.catalog}]}));
   }
  });
  agent.ctx.on('tools/result',(execution:any,result:any)=>{
   const value=current(agent.session.id);if(!value)return;
   if(execution.name==='bash')value.trace.after(execution,result);
   const path=join(value.task.output,'artifact-motif-audit.jsonl');
   if(!value.context||!existsSync(path))return;
   let count=0;
   for(const line of readFileSync(path,'utf8').split('\n').filter(Boolean)){
    const row=JSON.parse(line),key=JSON.stringify(row);
    if(row.kind==='artifact_program_verified'&&value.context.library.programs.some((p:any)=>p.id===row.program_id)&&!value.verified.has(key)){
     value.verified.add(key);count++;
    }
   }
   if(count)host.reused(value.task,count);
  });
 },{global:true});
 ctx.on('llm/stream',(options:any,next:any)=>{
  const value=current(options.sessionId);
  if(value?.catalog){
   const text=[options.system,options.systemPrompt,...(options.messages??[]).flatMap((m:any)=>(m.content??[]).filter((p:any)=>p.type==='text').map((p:any)=>p.text))].filter(t=>typeof t==='string').join('\n');
   value.seenInModel=text.includes(value.catalog);
   if(value.seenInModel&&!value.catalogRecorded){
    value.catalogRecorded=true;
    value.context?.audit({kind:'ppt_program_catalog_seen_in_model',task_id:value.task.request.task_id,library_digest:value.context.library.digest});
   }
  }
  return next();
 },{global:true});
 ctx.on('agent/status',({agent,status}:any)=>{if(status==='idle'){
  registerArtifactContext(agent.session.id,null);
  const task=host.current(agent.session.id);
  if(task&&['completed','failed','cancelled','budget_exhausted'].includes(task.status))tasks.delete(task.request.task_id);
 }},{global:true});
}
