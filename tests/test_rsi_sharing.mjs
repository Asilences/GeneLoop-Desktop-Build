import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {test} from 'node:test';
import {createHash} from 'node:crypto';
import {createRsiSharing, PRIVATE_DEFAULTS} from '../src/adapters/rsi_sharing.ts';
import {desktopNetworkAllowed,apiPurpose} from '../apps/desktop/src/privacy.ts';

const payload=JSON.stringify({format:'geneloop.rsi-shared-object/v1',kind:'tool_flow',trace:{
  format:'geneloop.rsi-learning-trace/v2',scene:'paper-proofreading',status:'completed',
  nodes:[{tool:'mcp__paper_checks__pin_document',outcome:'eligible_read'}],bindings:[],
}})+'\n';
const req=body=>new Request('http://local/api/harless/rsi-sharing',body===undefined?{}:{
  method:'POST',body:JSON.stringify(body),headers:{'Content-Type':'application/json'},
});
const preview=async sharing=>{const res=await sharing.handle(req({action:'preview',task_id:'owned'}));assert.equal(res.status,200);return res.json();};
const send=row=>({action:'send',preview_id:row.preview_id,sha256:row.sha256,consent:true});
async function sink(t,handler){
  const bodies=[],server=createServer(async(request,response)=>{
    const chunks=[];for await(const chunk of request)chunks.push(chunk);
    bodies.push({body:Buffer.concat(chunks).toString(),headers:request.headers});
    handler(request,response);
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  t.after(async()=>{server.closeAllConnections();await new Promise(done=>server.close(done));});
  return {url:'http://127.0.0.1:'+server.address().port+'/receive',bodies};
}

test('privacy defaults keep optional uploads off and preserve normal desktop task transports',async()=>{
  assert.deepEqual(PRIVATE_DEFAULTS,{trajectory_sharing:false,source_sharing:false,optional_telemetry:false});
  const sharing=createRsiSharing({prepare:async()=>payload,audit:()=>{}});
  const status=await(await sharing.handle(req())).json();
  assert.equal(status.enabled,false);
  const row=await preview(sharing);
  assert.equal((await sharing.handle(req(send(row)))).status,403);
  for(const path of ['/api/session/prompt','/api/session/uploadFileBinary','/api/harless/tasks','/api/remote.mux'])
    assert.equal(desktopNetworkAllowed('https://host.example'+path,'https://host.example/'),true);
  for(const path of ['/api/telemetry','/api/shared/source','/api/shared/trace','/api/unknown','/api/fixture/private']){
    assert.equal(apiPurpose(path),undefined);
    assert.equal(desktopNetworkAllowed('https://host.example'+path,'https://host.example/'),false);
  }
  assert.equal(desktopNetworkAllowed('wss://host.example/api/remote.mux','https://host.example/'),true);
  assert.equal(desktopNetworkAllowed('wss://host.example/api/telemetry','https://host.example/'),false);
  assert.equal(desktopNetworkAllowed('https://foreign.example/api/session/prompt','https://host.example/'),false);
});

test('sharing binds exact preview bytes, destination and one explicit consent',async t=>{
  const receiver=await sink(t,(_request,response)=>{response.end('ok');}),audit=[];
  const sharing=createRsiSharing({endpoint:receiver.url,allowLoopback:true,prepare:async()=>payload,audit:event=>audit.push(event)});
  const row=await preview(sharing);
  assert.equal(receiver.bodies.length,0);
  assert.equal(row.target,receiver.url);
  assert.equal(row.sha256,createHash('sha256').update(row.payload).digest('hex'));
  assert.equal(row.bytes,Buffer.byteLength(row.payload));
  for(const body of [{...send(row),consent:false},{...send(row),sha256:'changed'},
    {...send(row),payload:{password:'synthetic-secret'}},send({...row,preview_id:'foreign'})])
    assert.notEqual((await sharing.handle(req(body))).status,200);
  assert.equal(receiver.bodies.length,0);
  assert.equal((await sharing.handle(req(send(row)))).status,200);
  assert.equal(receiver.bodies.length,1);
  assert.equal(receiver.bodies[0].body,row.payload);
  assert.equal(receiver.bodies[0].headers.cookie,undefined);
  assert.equal(receiver.bodies[0].headers.authorization,undefined);
  assert.equal((await sharing.handle(req(send(row)))).status,409);
  assert.ok(audit.every(event=>Object.keys(event).join()==='event'));
});

test('cancel, expiry and restart invalidate consent without changing local material',async t=>{
  const receiver=await sink(t,(_request,response)=>response.end('ok'));
  const options={endpoint:receiver.url,allowLoopback:true,prepare:async()=>payload,audit:()=>{}};
  const sharing=createRsiSharing(options),row=await preview(sharing);
  assert.equal((await(await sharing.handle(req({action:'cancel',preview_id:row.preview_id}))).json()).state,'cancelled');
  assert.equal((await sharing.handle(req(send(row)))).status,409);
  const fresh=await preview(sharing);
  const now=Date.now;
  Date.now=()=>now()+11*60*1000;
  try{assert.equal((await sharing.handle(req(send(fresh)))).status,410);}
  finally{Date.now=now;}
  const beforeRestart=await preview(sharing);
  sharing.dispose();
  assert.equal((await createRsiSharing(options).handle(req(send(beforeRestart)))).status,410);
  assert.equal(receiver.bodies.length,0);
  assert.equal(options.prepare&&await options.prepare(),payload);
});

test('network interruption and cancellation during transfer keep an unknown receipt and never retry',{timeout:10000},async t=>{
  let arrived;
  const received=new Promise(resolve=>{arrived=resolve;});
  const receiver=await sink(t,()=>arrived());
  const sharing=createRsiSharing({endpoint:receiver.url,allowLoopback:true,prepare:async()=>payload,audit:()=>{}});
  const row=await preview(sharing),pending=sharing.handle(req(send(row)));
  await Promise.race([received,new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('receiver was not reached')),5000);timer.unref();})]);
  const cancelled=await(await sharing.handle(req({action:'cancel',preview_id:row.preview_id}))).json();
  assert.equal(cancelled.state,'unknown');
  assert.equal((await pending).status,502);
  assert.equal((await sharing.handle(req(send(row)))).status,409);
  assert.equal(receiver.bodies.length,1);
});

