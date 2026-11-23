/** Execute trace-compiled continuations through the owning Harness tool host. */
import {digest} from '../../../motif_core/runtime/online_skill_runtime.mjs';
import {executePptOperations} from './ppt_execution.ts';
import {validatePptWriteProgram} from './ppt_write_runtime.ts';
import {readFileSync} from 'node:fs';

export type PptWorkflowContract = {schema_sha256:string;read_only:boolean;page_write?:any;resource_argument?:string;observed_completion?:any};
export type PptWorkflowHost = {
  environment_sha256:string;
  contracts:Record<string,PptWorkflowContract>;
};

function field(value:any,path:(string|number)[]){
  if(!Array.isArray(path)||path.length>16||path.some(part=>
    typeof part!=='string'&&(!Number.isSafeInteger(part)||part<0)||['__proto__','prototype','constructor'].includes(String(part))))
    throw Error('ppt_workflow_field_invalid');
  for(const part of path){
    if(value===null||typeof value!=='object'||!Object.hasOwn(value,part))throw Error('ppt_workflow_field_missing');
    value=value[part];
  }
  return value;
}

export function validatePptWorkflowLibrary(library:any,host:PptWorkflowHost){
  if(!library||library.version!==1||library.kind!=='trace_learned_tool_continuations'||
    library.environment_sha256!==host.environment_sha256||!Array.isArray(library.programs)||library.programs.length>16)
    throw Error('ppt_workflow_environment_changed');
  const {digest:claimed,...body}=library;
  if(digest(body)!==claimed)throw Error('ppt_workflow_library_changed');
  for(const program of library.programs){
    const training=program.provenance??[],replay=program.certification?.replay??[];
    const independence=program.certification?.independence_policy;
    if(independence!==undefined&&independence!=='ppt_distinct_source_decision_v2')throw Error('ppt_workflow_independence_policy_unknown');
    const independentKeys=independence?['decision_id','source_signature']:['decision_id','source_signature','question_sha256'];
    const prefix=program.ir?.kind==='observed_page_write_delivery'?'ppt_write_':'ppt_flow_';
    if(program.id!==prefix+digest(program.ir).slice(0,24)||program.status!=='certified'||
      program.certification?.status!=='passed'||program.certification.training_decisions<2||
      program.certification.independent_replay_decisions<1||training.length<2||!replay.length||
      program.certification.training_decisions!==new Set(training.map((row:any)=>row.decision_id)).size||
      program.certification.independent_replay_decisions!==new Set(replay.map((row:any)=>row.decision_id)).size||
      independentKeys.some(key=>
        training.some((row:any)=>typeof row[key]!=='string'||!row[key])||new Set(training.map((row:any)=>row[key])).size<2||
        replay.some((row:any)=>typeof row[key]!=='string'||!row[key]||training.some((sample:any)=>sample[key]===row[key]))))
      throw Error('ppt_workflow_not_certified');
    if([...training,...replay].some((row:any)=>typeof row.question_sha256!=='string'||!row.question_sha256))
      throw Error('ppt_workflow_question_evidence_missing');
    const ir=program.ir;
    const family=(row:any)=>row.source_family??row.source_signature;
    if(new Set(training.map(family)).size<2||replay.some((row:any)=>training.some((source:any)=>family(row)===family(source))))
      throw Error('ppt_workflow_source_family_not_independent');
    if(ir?.kind==='observed_page_write_delivery'){
      if(program.certification.scope==='independent_native_write_execution'){
        const native=program.certification.native_execution;
        if(native?.status!=='passed'||native.environment_sha256!==host.environment_sha256||
          !/^[a-f0-9]{64}$/.test(native.sha256??'')||!/^[a-f0-9]{64}$/.test(native.plan_sha256??'')||native.model_requests!==0)
          throw Error('ppt_workflow_native_execution_missing');
      }
      validatePptWriteProgram(program,host);
      continue;
    }
    if(ir?.kind==='observed_anchor_read_map'){
      if(ir.version!==1||ir.collection_min!==1||ir.collection_max!==64||
        !validPath(ir.collection)||!validPath(ir.success)||!validPath(ir.empty_findings))
        throw Error('ppt_workflow_ir_invalid');
      const anchor=host.contracts[ir.anchor?.tool],step=ir.step,contract=host.contracts[step?.tool];
      if(!anchor||anchor.schema_sha256!==ir.anchor.schema_sha256)
        throw Error('ppt_workflow_anchor_contract_changed');
      if(step?.id!=='item'||!contract||contract.read_only!==true||contract.schema_sha256!==step.schema_sha256||
         !step.bindings||typeof step.bindings!=='object'||Array.isArray(step.bindings)||!Object.keys(step.bindings).length||
         Object.values(step.bindings).some((path:any)=>!validPath(path)||path.length!==1||typeof path[0]!=='string'))
        throw Error('ppt_workflow_continuation_contract_changed');
      const length=(row:any)=>Number.isSafeInteger(row.collection_length)&&row.collection_length>=1&&row.collection_length<=64;
      const lengths=new Set(training.map((row:any)=>row.collection_length));
      if(!training.every(length)||lengths.size<2||!replay.every((row:any)=>length(row)&&!lengths.has(row.collection_length)))
        throw Error('ppt_workflow_map_independent_lengths_required');
      continue;
    }
    if(!ir||ir.version!==1||ir.kind!=='observed_anchor_read_continuation'||!Array.isArray(ir.steps)||
      !ir.steps.length||ir.steps.length>16||!Array.isArray(ir.collection)||!Number.isSafeInteger(ir.collection_length)||
      ir.collection_length<1||ir.collection_length>64||!Array.isArray(ir.success)||!Array.isArray(ir.empty_findings))
      throw Error('ppt_workflow_ir_invalid');
    const anchor=host.contracts[ir.anchor.tool];
    if(!anchor||anchor.schema_sha256!==ir.anchor.schema_sha256)throw Error('ppt_workflow_anchor_contract_changed');
    const ids=new Set<string>();
    const covered=new Set<number>();
    for(const step of ir.steps){
      const contract=host.contracts[step.tool];
      if(!(/^[a-zA-Z0-9_-]{1,80}$/).test(step.id)||ids.has(step.id)||!contract||contract.read_only!==true||
        contract.schema_sha256!==step.schema_sha256||!step.bindings||typeof step.bindings!=='object'||Array.isArray(step.bindings))
        throw Error('ppt_workflow_continuation_contract_changed');
      ids.add(step.id);
      for(const path of Object.values(step.bindings) as any[]){
        if(!validPath(path)||path.length!==ir.collection.length+2||
          !ir.collection.every((part:any,n:number)=>part===path[n])||
          !Number.isSafeInteger(path[ir.collection.length])||path[ir.collection.length]>=ir.collection_length)
          throw Error('ppt_workflow_field_invalid');
        covered.add(path[ir.collection.length]);
      }
    }
    if(covered.size!==ir.collection_length)throw Error('ppt_workflow_full_collection_required');
  }
  return library;
}

