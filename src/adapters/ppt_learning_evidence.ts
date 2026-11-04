/** Validate sealed execution facts against current Task state; ignore UI/global counters. */
import {createHash} from 'node:crypto';
import {readFileSync,lstatSync,realpathSync} from 'node:fs';
import {join,basename,dirname,resolve} from 'node:path';
const stateKeys=['task_id','session_id','user_id','scene','mode','status','failure','source_task_id',
 'provider_mode','provider','model','reasoning_effort','scene_inputs','rsi','scene_options'];
const statsKeys=['upstream_requests','prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens',
 'completion_tokens','total_tokens','usage_complete','pending_requests','unknown_usage_requests','verified_skips'];
export function pptLearningState(state:any){return {...Object.fromEntries(stateKeys.map(k=>[k,state[k]??null])),
 stats:Object.fromEntries(statsKeys.map(k=>[k,state.stats?.[k]??null]))};}
function canonical(value:any):any{if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));return value;}
export const pptLearningStateDigest=(value:any)=>createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
export function verifyPptStateBinding(output:string,path:string){
 const match=/^learning-state-([a-f0-9]{64})\.json$/.exec(basename(path));if(!match)return;
 const row=JSON.parse(readFileSync(path,'utf8')),identity=row.task_id;
 if(typeof identity!=='string'||!/^\w{32}$/.test(identity)||!/^[a-f0-9]{32}$/.test(identity)||
  resolve(dirname(path))!==join(output,'tasks',identity)||row.schema_version!==1||row.kind!=='ppt_learning_state_binding_v1'||
  row.state_sha256!==match[1]||pptLearningStateDigest(row.state)!==match[1])throw Error('ppt_learning_state_binding_invalid');
 const current=join(output,'tasks',identity,'task-state.json'),stat=lstatSync(current);
 if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||realpathSync(current)!==current)throw Error('ppt_learning_state_path_changed');
 if(pptLearningStateDigest(pptLearningState(JSON.parse(readFileSync(current,'utf8'))))!==match[1])throw Error('ppt_learning_task_facts_changed');
}
