import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {test} from 'node:test';
import {LocalFrontendHost} from '../apps/desktop/src/frontend.ts';
import {Conversation} from '../apps/desktop/ui/desktop/conversation.js';
import {promptContent} from '../apps/desktop/ui/desktop/composer.js';
import {desktopNetworkAllowed} from '../apps/desktop/src/privacy.ts';

test('本机任务的既有模型接口可连接同一服务，未知出口和跨源仍拒绝',()=>{
  const server='https://fixture.example/';
  for(const path of ['lease','v1/chat/completions','video/render'])
    assert.equal(desktopNetworkAllowed(server+'api/harless/desktop-model/'+path,server),true);
  for(const url of [server+'api/harless/desktop-model/upload',server+'api/training/upload',
    'https://foreign.example/api/harless/desktop-model/lease'])
    assert.equal(desktopNetworkAllowed(url,server),false);
});

test('独立桌面只提供自己的页面和资源，不获取网页HTML、模块图或远程脚本',async()=>{
  const directory=mkdtempSync(join(tmpdir(),'geneloop-ui-')),network=[];
  try{
    writeFileSync(join(directory,'index.html'),'<main>INDEPENDENT_DESKTOP</main>');
    writeFileSync(join(directory,'app.js'),'OWN_RENDERER');
    const host=new LocalFrontendHost({server:'https://fixture.example/',ui:directory,assets:directory,fail:assert.fail,session:{fetch:async request=>{network.push(request.url);return new Response('API_STREAM',{headers:{'content-encoding':'gzip','content-length':'900'}});}}});
    const get=path=>host.fetch(new Request('https://fixture.example'+path));
    for(const path of ['/','/login','/starting'])assert.equal(await(await get(path)).text(),'<main>INDEPENDENT_DESKTOP</main>');
    assert.equal(await(await get('/desktop/app.js')).text(),'OWN_RENDERER');
    for(const path of ['/plugins/bootstrap.js','/assets/index-web.js','/desktop/unknown.js'])assert.equal((await get(path)).status,404);
    assert.deepEqual(network,[]);
    const api=await get('/api/harless/tasks');assert.equal(await api.text(),'API_STREAM');assert.equal(api.headers.get('content-encoding'),null);assert.equal(api.headers.get('content-length'),null);
    assert.deepEqual(network,['https://fixture.example/api/harless/tasks']);
    const headers=(await get('/')).headers;assert.match(headers.get('content-security-policy'),/default-src 'none'/);assert.match(headers.get('content-security-policy'),/form-action 'none'/);
  }finally{assert.equal(directory.startsWith(join(tmpdir(),'geneloop-ui-')),true);rmSync(directory,{recursive:true,force:true});}
});
test('API保持可信Origin、凭据omit与请求体；拒绝跨源及不透明写请求',async()=>{
  const forwarded=[],host=new LocalFrontendHost({server:'https://fixture.example/',ui:'unused',assets:'unused',fail:assert.fail,session:{fetch:async(request,options)=>{forwarded.push({origin:options.headers.get('origin'),credentials:options.credentials,body:await request.text()});return Response.json({ok:true});}}});
  const request=(initiator,headers={},url='https://fixture.example/api/account/login')=>{const value=new Request(url,{method:'POST',credentials:'omit',headers,body:'{"diagnostic":true}'});if(initiator!==undefined)Object.defineProperty(value,'initiatorOrigin',{value:initiator});return value;};
  assert.equal((await host.fetch(request('https://fixture.example'))).status,200);
  assert.deepEqual(forwarded,[{origin:'https://fixture.example',credentials:'omit',body:'{"diagnostic":true}'}]);
  for(const value of [request('https://foreign.example'),request('null'),request(undefined),request('https://fixture.example',{origin:'https://foreign.example'}),request('https://fixture.example',{'sec-fetch-site':'cross-site'}),request('https://fixture.example',{},'https://foreign.example/api/write')])assert.equal((await host.fetch(value)).status,403);
  assert.equal(forwarded.length,1);
});
test('网络错误保持独立界面可用，返回可重试API错误',async()=>{
  const host=new LocalFrontendHost({server:'https://fixture.example/',ui:'unused',assets:'unused',fail:assert.fail,session:{fetch:async()=>{throw Error('offline');}}});
  const response=await host.fetch(new Request('https://fixture.example/api/account/me'));assert.equal(response.status,503);assert.equal((await response.json()).error.code,'desktop/network');
});