function validPath(path:any){
  return Array.isArray(path)&&path.length>0&&path.length<=16&&path.every(part=>
    typeof part==='string'&&!['__proto__','prototype','constructor'].includes(part)||Number.isSafeInteger(part)&&part>=0);
}

let publicPreviewMotifs:any;

export function validatePublicPptPreviewMotifs(host:PptWorkflowHost){
  publicPreviewMotifs??=JSON.parse(readFileSync(new URL('../../../../scenarios/ppt_master/public-preview-motifs.json',import.meta.url),'utf8'));
  const {version,kind,programs}=publicPreviewMotifs;
  if(version!==1||kind!=='public_ppt_preview_continuations'||!Array.isArray(programs)||programs.length>16)
    throw Error('ppt_public_preview_library_invalid');
  return programs.filter(({id,ir,certification}:any)=>{
    if(id!=='ppt_flow_'+digest(ir).slice(0,24)||certification.training_decisions<2||certification.independent_replay_decisions<1||
       ir.version!==1||!['build_ppt','patch_ppt'].includes(ir.anchor.tool)||ir.success_value!=='passed'||
       digest([ir.success,ir.empty_findings,ir.collection])!==digest([['mechanical_status'],['findings'],['review_pages']]))
      throw Error('ppt_public_preview_program_invalid');
    if(host.contracts[ir.anchor.tool]?.schema_sha256!==ir.anchor.schema_sha256)return false;
    const read=host.contracts.read_image;
    if(!read?.read_only)return false;
    const isRead=(step:any,path:any[])=>step.tool==='read_image'&&read.schema_sha256===step.schema_sha256&&
      digest(step.bindings)===digest({file_path:path});
    if(ir.kind==='observed_anchor_read_map'){
      const {training_lengths,replay_lengths}=certification;
      return ir.collection_min===1&&ir.collection_max===64&&new Set(training_lengths).size>=2&&
        replay_lengths.length>0&&replay_lengths.every((n:number)=>!training_lengths.includes(n))&&isRead(ir.step,['path']);
    }
    return ir.kind==='observed_anchor_read_continuation'&&ir.anchor.tool==='patch_ppt'&&
      [1,2].includes(ir.collection_length)&&ir.steps.length===ir.collection_length&&
      ir.steps.every((step:any,index:number)=>isRead(step,['review_pages',index,'path']));
  });
}

