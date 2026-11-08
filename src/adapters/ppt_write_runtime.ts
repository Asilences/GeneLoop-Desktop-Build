/** Host-neutral interpreter for trace-discovered page writes and revisions. */
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {executePptOperations} from './ppt_execution.ts';

export function validatePptWriteProgram(program:any,host:any){
  const ir=program.ir,w=ir.writer,d=ir.delivery;
  const writer=host.contracts[w?.tool],delivery=host.contracts[d?.tool];
  if(ir.version!==1||!['new','revision'].includes(ir.mode)||!writer?.page_write||writer.read_only!==false||
    !delivery?.observed_completion||delivery.read_only!==false||w.schema_sha256!==writer.schema_sha256||
    d.schema_sha256!==delivery.schema_sha256||!['independent_observed_write_binding_replay','independent_native_write_execution'].includes(program.certification.scope))
    throw Error('ppt_write_contract_changed');
  for(const [key,value] of Object.entries(writer.page_write))if(digest(w[key])!==digest(value))throw Error('ppt_write_role_changed');
  for(const [key,value] of Object.entries(delivery.observed_completion))if(digest(d[key])!==digest(value))throw Error('ppt_write_delivery_changed');
  if(d.resource_argument!==delivery.resource_argument)throw Error('ppt_write_resource_changed');
  for(const item of [w,d])if(!Array.isArray(item.argument_names)||!item.argument_names.length||item.argument_names.length>32||
    item.argument_names.some((key:any)=>typeof key!=='string'||['__proto__','prototype','constructor'].includes(key))||
    new Set(item.argument_names).size!==item.argument_names.length)throw Error('ppt_write_arguments_invalid');
  if(!w.argument_names.includes(w.resource_argument)||!w.argument_names.includes(w.identity_argument)||
    !d.argument_names.includes(d.resource_argument)||!Array.isArray(w.version_output)||!w.version_output.length)
    throw Error('ppt_write_binding_invalid');
  if(ir.preview){
    const preview=host.contracts[ir.preview.tool];
    if(preview?.read_only!==true||preview.schema_sha256!==ir.preview.schema_sha256||!ir.preview.bindings||
      ir.preview.path_suffix!==undefined&&ir.preview.path_suffix!=='.png'||
      Object.values(ir.preview.bindings).some((key:any)=>typeof key!=='string'||['__proto__','prototype','constructor'].includes(key)))
      throw Error('ppt_write_preview_contract_changed');
  }
  return program;
}

function at(value:any,path:any[]){
  if(!Array.isArray(path)||path.length>16)throw Error('ppt_write_path_invalid');
  for(const key of path){
    if(['__proto__','prototype','constructor'].includes(String(key))||!value||!Object.hasOwn(value,key))throw Error('ppt_write_result_missing');
    value=value[key];
  }
  return value;
}

/** Build only the learned writer loop; content always comes from this call. */
export function pptWriteArguments(program:any,input:any){
  const ir=program.ir,w=ir.writer,d=ir.delivery;
  if(typeof input.project!=='string'||!input.project||!Array.isArray(input.pages)||!input.pages.length||input.pages.length>64)
    throw Error('ppt_write_input_invalid');
  if(w.repeated_page_run===false&&input.pages.length!==1)throw Error('ppt_write_single_page_evidence_only');
  const identities=new Set();
  const writes=input.pages.map((item:any,index:number)=>{
    if(!item||typeof item!=='object'||Array.isArray(item)||Object.hasOwn(item,w.resource_argument)||
      Object.keys(item).some(key=>!w.argument_names.includes(key)))throw Error('ppt_write_item_invalid');
    const args={...structuredClone(item),[w.resource_argument]:input.project};
    if(w.payload_choice_arguments?.length&&w.payload_choice_arguments.filter((key:string)=>Object.hasOwn(item,key)).length!==1)
      throw Error('ppt_write_payload_choice_required');
    const expected=(w.required_arguments??w.argument_names).filter((key:string)=>key!==w.resource_argument);
    if(expected.some((key:string)=>!Object.hasOwn(item,key)))throw Error('ppt_write_item_fields_required');
    const page=args[w.identity_argument];
    if(typeof page!=='string'||!page||identities.has(page))throw Error('ppt_write_page_identity_invalid');
    identities.add(page);
    const version=args[w.revision_argument];
    if(ir.mode==='revision'?!/^[a-f0-9]{64}$/.test(version??''):version!==undefined)throw Error('ppt_write_revision_version_required');
    return {id:'page_'+index,tool:w.tool,arguments:args};
  });
  const options=input.delivery??{};
  if(!options||typeof options!=='object'||Array.isArray(options)||Object.hasOwn(options,d.resource_argument)||
    Object.keys(options).some(key=>!d.argument_names.includes(key))||
    (d.required_arguments??d.argument_names).some((key:string)=>key!==d.resource_argument&&!Object.hasOwn(options,key)))throw Error('ppt_write_delivery_input_invalid');
  return {writes,delivery:{id:'delivery',tool:d.tool,arguments:{...structuredClone(options),[d.resource_argument]:input.project}}};
}

