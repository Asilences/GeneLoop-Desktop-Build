/** Durable decision replay checks; never decide file semantics or grant authority. */
import {readFileSync,readdirSync,lstatSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {digest} from '../../motif_core/runtime/online_skill_runtime.mjs';
import {bindLearnedDecision,prepareLearnedAction} from '../learned_decision_program.ts';

export function workspaceSnapshot(root:string){
 const files:any={},directories:string[]=[];
 function visit(path:string,prefix:string){
  for(const name of readdirSync(path).sort()){
   const file=join(path,name),relative=prefix+name,s=lstatSync(file);
   if(s.isSymbolicLink())throw Error('changed workspace contains symlink');
   if(s.isDirectory()){directories.push(relative);visit(file,relative+'/');}
   else if(s.isFile())files[relative]=createHash('sha256').update(readFileSync(file)).digest('hex');
   else throw Error('unsupported workspace object');
  }
 }
 visit(root,'');return {files,directories};
}

export function originalInitialization(operation:any,pending:any,tools:any[]){
 const tool='mcp__file_management__read_task',registered=operation.catalog?.[tool];
 const schema=tools.find(t=>t.name===tool)?.parameters;
 // Old metadata calls this semantic. Authority comes from the exact original
 // empty-argument task initialization, not from treating that label as a route.
 if(!registered||!schema||Object.keys(schema.properties??{}).length||(schema.required??[]).length||
  digest(schema)!==registered.schema_sha256||!pending.context.history.some((r:any)=>r.tool===tool&&
   Object.keys(r.args??{}).length===0&&digest(r.out?._sss_scope)===digest(operation.scope)))throw Error('original MCP initialization unavailable');
 return tool;
}

export function validatePendingDecision(p:any,current:any){
 const fail=(reason:string)=>({kind:'invalid',reason});
 if(p.format!=='file-paid-decision-checkpoint-v1')return fail('unknown_checkpoint');
 if(p.task_sha256!==current.task_sha256||p.owner!==current.owner||p.task_id!==current.task_id)return fail('task_or_permission_changed');
 if(p.payload_sha256!==digest(current.payload)||p.runtime_sha256!==current.runtime_sha256||p.models_sha256!==current.models_sha256)return fail('program_or_model_changed');
 const done=current.history.find((r:any)=>current.previous_call_ids.includes(r.call_id));
 if(done)return digest(done.args)===digest(p.binding.arguments)&&done.tool===p.binding.tool?{kind:'completed'}:fail('completed_call_differs');
 if(!['read','stage'].includes(current.effect)||current.external_roots)return fail('effect_requires_original_execution_journal');
 if(digest(p.workspace)!==digest(current.workspace))return fail('workspace_version_changed');
 let history=current.history;
 if(current.primer){
  const row=history.find((r:any)=>r.call_id===current.primer.call_id);
  if(!row||row.tool!==current.primer.tool||Object.keys(row.args??{}).length||
   digest(row.out?._sss_scope)!==digest(current.scope))return fail('recovery_initialization_failed');
  history=history.filter((r:any)=>r!==row);
 }
 if(digest(p.context.history)!==digest(history))return fail('task_progress_changed');
 if(digest(current.schema)!==p.tool_schema_sha256)return fail('tool_contract_changed');
 const prepared=prepareLearnedAction(current.payload.candidate,p.context);
 const binding=bindLearnedDecision(current.payload.candidate,p.context,p.resolution.values);
 if(!prepared||digest(prepared.request)!==digest(p.request)||digest(binding)!==digest(p.binding)||!p.resolution.accepted)return fail('original_decision_no_longer_binds');
 return {kind:'replay',binding};
}