/** A completed caller-owned write can anchor reads; the caller is never replayed. */
export function pptWorkflowOperations(program:any,value:any){
  const ir=program.ir;
  if(!validPath(ir.success)||!validPath(ir.empty_findings)||!validPath(ir.collection))throw Error('ppt_workflow_field_invalid');
  if(field(value,ir.success)!==ir.success_value||!Array.isArray(field(value,ir.empty_findings))||field(value,ir.empty_findings).length)
    return null;
  const collection=field(value,ir.collection);
  if(ir.kind==='observed_anchor_read_map'){
    if(!Array.isArray(collection)||collection.length<ir.collection_min||collection.length>ir.collection_max)return null;
    return collection.map((item:any,index:number)=>({id:'item_'+index,tool:ir.step.tool,arguments:Object.fromEntries(
      Object.entries(ir.step.bindings).map(([name,path]:[string,any])=>{
        if(!validPath(path))throw Error('ppt_workflow_field_invalid');
        const bound=field(item,path);
        if(typeof bound!=='string'||!bound||bound.includes('\0'))throw Error('ppt_workflow_scalar_binding_required');
        return [name,bound];
      }))}));
  }
  if(!Array.isArray(collection)||collection.length!==ir.collection_length)return null;
  return ir.steps.map((step:any)=>({id:step.id,tool:step.tool,arguments:Object.fromEntries(
    Object.entries(step.bindings).map(([name,path]:[string,any])=>{
      if(!validPath(path))throw Error('ppt_workflow_field_invalid');
      const bound=field(value,path);
      if(typeof bound!=='string'||!bound||bound.includes('\0'))throw Error('ppt_workflow_scalar_binding_required');
      return [name,bound];
    }))}));
}

