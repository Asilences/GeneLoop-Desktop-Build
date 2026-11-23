/** Real Kouri API acceptance, only with an explicitly supplied isolated trial plan. */
const {app}=require('electron');
const assert=require('node:assert/strict');
const {join}=require('node:path');
const {pathToFileURL}=require('node:url');
const {readFileSync,writeFileSync,mkdirSync,readdirSync}=require('node:fs');
const {readFileSync:readOriginalFile}=require('original-fs');
const {createHash,randomUUID}=require('node:crypto');
const plan=JSON.parse(readFileSync(process.env.GENELOOP_RSI_REAL_PLAN_FILE,'utf8'));
assert.equal(plan.real_model_authorized,true);
assert.equal(new URL(plan.server).hostname,'127.0.0.1');
mkdirSync(plan.profile,{recursive:true});
process.on('uncaughtException',error=>{console.error(error.stack);app.exit(1);});
app.setPath('userData',plan.profile);
Object.defineProperty(app,'isPackaged',{get:()=>true});
Object.defineProperty(process,'resourcesPath',{value:join(plan.packaged,'resources')});
Object.defineProperty(process,'execPath',{value:join(plan.packaged,'GeneLoop Desktop.exe')});
const sha=b=>createHash('sha256').update(b).digest('hex');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
app.whenReady().then(async()=>{
 const {LocalWorkspaceConversation}=await import(pathToFileURL(join(plan.packaged,'resources/app.asar/dist/local-workspace.js')).href);
 const cookie=JSON.parse(readFileSync(plan.cookieFile,'utf8')).map(c=>c.name+'='+c.value).join('; ');
 const source=join(plan.output,'source');mkdirSync(source,{recursive:true});
 const rows=[['alpha.txt','Public observation alpha: sensor average is 12.'],['beta.txt','Public observation beta: sensor average is 23.'],['gamma.txt','Public observation gamma: sensor average is 34.'],['delta.txt','Public observation delta: sensor average is 45.']];
 for(const [name,value] of rows)writeFileSync(join(source,name),value);
 const client={fetch:(url,init={})=>{assert.equal(new URL(url).origin,new URL(plan.server).origin);return fetch(url,{...init,headers:{...init.headers,...(init.credentials==='omit'?{}:{cookie})}});}};
 const run=new LocalWorkspaceConversation({server:plan.server,session:client,allowLoopback:true});
 const workspace={id:'rsi-real-trial',name:'RSI real trial',directory:source,updatedAt:Date.now()};
 const results=[];
 try{
  if(plan.drain_only){
   let status;const deadline=Date.now()+130000;
   do{status=await run.rsiStatus();if((status.collection.received??0)>=plan.expected_receipts)break;await pause(500);}while(Date.now()<deadline);
   assert.ok((status.collection.received??0)>=plan.expected_receipts);
   writeFileSync(join(plan.output,'real-drain-result.json'),JSON.stringify({paid_model_requests:0,counts:status.collection,mandatory:status.mandatory},null,2));
   console.log('existing real task objects reconciled',status.collection.received);
  }else{
  for(let index=0;index<(plan.task_limit??rows.length);index++){
   const [name]=rows[index];const prior=run.history(workspace).find(task=>task.prompt.includes(name)&&task.updates.filter(e=>e.kind==='done').at(-1)?.status==='completed');
   const threadId=prior?.threadId??randomUUID(),updates=prior?.updates??[];
   const prompt=index<3?'先调用 local_document_pin 固定当前目录的 '+name+'，再调用 local_document_read 读取第1页。请仅用一句话回答该观测均值，不写报告，不需提问。':
    '请用已经学得的本机只读 Motif 读取当前目录 delta.txt 第1页：先查看本机可用能力，再给它本轮的路径和页码。仅用一句话回答观测均值，不写报告。';
   if(!prior)await run.start(workspace,{prompt,scene:'files',threadId},event=>updates.push(event));
   const outcome=updates.filter(e=>e.kind==='done').at(-1);assert.equal(outcome?.status,'completed','normal local task '+(index+1));
   const deadline=Date.now()+130000;let status;
   const roots=readdirSync(join(plan.profile,'local-rsi')).filter(x=>/^[a-f0-9]{64}$/.test(x));assert.equal(roots.length,1);
   const root=join(plan.profile,'local-rsi',roots[0]);
   const tasks=readdirSync(join(root,'tasks')).map(id=>({id,...JSON.parse(readFileSync(join(root,'tasks',id,'task.json')))}));
   const task=tasks.find(t=>t.session_id===run.history(workspace).find(t=>t.threadId===threadId).sessionId);assert.ok(task);
   const pipeline=join(root,'tasks',task.id,'pipeline.json');let received=false;
   while(Date.now()<deadline){status=await run.rsiStatus();try{received=JSON.parse(readFileSync(pipeline)).collection==='received';}catch{}if(received)break;await pause(500);}
   assert.ok(received,'collector acknowledged task '+(index+1));
   if(index===2)assert.ok(status.learning.certified>=1,'independent local structural certification');
   const events=readFileSync(join(root,'tasks',task.id,'events.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
   const calls=events.filter(e=>e.type==='tool/call').map(e=>e.data.name);
   if(index<3){assert.ok(calls.includes('local_document_pin'));assert.ok(calls.includes('local_document_read'));}
   else assert.ok(calls.includes('local_motif_run'),'real successor invoked the local learned program');
   results.push({task:index+1,reused_existing_acceptance:Boolean(prior),status:outcome.status,calls,privacy:'admitted',collection:'received',structurally_certified:status.learning.certified??0});
   writeFileSync(join(plan.output,'real-result.json'),JSON.stringify({kind:'packaged-windows-real-kouri-local-rsi',version:'0.4.1',platform:process.platform,
    application_asar_sha256:sha(readOriginalFile(join(plan.packaged,'resources/app.asar'))),rsi_source_sha256:sha(readFileSync(join(plan.packaged,'resources/geneloop-tools/source/src/adapters/desktop/desktop_rsi.py'))),
    collection_transport:'explicit-loopback-over-existing-SSH-tunnel',quality_or_efficiency_claim:false,results},null,2));
   console.log('real local task completed',index+1,'tool calls',calls.length,'local motifs',status.learning.certified??0);
  }}
 }finally{run.dispose();}
 app.exit(0);
}).catch(error=>{writeFileSync(join(plan.output,'real-failure.json'),JSON.stringify({name:error.name,message:error.message},null,2));console.error(error.stack);app.exit(1);});