test('redirects, projection errors and unrecognized fields cannot create secondary uploads or raw error logs',async t=>{
  const receiver=await sink(t,(_request,response)=>{response.writeHead(302,{Location:'/other'});response.end();});
  const audit=[],sharing=createRsiSharing({endpoint:receiver.url,allowLoopback:true,prepare:async()=>payload,audit:event=>audit.push(event)});
  const row=await preview(sharing);
  assert.equal((await sharing.handle(req(send(row)))).status,502);
  assert.equal(receiver.bodies.length,1);
  const broken=createRsiSharing({prepare:async()=>{throw Error('/private/owner token=synthetic-secret');},audit:event=>audit.push(event)});
  const result=await broken.handle(req({action:'preview',task_id:'owned'}));
  assert.equal(result.status,409);
  assert.doesNotMatch(await result.text(),/private|synthetic-secret/);
  assert.doesNotMatch(JSON.stringify(audit),/private|synthetic-secret/);
  assert.equal((await broken.handle(req({action:'preview',task_id:'owned',source:{password:'synthetic-secret'}}))).status,400);
  for(const endpoint of ['https://user:pass@host.example/','http://127.0.0.1/','https://host.example/?token=x']){
    const value=await(await createRsiSharing({endpoint,prepare:async()=>payload,audit:()=>{}}).handle(req())).json();
    assert.equal(value.enabled,false);
  }
});

test('audit storage failure refuses the upload and returns no filesystem or credential exception',async t=>{
  const receiver=await sink(t,(_request,response)=>response.end('ok'));
  for(const failAt of ['preview','sending']){
    const sharing=createRsiSharing({endpoint:receiver.url,allowLoopback:true,prepare:async()=>payload,
      audit:({event})=>{if(event===failAt)throw Error('/private/account token=synthetic-secret');}});
    const first=await sharing.handle(req({action:'preview',task_id:'owned'}));
    const failed=failAt==='preview'?first:await sharing.handle(req(send(await first.json())));
    assert.equal(failed.status,503);
    assert.doesNotMatch(await failed.text(),/private\/account|synthetic-secret/);
  }
  assert.equal(receiver.bodies.length,0);
});
