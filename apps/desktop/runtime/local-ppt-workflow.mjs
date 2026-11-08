/** Optional adapter for the native desktop Agent scope, with server-only models. */
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
import {digest} from './ppt-shared/motif_core/online_skill_runtime.mjs';
import {registerPptWorkflowContinuation,validatePptWorkflowLibrary} from './ppt-shared/adapters/ppt_workflow_runtime.mjs';
import {executePptWriteProgram} from './ppt-shared/adapters/ppt_write_runtime.mjs';

const readonly=new Set(['local_list','local_read','local_search','local_ppt_read_material','local_ppt_read_source','local_paper_read_page']);
const anchors=new Set(['local_ppt_master_export','local_ppt_fill_template','local_ppt_create']);

export function localPptWorkflowEnvironment(){
  const base=dirname(fileURLToPath(import.meta.url));
  const manifest=JSON.parse(readFileSync(join(base,'ppt-workflow-bundle.json'),'utf8'));
  for(const item of manifest.files){
    if(typeof item.path!=='string'||item.path.split('/').includes('..')||item.path.startsWith('/')||
      createHash('sha256').update(readFileSync(join(base,item.path))).digest('hex')!==item.sha256)
      throw Error('desktop_ppt_workflow_bundle_changed');
  }
  return digest({platform:process.platform,architecture:process.arch,node:process.version,bundle:manifest});
}

/** Called by trusted worker setup after workspace approval. No model credentials. */
export function installLocalPptWorkflow(scope,options){
  if(options.enabled!==true||!options.library)return {close(){}};
  let active=true;
  const library=structuredClone(options.library);
  if(library.programs?.some(program=>program.ir.kind==='observed_page_write_delivery')&&
    (!options.writeHost||['admit','version','load','save'].some(name=>typeof options.writeHost[name]!=='function'))){
    options.audit?.({kind:'desktop_ppt_workflow_disabled',reason:'native_page_write_host_unavailable',ordinary_tools_preserved:true});
    return {status:'ordinary_tools_only',close(){active=false;}};
  }
  const task={status:'running',request:{task_id:options.taskId,mode:'execute'},selection:{rsi:true},scene_options:{allow_output:true}};
  const context={task,workflow:library,workflowAudit:options.audit,workflowValid:()=>active&&!options.signal.aborted,writePreviewOwned:new Set()};
  const current=session=>session===options.sessionId&&active?context:null;
  const profile=execution=>{
    const contracts={};
    for(const program of library.programs){
      if(program.ir.kind==='observed_page_write_delivery'){
        const trusted=options.writeHost?.contracts;
        if(!trusted)throw Error('desktop_ppt_native_page_write_host_required');
        for(const name of [program.ir.writer.tool,program.ir.delivery.tool,...(program.ir.preview?[program.ir.preview.tool]:[])]){
          const contract=trusted[name],definition=execution.agent.ctx.tools.get(name,execution.agent);
          if(!name.startsWith('local_ppt_')||!contract||!definition?.parameters)throw Error('desktop_ppt_write_tool_not_authorized');
          contracts[name]={...contract,schema_sha256:digest(definition.parameters)};
        }
        continue;
      }
      if(!anchors.has(program.ir.anchor.tool))throw Error('desktop_ppt_workflow_anchor_not_authorized');
      for(const name of [program.ir.anchor.tool,...program.ir.steps.map(step=>step.tool)]){
        const definition=execution.agent.ctx.tools.get(name,execution.agent);
        if(!definition?.parameters||!anchors.has(name)&&!readonly.has(name))throw Error('desktop_ppt_workflow_tool_not_authorized');
        contracts[name]={schema_sha256:digest(definition.parameters),read_only:readonly.has(name)};
      }
    }
    return {environment_sha256:localPptWorkflowEnvironment(),contracts};
  };
  registerPptWorkflowContinuation(scope,current,profile);
  if(library.programs.some(program=>program.ir.kind==='observed_page_write_delivery')){
    const host=options.writeHost;
    if(!host||['admit','version','load','save'].some(name=>typeof host[name]!=='function'))throw Error('desktop_ppt_native_page_write_host_required');
    const internal=new Set(),leases=new Set();
    scope.tools.guard(execution=>{
      if(internal.has(execution.callId))return;
      const program=library.programs.find(program=>program.ir.writer?.tool===execution.name);
      if(program||leases.size&&host.isManagedMutation?.(execution))return '当前选定页面由execute_ppt_program执行与修订；不得在外部覆盖已管理页面。';
    });
    scope.tools.register({name:'execute_ppt_program',description:'在本机执行本平台独立认证的轨迹写页/修订程序，模型仅由既有服务器转发。一次提交pages参数，按当前SHA修订指定页。',
      parameters:{type:'object',properties:{id:{type:'string'},project:{type:'string'},pages:{type:'array',items:{type:'object'}},delivery:{type:'object'},resume:{type:'boolean'}},required:['id','project','pages'],additionalProperties:false},
      output:{schema:{type:'object'},render:(_args,result)=>[{type:'text',text:JSON.stringify({...result,images:undefined})},...(result.images??[])]},
      async execute(input,execution){
        if(!active||execution.agent.session.id!==options.sessionId)throw Error('desktop_ppt_workflow_revoked');
        validatePptWorkflowLibrary(library,profile(execution));
        const program=library.programs.find(program=>program.id===input.id&&program.ir.kind==='observed_page_write_delivery');
        if(!program)throw Error('desktop_ppt_write_program_missing');
        return executePptWriteProgram(program,input,execution,{...host,
          check(){if(!active||options.signal.aborted)throw Error('desktop_ppt_workflow_revoked');validatePptWorkflowLibrary(library,profile(execution));host.check?.();},
          async dispatch(call){
            const owns=!!program.ir.preview&&call.name===program.ir.delivery.tool;
            if(owns)context.writePreviewOwned.add(call.callId);
            try{return await scope.tools.execute(call);}finally{if(owns)context.writePreviewOwned.delete(call.callId);}
          },internal:(id,on)=>on?internal.add(id):internal.delete(id),
          lease:project=>{leases.add(project);host.lease?.(project,program.id);},audit:row=>options.audit({...row,task_id:options.taskId})});
      }});
  }
  options.signal.addEventListener('abort',()=>{active=false;task.status='cancelled';},{once:true});
  return {close(){active=false;task.status='closed';}};
}
