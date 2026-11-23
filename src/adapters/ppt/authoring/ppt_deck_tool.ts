/** Web host adapter; the same lazy engine is callable by a desktop native host. */
import {existsSync,lstatSync,mkdirSync,readFileSync,realpathSync,appendFileSync,renameSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {pptDeckBuildTool,pptDeckPatchTool} from './ppt_deck_contract.ts';
import {buildPptDeck,patchPptDeck} from './ppt_deck_engine.ts';
import {pptThemes} from './ppt_design.ts';
import {digest} from '../../../motif_core/runtime/online_skill_runtime.mjs';
import {officeEvidenceVersion} from '../../geneloop_presentation.ts';

const sha=(bytes:any)=>createHash('sha256').update(bytes).digest('hex');
const busy=new Set<string>();
function parent(workspace:string){
 if(lstatSync(workspace).isSymbolicLink()||realpathSync(workspace)!==resolve(workspace))throw Error('ppt_deck_workspace_changed');
 const code=join(workspace,'code');mkdirSync(code,{recursive:true,mode:0o700});
 if(lstatSync(code).isSymbolicLink()||realpathSync(code)!==resolve(code))throw Error('ppt_deck_workspace_changed');
 const projects=join(code,'projects');mkdirSync(projects,{recursive:true});
 if(lstatSync(projects).isSymbolicLink()||realpathSync(projects)!==resolve(projects))throw Error('ppt_deck_workspace_changed');
 return projects;
}
export function registerPptDeckTools(ctx:any,current:(session:string)=>any,resources:any={}){
 ctx.tools.guard?.((call:any)=>{
  const task=current(call.agent?.session?.id)?.task,project=task?.stats?.ppt_native_deck_project;
  if(task?.status!=='running'||!project)return;
  const path=call.arguments?.file_path??call.arguments?.path;
  if(['start_ppt','compose_ppt_page','prepare_ppt','finalize_ppt'].includes(call.name)||['write','edit'].includes(call.name)&&typeof path==='string'&&path.startsWith(project+'/'))
   return '当前已采用JSON稿件 '+project+'。请用patch_ppt修改指定页、用append_slides补页，或传空edits读取当前ID/恢复导出，保留成功内容；不要另建项目重做。';
 });
 const output={schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]};
 const owning=(execution:any)=>{
  const owner=current(execution?.agent?.session?.id),task=owner?.task;
  if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true)throw Error('ppt_deck_task_not_authorized');
  return {owner,task};
 };
 const execute=async(args:any,execution:any,build:boolean)=>{
  const {owner,task}=owning(execution);
  if(busy.has(task.workspace))throw Error('ppt_deck_operation_already_running');
  busy.add(task.workspace);
  try{
   const delivery=await import('../delivery/ppt_delivery_pipeline.ts');
   const projects=parent(task.workspace);
   const logical=build?'/work/projects/'+args.name:args.project;
   if(!/^\/work\/projects\/[\p{L}\p{N}][\p{L}\p{N}_-]{0,79}$/u.test(logical))throw Error('ppt_deck_project_name_invalid');
   const root=build?join(projects,args.name):delivery.pptWorkspacePath(task.workspace,logical);
   const imagePath=(path:string)=>{
    if(!/^\/work\/(?:inputs|projects|outputs)\/.+\.(?:png|jpe?g)$/i.test(path))throw Error('ppt_deck_image_requires_session_png_or_jpeg');
    return delivery.pptWorkspacePath(task.workspace,path);
   };
   if(build&&task.stats?.ppt_native_deck_project)throw Error('ppt_deck_already_adopted_use_patch_ppt: '+task.stats.ppt_native_deck_project);
   let result:any;
   if(build){
    const theme=pptThemes().themes.find((v:any)=>v.id===(args.plan?.theme??'general'));
    if(!theme)throw Error('ppt_theme_unknown_use_read_ppt_design');
    result=await buildPptDeck({root,plan:args.plan,theme,imagePath,fontFamily:'Noto Sans CJK SC',signal:execution.signal});
   }else result=await patchPptDeck({root,expected_revision:args.expected_revision,edits:args.edits,append_slides:args.append_slides,imagePath,signal:execution.signal});
   if(result.status==='rejected')return {...result,project:logical};
   (task.stats??={}).ppt_native_deck_project=logical;task.stats.ppt_work_started=true;
   execution.signal?.throwIfAborted();
   const input=logical+'/deck.pptx',doc=logical+'/deck.json',version=sha(readFileSync(join(root,'deck.pptx')));
   const dependencies={files:[{path:'deck.json',sha256:sha(readFileSync(join(root,'deck.json')))},{path:'geneloop-deck.json',sha256:sha(readFileSync(join(root,'geneloop-deck.json')))}],environment:officeEvidenceVersion(resources)};
   const key=digest({kind:'ppt_native_json_v1',project:logical,revision:result.revision,version,dependencies});
   const folder=join(task.output,'ppt-delivery-receipts');mkdirSync(folder,{recursive:true,mode:0o700});
   // Host-private conversation cache: unavailable to model file/shell mounts.
   const cache=join(task.workspace,'ppt-deck-exports');mkdirSync(cache,{recursive:true,mode:0o700});
   if(lstatSync(cache).isSymbolicLink()||realpathSync(cache)!==resolve(cache))throw Error('ppt_deck_cache_changed');
   const saved=join(cache,key+'.json');
   let receipt:any=null;
   if(existsSync(saved)&&!lstatSync(saved).isSymbolicLink()&&lstatSync(saved).nlink===1&&lstatSync(saved).size<1_000_000)
    receipt=delivery.cachedPptDelivery(task,JSON.parse(readFileSync(saved,'utf8')),key);
   if(!receipt){
    const rendered=await delivery.runPptInSession(task,{operation:'native_render',source:input,source_sha256:version,
     slide_count:result.slide_count,output:'/work/outputs/ppt-deck-'+randomUUID()},resources,execution.signal);
    execution.signal?.throwIfAborted();
    if(current(execution.agent.session.id)!==owner||task.status!=='running'||task.scene_options.allow_output!==true)throw Error('ppt_deck_authority_changed');
    if(sha(readFileSync(join(root,'deck.json')))!==dependencies.files[0].sha256||sha(readFileSync(join(root,'deck.pptx')))!==version)throw Error('ppt_deck_changed_during_render');
    if(rendered.mechanical_status!=='passed')return {...result,project:logical,...rendered,next_action:'keep_project_retry_patch_ppt_with_empty_edits_or_fix_specific_error'};
    receipt={...rendered,kind:'ppt_native_json_v1',key,project:logical,revision:result.revision,source_type:'native_json',
     deck_source:{path:doc,sha256:dependencies.files[0].sha256,pptx_path:input,pptx_sha256:version},dependencies,
     delivery_id:randomUUID(),reused_checks:false};
    receipt.review_pages=delivery.pptReviewPages(task,receipt);
   }
   delivery.acceptPptDeckReceipt(task,receipt);
   const pending=saved+'.'+randomUUID()+'.tmp';writeFileSync(pending,JSON.stringify(receipt),{flag:'wx',mode:0o600});renameSync(pending,saved);
   if(task.request?.learning_eligible!==false){
    try{
     const {mkdirSync,writeFileSync}=await import('node:fs');
     const directory=join(task.output,'reuse-evidence');mkdirSync(directory,{recursive:true,mode:0o700});
     for(const file of dependencies.files){
      const target=join(directory,file.sha256),raw=readFileSync(join(root,file.path));
      if(sha(raw)!==file.sha256)throw Error('ppt_deck_learning_source_changed');
      if(existsSync(target)){if(lstatSync(target).isSymbolicLink()||sha(readFileSync(target))!==file.sha256)throw Error('ppt_deck_learning_snapshot_changed');}
      else writeFileSync(target,raw,{flag:'wx',mode:0o400});
     }
     appendFileSync(join(task.output,'ppt-deck-sources.jsonl'),JSON.stringify({call_id:execution.callId,project:logical,
      revision:result.revision,delivery_id:receipt.delivery_id,sources:dependencies.files,
      role:'immutable_native_json_evidence',model_requests_skipped_verified:0})+'\n',{mode:0o600});
    }catch{
     // Optional sample capture must not revoke the user's completed delivery.
     task.stats.ppt_learning_capture_failed=true;
    }
   }
   // Record a real outer invocation. Internal stages are engineering with zero LLM skips.
   appendFileSync(join(task.output,'ppt-delivery-audit.jsonl'),JSON.stringify({kind:'ppt_deck_engine_delivered',
    call_id:execution.callId,tool:build?'build_ppt':'patch_ppt',project:logical,revision:result.revision,
    arguments_sha256:digest(args),delivery_id:receipt.delivery_id,reused_checks:receipt.reused_checks,
    optimization_kind:'shared_engineering',model_requests_skipped_verified:0})+'\n',{mode:0o600});
   return {...result,project:logical,...receipt,next_action:receipt.review_pages?.length?'read_image_for_review_pages_then_deliver':'present_current_delivery'};
  }finally{busy.delete(task.workspace);}
 };
 ctx.tools.register({...pptDeckBuildTool,output,execute:(args:any,execution:any)=>execute(args,execution,true)});
 ctx.tools.register({...pptDeckPatchTool,output,execute:(args:any,execution:any)=>execute(args,execution,false)});
}