export function registerPptWorkflowContinuation(ctx:any,current:(session:string)=>any,host:PptWorkflowHost|((execution:any)=>PptWorkflowHost)){
  const active=new Set<string>();
  ctx.on('tools/post-execute',async(execution:any,result:any,next:any)=>{
    const decision=await next();
    if(decision.kind!=='accept'||Object.hasOwn(decision,'value'))return decision;
    const session=execution.agent?.session?.id;
    const value=typeof session==='string'?current(session):null;
    const task=value?.task,library=value?.workflow;
    if(value?.writePreviewOwned?.has(execution.callId))return decision;
    if(result.isError||(!library&&!value?.publicPreviewMotifs)||task?.status!=='running'||task.request.mode!=='execute'||
      task.selection?.rsi!==true||task.scene_options?.allow_output!==true||typeof ctx.tools.execute!=='function')return decision;
    const audit=(row:any)=>value.workflowAudit?.({...row,task_id:task.request.task_id});
    let program:any,operations:any,publicProgram=false;
    let profile:PptWorkflowHost;
    try{
      if(!library?.programs?.some((row:any)=>row.ir?.anchor?.tool===execution.name)&&
         !(value.publicPreviewMotifs&&['build_ppt','patch_ppt'].includes(execution.name)))return decision;
      profile=typeof host==='function'?host(execution):host;
      let local=[];
      if(library)try{local=validatePptWorkflowLibrary(library,profile).programs;}catch(error:any){
        audit({kind:'ppt_workflow_guard_fallback',reason:error.message});
      }
      const published=value.publicPreviewMotifs?validatePublicPptPreviewMotifs(profile):[];
      const candidates=[...local.map((row:any)=>({row,published:false})),...published.map((row:any)=>({row,published:true}))]
        .filter(({row})=>row.ir.anchor?.tool===execution.name)
        .sort((a,b)=>Number(a.published)-Number(b.published)||
          (a.published?1:-1)*(Number(a.row.ir.kind==='observed_anchor_read_map')-Number(b.row.ir.kind==='observed_anchor_read_map')));
      for(const candidate of candidates){
        const bound=pptWorkflowOperations(candidate.row,result.value);
        if(bound){program=candidate.row;publicProgram=candidate.published;operations=bound;break;}
      }
      if(!program)return decision;
    }catch(error:any){
      audit({kind:'ppt_workflow_guard_fallback',reason:error.message});
      return decision;
    }
    const key=session+'\0'+execution.callId;
    if(active.has(key))return decision;
    active.add(key);
    try{
      const check=()=>{
        if(current(session)!==value||task.status!=='running'||task.selection?.rsi!==true||task.scene_options?.allow_output!==true)
          throw Error('ppt_workflow_task_revoked');
        const currentProfile=typeof host==='function'?host(execution):profile;
        if(publicProgram){
          if(!validatePublicPptPreviewMotifs(currentProfile).some((row:any)=>row.id===program.id))
            throw Error('ppt_workflow_selection_withdrawn');
        }else{
          if(value.workflowValid&&value.workflowValid()!==true)throw Error('ppt_workflow_selection_withdrawn');
          validatePptWorkflowLibrary(library,currentProfile);
        }
      };
      const completed=await executePptOperations(operations,execution,{dispatch:call=>ctx.tools.execute(call),check,audit});
      audit({kind:'ppt_workflow_executed',program_id:program.id,library_digest:publicProgram?digest(publicPreviewMotifs):library.digest,
        public_program:publicProgram,
        anchor_call_id:execution.callId,status:completed.status,child_calls:completed.completed.length,
        model_requests_inside_continuation:0,quality_judgment_skipped:false});
      const canonical={...result.value,workflow_continuation:{id:program.id,status:completed.status},
        next_action:completed.status==='completed'?'review_returned_images_then_continue':'handle_failed_continuation'};
      const definition=execution.agent?.ctx?.tools?.get(execution.name,execution.agent);
      const content=decision.content??definition?.output?.render(execution.arguments,canonical)??result.content;
      // Public post-execute content replacement survives registry normalization.
      // Keep the tool's validated canonical value; enrich only model content.
      return {...decision,content:[...content,...completed.completed.flatMap(row=>row.result.content)]};
    }catch(error:any){
      if(execution.signal?.aborted)throw error;
      // The anchor already completed. A failed read must not turn a successful
      // export into a tool error that encourages replaying the write operation.
      audit({kind:'ppt_workflow_continuation_failed',program_id:program.id,anchor_call_id:execution.callId,
        reason:error.message,anchor_preserved:true});
      return decision;
    }finally{active.delete(key);}
  },{global:true});
}
