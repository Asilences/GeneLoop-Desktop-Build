import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,readdirSync,rmSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createServer} from 'node:http';
import {createHash,randomUUID} from 'node:crypto';
import {createRsiCollectionRoute} from '../scripts/harless_rsi_collection.mjs';
import {validCollectedObject,COLLECTION_PATH} from '../apps/desktop/src/rsi-object.ts';
import {LocalRsiHost} from '../apps/desktop/src/local-rsi.ts';
const object=(status='completed')=>({format:'geneloop.rsi-collected-object/v1',kind:'tool_flow',trace:{format:'geneloop.rsi-learning-trace/v4',scene:'generic',status,nodes:[{tool:'tool-0',outcome:'observed_success'}],bindings:[]}});
const hash=b=>createHash('sha256').update(b).digest('hex');
const roots=[];const temporary=()=>{const p=mkdtempSync(join(tmpdir(),'geneloop-rsi-'));roots.push(p);return p;};
test.after(()=>{for(const p of roots)rmSync(p,{recursive:true,force:true});});
test('collected objects retain true outcomes and reject every content-bearing extension',()=>{
 for(const status of ['completed','cancelled','failed','interrupted'])assert.ok(validCollectedObject(object(status)));
 for(const mutate of [v=>v.trace.content=['PRIVATE_CANARY'],v=>v.trace.scene='customer-name',v=>v.trace.nodes[0].tool='read_private_customer',v=>v.trace.bindings.push({path:'secret'}),v=>v.trace.nodes[0].arguments='secret',v=>v.trace.status='running',v=>v.trace.nodes[0].tool='tool-3']){
  const value=object();mutate(value);assert.equal(validCollectedObject(value),false);
 }
});
test('authenticated durable receiver: duplicate, lost response lookup, account isolation and conflicts',async()=>{
 const dir=temporary(),route=createRsiCollectionRoute({dataDir:dir,authorize:req=>req.headers.origin==='https://collector.test'});
 const server=createServer(async(req,res)=>{try{if(!await route(req,res,req.headers.cookie?{id:req.headers.cookie}:undefined)){res.writeHead(404);res.end();}}catch{res.writeHead(500);res.end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port+COLLECTION_PATH;
 const id=randomUUID(),body=JSON.stringify(object()),headers={cookie:'account-a',origin:'https://collector.test','content-type':'application/json','x-geneloop-object-id':id,'x-geneloop-object-sha256':hash(body)};
 try{
  assert.equal((await fetch(url,{method:'POST',headers:{...headers,cookie:''},body})).status,401);
  const first=await fetch(url,{method:'POST',headers,body});assert.equal(first.status,201);const receipt=await first.json();
  const second=await fetch(url,{method:'POST',headers,body});assert.equal(second.status,200);assert.deepEqual(await second.json(),receipt);
  assert.deepEqual(await (await fetch(url+'?object_id='+id,{headers:{cookie:'account-a'}})).json(),receipt);
  assert.equal((await fetch(url+'?object_id='+id,{headers:{cookie:'account-b'}})).status,404);
  const changed=JSON.stringify(object('failed'));
  assert.equal((await fetch(url,{method:'POST',headers:{...headers,'x-geneloop-object-sha256':hash(changed)},body:changed})).status,409);
  const raw=JSON.stringify({...object(),raw:'PRIVATE_CANARY'});
  assert.equal((await fetch(url,{method:'POST',headers:{...headers,'x-geneloop-object-id':randomUUID(),'x-geneloop-object-sha256':hash(raw)},body:raw})).status,422);
  assert.equal((await fetch(url,{method:'POST',headers:{...headers,origin:'https://attacker.test'},body})).status,403);
  const account=join(dir,'rsi-collected',hash('account-a'));assert.equal(readdirSync(account).length,1);
  assert.ok(!readFileSync(join(account,id+'.json'),'utf8').includes('PRIVATE_CANARY'));
 }finally{await new Promise(r=>server.close(r));}
});
test('native outbox survives lost ACK/restart; retries use same ID and never carry raw events',async()=>{
 const base=temporary(),source=join(base,'source'),adapter=join(source,'src','adapters','desktop');mkdirSync(adapter,{recursive:true});
 // Protocol fixture only. Real privacy dependencies/normal task admission are checked separately.
 writeFileSync(join(adapter,'desktop_rsi.py'),`import json,sys,pathlib\np=pathlib.Path(sys.argv[2])/'tasks'/sys.argv[3]\n(p/'collected-object.json').write_text(${JSON.stringify(JSON.stringify(object()))})\nprint(json.dumps({'privacy':'admitted','has_object':True,'learning':{'state':'waiting_for_independent_evidence'}}))\n`);
 let uploads=0,lost=true,stored,notice=0,current='account-a';
 const options={directory:join(base,'accounts'),server:'https://collector.test',identity:async()=>current,
  tools:()=>({python:process.env.SSS_PYTHON||'python',sourceRoot:source,gitleaks:join(base,'unused-fixture.exe')}),notice:async()=>{notice++;},
  fetch:async(url,init)=>{
   assert.ok(url.startsWith('https://collector.test/'));
   if(init.method==='GET')return stored?Response.json(stored):Response.json({error:'not_found'},{status:404});
   uploads++;assert.ok(!init.body.includes('PRIVATE_CANARY'));assert.ok(validCollectedObject(JSON.parse(init.body)));
   stored={object_id:init.headers['x-geneloop-object-id'],sha256:hash(init.body),receipt_id:randomUUID(),accepted:true};
   if(lost){lost=false;throw Error('connection lost after acceptance');}return Response.json(stored);
  }};
 let host=new LocalRsiHost(options);
 const binding=await host.begin({logicalTask:randomUUID(),sessionId:randomUUID(),scene:'files',workspaceId:'workspace'});
 host.record(binding,{type:'tool/call',data:{callId:'one',name:'local_read',arguments:'{"path":"PRIVATE_CANARY"}'}});
 host.finish(binding,'completed');await host.idle();
 assert.equal(uploads,1);assert.equal((await host.status()).collection.unknown,1);host.dispose();
 host=new LocalRsiHost(options);host.schedule();await host.idle();assert.equal(uploads,1);assert.equal((await host.status()).collection.received,1);assert.equal(notice,1);
 current='account-b';assert.deepEqual((await host.status()).collection,{});host.dispose();
});

test('oversized derived capture is blocked without throwing into normal task completion',async()=>{
 const base=temporary();let sent=0;
 const host=new LocalRsiHost({directory:base,server:'https://collector.test',identity:async()=> 'account',tools:()=>undefined,
  fetch:async()=>{sent++;throw Error('no upload expected');}});
 const binding=await host.begin({logicalTask:randomUUID(),sessionId:randomUUID(),scene:'files',workspaceId:'workspace'});
 assert.doesNotThrow(()=>host.record(binding,{type:'assistant/message',data:{content:'x'.repeat(32*1024*1024)}}));
 assert.doesNotThrow(()=>host.finish(binding,'completed'));await host.idle();
 assert.equal((await host.status()).collection.blocked,1);assert.equal(sent,0);host.dispose();
});

test('opening after 90 days removes both raw and derived copies before any transmission',async()=>{
 const base=temporary();let sent=0;
 const host=new LocalRsiHost({directory:base,server:'https://collector.test',identity:async()=> 'account',tools:()=>undefined,
  fetch:async()=>{sent++;throw Error('no upload expected');}});
 const binding=await host.begin({logicalTask:randomUUID(),sessionId:randomUUID(),scene:'files',workspaceId:'workspace'});
 const dir=join(binding.root,'tasks',binding.attempt),meta=JSON.parse(readFileSync(join(dir,'task.json')));
 writeFileSync(join(dir,'task.json'),JSON.stringify({...meta,at:Date.now()-91*86400000}));
 for(const name of ['privacy-learning.json','admission.json','collected-object.json'])writeFileSync(join(dir,name),'PRIVATE_CANARY');
 host.finish(binding,'completed');await host.idle();
 for(const name of ['events.jsonl','privacy-learning.json','admission.json','collected-object.json'])assert.equal(existsSync(join(dir,name)),false);
 assert.equal(sent,0);host.dispose();
});