/** Checkpoints never repeat completed writes. No arbitrary code or tool names. */
async function executeWrite(program:any,input:any,execution:any,host:any){
  // The native tool already accepts object OR file parameters. Pin a file's
  // actual bytes once before hashing the invocation or starting any write.
  // This deterministic input adaptation does not choose or invent a recipe.
  host.check();
  if(host.prepareInput)input=await host.prepareInput(program,input);
  const operations=pptWriteArguments(program,input);
  const {resume,...payload}=input;
  const key=digest({program:program.id,input:payload});
  let journal=host.load?.(key)??{version:1,key,program_id:program.id,status:'prepared',completed:[]};
  if(journal.key!==key||journal.program_id!==program.id)throw Error('ppt_write_journal_changed');
  if(journal.status==='running'&&input.resume!==true)throw Error('ppt_write_explicit_resume_required_after_interruption');
  if(['failed','cancelled'].includes(journal.status)&&input.resume!==true)throw Error('ppt_write_explicit_resume_required');
  host.check();
  await host.admit(operations.writes,journal.completed);
  for(const saved of journal.completed)if(await host.version(operations.writes[saved.index])!==saved.version)throw Error('ppt_write_completed_page_changed');
  if(journal.status==='completed'&&(!host.deliveryCurrent||await host.deliveryCurrent(journal.delivery)))return {...journal,reused_execution:true};
  journal={...journal,status:'running'};host.save?.(key,journal);
  host.lease?.(input.project,program.id);
  const audit=(row:any)=>host.audit({...row,program_id:program.id,execution_key:key});
  const call=async(operation:any)=>{
    const result=await executePptOperations([operation],execution,{check:host.check,audit,
      dispatch:async(child:any)=>{
        host.internal?.(child.callId,true);
        try{return await host.dispatch(child);}finally{host.internal?.(child.callId,false);}
      }});
    if(result.status!=='completed'){
      const error:any=Error('ppt_write_child_failed: '+operation.id);error.details=result.completed[0]?.result.content;throw error;
    }
    return result.completed[0].result;
  };
  try{
    for(let index=journal.completed.length;index<operations.writes.length;index++){
      const operation=operations.writes[index];
      const result=await call(operation);
      const version=at(result.value,program.ir.writer.version_output);
      if(!/^[a-f0-9]{64}$/.test(version??'')||await host.version(operation)!==version)throw Error('ppt_write_page_receipt_changed');
      journal.completed.push({index,version});host.save?.(key,journal);
    }
    const delivered=await call(operations.delivery);
    const d=program.ir.delivery;
    const findings=at(delivered.value,d.empty_findings);
    if(at(delivered.value,d.success)!==d.success_value||!Array.isArray(findings)||
      findings.some((item:any)=>!item||(d.allowed_finding_severities??[]).includes(item.severity)!==true)){
      const error:any=Error('ppt_write_delivery_quality_failed');error.details=delivered.value;throw error;
    }
    if(host.reconcile)journal.completed=await host.reconcile(operations.writes,journal.completed,delivered.value);
    else for(const saved of journal.completed)if(await host.version(operations.writes[saved.index])!==saved.version)
      throw Error('ppt_write_page_changed_during_delivery');
    host.save?.(key,journal);
    await host.verifyUnchanged?.(input.project,operations.writes);
    // A previously certified read continuation may already be part of the
    // delivery result. Reuse those images instead of scheduling another read.
    const images:any[]=program.ir.preview?[]:(delivered.content??[]).filter((block:any)=>block.type==='image');
    if(program.ir.preview){
      const preview=program.ir.preview,all=at(delivered.value,preview.collection??d.collection);
      const collection=preview.path_suffix&&Array.isArray(all)?all.filter((row:any)=>typeof row.path==='string'&&row.path.endsWith(preview.path_suffix)):all;
      if(!Array.isArray(collection)||!collection.length||collection.length>200)throw Error('ppt_write_preview_collection_invalid');
      for(let index=0;index<collection.length;index++){
        const arguments_=Object.fromEntries(Object.entries(preview.bindings).map(([key,field]:[string,any])=>[key,at(collection[index],[field])]));
        const result=await call({id:'preview_'+index,tool:preview.tool,arguments:arguments_});
        const blocks=result.content.filter((block:any)=>block.type==='image');
        if(!blocks.length||collection[index].sha256&&!blocks.some((block:any)=>block.attachment?.attachmentId==='sha256:'+collection[index].sha256))
          throw Error('ppt_write_preview_missing_or_changed');
        images.push(...blocks);
      }
    }
    const preview=program.ir.preview,allPreviews=at(delivered.value,preview?.collection??d.collection);
    const previews=preview?.path_suffix&&Array.isArray(allPreviews)?allPreviews.filter((row:any)=>typeof row.path==='string'&&row.path.endsWith(preview.path_suffix)):allPreviews;
    const preview_complete=Array.isArray(previews)&&previews.length>0&&previews.every((row:any)=>row.sha256&&
      images.some((image:any)=>image.attachment?.attachmentId==='sha256:'+row.sha256));
    if(findings.length&&!preview_complete)throw Error('ppt_write_advisory_review_images_required');
    journal={...journal,status:'completed',delivery:delivered.value,images,preview_complete};host.save?.(key,journal);
    audit({kind:'ppt_write_program_completed',pages:journal.completed.length,model_requests_inside_program:0});
    return journal;
  }catch(error:any){
    journal={...journal,status:execution.signal?.aborted?'cancelled':'failed',failure:error.message,error_details:error.details??null,
      current_versions:await Promise.all(operations.writes.map(async(operation:any)=>{
        try{return await host.version(operation);}catch{return 'unavailable';}
      }))};
    host.save?.(key,journal);
    audit({kind:'ppt_write_program_failed',completed_pages:journal.completed.length,reason:error.message,automatic_write_retry:false});
    if(execution.signal?.aborted)throw error;
    return journal;
  }
}

const active=new WeakMap<object,Set<string>>();
/** Serial ownership applies on Windows/macOS too; a restart still needs resume. */
export async function executePptWriteProgram(program:any,input:any,execution:any,host:any){
  const owner=execution.agent??execution,key=input.project;
  let held=active.get(owner);if(!held){held=new Set();active.set(owner,held);}
  if(held.has(key))throw Error('ppt_write_execution_running');
  held.add(key);
  try{return await executeWrite(program,input,execution,host);}finally{held.delete(key);}
}
