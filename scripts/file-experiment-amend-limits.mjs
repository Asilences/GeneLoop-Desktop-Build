/** Host-only quota amendment. Keeps the original job, grants and every counter. */
import {readFileSync,writeFileSync,existsSync,realpathSync} from 'node:fs';
import {resolve,dirname,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {OperationJob} from '../src/adapters/operation_job.ts';
import {digest} from '../src/adapters/file_workflow_job.ts';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export function amend(jobPath,authorizationPath){
 const authPath=realpathSync(authorizationPath),local=relative(resolve(root,'.local'),authPath);
 if(!local||local==='..'||local.startsWith('..'+sep))throw Error('host authorization must be private');
 const auth=JSON.parse(readFileSync(authPath,'utf8'));
 if(auth.format!=='sss-file-experiment-unlimited-authorization-v1'||auth.explicit_human_authorization!==true
    ||auth.scope!=='current-file-rsi-experiments'||!Array.isArray(auth.effective_limits)
    ||auth.effective_limits.length!==5||auth.effective_limits.some(v=>v!==null))throw Error('explicit unlimited experiment authorization required');
 const job=new OperationJob(root,jobPath),state=job.load();job.validateBinding(state);
 if(!['running','paused','limit_exhausted'].includes(state.status)||Object.keys(state.pending).length)throw Error('only a settled nonterminal original job can be amended');
 if(state.owner_pid){try{process.kill(state.owner_pid,0);throw Error('original task owner still active');}catch(e){if(e.code!=='ESRCH')throw e;}}
 const before={...state.limits},counters={requests:state.requests,steps:state.steps,repairs:state.repairs,checks:state.checks,spent_units:state.spent_units};
 state.limits={budget_usd:null,max_requests:null,max_steps:null,max_output:null,max_repairs:null};
 const previousStatus=state.status;
 if(state.status==='limit_exhausted')state.status='paused';
 const detail={authorization_path:authPath,authorization_sha256:digest(auth),before,after:{...state.limits},counters,
   previous_status:previousStatus,status:state.status,
   original_task_sha256:state.task_sha256,original_execution_version_sha256:state.execution_version_sha256};
 const result=job.commit(state,'human_authorized_quota_amendment',detail);
 for(const [k,v] of Object.entries(counters))if(result[k]!==v)throw Error('original counters changed');
 return {job:resolve(jobPath),limits:result.limits,counters_preserved:counters,task_and_permissions_unchanged:true};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const args=JSON.parse(readFileSync(0,'utf8'));console.log(JSON.stringify(amend(args.job,args.authorization)));}
 catch(e){console.error(String(e));process.exitCode=1;}
}
