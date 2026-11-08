/** 确定性桌面协议夹具：只验证交互与渲染，不代表模型/场景验收。 */
import {createServer} from 'node:http';
import {once} from 'node:events';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {randomUUID} from 'node:crypto';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createMotifViewRoute} from '../../../scripts/harless_motif_view.ts';
import {createRsiSharing} from '../../../src/adapters/rsi_sharing.ts';
import {projectPrivateLearningTrace} from '../../../src/adapters/harless_learning_trace.ts';
const require=createRequire(import.meta.url),{WebSocketServer}=require('ws');
const app=fileURLToPath(new URL('../',import.meta.url));
const output=join(app,'.local/validation/renderer-'+randomUUID());mkdirSync(output,{recursive:true});
// Pinned public catalog emitted by PR161's original loader/projector; protocol only.
const runtimeCatalog=JSON.parse(readFileSync(join(app,'../../tests/fixtures/motif-catalog-pr161.json'),'utf8')).catalog;
const privacyDiagnostic=process.env.GENELOOP_PRIVACY_DIAGNOSTIC==='1';
const sharingBodies=[],sharingAudit=[];
let receiverMode='accept',receiver;
if(privacyDiagnostic){
 if(!process.env.SSS_PYTHON)throw Error('SSS_PYTHON is required for the real local privacy projector');
 receiver=createServer(async(req,res)=>{
  const chunks=[];for await(const chunk of req)chunks.push(chunk);
  sharingBodies.push(Buffer.concat(chunks).toString());
  if(receiverMode==='drop')res.destroy();else res.end('ok');
 });
 receiver.listen(0,'127.0.0.1');await once(receiver,'listening');
}
const shareSources=new Map();
for(const [scene,names] of [
 ['paper-proofreading',['mcp__paper_checks__pin_document','mcp__paper_checks__read_pinned_document']],
 ['ppt',['mcp__ppt_master__pin_source','mcp__ppt_master__convert_source','mcp__ppt_master__read_converted_source']],
]){
 const source='source-'+'a'.repeat(32),converted='result-'+'b'.repeat(32),raw='Synthetic Alice Carter alice-private@example.com /mnt/private/draft.pdf';
 const events=[{type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:raw}]}}];
 for(const [i,name] of names.entries()){
  const args=i===0?{name:raw,sha256:'c'.repeat(64)}:i===1?{source_id:source}:{converted_id:converted};
  events.push({type:'tool/call',data:{callId:'private-'+i,name,arguments:JSON.stringify(args)}});
  events.push({type:'tool/result',data:{message:{source:{kind:'tool',callId:'private-'+i},content:[
   {type:'tool-result',isError:false,content:[{type:'text',text:JSON.stringify(i===0?{source_id:source}:{converted_id:converted,text:raw})}]},
  ]}}});
 }
 const path=join(output,scene+'-events.jsonl');
 writeFileSync(path,events.map(event=>JSON.stringify(event)).join('\n')+'\n',{mode:0o600});
 shareSources.set(scene,path);
}
const sharing=createRsiSharing({
 endpoint:receiver?'http://127.0.0.1:'+receiver.address().port+'/private-privacy-receiver':undefined,
 allowLoopback:true,audit:event=>sharingAudit.push(event),
 async prepare(taskId){
  if(!shareSources.has(taskId))throw Error('unknown diagnostic task');
  return projectPrivateLearningTrace(process.env.SSS_PYTHON,shareSources.get(taskId),taskId,'completed',0,{share:true});
 },
});
const motifFile=join(output,'motif-export.json');writeFileSync(motifFile,readFileSync(join(app,'ui/desktop/motif-example.json')));
const motifRoute=createMotifViewRoute({sources:[{accountId:'renderer-fixture',workspaceId:'workspace',path:motifFile,executionLocation:'cloud'}]});
let motifAuthenticated=true;
let runtimeCatalogFail=false;
let workspaceTasks=[];
// The UI must offer completed tasks from future MCP scenes as well. Its
// protocol fixture needs no NLP installation; actual v4 admission runs on Linux.
shareSources.set('future-custom-mcp',shareSources.get('ppt'));
const requests=[],streams=new Map(),sessions=[],selections=new Map(),modelSelections=new Map();let questionPending=false;
const archived=new Set(),deleted=new Set();
const scenes=[['new-scene','Chat','chat'],['ppt','PPT','ppt'],['paper-proofreading','论文校对','paper'],['research-data-analysis','数据分析','data'],['files','文件管理','file'],['video-editing','视频编辑','video']].map(([id,label,shortcut])=>({id,label,shortcut,available:true}));
const catalog={models:[{provider:'diagnostic',model:'fixture',label:'协议诊断模型（无调用）',available:true,reasoning_modes:[{id:'off',label:'关闭',available:true},{id:'high',label:'高',available:true}]}],default:{provider:'diagnostic',model:'fixture',reasoning_effort:'off'}};
const comparison={id:'comparison-fixture',session_id:'history',presentation:'paired',status:'completed',revision:1,scoring_available:true,scores:{baseline:5},lanes:{baseline:{status:'completed',answer:'标准执行结果',output_sha256:'fixture-output',artifacts:[{id:'artifact',name:'diagnostic.txt',bytes:24},{id:'deck',name:'研究汇报.pptx'},{id:'slide-10',name:'slide_10.png'},{id:'slide-2',name:'slide_02.png'}],stats:{model_requests:161}},motif:{status:'completed',answer:'Motif执行结果',artifacts:[],stats:{}}}};
const event=(seq,type,data)=>({type:'event',event:{seq,type,time:Date.now(),data,surfaceOp:'append'}});
const records=[event(1,'user/message',{source:{kind:'user'},content:[{type:'text',text:'历史协议诊断'}],harless_comparison:{id:comparison.id,value:comparison}}),event(2,'assistant/message',{message:{content:[{type:'reasoning',text:'诊断过程'},{type:'text',text:'## 历史记录\n这是**合成诊断**，不代表模型回答。'}]}})];
sessions.push({sessionId:'history',blank:false,running:false,projections:{asOfSeq:2,values:{title:'协议诊断历史'}}});
sessions.push({sessionId:'menu-fixture',blank:true,running:false,projections:{asOfSeq:0,values:{title:'菜单诊断'}}});
sessions.push({sessionId:'empty-fixture',blank:true,running:false});
const settings=id=>({selection:selections.get(id)||{scene:'new-scene',mode:'baseline',rsi:false},scenes,scene_options:{},scene_option_fields:[],paired_comparison:false});
const json=(res,value,status=200)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(value));};
const push=(endpoint,value,sessionId)=>{for(const [key,row]of streams)if(row.endpoint===endpoint&&(!sessionId||row.sessionId===sessionId))row.socket.send(JSON.stringify({type:'item',streamId:key,value}));};
const server=createServer(async(req,res)=>{
 try{
  if(await motifRoute(req,res,motifAuthenticated?{id:'renderer-fixture'}:null))return;
  const url=new URL(req.url,'http://127.0.0.1'),path=url.pathname;const buffers=[];for await(const chunk of req)buffers.push(chunk);const raw=Buffer.concat(buffers),body=raw.length&&(req.headers['content-type']||'').includes('json')?JSON.parse(raw):{};
  requests.push({path,method:req.method,body});
  if(path==='/api/fixture/motif-logout'&&req.method==='POST'){motifAuthenticated=false;return json(res,{ok:true});}
  if(path==='/api/fixture/motif-update'&&req.method==='POST'){const next=JSON.parse(readFileSync(motifFile,'utf8'));next.capabilities[0].name+=' · 更新诊断';writeFileSync(motifFile,JSON.stringify(next));return json(res,{ok:true});}
  if(path==='/api/account/me'){await new Promise(resolve=>setTimeout(resolve,600));return json(res,{user:{id:'diagnostic',displayName:'协议诊断账号',username:'diagnostic'}});}
  if(path==='/api/harless/desktop-model/lease')return json(res,{error:'诊断网关未开放模型'},404);
  if(path==='/api/workspace/ready')return json(res,{ready:true});
  if(path==='/api/harless/settings'){
   const id=body.session_id||url.searchParams.get('session_id');
   if(req.method==='GET'&&id&&id!=='history')await new Promise(resolve=>setTimeout(resolve,450));
   if(req.method==='POST'){
    if(body.selection?.scene==='ppt')await new Promise(resolve=>setTimeout(resolve,750));
    if(body.selection?.scene==='paper-proofreading'){
     await new Promise(resolve=>setTimeout(resolve,250));
     return json(res,{error:{message:'场景同步诊断拒绝'}},409);
    }
    selections.set(id,{...settings(id).selection,...body.selection});
   }
   return json(res,settings(id));
  }
  if(path==='/api/harless/models')return json(res,{...catalog,session_selection:modelSelections.get(url.searchParams.get('session_id'))});
  if(path==='/api/harless/file-scene')return json(res,{selected:false});
  if(path==='/api/harless/tasks')return json(res,{tasks:[...workspaceTasks,...(privacyDiagnostic?[...shareSources.keys()].map(scene=>({task_id:scene,scene,status:'completed'})):[])]});
  if(path==='/api/fixture/runtime-catalog-fail'&&req.method==='POST'){runtimeCatalogFail=!runtimeCatalogFail;return json(res,{ok:true});}
  if(path==='/api/harless/motif-catalog')return !motifAuthenticated?json(res,{error:'login_required'},401):runtimeCatalogFail?json(res,{error:'catalog_unavailable'},503):json(res,runtimeCatalog);
  if(path==='/api/fixture/task-progress'&&req.method==='POST'){workspaceTasks[0].duration_ms=2400;return json(res,{ok:true});}
  if(path==='/api/fixture/workspace-task'&&req.method==='POST'){
   const time='2026-11-06T00:00:00.000Z';
   workspaceTasks=[{task_id:'workspace-ui-task',session_id:'history',input_summary:'界面验收（合成）：核对材料并整理交付',scene:'files',status:'running',created_at:time,started_at:time,duration_ms:1200,stats:{model_requests:0,cost_usd:0},
    todos:[{content:'读取已授权的材料目录（合成步骤）',status:'completed'},{content:'核对资料与来源标识（合成步骤）',status:'completed'},{content:'整理交付入口（合成步骤）',status:'in_progress'}],
    progress:{label:'正在核对交付入口（合成进度）',status:'running'},trace:[{id:'ui-read',kind:'tool',label:'已读取目录信息（合成记录）',status:'completed',time},{id:'ui-motif',kind:'motif',label:'界面协议回执（合成）',status:'completed',optimized:true,verified_skip:false,time},{id:'ui-output',kind:'tool',label:'正在整理交付入口（合成记录）',status:'running',time}]},
    {task_id:'foreign-ui-task',session_id:'foreign-session',input_summary:'另一工作区的任务不得显示',status:'running',created_at:time}];
   return json(res,{ok:true});
  }
  if(path==='/api/harless/rsi-sharing'){
   const response=await sharing.handle(new Request('http://local'+req.url,{
    method:req.method,...(req.method==='POST'?{body:raw.toString()}:{}),
   }));
   res.writeHead(response.status,{'content-type':'application/json'});return res.end(await response.text());
  }
  if(path==='/api/fixture/privacy-receiver'){
   receiverMode=body.mode;return json(res,{received:sharingBodies.length});
  }
  if(path==='/api/harless/session-trash'||path==='/api/fixture/external-trash'){
   const id=path==='/api/fixture/external-trash'?'history':body.session_id;
   if(body.action==='archive')archived.add(id);
   if(body.action==='unarchive')archived.delete(id);
   if(body.action==='delete')deleted.add(id);
   if(body.action==='restore'){deleted.delete(id);archived.delete(id);}
   if(body.action)push('workspace/follow',{type:'archived',archivedSessionIds:[...archived]});
   return json(res,{sessions:sessions.filter(row=>deleted.has(row.sessionId)).map(row=>({session_id:row.sessionId,title:row.projections.values.title})),revision:'fixture'});
  }
  if(path==='/api/harless/questions'){if(req.method==='POST')questionPending=false;return json(res,{questions:questionPending?[{id:'question-fixture',questions:[
    {id:'q1',question:'请选择资料处理范围',multiSelect:true,options:[{id:'wrong-id-1',label:'保留来源'},{id:'wrong-id-2',label:'生成副本'}]},
    {id:'q2',question:'你希望为哪类读者准备这份演示文稿？',options:['零基础入门','课题组讨论','专业汇报']},
  ]}]:[]});}
  if(path==='/api/fixture/questions'){questionPending=true;return json(res,{ok:true});}
  if(path==='/api/harless/comparisons'){
   const file=url.searchParams.get('file');
   if(file?.startsWith('slide-')){
    res.writeHead(200,{'content-type':'application/octet-stream','content-disposition':'attachment','x-content-type-options':'nosniff'});
    return res.end(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jH1sAAAAASUVORK5CYII=','base64'));
   }
   if(file){res.writeHead(200,{'content-type':'text/plain','content-disposition':'attachment; filename="diagnostic.txt"'});return res.end('diagnostic file contents');}
   return json(res,comparison);
  }
  if(path==='/api/fixture/approval'){push('$events',{type:'waterfall',event:'approval/request',eventId:'approval-fixture',request:{reason:'合成写入确认',tool:'diagnostic-write'}});return json(res,{ok:true});}
  const endpoint=path.replace('/api/',''),args=body.payload?.args||{},request=args.request;let value;
  if(endpoint==='session/list'){if(!Object.hasOwn(args,'_request'))throw Error('session/list requires _request');value={items:sessions.filter(row=>!deleted.has(row.sessionId))};}
  else if(endpoint==='session/create'){const sessionId=randomUUID();sessions.push({sessionId,blank:true,running:false,projections:{asOfSeq:0,values:{title:'新会话'}}});value={sessionId};}
  else if(endpoint==='session/rename'){const row=sessions.find(row=>row.sessionId===request.sessionId);row.projections.values.title=request.title;value={title:request.title,seq:3};}
  else if(endpoint==='session/selectModel'){modelSelections.set(request.sessionId,{...request,reasoning_effort:request.reasoningEffort});value={selected:request};}
  else if(endpoint==='session/prompt'){
   if(request.content[0].text==='/ppt 诊断发送'&&selections.get(request.sessionId)?.scene!=='ppt')throw Error('Prompt arrived before scene confirmation');
   value={accepted:true};const id=request.sessionId;
   push('session/follow',event(3,'turn/start',{turn:1}),id);push('session/follow',event(4,'user/message',{source:{kind:'user',rpcId:request.requestId},content:request.content}),id);
   push('session/follow',{type:'assistant-stream',frame:{type:'start',attemptId:'fixture',revision:1}},id);
   push('session/follow',{type:'assistant-stream',frame:{type:'chunk',attemptId:'fixture',revision:2,chunk:{type:'text-delta',index:0,text:'正在呈现协议诊断流'}}},id);
   setTimeout(()=>{push('session/follow',event(5,'assistant/message',{message:{content:[{type:'text',text:'协议诊断响应完成'}]}}),id);push('session/follow',event(6,'turn/end',{turn:1}),id);},250);
  }
  else if(endpoint==='workspace/delete'){push('workspace/follow',{type:'remove',workspaceId:request.workspaceId});value={deleted:true};}
  else if(endpoint==='session/cancel')value={accepted:true};
  else if(endpoint==='$events/result')value={accepted:true};
  else return json(res,{error:{message:'fixture endpoint missing: '+endpoint}},404);
  return json(res,{type:'server-response',rpcId:body.rpcId,result:{ok:true,value}});
 }catch(error){json(res,{error:{message:error.message}},400);}
});
const ws=new WebSocketServer({server,path:'/api/remote.mux'});
ws.on('connection',socket=>{socket.on('message',data=>{const frame=JSON.parse(data);if(frame.type==='cancel'){streams.delete(frame.streamId);return;}const row={socket,endpoint:frame.endpoint,sessionId:frame.payload.args.request?.address?.sessionId};streams.set(frame.streamId,row);const item=value=>socket.send(JSON.stringify({type:'item',streamId:frame.streamId,value}));if(frame.endpoint==='workspace/follow')item({type:'baseline',value:{items:[{workspaceId:'workspace',title:'诊断工作区',sessionIds:['history','menu-fixture']},{workspaceId:'empty-workspace',title:'空工作区',sessionIds:[]}],archivedSessionIds:[...archived]}});else if(frame.endpoint==='$events')item({type:'ready',clientId:'fixture-client'});else if(frame.endpoint==='session/control')item({type:'baseline',value:{}});else if(frame.endpoint==='session/follow')item({type:'snapshot',header:{id:row.sessionId},cursor:2,records:row.sessionId==='history'?records:[],hasMore:false,projections:{asOfSeq:2,values:{}}});});socket.on('close',()=>{for(const [id,row]of streams)if(row.socket===socket)streams.delete(id);});});
server.listen(0,'127.0.0.1');await once(server,'listening');
const fixture=join(output,'fixture.json');writeFileSync(fixture,JSON.stringify({diagnostic:true,privacy:privacyDiagnostic,server:`http://127.0.0.1:${server.address().port}/`,output}));
const env={...process.env,GENELOOP_RENDERER_FIXTURE:fixture,
  GENELOOP_FFMPEG_DIRECTORY:join(output,'missing-media-tools')};delete env.ELECTRON_RUN_AS_NODE;
let result=1;
try{const child=spawn(require('electron'),['test/renderer.cjs'],{cwd:app,env,stdio:'inherit',windowsHide:true});const [code,signal]=await once(child,'exit');result=code??1;console.log(JSON.stringify({diagnostic_child_exit:code,signal}));if(!JSON.parse(readFileSync(join(output,'summary.json'))).ok)throw Error('Renderer diagnostic failed before quit');
 const prompts=requests.filter(row=>row.path==='/api/session/prompt');if(prompts.length!==3)throw Error('Expected exactly three synthetic prompt submissions');
 const created=requests.filter(row=>row.path==='/api/session/create');
 if(created.length!==1||created[0].body.payload.args.request.workspaceId!=='empty-workspace')throw Error('Only the submitted draft should create a session in its workspace');
 if(prompts[2].body.payload.args.request.content[0].text!=='工作区草稿诊断')throw Error('Draft content was not sent');
 if(prompts[0].body.payload.args.request.content[0].text!=='/ppt 诊断发送')throw Error('Scene shortcut missing from wire prompt');
 if(prompts[1].body.payload.args.request.content[0].text!=='普通下一轮')throw Error('Scene selection did not reset per turn');
 const selected=requests.findIndex(row=>row.path==='/api/session/selectModel'),sent=requests.findIndex(row=>row.path==='/api/session/prompt');if(selected<0||selected>sent)throw Error('Prompt did not await model selection');
 const reply=requests.find(row=>row.path==='/api/$events/result');if(reply?.body.payload.args.outcome.value!=='allowed-once')throw Error('Explicit approval reply missing');
 const answered=requests.find(row=>row.path==='/api/harless/questions'&&row.method==='POST');
 const [multiple,single]=answered?.body.answers??[];
 if(JSON.stringify(multiple?.selected)!==JSON.stringify(['保留来源','生成副本'])||multiple?.custom!=='保留原始资料\n只写入输出目录'||JSON.stringify(single?.selected)!==JSON.stringify(['课题组讨论']))throw Error('Human answer selections or multiline details did not match server contract');
 if(privacyDiagnostic){
  if(sharingBodies.length!==2)throw Error('Expected one confirmed upload and one interrupted upload');
  if(sharingBodies.some(body=>/Alice|alice-private|\/mnt\/private|draft.pdf/.test(body)))throw Error('Sensitive synthetic marker reached receiver');
  const report=JSON.parse(readFileSync(join(output,'summary.json')));
  if(sharingBodies[0]!==report.sharing_payload)throw Error('Uploaded bytes differ from the visible preview');
  const restarted=spawn(require('electron'),['test/privacy-restart.cjs'],{cwd:app,env,stdio:'inherit',windowsHide:true});
  const [restartCode]=await once(restarted,'exit');
  if(restartCode!==0||!JSON.parse(readFileSync(join(output,'privacy-restart-summary.json'))).ok)
   throw Error('Desktop restart privacy check failed');
  if(sharingBodies.length!==2)throw Error('Desktop restart repeated a sharing request');
 }
}catch(error){console.error(error);result=1;}finally{sharing.dispose();if(receiver){receiver.closeAllConnections();await new Promise(done=>receiver.close(done));}for(const client of ws.clients)client.terminate();await new Promise(done=>ws.close(done));await new Promise(done=>server.close(done));writeFileSync(join(output,'requests.json'),JSON.stringify({kind:'synthetic-protocol-diagnostic',real_model_requests:0,requests},null,2));writeFileSync(join(output,'sharing-receiver.json'),JSON.stringify({kind:'synthetic-private-receiver',bodies:sharingBodies,audit:sharingAudit},null,2));}
process.exitCode=result;
