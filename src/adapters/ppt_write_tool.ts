/** Server binding of the shared learned-write interpreter. Not a learned recipe. */
import {appendFileSync,existsSync,mkdirSync,readFileSync,readdirSync,renameSync,writeFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';
import {admitPptComponent} from './ppt_execution.ts';
import {executePptWriteProgram,pptWriteArguments} from './ppt_write_runtime.ts';
import {validatePptWorkflowLibrary} from './ppt_workflow_runtime.ts';
import {pptWorkflowHost} from './ppt_workflow_host.ts';
import {componentRequest} from './ppt_component_tool.ts';
import {pptDeliveryView} from './ppt_delivery_pipeline.ts';

export const pptWriteProgramTool={name:'execute_ppt_program',
 description:'执行本任务从真实轨迹学得并认证的有限制作/修订程序，严格按程序卡mode和page_count。revision不是初稿生成器；page_count=1只传一页，提供当前页SHA。选定组件的create_ppt_page修订由宿主自动续接，勿重复执行。project用start_ppt返回路径，output由宿主分配。失败返回具体缺陷和已完成进度；仅明确resume才能续接，不重做成功页。',
 parameters:{type:'object',properties:{id:{type:'string'},project:{type:'string'},pages:{type:'array',items:{type:'object'}},
  delivery:{type:'object'},resume:{type:'boolean'}},required:['id','project','pages'],additionalProperties:false}};
export const pptWriteReleaseTool={name:'release_ppt_program',
 description:'仅在受管制作有客观失败或用户明确要求但组件不能表达的内容时退出受管路径。保留当前成品和费用。不得只因想尝试另一版样式而重做。unsupported_requirement需逐字引用当前用户要求。',
 parameters:{type:'object',properties:{project:{type:'string'},reason:{type:'string',enum:['delivery_failure','unsupported_requirement']},
  requirement_quote:{type:'string'}},required:['project','reason'],additionalProperties:false}};
export const pptWriteTools=[pptWriteProgramTool,pptWriteReleaseTool];
const pageName=/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,127}\.svg$/u;
const hash=(path:string)=>existsSync(path)?createHash('sha256').update(readFileSync(path)).digest('hex'):null;
const activeProjects=new Set<string>();

