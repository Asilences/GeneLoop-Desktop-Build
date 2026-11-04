/** PPT-only product wiring for the existing Artifact compiler/runtime.
 * The model selects applicability; a reused program is not a verified LLM skip.
 */
import {appendFileSync,existsSync,readFileSync,writeFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {createArtifactTrace} from './artifact_motif_trace.ts';
import {artifactProgramPath,loadArtifactLibrary,provideArtifactPrograms,registerArtifactContext} from './artifact_motif_runtime.ts';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
import {registerPptComponentTool} from './ppt_component_tool.ts';
import {registerPptDeliveryTool} from './ppt_delivery_pipeline.ts';

export function installPptProgramLearning(ctx:any,host:{current:(session:string)=>any;resolve:()=>any;resources:any;reused:(task:any,count:number)=>void;deliveryFontRules?:()=>any[]}){
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
   try{
    const selected=host.resolve();
    if(selected){
     const library=loadArtifactLibrary(selected.library);
     if(library.scene!=='ppt'||library.digest!==selected.library_digest)throw Error('PPT program library changed');
     value.context=provideArtifactPrograms({library,workspace:task.workspace,taskId:key,allowOutput:task.scene_options.allow_output===true,
      cacheRoot:join(dirname(selected.library),'page-cache'),
      resources:host.resources??{},audit,auditPath});
     registerArtifactContext(session,value.context);
     value.catalog='\n本任务可选的内部程序已通过不同输入的隔离执行认证；这不代表科研/视觉质量认证。符合当前需求时优先复用，内容和方法取舍仍由你负责。不适用则使用普通工具。\n'+
      '调用 python3 program_path，按 argv_order 传本次输入文件和一个尚不存在的 /work/outputs/新目录。无需重写、复制或 chmod 程序。执行后仍需正常检查、渲染和交付。\n'+
      '带 component 接口的页面直接调用 create_ppt_page，填id和parameters，可同时传project与page（例如slide_03.svg），宿主安装到svg_output，output由宿主默认分配。只填本次内容参数。准备备注后使用finalize_ppt，查看实际Office逐页PNG。按具体缺陷修复，相同依赖复用检查回执。上游整页手写限制由GeneLoop运行规则覆盖。\n'+
      JSON.stringify(library.programs.map((p:any)=>p.component?{id:p.id,
       metadata_path:artifactProgramPath(library,p).replace(/\.py$/,'.json'),
       component:{description:p.component.summary,parameters_schema:p.component.parameters_schema}}:({id:p.id,program_path:artifactProgramPath(library,p),interface:p.interface,inputs:p.inputs,
       argv_order:Array.from({length:p.argument_count},(_,i)=>i===p.output_argument_index?'new_output_directory':'input['+p.input_argument_indices.indexOf(i)+']'),
       outputs:p.certification.output_extensions})))+'\n';
     writeFileSync(join(task.output,'ppt-program-snapshot.json'),JSON.stringify(selected),{mode:0o600,flag:'wx'});
     audit({kind:'ppt_program_library_loaded',library_digest:library.digest,phase:selected.phase});
    }
   }catch(error:any){registerArtifactContext(session,null);value.context=null;value.catalog='';audit({kind:'ppt_program_fallback',reason:error.message});}
  }
  tasks.set(key,value);return value;
 }
 registerPptComponentTool(ctx,current);
 registerPptDeliveryTool(ctx,current,host.resources??{});
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
