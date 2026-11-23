/** Synthetic event/lifecycle diagnostics; no provider or scientific-quality claims. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import {resolve,join} from 'node:path';
import {createPptLearning,pptLearningPolicies} from '../src/adapters/web/learning/harless_ppt_learning.ts';
const python=process.env.SSS_PURE_CODE_PYTHON??process.env.SSS_PYTHON;
const root=resolve(import.meta.dirname,'..'),scope='a'.repeat(64),user='diagnostic-user';
const enabled=Boolean(python&&existsSync(python));
const read=path=>JSON.parse(readFileSync(path,'utf8'));
test('a normal paid task enables learning without silently enabling internal LLM scoring',()=>{
 assert.deepEqual(pptLearningPolicies({SSS_WEB_POLICY:'private-web-policy'}),{learning:'private-web-policy',review:undefined});
 assert.deepEqual(pptLearningPolicies({SSS_WEB_POLICY:'web',GENELOOP_PPT_REVIEW_POLICY:'internal-review'}),{learning:'web',review:'internal-review'});
 assert.deepEqual(pptLearningPolicies({SSS_WEB_POLICY:'web',GENELOOP_PPT_COMPONENT_LEARNING_POLICY:'',GENELOOP_PPT_REVIEW_POLICY:''}),{learning:'',review:''});
});
const storeFor=output=>join(output,'learning','ppt-'+createHash('sha256').update(user+'\0'+scope).digest('hex'));
test('an explicit evaluation freeze stops worker scheduling without changing runtime read methods',async()=>{
 const output=join(root,'.local/node-ppt-learning',randomUUID());mkdirSync(output,{recursive:true});
 const previous=process.env.GENELOOP_PPT_LEARNING_READONLY;
 try{
  process.env.GENELOOP_PPT_LEARNING_READONLY='1';
  const manager=createPptLearning({output,user,scope,python:process.execPath,taskIds:()=>{throw Error('frozen learning must not inspect new tasks');}});
  manager.schedule();await manager.idle();
  assert.equal(existsSync(join(storeFor(output),'request.json')),false);
  assert.equal(typeof manager.workflow,'function');assert.equal(typeof manager.program,'function');
 }finally{
  if(previous===undefined)delete process.env.GENELOOP_PPT_LEARNING_READONLY;else process.env.GENELOOP_PPT_LEARNING_READONLY=previous;
  rmSync(output,{recursive:true,force:true});
 }
});
function add(output,index,paired=false){
 const code=`from src.adapters.filesystem_paths import Path\nfrom tests.test_web_ppt_learning import task,pair,save\nout=Path(${JSON.stringify(output)})\nstore=Path(${JSON.stringify(storeFor(output))})\nstore.mkdir(parents=True,exist_ok=True)\np=store/'request.json'\nif not p.exists():save(p,{'schema_version':1,'output':str(out),'user':'diagnostic-user','scope':'a'*64,'task_ids':[],'automatic_structural_learning':True})\nif not (out/'comparisons.json').exists():save(out/'comparisons.json',{'version':1,'principal':'diagnostic-user','turns':[]})\nowned=(out,store,p)\nn=${index}\nbase=task(owned,n*10,source=n,cost=.003)\nopt=task(owned,n*10+1,source=n,mode='execute',version='round-0001',cost=.001) if ${paired?'True':'False'} else None\npair(owned,n,base,opt,review=False)`;
 execFileSync(python,['-c',code],{cwd:root,env:{...process.env,PYTHONUTF8:'1'},stdio:'pipe'});
}

test('PPT learning worker failure cannot break chat or escape an already removed output',async()=>{
 const output=join(root,'.local/node-ppt-learning',randomUUID());mkdirSync(output,{recursive:true});
 const manager=createPptLearning({output,user,scope,python:process.execPath,taskIds:()=>[]});
 manager.schedule();rmSync(output,{recursive:true,force:true});
 try{await manager.idle();}finally{rmSync(output,{recursive:true,force:true});}
});

test('review has its own request and failure status and never suspends the learned library',async()=>{
 const output=join(root,'.local/node-ppt-learning',randomUUID());mkdirSync(output,{recursive:true});
 const old=process.env.GENELOOP_PPT_REVIEW_POLICY;
 try{
  process.env.GENELOOP_PPT_REVIEW_POLICY='diagnostic-only-no-network';
  const manager=createPptLearning({output,user,scope,python:process.execPath,taskIds:()=>[]});
  manager.schedule();await manager.idle();
  const store=storeFor(output);
  assert.equal(read(join(store,'request.json')).worker_mode,'learning');
  assert.equal(read(join(store,'review-request.json')).worker_mode,'review');
  assert.equal(read(join(store,'review-worker-status.json')).status,'failed');
  assert.equal(existsSync(join(store,'suspended.json')),false);
 }finally{
  if(old===undefined)delete process.env.GENELOOP_PPT_REVIEW_POLICY;else process.env.GENELOOP_PPT_REVIEW_POLICY=old;
  rmSync(output,{recursive:true,force:true});
 }
});

test('Single-task completion captures immutable evidence and schedules certification without comparison records',{skip:!enabled},async()=>{
 const output=join(root,'.local/node-ppt-learning',randomUUID());mkdirSync(output,{recursive:true});
 try{
  const ids=[],manager=createPptLearning({output,user,scope,python,taskIds:()=>ids});
  for(let n=1;n<=3;n++){
   const script=`from src.adapters.filesystem_paths import Path\nimport json\nfrom tests.test_web_ppt_learning import task,single,save\nout=Path(${JSON.stringify(output)})\nstore=Path(${JSON.stringify(storeFor(output))})\nstore.mkdir(parents=True,exist_ok=True)\np=store/'request.json'\nif not p.exists():save(p,{'schema_version':1,'output':str(out),'user':'diagnostic-user','scope':'a'*64,'task_ids':[],'automatic_structural_learning':True})\nd=task((out,store,p),${n})\nr=single((out,store,p),d)\n(d/'ppt-learning-delivery.json').unlink()\nprint(json.dumps({'task_id':d.name,'session_id':r['session_id'],'artifacts':r['artifacts']}))`;
   const data=JSON.parse(execFileSync(python,['-c',script],{cwd:root,env:{...process.env,PYTHONUTF8:'1'},encoding:'utf8'}));
   ids.push(data.task_id);
   const task={request:{task_id:data.task_id,session_id:data.session_id,mode:'baseline'},scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},
    output:join(output,'tasks',data.task_id),status:'completed'};
   manager.captureSingle(task,data.artifacts);manager.captureSingle(task,data.artifacts);
   assert.throws(()=>manager.captureSingle(task,[]),/delivery_changed/);
  }
  assert.equal(existsSync(join(output,'comparisons.json')),false);
  manager.schedule();await manager.idle();
  const scene={id:'ppt',ppt_execution_strategy:'ppt_master',config_sha256:'single-original',instructions:'same',allowed_tools:[]};
  assert.equal(manager.resolve(scene).learning_phase,'probation',JSON.stringify({worker:read(join(storeFor(output),'worker-log.json')),status:read(join(storeFor(output),'status.json'))}));
  assert.equal(existsSync(join(output,'comparisons.json')),false);
  assert.equal(read(join(storeFor(output),'status.json')).extra_provider_requests,0);
  assert.equal(createPptLearning({output,user:'other',scope,python,taskIds:()=>ids}).resolve(scene),scene);
 }finally{rmSync(output,{recursive:true,force:true});}
});

test('PPT lifecycle: automatic certification, future-only probation, promotion, restart, veto and integrity guards',{skip:!enabled},async()=>{
 const segments=process.platform==='win32'?['deep-certification-'+ 'x'.repeat(72)]:[];
 const output=join(root,'.local/node-ppt-learning',...segments,randomUUID());mkdirSync(output,{recursive:true});
 try{
  const ids=[],config={output,user,scope,python,taskIds:()=>ids};
  for(let n=1;n<=3;n++){add(output,n);ids.push((n*10).toString(16).padStart(32,'0'));}
  const manager=createPptLearning(config),base={id:'ppt',ppt_execution_strategy:'ppt_master',config_sha256:'original',instructions:'unchanged',allowed_tools:['unchanged']};
  assert.equal(manager.resolve(base),base);
  manager.schedule();manager.schedule();await manager.idle();
  const one=manager.resolve(base);assert.equal(one.learning_version,'round-0001',JSON.stringify({worker:read(join(storeFor(output),'worker-log.json')),status:read(join(storeFor(output),'status.json'))}));assert.equal(one.learning_phase,'probation');
  assert.equal(one.runtime_kind,'ppt_master_v2');assert.equal(one.instructions,'unchanged');assert.deepEqual(one.allowed_tools,['unchanged']);
  assert.ok(!one.runtime_library.startsWith('\\\\?\\'),'Persisted evidence uses logical paths, not Windows IO namespace paths');
  if(process.platform==='win32')assert.ok(one.runtime_library.length>260,'Certification must exercise a real deep Windows learning path');
  assert.equal(base.learning_version,undefined);
  // Real API reads refresh these projections after certification. They are
  // neither source-version changes nor new execution evidence.
  const statePath=join(output,'tasks',ids[0],'task-state.json'),state=read(statePath);
  state.progress={text:'refreshed'};state.stats.global_upstream_requests=99999;state.stats.global_estimated_cost_usd=123;
  writeFileSync(statePath,JSON.stringify(state));assert.equal(manager.resolve(base).learning_phase,'probation');
  state.failure='late_failure';writeFileSync(statePath,JSON.stringify(state));assert.equal(manager.resolve(base),base);
  delete state.failure;writeFileSync(statePath,JSON.stringify(state));assert.equal(manager.resolve(base).learning_phase,'probation');
  assert.equal(createPptLearning({...config,user:'other'}).resolve(base),base);
  assert.equal(createPptLearning({...config,scope:'b'.repeat(64)}).resolve(base),base);
  assert.equal(manager.resolve({...base,id:'paper-proofreading'}).learning_version,undefined);
  for(let n=4;n<=5;n++){add(output,n,true);ids.push(...[n*10,n*10+1].map(i=>i.toString(16).padStart(32,'0')));manager.schedule();await manager.idle();}
  const active=manager.resolve(base);assert.equal(active.learning_phase,'active');
  const status=read(join(storeFor(output),'status.json'));assert.equal(status.quality_cost_promoted,false);assert.equal(status.mechanical_cost_promoted,true);
  assert.equal(createPptLearning(config).resolve(base).learning_phase,'active');
  for(const path of [active.runtime_library,join(storeFor(output),'round-0001/promotion.json'),join(storeFor(output),'round-0001/evaluation.json')]){
   const bytes=readFileSync(path);writeFileSync(path,'{}');assert.equal(manager.resolve(base),base);writeFileSync(path,bytes);
  }
  // Simulate an older worker clearing the temporary suspension after a veto.
  // The persistent generation still prevents stale admission.
  const feedback=join(storeFor(output),'feedback-version.json');
  writeFileSync(feedback,JSON.stringify({version:'concurrent-veto'}));
  assert.equal(manager.resolve(base),base);rmSync(feedback);
  const comparisons=read(join(output,'comparisons.json')),snapshot=comparisons.turns.at(-1);
  assert.throws(()=>manager.review(snapshot,{lane:'motif',output_sha256:'wrong'}),/version_changed/);
  snapshot.lanes.motif.feedback='down';writeFileSync(join(output,'comparisons.json'),JSON.stringify(comparisons));
  manager.negativeFeedback(snapshot);assert.equal(manager.resolve(base),base);await manager.idle();
  assert.equal(read(join(storeFor(output),'selected.json')).phase,'disabled');assert.equal(manager.resolve(base),base);
 }finally{rmSync(output,{recursive:true,force:true});}
});
