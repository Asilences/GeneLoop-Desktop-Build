import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {join,resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {OperationJob} from '../src/adapters/operation_job.ts';
import {amend} from '../scripts/file-experiment-amend-limits.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const enabled={skip:!process.features?.typescript};
function fixture(){
 const home=join(root,'.local','unlimited-tests',randomUUID());mkdirSync(home,{recursive:true});
 const task=join(home,'task.json');writeFileSync(task,JSON.stringify({id:'diagnostic',allowed_operations:[]}));
 const path=join(home,'job.json');const job=new OperationJob(root,path);
 job.apply('init',{task_file:task,delivery_root:join(home,'delivery'),execution_version_sha256:'a'.repeat(64),
  limits:{budget_usd:1,max_requests:2,max_steps:2,max_output:4000,max_repairs:2}});
 const authorization=join(home,'authorization.json');
 const auth={format:'sss-file-experiment-unlimited-authorization-v1',explicit_human_authorization:true,
  scope:'current-file-rsi-experiments',effective_limits:[null,null,null,null,null]};
 writeFileSync(authorization,JSON.stringify(auth));
 return {home,path,job,task,authorization,auth,close:()=>rmSync(home,{recursive:true,force:true})};
}
test('quota amendment retains counters, task grants and history and permits spending beyond old limits',enabled,()=>{
 const f=fixture();try{
  for(let i=0;i<2;i++){
   const r=f.job.apply('reserve',{upper_usd:.1,model:'deepseek-flash',request_sha256:'b'.repeat(64)});
   f.job.apply('settle',{request_id:r.request_id,model:'deepseek-flash',observed_usd:.1});
  }
  assert.equal(f.job.apply('reserve',{upper_usd:.1,model:'deepseek-flash',request_sha256:'b'.repeat(64)}).admitted,false);
  const before=f.job.load(),originalTask=readFileSync(f.task,'utf8');
  const value=amend(f.path,f.authorization),after=f.job.load();
  assert.deepEqual(after.limits,{budget_usd:null,max_requests:null,max_steps:null,max_output:null,max_repairs:null});
  for(const key of ['requests','steps','repairs','checks','spent_units','task_sha256','execution_version_sha256'])assert.equal(after[key],before[key]);
  assert.equal(readFileSync(f.task,'utf8'),originalTask);assert.equal(value.task_and_permissions_unchanged,true);
  assert.equal(after.status,'paused');
  f.job.apply('recover',{execution_version_sha256:after.execution_version_sha256,owner_pid:process.pid});
  const more=f.job.apply('reserve',{upper_usd:.9,model:'deepseek-flash',request_sha256:'b'.repeat(64)});
  assert.equal(more.admitted,true);assert.equal(more.state.requests,3);assert.ok(more.state.spent_units>1e9);
  assert.throws(()=>amend(f.path,f.authorization),/settled|owner still active/);
 }finally{f.close();}
});
test('missing human authorization or changed task bytes cannot remove a quota',enabled,()=>{
 const f=fixture();try{
  writeFileSync(f.authorization,JSON.stringify({...f.auth,explicit_human_authorization:false}));
  assert.throws(()=>amend(f.path,f.authorization),/explicit unlimited/);
  writeFileSync(f.authorization,JSON.stringify(f.auth));writeFileSync(f.task,'changed');
  assert.throws(()=>amend(f.path,f.authorization),/frozen task\/permission/);
 }finally{f.close();}
});
