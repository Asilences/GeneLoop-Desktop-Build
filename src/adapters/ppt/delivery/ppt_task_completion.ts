/** Task-level selection of the delivered manuscript; not an RSI execution rule. */
import {existsSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {nativePresentedFiles} from '../../geneloop_native_work.ts';
import {pptTaskAcceptance,pptCurrentDeliveryFiles,pptSourceState,pptWorkspacePath,pptReadyDelivery} from './ppt_delivery_pipeline.ts';

/** Ordinary request routing, not a learned operation. Attachment text is excluded. */
export function pptDeliveryRequested(task:any){
 const text=(task.request?.content??[]).filter((p:any)=>p.type==='text').map((p:any)=>p.text??'').join('\n');
 const object='(?:pptx?|powerpoint|presentation|slide(?:s|\\s*deck)?|幻灯片|演示文稿|课件)';
 const action='(?:生成|制作|做(?:一[个份套])?|创建|修改|修订|改成|改为|替换|调整|精简|更新|导出|添加|加入|删除|移动|对齐|creat(?:e|ing)|mak(?:e|ing)|generat(?:e|ing)|build(?:ing)?|prepar(?:e|ing)|edit|revise|modify|simplify|update|replace|align|export|add|remove)';
 if(/^(?:不用|不要|无需|不必)[^\n。！？?]{0,10}(?:制作|生成|修改|修订)/.test(text.trim()))return false;
 if(/^(?:请问|如何|怎么|为什么|how\b|why\b|what\b)/i.test(text.trim())&&!/(?:请帮我|帮我|please|could you|can you)/i.test(text))return false;
 const existing=Object.keys(task.ppt_initial_sources??{}).length>0||task.scene_inputs?.some((row:any)=>/\.pptx$/i.test(row.file??''));
 if(existing&&/(?:居中|靠左|靠右|替换|调整|精简|对齐|添加|删掉|移到|修改|修订)|\b(?:center|align|replace|simplify|edit|revise|change|update|remove|add)\b/i.test(text))return true;
 return new RegExp(action+'[^\\n。！？?]{0,100}'+object,'i').test(text)||
  new RegExp(object+'[^\\n。！？?]{0,60}'+action,'i').test(text)||
  /(?:修改|修订|精简|调整|替换|对齐|改成|改为)[^\n。！？?]{0,40}第?\s*\d+\s*页|第\s*\d+\s*页[^\n。！？?]{0,40}(?:改|精简|调整|替换)/.test(text);
}

/** Shared delivery, not a model's claim of completion. */
function requiredTask(task:any){return task.scene?.id==='ppt'&&task.scene?.ppt_execution_strategy==='ppt_master'&&
 task.scene_options?.allow_output===true&&pptDeliveryRequested(task);}

export function pptFinalTaskAcceptance(task:any,resources:any={}){
 let strict=pptTaskAcceptance(task,resources);
 if(!strict.required&&requiredTask(task))strict={required:true,passed:false,reason:'ppt_requested_delivery_missing'};
 if(strict.passed||!strict.required)return strict;
 try{
  // A single selected current export is authoritative even if optional probes
  // remain. Source edits after export already invalidate pptReadyDelivery.
  const ready=(requiredTask(task)||task.stats?.ppt_last_delivered_project)?pptReadyDelivery(task,resources):[];
  if(ready.length)return {required:true,passed:true,delivery_ids:ready.map(row=>row.delivery_id),selection:'host_current_manuscript'};
  // Only a successful present in THIS turn can select the final manuscript.
  // Its host proof must still match the actual bytes, not a path in tool prose.
  const published=nativePresentedFiles({workspace:task.workspace,eventsPath:join(task.output,'events.jsonl'),
   startedAt:task.started_at,finishedAt:task.finished_at??new Date().toISOString()});
  const pptx=[...published.keys()].filter(path=>path.toLowerCase().endsWith('.pptx'));
  const pdf=[...published.keys()].filter(path=>path.toLowerCase().endsWith('.pdf'));
  if(!pptx.length||!pdf.length)return strict;
  const state=pptSourceState(task.workspace);
  const selected={...task,ppt_initial_sources:state,stats:{...task.stats,ppt_work_started:true}};
  const current=pptTaskAcceptance(selected,resources);
  if(current.passed){
   const files=pptCurrentDeliveryFiles(selected,resources);
   if([...pptx,...pdf].every(path=>files.get(path)===published.get(path)))
    return {...current,selection:'explicit_current_manuscript',unselected_projects_not_required:true};
  }
  // Imported native PPTX edits use the shared, byte-bound present path. They
  // do not have a Generate SVG export receipt. Do not bypass a real Generate
  // project with missing/stale receipts, even if another PPTX was presented.
  const generated=Object.keys(state).some(project=>{
   const path=pptWorkspacePath(task.workspace,project);
   return existsSync(join(path,'geneloop-deck.json'))||existsSync(join(path,'spec_lock.md'))&&existsSync(join(path,'svg_output'))&&
    !existsSync(join(path,'sources/source.pptx'));
  });
  if(generated)return strict;
  if(pptx.every(path=>readFileSync(path).subarray(0,4).equals(Buffer.from([0x50,0x4b,3,4])))&&
     pdf.every(path=>readFileSync(path).subarray(0,5).toString()==='%PDF-'))
   return {required:true,passed:true,selection:'native_presented_current_bytes',
    // This establishes current delivery, not visual/scientific quality or
    // equivalence of the PDF. Those remain separate evaluation dimensions.
    quality_verified:false};
 }catch{/* Missing, redirected, modified, or old evidence cannot grant completion. */}
 return strict;
}

export function pptFinalDeliveryFiles(task:any,resources:any={}):Map<string,string>{
 const acceptance=pptFinalTaskAcceptance(task,resources);
 if(!acceptance.required||!acceptance.passed)return new Map();
 if(acceptance.selection==='host_current_manuscript'){
  const rows=pptReadyDelivery(task,resources);
  return new Map(rows.flatMap(row=>row.artifacts).map((row:any)=>[pptWorkspacePath(task.workspace,row.path),row.sha256]));
 }
 return pptCurrentDeliveryFiles(task,resources);
}
