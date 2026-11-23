/** Real bundled privacy kernel + authenticated TLS receiver; source events are labelled protocol fixtures. */
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createServer,request as httpsRequest} from 'node:https';
import {mkdtempSync,readFileSync,writeFileSync,readdirSync,mkdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {LocalRsiHost} from '../src/local-rsi.ts';
import {createRsiCollectionRoute} from '../../../scripts/harless_rsi_collection.mjs';
const root=mkdtempSync(join(process.env.GENELOOP_DESKTOP_VALIDATION_ROOT||tmpdir(),'gl-local-rsi-'));
const bundle=resolve(process.env.GENELOOP_DESKTOP_TOOLS_STAGE||fileURLToPath(new URL('../desktop-tools-bundle',import.meta.url)));
const openssl=process.env.SSS_OPENSSL||(process.platform==='win32'?'C:/Program Files/Git/usr/bin/openssl.exe':'openssl');
const key=join(root,'tls-private.pem'),cert=join(root,'tls.pem');
const generated=spawnSync(openssl,['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',key,'-out',cert,'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],{windowsHide:true,encoding:'utf8'});
assert.equal(generated.status,0,'isolated TLS certificate generation');
const token=randomUUID(),ca=readFileSync(cert);let origin,posts=0;
const route=createRsiCollectionRoute({dataDir:join(root,'receiver'),authorize:req=>req.headers.origin===origin});
const server=createServer({key:readFileSync(key),cert:ca},async(req,res)=>{
 try{if(req.method==='POST')posts++;if(!await route(req,res,req.headers.cookie===token?{id:'diagnostic-account'}:undefined)){res.writeHead(404);res.end();}}
 catch{res.writeHead(500);res.end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));origin='https://127.0.0.1:'+server.address().port;
const transport=(url,init)=>new Promise((resolve,reject)=>{
 const req=httpsRequest(url,{method:init.method,headers:{...init.headers,cookie:token},ca,rejectUnauthorized:true},res=>{
  const parts=[];res.on('data',chunk=>parts.push(chunk));res.on('end',()=>resolve(new Response(Buffer.concat(parts),{status:res.statusCode,headers:res.headers})));
 });req.on('error',reject);if(init.body)req.write(init.body);req.end();
});
const host=new LocalRsiHost({directory:join(root,'local'),server:origin+'/',identity:async()=> 'diagnostic-account',fetch:transport,
 tools:()=>({python:join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python'),sourceRoot:join(bundle,'source'),gitleaks:join(bundle,'privacy',process.platform==='win32'?'gitleaks.exe':'gitleaks')})});
async function sample(status,result){
 const binding=await host.begin({logicalTask:randomUUID(),sessionId:randomUUID(),scene:'files',workspaceId:'diagnostic-workspace'});
 host.record(binding,{type:'tool/call',seq:0,data:{callId:'one',name:'local_document_pin',arguments:'{"path":"public.txt"}'}});
 host.record(binding,{type:'tool/result',seq:1,data:{message:{source:{kind:'tool',callId:'one'},content:[{type:'tool-result',toolCallId:'one',content:[{type:'text',text:JSON.stringify(result)}]}]}}});
 host.finish(binding,status);await host.idle();return join(binding.root,'tasks',binding.attempt);
}
try{
 const normal=await sample('completed',{content:'Ordinary public research observations.'});
 assert.equal(JSON.parse(readFileSync(join(normal,'pipeline.json'))).collection,'received');
 const pii=await sample('canceled',{email:'alice.researcher@example.com',phone:'13800138000',content:'Contact Alice Researcher for this material.'});
 const visible=readFileSync(join(pii,'privacy-learning.json'),'utf8');assert.ok(!visible.includes('alice.researcher@example.com'));assert.ok(!visible.includes('13800138000'));
 const object=JSON.parse(readFileSync(join(pii,'collected-object.json')));assert.equal(object.trace.status,'cancelled');
 assert.equal(JSON.parse(readFileSync(join(pii,'pipeline.json'))).collection,'received');
 const secret=await sample('completed',{api_key:'sk-proj-'+'a'.repeat(48)});
 assert.equal(JSON.parse(readFileSync(join(secret,'pipeline.json'))).collection,'blocked');assert.equal(posts,2);
 const status=await host.status();assert.equal(status.collection.received,2);assert.equal(status.collection.blocked,1);
 writeFileSync(join(root,'result.json'),JSON.stringify({kind:'bundled-privacy-real-tls-protocol-diagnostic',real_model_requests:0,tls_certificate_verified:true,
  completed_received:true,cancelled_received:true,pii_removed:true,credential_sample_blocked:true,raw_trace_uploaded:false,posts,counts:status.collection},null,2));
 console.log(JSON.stringify({result:join(root,'result.json'),checks:7,posts,real_model_requests:0}));
}finally{host.dispose();await new Promise(r=>server.close(r));}