export function registerPptWriteTool(ctx:any,current:(session:string)=>any,paths:any,resources:any={}){
 const owning=(execution:any)=>{
  const value=current(execution.agent?.session?.id),task=value?.task;
  if(task?.status!=='running'||task.request.mode!=='execute'||task.selection?.rsi!==true||task.scene_options?.allow_output!==true)
   throw Error('ppt_write_task_not_authorized');
  value.writeInternalCalls??=new Set();value.writePreviewOwned??=new Set();value.writeLeases??=new Map();value.writeReleased??=new Set();
  const folder=join(dirname(dirname(task.output)),'ppt-managed-projects');
  mkdirSync(folder,{recursive:true,mode:0o700});
  const record=join(folder,digest({workspace:task.workspace})+'.json');
  if(existsSync(record))value.writeLeases=new Map(Object.entries(JSON.parse(readFileSync(record,'utf8'))));
  value.setPptWriteLease=(project:string,lease:any)=>{
   const saved=existsSync(record)?JSON.parse(readFileSync(record,'utf8')):{};
   if(lease===null){delete saved[project];value.writeLeases.delete(project);}else{saved[project]=lease;value.writeLeases.set(project,lease);}
   const pending=record+'.'+randomUUID()+'.pending';writeFileSync(pending,JSON.stringify(saved),{mode:0o600,flag:'wx'});renameSync(pending,record);
  };
  value.managePptSelection=(project:string,id:string,mode:string='new')=>{
   if(project&&value.context?.library.programs.some((p:any)=>p.id===id&&p.component)&&
     value.workflow?.programs.some((p:any)=>p.ir.kind==='observed_page_write_delivery'&&p.ir.writer.tool==='create_ppt_page'&&p.ir.mode===mode))
    value.setPptWriteLease(project,{program_id:id});
  };
  return value;
 };
 const version=(task:any,operation:any)=>{
  const {project,page}=operation.arguments;
  if(typeof page!=='string'||!pageName.test(page))throw Error('ppt_write_page_path_invalid');
  const target=join(paths(task.workspace,project+'/svg_output'),page);
  return existsSync(target)?hash(paths(task.workspace,project+'/svg_output/'+page)):null;
 };
 const continuedImages=new Map<string,any[]>();
 const matchingWrite=(value:any,execution:any)=>{
  if(value?.task?.status!=='running'||value.task.request.mode!=='execute'||value.task.selection?.rsi!==true||
    value.task.scene_options?.allow_output!==true||execution.name!=='create_ppt_page'||value.writeInternalCalls?.has(execution.callId))return null;
  const args=execution.arguments,mode=args?.expected_page_sha256?'revision':'new';
  if(typeof args?.notes!=='string'||!args.notes.trim())return null;
  if(value.writeReleased?.has(args?.project)||!value.context?.library.programs.some((p:any)=>p.id===args?.id&&p.component))return null;
  // Historical generation traces revise the first page before the deck exists.
  // Keep that ordinary construction path; automatic delivery starts from a draft.
  if(mode==='revision'){
   try{paths(value.task.workspace,args.project+'/delivery.json');}catch{return null;}
  }
  return value.workflow?.programs.find((p:any)=>p.status==='certified'&&p.ir.kind==='observed_page_write_delivery'&&p.ir.writer.tool==='create_ppt_page'&&p.ir.mode===mode)??null;
 };
 ctx.on?.('tools/execute',async(execution:any,next:any)=>{
  const value=current(execution.agent?.session?.id),program=matchingWrite(value,execution);
  if(!program)return next();
  owning(execution);
  const request=componentRequest(value.task,execution.arguments),page:any={id:request.id,page:request.page,parameters:request.parameters,notes:request.notes};
  if(request.expected_page_sha256!==undefined)page.expected_page_sha256=request.expected_page_sha256;
  value.workflowAudit?.({kind:'ppt_component_host_continued',program_id:program.id,parent_call_id:execution.callId});
  const result=await ctx.tools.execute({name:'execute_ppt_program',arguments:{id:program.id,project:request.project,pages:[page]},
   callId:execution.callId+':learned-write',rootCallId:execution.rootCallId,parent:execution.token,agent:execution.agent,signal:execution.signal});
  if(result.isError)return result;
  const receipt=result.value,images=result.content.filter((block:any)=>block.type==='image');
  if(images.length)continuedImages.set(execution.callId,images);
  return {isError:false,value:{installed_page:request.project+'/svg_output/'+request.page,
   installed_page_sha256:receipt.current_page_versions?.[request.page]??null,notes_saved:!!receipt.current_page_versions?.[request.page],
   continued_by:'execute_ppt_program',workflow_program_id:program.id,
   delivery:JSON.parse(JSON.stringify(pptDeliveryView(receipt.delivery??(receipt.error_details?.mechanical_status?receipt.error_details:{})))),
   error_details:receipt.error_details??null,
   execution_status:receipt.status,failure:receipt.failure??null,
   next_action:receipt.status==='completed'?'review_returned_images_then_present':'repair_specific_recorded_execution_failure'}};
 },{global:true});
 ctx.on?.('tools/post-execute',async(execution:any,result:any,next:any)=>{
  const decision=await next(),images=continuedImages.get(execution.callId);continuedImages.delete(execution.callId);
  return images&&decision.kind==='accept'?{...decision,content:[...(decision.content??result.content),...images]}:decision;
 },{global:true});
 ctx.tools.guard((execution:any)=>{
  const value=current(execution.agent?.session?.id);
  if(!value||value.task.request.mode!=='execute'||value.task.selection?.rsi!==true)return;
  owning(execution);
  if(value.writeInternalCalls.has(execution.callId))return;
  const programs=value.workflow?.programs.filter((p:any)=>p.ir.kind==='observed_page_write_delivery')??[];
  if(!programs.length)return;
  if(matchingWrite(value,execution)){
   if(typeof ctx.on==='function')return; // The host directly continues; no rejected round-trip.
   return '本任务已有认证的连续制作程序，请将当前页参数传给execute_ppt_program。';
  }
  if(!value.writeLeases.size)return;
  const project=execution.arguments?.project,path=execution.arguments?.file_path??execution.arguments?.path;
  const managed=value.writeLeases.has(project)||typeof path==='string'&&[...value.writeLeases.keys()].some((p:any)=>path.startsWith(p+'/'));
  if(execution.name==='bash'||managed&&['write','edit','compose_ppt_page','create_ppt_page'].includes(execution.name))
   return '已选组件的页面由执行层维护。请通过execute_ppt_program修订当前页；只有客观失败或明确不支持的用户要求才使用release_ppt_program退出，保留其他页。';
 });
 ctx.tools.register({...pptWriteProgramTool,output:{schema:{type:'object'},render:(_args:any,result:any)=>[
  {type:'text',text:JSON.stringify({status:result.status,execution_key:result.key,completed_pages:result.completed?.length,
   failure:result.failure,error_details:result.error_details,current_versions:result.current_versions,current_page_versions:result.current_page_versions,delivery:result.delivery,
   next_action:result.status==='completed'?(result.preview_complete?'review_returned_images_then_present':'read_remaining_review_pages_then_present'):'repair_explicit_failure_using_current_versions'})},...(result.images??[])]},
  async execute(args:any,execution:any){
   const value=owning(execution),task=value.task,library=value.workflow;
   validatePptWorkflowLibrary(library,pptWorkflowHost(execution));
   const program=library.programs.find((p:any)=>p.id===args.id&&p.ir.kind==='observed_page_write_delivery');
   if(!program)throw Error('ppt_write_program_not_available');
   const frozen=digest(library),project=args.project;
   const folder=join(task.output,'ppt-write-executions');mkdirSync(folder,{recursive:true,mode:0o700});
   const audit=(row:any)=>value.workflowAudit?.({...row,task_id:task.request.task_id});
   const save=(key:string,row:any)=>{
    const target=join(folder,key+'.json'),pending=target+'.'+randomUUID()+'.pending';
    writeFileSync(pending,JSON.stringify(row),{mode:0o600,flag:'wx'});renameSync(pending,target);
   };
   const allVersions=()=>{
    const dir=paths(task.workspace,project+'/svg_output');
    return Object.fromEntries(readdirSync(dir).filter((name:string)=>pageName.test(name)).map((name:string)=>[name,hash(paths(task.workspace,project+'/svg_output/'+name))]));
   };
   const before=allVersions(),targetPages=new Set(pptWriteArguments(program,args).writes.map((row:any)=>row.arguments.page));
   const notesFolder=paths(task.workspace,project+'/notes');
   const beforeNotes=Object.fromEntries(readdirSync(notesFolder).filter((name:string)=>/\.md$/.test(name)).map((name:string)=>[name,
    hash(paths(task.workspace,project+'/notes/'+name))]));
   const check=()=>{
    execution.signal?.throwIfAborted();
    if(current(execution.agent.session.id)!==value||task.status!=='running'||task.scene_options?.allow_output!==true||task.selection?.rsi!==true||
      digest(value.workflow)!==frozen||value.workflowValid?.()===false)throw Error('ppt_write_authority_changed');
    validatePptWorkflowLibrary(library,pptWorkflowHost(execution));
   };
   const projectKey=task.workspace+'\0'+project;
   if(activeProjects.has(projectKey))throw Error('ppt_write_project_execution_running');
   activeProjects.add(projectKey);
   try{
   const result=await executePptWriteProgram(program,args,execution,{check,audit,save,
    prepareInput:(_program:any,input:any)=>{
     if(program.ir.writer.tool!=='create_ppt_page')return input;
     // Bind approved parameter files to values before the journal key is made.
     // The subsequent native write consumes these values, not a mutable file.
     return {...input,pages:input.pages.map((item:any)=>{
      // Scratch paths are execution resources, not learned scientific bindings.
      // Native writes allocate a fresh child per attempt, including recovery.
      const {output,...rest}=item;
      if(output!==undefined)audit({kind:'ppt_write_scratch_output_host_owned',requested_output_sha256:digest(output)});
      if(rest.parameters_file===undefined)return rest;
      const bound=componentRequest(task,{...rest,project:input.project});
      const {parameters_file,...payload}=rest;
      audit({kind:'ppt_write_parameter_file_bound',parameters_sha256:digest(bound.parameters)});
      return {...payload,parameters:bound.parameters};
     })};
    },
    load:(key:string)=>existsSync(join(folder,key+'.json'))?JSON.parse(readFileSync(join(folder,key+'.json'),'utf8')):null,
    dispatch:async(call:any)=>{
     const owns=!!program.ir.preview&&call.name===program.ir.delivery.tool;
     if(owns)value.writePreviewOwned.add(call.callId);
     try{return await ctx.tools.execute(call);}finally{if(owns)value.writePreviewOwned.delete(call.callId);}
    },internal:(id:string,active:boolean)=>active?value.writeInternalCalls.add(id):value.writeInternalCalls.delete(id),
    lease:()=>{value.writeReleased.delete(project);value.setPptWriteLease(project,{program_id:program.id});},
    version:(operation:any)=>version(task,operation),
    reconcile:async(operations:any[],completed:any[],receipt:any)=>completed.map(saved=>{
     const operation=operations[saved.index],current=version(task,operation);
     if(current===saved.version)return saved;
     const source=project+'/svg_output/'+operation.arguments.page;
     const proof=receipt.page_receipts?.find((page:any)=>page.source===source&&page.source_initial_sha256===saved.version&&page.source_sha256===current);
     if(!proof)throw Error('ppt_write_delivery_page_version_unproven');
     return {...saved,version:current,initial_version:saved.initial_version??saved.version};
    }),
    deliveryCurrent:async(receipt:any)=>{
     try{
      const {deliveryDependencies,cachedPptDelivery}=await import('./ppt_delivery_pipeline.ts');
      return digest(receipt.dependencies)===digest(deliveryDependencies(task.workspace,project,receipt.manifest,resources))&&!!cachedPptDelivery(task,receipt,receipt.key);
     }catch{return false;}
    },
    admit:async(operations:any[],completed:any[])=>{
     if(Object.hasOwn(beforeNotes,'total.md')){
      value.setPptWriteLease(project,{program_id:program.id,failure:'ppt_write_legacy_total_notes_requires_explicit_migration'});
      throw Error('ppt_write_legacy_total_notes_requires_explicit_migration');
     }
     const profile=pptWorkflowHost(execution);
     for(let index=0;index<operations.length;index++){
      const operation=operations[index],definition=execution.agent.ctx.tools.get(operation.tool,execution.agent);
      if(!definition||digest(definition.parameters)!==profile.contracts[operation.tool].schema_sha256)throw Error('ppt_write_item_schema_changed');
      const errors=validateJsonSchemaValue(definition.parameters,operation.arguments);
      if(errors.length)throw Error('ppt_write_item_schema_invalid: '+JSON.stringify(errors));
      if(completed.some((row:any)=>row.index===index))continue;
      const actual=version(task,operation),expected=operation.arguments.expected_page_sha256;
      if(actual?actual!==expected:expected!==undefined)throw Error('ppt_write_page_version_changed');
      if(operation.tool==='create_ppt_page'){
       const component=value.context?.library.programs.find((p:any)=>p.id===operation.arguments.id&&p.component);
       if(!component)throw Error('ppt_write_component_not_available');
       try{admitPptComponent(component,operation.arguments.parameters);}
       catch(error:any){value.setPptWriteLease(project,{program_id:program.id,failure:error.message});throw error;}
       if(typeof operation.arguments.notes!=='string'||!operation.arguments.notes.trim())throw Error('ppt_write_page_notes_required');
      }
     }
    },
    verifyUnchanged:()=>{
     const after=allVersions();
     for(const [name,sha] of Object.entries(before))if(!targetPages.has(name)&&after[name]!==sha)throw Error('ppt_write_other_page_changed');
     for(const [name,sha] of Object.entries(beforeNotes))if(!targetPages.has(name.replace(/\.md$/,'.svg'))&&
       hash(paths(task.workspace,project+'/notes/'+name))!==sha)throw Error('ppt_write_other_notes_changed');
    }});
   if(result.status==='failed')value.setPptWriteLease(project,{program_id:program.id,failure:result.failure});
   return {...result,current_page_versions:allVersions()};
   }finally{activeProjects.delete(projectKey);}
  }});
 ctx.tools.register({...pptWriteReleaseTool,output:{schema:{type:'object'},render:(_args:any,result:any)=>[{type:'text',text:JSON.stringify(result)}]},
  async execute(args:any,execution:any){
   const value=owning(execution),lease=value.writeLeases.get(args.project);
   if(!lease)throw Error('ppt_write_managed_project_not_found');
   if(args.reason==='delivery_failure'){
    if(!lease.failure)throw Error('ppt_write_no_recorded_failure');
   }else{
    const quote=args.requirement_quote;
    if(typeof quote!=='string'||quote.length<12||!JSON.stringify(value.task.request.content??value.task.request.prompt??[]).includes(quote))throw Error('ppt_write_user_requirement_quote_required');
   }
   value.workflowAudit?.({kind:'ppt_write_managed_release',project:args.project,reason:args.reason,
    requirement_quote_sha256:args.requirement_quote?digest(args.requirement_quote):null,preserved_current_pages:true});
   value.setPptWriteLease(args.project,null);
   value.writeReleased.add(args.project);
   return {status:'released',preserved_current_pages:true,next_action:'repair_only_unsupported_part_and_finalize'};
  }});
}
