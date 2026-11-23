const assert=require('node:assert/strict');
const {app}=require('electron');
const {existsSync,readFileSync}=require('node:fs');
const {join}=require('node:path');
const {pathToFileURL}=require('node:url');
const {randomUUID}=require('node:crypto');
const fixture=JSON.parse(process.env.GENELOOP_FILE_RECOVERY_FIXTURE);
app.setPath('userData',fixture.profile);
const packaged=process.env.GENELOOP_FILE_RECOVERY_PACKAGE;
if(packaged){
 assert.ok(existsSync(join(packaged,'resources/app.asar')));
 Object.defineProperty(app,'isPackaged',{get:()=>true});
 Object.defineProperty(process,'resourcesPath',{value:join(packaged,'resources')});
 Object.defineProperty(process,'execPath',{value:join(packaged,'GeneLoop Desktop.exe')});
}

const wait=async(predicate,label)=>{
 const end=Date.now()+65000;
 while(Date.now()<end){if(await predicate())return;await new Promise(resolve=>setTimeout(resolve,100));}
 throw Error('Timed out: '+label);
};
app.whenReady().then(async()=>{
 const {LocalWorkspaceConversation}=await import(pathToFileURL(packaged?join(packaged,'resources/app.asar/dist/local-workspace.js'):join(__dirname,'../dist/local-workspace.js')).href);
 const create=()=>new LocalWorkspaceConversation({server:fixture.origin+'/',session:{fetch:(url,options)=>fetch(url,options)}});
 const workspace={id:'file-recovery-fixture',name:'File recovery',directory:fixture.source,updatedAt:Date.now()};
 const threadId=randomUUID(),local=create();
 try{
  const running=local.start(workspace,{threadId,scene:'files',prompt:'Inspect and classify invoice.txt, preserving originals.'},()=>{});
  await wait(()=>existsSync(join(fixture.output,'waiting')),'paid judgement completed and model waiting');
  local.cancel(workspace.id,threadId);await running;
  const [interrupted]=local.history(workspace);
  assert.equal(interrupted.recoverable,true);
  assert.equal(interrupted.updates.at(-1).status,'canceled');
  local.dispose();
  const recovered=create();
  try{
   await assert.rejects(()=>recovered.start(workspace,{threadId,recover:true,taskId:randomUUID()},()=>{}),/不可恢复/);
   await recovered.start(workspace,{threadId,recover:true,taskId:interrupted.taskId},()=>{});
   const rows=recovered.history(workspace);
   assert.equal(rows.length,1,'resume updates the original task');
   assert.equal(rows[0].taskId,interrupted.taskId);
   assert.equal(rows[0].sessionId,interrupted.sessionId);
   assert.equal(rows[0].recoverable,false);
   assert.equal(rows[0].updates.at(-1).status,'completed');
   assert.match(rows[0].updates.find(update=>update.kind==='report').report.name,/\.md$/);
   assert.equal(readFileSync(join(fixture.source,'invoice.txt'),'utf8'),'Invoice: microscope reagents. Total: 125 CNY.');
  }finally{recovered.dispose();}
 }finally{local.dispose();}
 app.exit(0);
}).catch(error=>{console.error(error.stack);app.exit(1);});
