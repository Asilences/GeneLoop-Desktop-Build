/** Protocol fixture: real packaged DSH, files, privacy, miner, certificate and read executor. No paid model. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {randomBytes,randomUUID} from 'node:crypto';
import {createRsiCollectionRoute} from '../../../scripts/harless_rsi_collection.mjs';
const app=fileURLToPath(new URL('../',import.meta.url)),require=createRequire(import.meta.url);
const output=mkdtempSync(join(process.env.GENELOOP_DESKTOP_VALIDATION_ROOT||tmpdir(),'gl-rsi-life-'));
const source=join(output,'source');mkdirSync(source);for(let i=1;i<=4;i++)writeFileSync(join(source,'doc'+i+'.txt'),'Public observation '+i+': '+(i===4?'fourth-current':'independent-'+i));
let origin,leases=0,models=0,failure;const tasks=new Map();
const receiver=createRsiCollectionRoute({dataDir:join(output,'receiver'),authorize:req=>req.headers.origin===origin});
const server=createServer(async(req,res)=>{
 const json=value=>{res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify(value));};
 try{
  if(await receiver(req,res,{id:'lifecycle-fixture'}))return;
  if(req.url==='/api/account/me')return json({user:{id:'lifecycle-fixture'}});
  if(req.url==='/api/harless/desktop-model/lease'){
   if(req.method==='DELETE')return json({ok:true});
   const token=randomBytes(32).toString('base64url');tasks.set(token,{index:++leases,step:0});return json({token,model:'deepseek-flash',toolsetVersion:4,localRsiTools:true});
  }
  assert.equal(req.url,'/api/harless/desktop-model/v1/chat/completions');
  const chunks=[];for await(const chunk of req)chunks.push(chunk);const body=JSON.parse(Buffer.concat(chunks));
  const row=tasks.get(req.headers.authorization?.slice(7));assert.ok(row);row.step++;models++;
  const results=body.messages.filter(m=>m.role==='tool');let call;
  if(row.index<=3){
   if(row.step===1)call=['local_document_pin',{path:'doc'+row.index+'.txt'}];
   else if(row.step===2)call=['local_document_read',{source_id:JSON.parse(results.at(-1).content).source_id,page:1}];
   else assert.ok(results.at(-1).content.includes('independent-'+row.index));
  }else{
   if(row.step===1)call=['local_motif_list',{}];
   else if(row.step===2){const list=JSON.parse(results.at(-1).content);assert.ok(list.length);assert.deepEqual(list[0].entry_parameters.local_document_read,['page']);call=['local_motif_run',{motif_id:list[0].id,bindings:JSON.stringify({local_document_pin:{path:'doc4.txt'},local_document_read:{page:1}})}];}
   else{const value=JSON.parse(results.at(-1).content);assert.equal(value.status,'completed');assert.ok(JSON.stringify(value).includes('fourth-current'),'actual current native file read, not a training reply');}
  }
  const delta=call?{tool_calls:[{index:0,id:randomUUID(),type:'function',function:{name:call[0],arguments:JSON.stringify(call[1])}}]}:{content:'Diagnostic task completed.'};
  const envelope={id:randomUUID(),object:'chat.completion.chunk',created:1,model:'protocol-fixture',choices:[{index:0,delta,finish_reason:null}]};
  res.writeHead(200,{'content-type':'text/event-stream'});res.write('data: '+JSON.stringify(envelope)+'\n\n');res.write('data: '+JSON.stringify({...envelope,choices:[{index:0,delta:{},finish_reason:call?'tool_calls':'stop'}],usage:{prompt_tokens:1,completion_tokens:1,total_tokens:2}})+'\n\n');res.end('data: [DONE]\n\n');
 }catch(error){failure=error;res.writeHead(500,{'content-type':'application/json'});res.end(JSON.stringify({error:'fixture assertion failed'}));}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));origin='http://127.0.0.1:'+server.address().port;
const env={...process.env,GENELOOP_RSI_LIFECYCLE:JSON.stringify({origin,source,output,profile:join(output,'profile'),packaged:process.env.GENELOOP_FILE_RECOVERY_PACKAGE})};delete env.ELECTRON_RUN_AS_NODE;
const child=spawn(require('electron'),[join(app,'test/local-rsi-lifecycle.cjs')],{cwd:app,env,windowsHide:true,stdio:'inherit'});
const code=await new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',resolve);});
await new Promise(r=>server.close(r));if(failure)throw failure;assert.equal(code,0);
console.log(JSON.stringify({passed:true,output,fixture_model_requests:models,paid_model_requests:0,tasks:leases,certification:'independent_trace_structure',current_file_reuse:true}));
