const {app}=require('electron');
const assert=require('node:assert/strict');
const {mkdirSync,writeFileSync}=require('node:fs');
const {join}=require('node:path');
const {pathToFileURL}=require('node:url');
const {randomUUID}=require('node:crypto');
const plan=JSON.parse(process.env.GENELOOP_RSI_LIFECYCLE);mkdirSync(plan.profile,{recursive:true});app.setPath('userData',plan.profile);
Object.defineProperty(app,'isPackaged',{get:()=>true});Object.defineProperty(process,'resourcesPath',{value:join(plan.packaged,'resources')});Object.defineProperty(process,'execPath',{value:join(plan.packaged,'GeneLoop Desktop.exe')});
app.whenReady().then(async()=>{
 const {LocalWorkspaceConversation}=await import(pathToFileURL(join(plan.packaged,'resources/app.asar/dist/local-workspace.js')).href);
 const runner=new LocalWorkspaceConversation({server:plan.origin+'/',session:{fetch:(url,init)=>fetch(url,init)},allowLoopback:true});
 const workspace={id:'diagnostic',name:'Diagnostic',directory:plan.source,updatedAt:Date.now()},results=[];
 try{
  for(let i=1;i<=4;i++){
   const updates=[];await runner.start(workspace,{prompt:'Read independent public document '+i,scene:'files',threadId:randomUUID()},e=>updates.push(e));
   assert.equal(updates.filter(e=>e.kind==='done').at(-1)?.status,'completed');
   let status;const deadline=Date.now()+130000;
   do{status=await runner.rsiStatus();if(status.collection.received===i)break;await new Promise(r=>setTimeout(r,300));}while(Date.now()<deadline);
   assert.equal(status.collection.received,i);
   const catalog=await runner.rsiCatalog();
   if(i>=3){
    assert.ok(status.learning.certified>=1);
    const motif=catalog.find(row=>row.scene==='files'&&row.tools.join('/')==='local_document_pin/local_document_read');
    assert.ok(motif,'native certificate is visible to the account catalog');
    assert.equal(motif.witnesses,3);assert.equal(motif.reuses,i===4?1:0);
   }else assert.deepEqual(catalog,[]);
   results.push({task:i,received:true,structural_certificates:status.learning.certified??0,catalog_entries:catalog.length});
  }
  writeFileSync(join(plan.output,'result.json'),JSON.stringify({kind:'packaged-protocol-diagnostic',paid_model_requests:0,results},null,2));
 }finally{runner.dispose();}
 app.exit(0);
}).catch(error=>{console.error(error.stack);app.exit(1);});