test('共享控制请求在桌面拒绝原文、嵌套字段和未同意请求，只有固定控制字段可以转发',async()=>{
  const forwarded=[],host=new LocalFrontendHost({server:'https://fixture.example/',ui:'unused',assets:'unused',
    fail:assert.fail,session:{fetch:async request=>{forwarded.push(await request.text());return Response.json({ok:true});}}});
  const send=body=>host.fetch(new Request('https://fixture.example/api/harless/rsi-sharing',{
    method:'POST',headers:{Origin:'https://fixture.example','Content-Type':'application/json'},body:JSON.stringify(body),
  }));
  for(const body of [
    {action:'preview',task_id:'owned',source:{content:'private@example.com'}},
    {action:'preview',task_id:'/private/trace'},
    {action:'send',preview_id:'a'.repeat(36),sha256:'b'.repeat(64),consent:false},
  ])assert.equal((await send(body)).status,403);
  assert.equal((await host.fetch(new Request('https://fixture.example/api/harless/rsi-sharing?source=private'))).status,403);
  assert.deepEqual(forwarded,[]);
  assert.equal((await send({action:'preview',task_id:'owned-task'})).status,200);
  assert.deepEqual(forwarded,[JSON.stringify({action:'preview',task_id:'owned-task'})]);
});
test('独立日志投影处理快照、流式增量、持久替换及重连，不重复消息',()=>{
  const c=new Conversation(),event=(seq,type,data,surfaceOp)=>({type:'event',event:{seq,type,data,surfaceOp,time:1}});
  const user=event(1,'user/message',{source:{kind:'user'},content:[{type:'text',text:'问题'}]});
  c.accept({type:'snapshot',cursor:1,records:[user],hasMore:false});
  c.accept({type:'assistant-stream',frame:{type:'start'}});c.accept({type:'assistant-stream',frame:{type:'chunk',chunk:{type:'text-delta',index:0,text:'回答'}}});assert.equal(c.live.get(0).text,'回答');
  const answer=event(2,'assistant/message',{message:{content:[{type:'text',text:'回答'}]}});c.accept(answer);c.accept(answer);assert.equal(c.rows().length,2);assert.equal(c.live.size,0);
  c.accept(event(3,'assistant/message',{message:{content:[{type:'text',text:'修订'}]}},{op:'replace',startSeq:2,endSeq:2}));assert.deepEqual(c.rows().map(row=>row.blocks[0].text),['问题','修订']);
  c.accept({type:'snapshot',cursor:1,records:[user],hasMore:false});assert.equal(c.rows().length,1);
});
test('独立分发不依赖DSH网页或运行时包',()=>{
  const root=new URL('../apps/desktop/',import.meta.url),pkg=JSON.parse(readFileSync(new URL('package.json',root)));
  assert.deepEqual(pkg.dependencies,{});
  const build=readFileSync(new URL('scripts/prepare-assets.mjs',root),'utf8');assert.doesNotMatch(build,/frontend\/dist|clients\/|copyFileSync.*harless_account/);
  const page=readFileSync(new URL('ui/desktop/index.html',root),'utf8');assert.match(page,/\/desktop\/app.js/);assert.doesNotMatch(page,/__DSH_BOOT__|__ModuleLoader__|iframe/);
});
test('选中场景按逐轮协议序列化；显式命令优先，长文本与文件回执原样保留',()=>{
  const scenes=[{id:'ppt',shortcut:'ppt'},{id:'files',shortcut:'file'},{id:'paper-proofreading',shortcut:'paper'}],text='正文'.repeat(9000);
  assert.deepEqual(promptContent(text,[{receiptId:'receipt'}],'ppt',scenes),[{type:'text',text:'/ppt '+text},{type:'file',receiptId:'receipt'}]);
  assert.equal(promptContent('/paper 校对',[],'ppt',scenes)[0].text,'/paper 校对');
  assert.equal(promptContent('普通对话',[],'new-scene',scenes)[0].text,'普通对话');
  assert.deepEqual(promptContent('',[{receiptId:'r'}],'files',scenes),[{type:'text',text:'/file'},{type:'file',receiptId:'r'}]);
});
test('重连恢复紧凑流记录中的文字与思考，终止快照清除旧运行状态',()=>{
  const c=new Conversation();c.accept({type:'snapshot',records:[],cursor:0,assistantStream:{activeAttempt:{stream:[{type:'text-chunks',index:0,texts:['恢','复']},{type:'reasoning-chunks',index:1,texts:['检查']}]}}});
  assert.equal(c.live.get(0).text,'恢复');assert.equal(c.live.get(1).type,'reasoning');assert.equal(c.running,true);c.accept({type:'snapshot',records:[],cursor:0});assert.equal(c.running,false);
});
