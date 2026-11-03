import {request,post,rpc,upload,RemoteStreams} from './api.js';
import {Conversation} from './conversation.js';
import {node,button,blocks,markdown,dialog,icon,popupMenu,choiceControl,refreshChoice} from './components.js';
import {promptContent} from './composer.js';
import {settingsPanel} from './panels.js';
import {comparisonCard} from './comparison.js';
import {bindScenePicker} from './scene-picker.js';
import {deliveryPath,deliveryFiles,deliveryName,presentation,presentationCard,previewPresentation} from './deliveries.js';
const $=id=>document.getElementById(id),state={user:null,sessions:[],workspaces:[],archived:new Set(),session:null,workspace:null,settings:null,models:[],conversation:new Conversation(),attachments:[],trace:false,generation:0,submitting:false,drafts:new Map(),comparisons:new Map(),pending:new Map()};
const labels={'new-scene':'Chat',ppt:'PPT','paper-proofreading':'论文校对','research-data-analysis':'数据分析',files:'文件管理','video-editing':'视频编辑'};
const examples=[
  ['paper-proofreading','检查论文引用','请检查我上传的论文，列出正文引用与参考文献不一致的地方，并标明位置。'],
  ['ppt','根据材料生成 PPT','请根据我上传的材料拟一份演示文稿大纲，写出每页标题、要点和建议配图。'],
  ['research-data-analysis','找出数据中的异常','请检查我上传的数据，列出缺失值、异常值和可能的原因，并说明判断依据。'],
];
let toastTimer,pollTimer,renderPending=false,registering=false,currentFollow,workspaceFollow,eventFollow,controlFollow,previewUrl;
let selectionChange=Promise.resolve(),creatingSession;
let scratchText='';
const historyCache=new Map();
const workspaceDrafts=new Map();
const newWorkspaceDrafts=new Map();
let activeWorkspaceDraft=null;
let awaitingHistory=false,historyError='';
let pinnedWorkspaces=[];
let homeDelivery=null;
function changeSelection(action){const operation=selectionChange.catch(()=>{}).then(action);selectionChange=operation;return operation;}
const errorText=error=>error?.message||String(error);
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5500);}
const fail=error=>toast(errorText(error));
function screen(name){for(const id of ['auth','loading','workspace'])$(id).hidden=id!==name;document.body.dataset.desktopScreen=name;document.body.toggleAttribute('data-auth-active',name==='auth');}
function warning(error){$('connection-warning').textContent=errorText(error)+' · 点击重新连接';$('connection-warning').hidden=false;}
let streams=new RemoteStreams(warning);
function theme(){const value=localStorage.getItem('geneloop.desktop.theme')||'system';document.body.toggleAttribute('data-ds-dark-theme',value==='dark'||value==='system'&&matchMedia('(prefers-color-scheme:dark)').matches);}
theme();matchMedia('(prefers-color-scheme:dark)').addEventListener('change',theme);
function titleOf(row){const value=row?.projections?.values?.title;return typeof value==='string'?value:value?.title||value?.text||row?.title||'新会话';}
function renderLoginServer(){
  const label=$('auth-server');
  label.hidden=location.origin==='https://geneloop.ai';
  label.textContent=label.hidden?'':'连接到 '+location.origin;
}
function restoreLoginPreference(){
  const username=localStorage.getItem('geneloop.desktop.username');
  $('login-user').value=username||'';
  $('remember-login').checked=localStorage.getItem('geneloop.desktop.remember-login')!=='off';
}
function showAuth(){streams.close();clearInterval(pollTimer);state.generation++;state.user=null;state.sessions=[];state.workspaces=[];state.session=null;state.workspace=null;state.attachments=[];state.drafts.clear();state.pending.clear();historyCache.clear();workspaceDrafts.clear();newWorkspaceDrafts.clear();activeWorkspaceDraft=null;pinnedWorkspaces=[];scratchText='';$('prompt').value='';renderLoginServer();restoreLoginPreference();screen('auth');$('login-pass').value='';}
async function initialize(){screen('loading');$('connect-retry').hidden=true;$('loading-message').textContent='正在读取账号与工作空间…';try{
    let account;
    try{account=await request('/api/account/me');}catch(error){if(error.status===404||error.code==='http/200'){await rpc('session/list',{});account={user:{id:'standalone-host',displayName:'工作空间',standalone:true}};}else throw error;}
    if(!account.user){showAuth();return;}state.user=account.user;$('account-name').textContent=account.user.displayName;
    if(!account.user.standalone){for(let attempt=0;attempt<90;attempt++){const ready=await request('/api/workspace/ready');if(ready.ready)break;if(attempt===89)throw Error('工作空间启动尚未完成，请稍后重连。');$('loading-message').textContent='服务器正在准备你的工作空间…';await new Promise(resolve=>setTimeout(resolve,1000));}}
    await connectWorkspace();
  }catch(error){$('loading-message').textContent=errorText(error);$('connect-retry').hidden=false;}}
async function connectWorkspace(){
  streams.close();streams=new RemoteStreams(warning);currentFollow=workspaceFollow=eventFollow=controlFollow=null;state.generation++;state.conversation=new Conversation();state.comparisons=new Map();$('connection-warning').hidden=true;
  await loadSessions();state.settings=await request('/api/harless/settings');const catalog=await request('/api/harless/models');state.models=catalog.models||[];state.defaultModel=catalog.default;
  const user=state.user;
  request('/api/harless/workspaces/preferences').then(value=>{if(state.user===user){pinnedWorkspaces=value.pinned_workspace_ids||[];renderSidebar();}}).catch(()=>{});
  workspaceFollow=await streams.follow('workspace/follow',undefined,frame=>{
    if(frame.type==='baseline'){state.workspaces=frame.value.items||[];state.archived=new Set(frame.value.archivedSessionIds||[]);}
    if(frame.type==='upsert'){const at=state.workspaces.findIndex(row=>row.workspaceId===frame.workspace.workspaceId);if(at<0)state.workspaces.push(frame.workspace);else state.workspaces[at]=frame.workspace;}
    if(frame.type==='remove')state.workspaces=state.workspaces.filter(row=>row.workspaceId!==frame.workspaceId);
    if(frame.type==='archived')state.archived=new Set(frame.archivedSessionIds);
    if(frame.type==='order')state.workspaces.sort((a,b)=>frame.workspaceIds.indexOf(a.workspaceId)-frame.workspaceIds.indexOf(b.workspaceId));renderSidebar();if(!state.session)scheduleRender();
  },warning);
  eventFollow=await streams.follow('$events',undefined,frame=>{handleEvent(frame).catch(fail);},warning);
  controlFollow=await streams.follow('session/control',undefined,frame=>{if(frame.type==='queue'&&frame.sessionId===state.session){$('session-status').textContent=frame.items.length?'排队中 · '+frame.items.length+' 条':'工作空间已连接';}if(frame.type==='jobs'&&frame.sessionId===state.session){state.jobs=frame.jobs;scheduleRender();}},warning);
  screen('workspace');renderSidebar();renderModels();renderScenes();renderConversation();
  clearInterval(pollTimer);pollTimer=setInterval(()=>{if(state.session)refreshTaskPanels().catch(()=>{});},4000);
  if(state.session&&state.sessions.some(row=>row.sessionId===state.session))await selectSession(state.session,{force:true});else state.session=null;
}
async function loadSessions(){const value=await rpc('session/list',{});if(!Array.isArray(value.items))throw Error('会话目录响应不兼容');state.sessions=value.items.filter(row=>row.origin!=='subagent');renderSidebar();if(state.session||state.workspace)scheduleRender();}
function visibleSession(row){
  if(!row||state.archived.has(row.sessionId)||[...newWorkspaceDrafts.values()].some(draft=>draft.sessionId===row.sessionId))return false;
  const draft=state.drafts.get(row.sessionId);
  return row.blank!==true||row.running||titleOf(row)!=='新会话'||Boolean(draft?.text.trim()||draft?.attachments.length);
}
function renderSidebar(){const list=$('workspace-list'),query=$('search').value.trim().toLowerCase();list.replaceChildren();const grouped=new Set(state.workspaces.flatMap(row=>row.sessionIds));
  const visible=row=>visibleSession(row)&&titleOf(row).toLowerCase().includes(query);
  const sessionButton=row=>{
    const element=node('div',{class:'session-row'+(row.sessionId===state.session?' active':''),'data-session-id':row.sessionId,onclick:()=>selectSession(row.sessionId).catch(fail)});
    const label=node('button',{class:'session-link',type:'button'},(row.running?'● ':'')+titleOf(row));
    const more=button(icon('more'),event=>{event.stopPropagation();openSessionMenu(row.sessionId,{anchor:more});},'session-more icon');more.title='管理对话';more.setAttribute('aria-label','管理对话：'+titleOf(row));more.setAttribute('aria-haspopup','menu');
    element.append(label,more);element.addEventListener('contextmenu',event=>{event.preventDefault();event.stopPropagation();openSessionMenu(row.sessionId,{x:event.clientX,y:event.clientY,anchor:label});});return element;
  };
  const groups=[...state.workspaces].sort((a,b)=>Number(pinnedWorkspaces.includes(b.workspaceId))-Number(pinnedWorkspaces.includes(a.workspaceId)));
  for(const group of groups){
    const rows=group.sessionIds.map(id=>state.sessions.find(row=>row.sessionId===id)).filter(visible);
    const draft=newWorkspaceDrafts.get(group.workspaceId);
    const showDraft=draft&&(!query||'新会话 · 草稿'.includes(query));
    if(query&&!rows.length&&!showDraft&&!group.title.toLowerCase().includes(query))continue;
    const header=button(node('span',{},group.title),()=>openWorkspace(group.workspaceId),'workspace-row');
    header.prepend(icon('folder'));
    if(state.workspace===group.workspaceId)header.setAttribute('aria-current','true');
    const more=button(icon('more'),()=>workspaceMenu(group,{anchor:more}),'workspace-more icon');
    more.setAttribute('aria-label','工作区菜单：'+group.title);more.setAttribute('aria-haspopup','menu');
    const row=node('div',{class:'workspace-entry'},header,more);
    row.addEventListener('contextmenu',event=>{event.preventDefault();workspaceMenu(group,{anchor:header,x:event.clientX,y:event.clientY});});
    const section=node('section',{class:'workspace-group','aria-label':group.title},row);
    const children=rows.map(sessionButton);
    if(showDraft){
      const label=button('新会话 · 草稿',()=>beginWorkspaceDraft(group.workspaceId).catch(fail),'session-link');
      if(draft===activeWorkspaceDraft)label.setAttribute('aria-current','true');
      children.unshift(node('div',{class:'session-row workspace-draft'+(draft===activeWorkspaceDraft?' active':'')},label));
    }
    if(children.length)section.append(node('div',{class:'workspace-children'},children));
    list.append(section);
  }
  const ungrouped=state.sessions.filter(row=>!grouped.has(row.sessionId)&&visible(row));if(ungrouped.length)list.append(node('div',{class:'workspace-heading'},'其他对话'),...ungrouped.map(sessionButton));
  if(!list.children.length)list.append(node('p',{class:'empty'},query?'没有匹配的对话':'创建工作区，开始第一段研究。'));
}
function workspaceMenu(group,position){
  const id=group.workspaceId,pinned=pinnedWorkspaces.includes(id);
  popupMenu([
    {id:'workspace-home',label:'打开工作区',icon:'folder',action:()=>openWorkspace(id)},
    {id:'workspace-new',label:'在此新建会话',icon:'plus',action:()=>beginWorkspaceDraft(id).catch(fail)},
    {id:'workspace-pin',label:pinned?'取消置顶':'置顶工作区',icon:'pin',action:async()=>{
      try{const value=await post('/api/harless/workspaces/preferences',{workspace_id:id,pinned:!pinned});pinnedWorkspaces=value.pinned_workspace_ids;renderSidebar();}catch(error){fail(error);}
    }},
    {id:'workspace-rename',label:'重命名工作区',icon:'edit',action:()=>askText('重命名工作区','工作区名称',group.title,async title=>{
      const {workspace}=await rpc('workspace/rename',{workspaceId:id,title});
      state.workspaces=state.workspaces.map(row=>row.workspaceId===id?workspace:row);renderSidebar();renderConversation();
    })},
  ],position);
}
function clearSessionPanels(){
  state.deliveries=[];state.nativePresentations=[];homeDelivery=null;renderDeliveries();renderQuestions([]);$('preview').replaceChildren();
  if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null;}
}
function saveComposer(){
  const content={text:$('prompt').value,attachments:state.attachments};
  if(activeWorkspaceDraft){
    const draft=activeWorkspaceDraft;
    activeWorkspaceDraft=null;
    Object.assign(draft,content);
    if(!content.text.trim()&&!content.attachments.length)newWorkspaceDrafts.delete(draft.workspaceId);
    if(draft.sessionId)state.drafts.delete(draft.sessionId);
  }else if(state.session)state.drafts.set(state.session,content);
  else scratchText=content.text;
}
async function beginWorkspaceDraft(id){
  if(creatingSession||state.submitting)return;
  if(activeWorkspaceDraft?.workspaceId===id){$('prompt').focus();return;}
  openWorkspace(id,{focus:true});
  const draft=newWorkspaceDrafts.get(id)||{workspaceId:id,sessionId:null,text:'',attachments:[]};
  newWorkspaceDrafts.set(id,draft);
  activeWorkspaceDraft=draft;
  if(draft.sessionId)await selectSession(draft.sessionId,{workspaceDraft:draft});
  else{
    $('prompt').value=draft.text;
    renderSidebar();renderConversation();
  }
  if(activeWorkspaceDraft===draft)$('prompt').focus();
}
function openWorkspace(id,{focus=false}={}){
  if(creatingSession||state.submitting)return;
  saveComposer();
  if(id!==state.workspace){
    workspaceDrafts.set(state.workspace,scratchText);
    scratchText=workspaceDrafts.get(id)||'';
  }
  currentFollow?.();currentFollow=null;state.generation++;state.session=null;state.workspace=id;
  state.conversation=new Conversation();state.comparisons=new Map();state.jobs=[];state.trace=false;
  awaitingHistory=false;historyError='';$('composer').inert=false;
  $('deliveries').hidden=true;
  state.composerScene='new-scene';state.attachments=[];$('prompt').value=scratchText;
  clearSessionPanels();renderScenes();renderAttachments();renderSidebar();renderConversation();
  $('history').scrollTop=0;
  if(id&&!focus)refreshHomeDelivery(id).catch(()=>{});
  if(focus)$('prompt').focus();
}
async function ensureSession(){
  if(state.session)return state.session;
  if(creatingSession)return creatingSession;
  creatingSession=(async()=>{
    const workspaceDraft=activeWorkspaceDraft;
    if(!state.workspace&&state.workspaces.length)state.workspace=state.workspaces[0].workspaceId;
    const {sessionId}=await rpc('session/create',state.workspace?{workspaceId:state.workspace}:{});
    const content={text:$('prompt').value,attachments:state.attachments};
    if(workspaceDraft)Object.assign(workspaceDraft,content,{sessionId});
    else state.drafts.set(sessionId,content);
    await loadSessions().catch(fail);
    await selectSession(sessionId,{fromScratch:true,workspaceDraft});
    return sessionId;
  })();
  try{return await creatingSession;}finally{creatingSession=null;}
}
async function selectSession(id,{fromScratch=false,force=false,workspaceDraft=null}={}){
  if((creatingSession||state.submitting)&&!fromScratch)return;
  if(state.session===id&&!force&&!historyError)return;
  if(!workspaceDraft){
    if(fromScratch)scratchText='';
    else if(!force||state.session!==id)saveComposer();
    else if(!activeWorkspaceDraft)state.drafts.set(id,{text:$('prompt').value,attachments:state.attachments});
    else Object.assign(activeWorkspaceDraft,{text:$('prompt').value,attachments:state.attachments});
  }
  currentFollow?.();currentFollow=null;
  const generation=++state.generation;
  state.session=id;clearSessionPanels();state.composerScene='new-scene';state.trace=false;state.jobs=[];
  const cached=historyCache.get(id);
  state.conversation=cached?.conversation||new Conversation();state.comparisons=cached?.comparisons||new Map();
  awaitingHistory=true;historyError='';$('composer').inert=true;
  const draft=workspaceDraft||activeWorkspaceDraft||state.drafts.get(id)||{text:'',attachments:[]};
  $('prompt').value=draft.text;state.attachments=draft.attachments;renderAttachments();
  state.workspace=state.workspaces.find(row=>row.sessionIds.includes(id))?.workspaceId||state.workspace;
  renderSidebar();renderConversation();
  const current=()=>generation===state.generation;
  const onError=error=>{if(current()){awaitingHistory=false;historyError=errorText(error);warning(error);scheduleRender();}};
  const follow=streams.follow('session/follow',{address:{kind:'session',sessionId:id},maxMessages:80,assistantStream:true},frame=>{
    if(!current())return;
    state.conversation.accept(frame);
    if(frame.type==='snapshot'){
      awaitingHistory=false;
      state.conversation.running||=Boolean(state.sessions.find(row=>row.sessionId===id)?.running);
      historyCache.delete(id);historyCache.set(id,{conversation:state.conversation,comparisons:state.comparisons});
      if(historyCache.size>8)historyCache.delete(historyCache.keys().next().value);
    }
    const pending=state.pending.get(id);
    if(pending&&[...state.conversation.events.values()].some(event=>event.type==='user/message'&&event.data?.source?.rpcId===pending.requestId))state.pending.delete(id);
    scheduleRender();
    if(frame.type==='snapshot'||frame.type==='event'&&frame.event.type==='turn/end')refreshTaskPanels().catch(()=>{});
  },onError).then(stop=>{if(current())currentFollow=stop;else stop();},onError);
  try{
    const query='?session_id='+encodeURIComponent(id);
    const [settings,file,catalog]=await Promise.all([
      request('/api/harless/settings'+query),request('/api/harless/file-scene'+query).catch(()=>null),request('/api/harless/models'+query),
    ]);
    if(!current())return;
    if(file?.selected)settings.selection={scene:'files',mode:'execute',rsi:true};
    state.settings=settings;state.models=catalog.models||[];state.defaultModel=catalog.session_selection||catalog.default;
    renderScenes();renderModels();$('composer').inert=false;
  }catch(error){onError(error);}
  await follow;
}
function scheduleRender(){if(renderPending)return;renderPending=true;requestAnimationFrame(()=>{renderPending=false;renderConversation();});}
function fillExample(text){
  const input=$('prompt');
  if(!input.value.trim())input.value=text;
  else if(input.value!==text)toast('已有草稿，已保留原文。');
  input.focus();
}
function exampleButtons(){
  return examples.filter(([id])=>state.settings?.scenes?.some(scene=>scene.id===id&&scene.available!==false))
    .map(([,title,text])=>button(title,()=>fillExample(text),'prompt-example'));
}
function workspaceSessions(group){
  const ids=new Set(group.sessionIds);
  return state.sessions.filter(row=>ids.has(row.sessionId)&&visibleSession(row))
    .sort((a,b)=>(new Date(b.updatedAt).getTime()||0)-(new Date(a.updatedAt).getTime()||0));
}
function recentSessionEvents(id){
  return new Promise((resolve,reject)=>{
    let stop,finished=false;
    const finish=(callback,value)=>{if(finished)return;finished=true;clearTimeout(timer);stop?.();callback(value);};
    const timer=setTimeout(()=>finish(resolve,[]),5000);
    streams.follow('session/follow',{address:{kind:'session',sessionId:id},maxMessages:20,assistantStream:false},
      frame=>{if(frame.type==='snapshot')finish(resolve,frame.records||[]);},error=>finish(reject,error))
      .then(cancel=>{stop=cancel;if(finished)stop();},error=>finish(reject,error));
  });
}
async function refreshHomeDelivery(workspaceId){
  const group=state.workspaces.find(row=>row.workspaceId===workspaceId);
  if(!group)return;
  const row=workspaceSessions(group)[0];
  if(!row||row.running)return;
  const {sessionId}=row,generation=state.generation;
  const current=()=>generation===state.generation&&!state.session&&!activeWorkspaceDraft&&state.workspace===workspaceId;
  const [records,tasks]=await Promise.all([
    recentSessionEvents(sessionId).catch(()=>[]),
    request('/api/harless/tasks').catch(()=>({tasks:[]})),
  ]);
  if(!current())return;
  const refs=records.map(row=>row.event?.data?.harless_comparison).filter(Boolean).reverse();
  const native=(tasks.tasks||[]).filter(task=>task.session_id===sessionId&&task.scene==='ppt'&&task.status==='completed')
    .sort((a,b)=>(b.native_turn||0)-(a.native_turn||0));
  const candidates=[...refs.map(ref=>({id:ref.id,turn:ref.turn})),
    ...native.map(task=>({id:'native-'+task.task_id,turn:task.native_turn}))]
    .sort((a,b)=>(b.turn||0)-(a.turn||0)).slice(0,4);
  for(const candidate of candidates){
    const path=deliveryPath(sessionId,candidate.id);
    const value=await request(path).catch(()=>null);
    if(!current())return;
    const decks=Object.entries(value?.lanes||{}).map(([lane,result])=>({
      label:lane==='motif'?'Motif 执行':'标准执行',
      deck:presentation(deliveryFiles(path,lane,result)),
    })).filter(row=>row.deck);
    if(decks.length){homeDelivery={sessionId,decks};scheduleRender();return;}
  }
}
function workspaceHome(group){
  const rows=workspaceSessions(group);
  const next=rows.find(row=>row.running)||rows[0];
  const decks=!next?.running&&homeDelivery?.sessionId===next?.sessionId?homeDelivery?.decks:null;
  const resume=next?node('section',{class:'workspace-resume','aria-label':'继续工作'},
    node('div',{class:'workspace-resume-mark'},node('img',{src:'/assets/geneloop-spiral.svg',alt:''})),
    node('div',{class:'workspace-resume-copy'},node('div',{class:'delivery-kicker'},'继续工作'),
      node('h3',{},titleOf(next)),node('p',{},next.running?'正在执行':decks?'演示文稿交付已就绪':'最近更新的研究对话')),
    node('div',{class:'delivery-actions'},
      button('打开对话',()=>selectSession(next.sessionId).catch(fail),'secondary'),
      decks?button('查看交付',()=>{
        if(decks.length===1&&decks[0].deck.slides.length)previewPresentation(decks[0].deck);
        else dialog('演示文稿交付',node('div',{class:'workspace-delivery-options'},decks.map(({label,deck})=>
          node('div',{},decks.length>1?node('p',{},label):null,presentationCard(deck)))));
      },'secondary'):null)):null;
  const create=button(node('span',{},icon('plus'),'新会话'),()=>beginWorkspaceDraft(group.workspaceId).catch(fail),'secondary workspace-start');
  const summary=node('div',{class:'workspace-home-heading'},
    node('div',{class:'workspace-home-name'},node('span',{class:'workspace-home-icon'},icon('folder')),
      node('div',{},node('h2',{},group.title),node('p',{},'研究工作区'))),
    create);
  const section=node('section',{class:'workspace-recent','aria-label':'最近对话'},
    node('div',{class:'workspace-recent-heading'},node('h3',{},'最近对话'),node('span',{},rows.length+' 个对话')));
  if(!rows.length){
    section.append(node('div',{class:'workspace-empty'},node('h4',{},'还没有对话'),node('p',{},'从下方输入框开始，或选一个研究示例填入草稿。'),
      node('div',{class:'scene-cards','aria-label':'研究示例'},exampleButtons())));
  }else{
    const date=new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeStyle:'short'});
    const list=node('ul',{class:'workspace-recent-list'});
    for(const row of rows){
      const updated=new Date(row.updatedAt);
      const time=Number.isFinite(updated.getTime())?node('time',{datetime:updated.toISOString()},date.format(updated)):null;
      const label=node('span',{class:'workspace-recent-title'},titleOf(row));
      const meta=node('span',{class:'workspace-recent-meta'},row.running?node('span',{class:'workspace-running'},'执行中'):null,time);
      const link=button(node('span',{class:'workspace-recent-content'},label,meta),()=>selectSession(row.sessionId).catch(fail),'workspace-recent-link');
      list.append(node('li',{},link));
    }
    section.append(list);
  }
  return node('div',{class:'workspace-home'},summary,resume,section);
}
function renderConversation(){
  const history=$('history'),previousTop=history.scrollTop,nearBottom=history.scrollHeight-previousTop-history.clientHeight<140;
  const rows=state.conversation.rows(),renderedComparisons=new Set();
  const resultCard=id=>comparisonCard(state.comparisons.get(id),{trace:state.trace,fail,onUpdate:next=>{state.comparisons.set(id,next);scheduleRender();}});
  const group=state.workspaces.find(row=>row.workspaceId===state.workspace);
  const home=!state.session&&!activeWorkspaceDraft&&group;
  const formal=state.session&&!activeWorkspaceDraft;
  $('chat-tab').parentElement.hidden=!formal;
  for(const id of ['rename-session','session-actions','deliveries-toggle'])$(id).hidden=!formal;
  $('prompt').placeholder=group&&(home||activeWorkspaceDraft)?'在「'+group.title+'」中开始新会话':'发送消息或创建任务';
  $('session-title').textContent=activeWorkspaceDraft?'新会话 · 草稿':state.session?titleOf(state.sessions.find(row=>row.sessionId===state.session)):group?.title||'新会话';
  $('session-status').textContent=historyError?'会话加载失败':awaitingHistory?'正在加载对话…':state.conversation.running?'正在执行…':state.session?'工作空间已连接':home?'工作区首页':'开始你的研究';
  $('stop').hidden=!state.conversation.running;
  $('chat-tab').classList.toggle('selected',!state.trace);$('trace-tab').classList.toggle('selected',state.trace);
  history.replaceChildren();
  if(home){
    history.append(workspaceHome(group));
    history.scrollTop=previousTop;
    return;
  }
  if(!rows.length&&state.session&&(awaitingHistory||historyError)){
    history.append(node('div',{class:'welcome',role:'status'},node('p',{},historyError||'正在加载对话…'),historyError?button('重试',()=>selectSession(state.session,{force:true}).catch(fail),'secondary'):null));
  }else if(!rows.length&&!state.conversation.live.size){
    const cards=exampleButtons();
    history.append(node('div',{class:'welcome'},node('img',{src:'/assets/geneloop-spiral.svg',alt:''}),node('h2',{},'探索未至之境'),node('p',{},'把资料、想法和下一步，连接起来。'),node('div',{class:'scene-cards','aria-label':'写作示例'},cards)));
  }
  if(state.conversation.hasMore)history.prepend(button('加载更早消息',loadEarlier,'secondary'));
  const native=state.trace?[]:state.nativePresentations||[],nativeAt=new Map();
  let turn,lastAssistant;
  for(const event of [...state.conversation.events.values()].sort((a,b)=>a.seq-b.seq)){
    if(event.type==='turn/start'){turn=event.data?.turn;lastAssistant=null;}
    if(event.type==='assistant/message'&&turn!=null)lastAssistant=event.seq;
    if(event.type==='turn/end'&&event.data?.turn===turn&&lastAssistant!=null){
      const decks=native.filter(item=>item.turn===turn);
      if(decks.length)nativeAt.set(lastAssistant,decks);
    }
  }
  const shownNative=new Set();
  for(const row of rows){
    if(row.role==='tool'||row.role==='tool-result'){
      if(state.trace)history.append(node('details',{class:'trace-item'},node('summary',{},row.role==='tool'?'调用工具 · '+row.name:'工具返回'),node('pre',{},row.arguments||JSON.stringify(row.data,null,2))));
      continue;
    }
    if(state.trace)continue;
    const article=node('article',{class:'message '+row.role,'data-seq':row.seq});
    if(row.role==='assistant')article.append(node('div',{class:'message-label'},node('img',{src:'/assets/geneloop-spiral.svg',alt:''}),'GeneLoop'));
    const decks=nativeAt.get(row.seq)||[];
    const groupedNames=new Set(decks.flatMap(({deck,slides})=>(deck?[deck,...slides]:slides).map(deliveryName)));
    article.append(blocks(row.blocks.filter(block=>!groupedNames.has(block.attachment?.name))));
    for(const deck of decks){article.append(presentationCard(deck));shownNative.add(deck);}
    if(row.role==='assistant')article.append(node('div',{class:'message-meta'},button('复制',()=>navigator.clipboard.writeText(row.blocks.filter(block=>block.type==='text').map(block=>block.text).join('\n'))),new Date(row.time).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}),row.interrupted?'已中断':null));
    history.append(article);
    const reference=state.conversation.events.get(row.seq)?.data?.harless_comparison;
    if(reference&&state.comparisons.has(reference.id)){history.append(resultCard(reference.id));renderedComparisons.add(reference.id);}
  }
  if(!state.trace&&state.conversation.live.size)history.append(node('article',{class:'message assistant live'},node('div',{class:'message-label'},'GeneLoop · 正在回复'),blocks([...state.conversation.live.values()])));
  for(const [id]of state.comparisons)if(!renderedComparisons.has(id))history.append(resultCard(id));
  for(const deck of native)if(!shownNative.has(deck))history.append(node('div',{class:'native-delivery'},presentationCard(deck)));
  if(state.trace&&state.jobs?.length)history.append(node('div',{class:'trace-item'},'后台任务',node('pre',{},JSON.stringify(state.jobs,null,2))));
  history.scrollTop=nearBottom?history.scrollHeight:previousTop;
}
async function loadEarlier(){try{const before=Math.min(...state.conversation.events.keys());const value=await rpc('session/page',{address:{kind:'session',sessionId:state.session},throughSeq:state.conversation.cursor,beforeSeq:before,maxMessages:80});state.conversation.prepend(value.records);state.conversation.hasMore=value.hasMore;renderConversation();}catch(error){fail(error);}}
function renderScenes(){
  const trigger=$('scene-select'),id=state.composerScene||'new-scene';
  const scene=state.settings?.scenes?.find(row=>row.id===id);
  trigger.value=id;
  trigger.replaceChildren(node('span',{},labels[id]||scene?.label||id),icon('chevron-down'));
}
async function chooseScene(id){return changeSelection(async()=>{const scene=state.settings.scenes.find(row=>row.id===id);if(scene?.available===false)throw Error(scene.unavailable_reason||'该场景暂不可用');await ensureSession();if(id==='files'||state.settings.selection.scene==='files'){await post('/api/harless/file-scene',{action:'select',session_id:state.session,selected:id==='files'});}if(id!=='files')state.settings=await post('/api/harless/settings',{action:'select',session_id:state.session,selection:{scene:id}});else state.settings={...state.settings,selection:{scene:'files',mode:'execute',rsi:true},scene_option_fields:[]};state.composerScene=id;renderScenes();toast('已选择 '+(labels[id]||id));}).catch(error=>{renderScenes();throw error;});}
function renderModels(){const select=$('model-select');select.replaceChildren();for(const model of state.models)select.append(node('option',{value:JSON.stringify([model.provider,model.model]),disabled:model.available===false},model.label||model.model));const selection=state.defaultModel||{};select.value=JSON.stringify([selection.provider,selection.model]);if(select.selectedIndex<0&&select.options.length)select.selectedIndex=0;refreshChoice(select);renderEfforts(selection.reasoning_effort||'off');}
function renderEfforts(selected='off'){const model=state.models.find(row=>JSON.stringify([row.provider,row.model])===$('model-select').value);const select=$('effort-select');select.replaceChildren();for(const mode of model?.reasoning_modes?.length?model.reasoning_modes:[{id:'off',label:'关闭',available:true}])select.append(node('option',{value:mode.id,disabled:mode.available===false,title:mode.unavailable_reason},mode.label||mode.id));select.value=selected;if(select.selectedIndex<0)select.selectedIndex=0;refreshChoice(select);}
async function changeModel(){const [provider,model]=JSON.parse($('model-select').value),reasoningEffort=$('effort-select').value;return changeSelection(async()=>{await ensureSession();const selected=await rpc('session/selectModel',{sessionId:state.session,provider,model,reasoningEffort});state.defaultModel={...selected.selected,reasoning_effort:selected.selected.reasoningEffort};renderModels();});}
function sceneOptions(){const form=node('form');const selection=state.settings?.selection||{};const mode=node('select',{name:'mode'},...['baseline','shadow','execute'].map(id=>node('option',{value:id},({baseline:'标准执行',shadow:'观察候选',execute:'校验后复用'})[id])));mode.value=selection.mode||'baseline';const rsi=node('input',{type:'checkbox',name:'rsi'});rsi.checked=Boolean(selection.rsi);if(!state.settings?.paired_comparison)form.append(node('div',{class:'choice-field'},node('span',{},'执行模式'),choiceControl(mode,'执行模式')),node('label',{class:'check-row'},rsi,node('span',{},'开启持续学习与改进')));
  const fields=[];for(const field of state.settings?.scene_option_fields||[]){const select=node('select',{name:field.key});for(const choice of field.values||[])select.append(node('option',{value:JSON.stringify(choice.value)},choice.label));select.value=JSON.stringify(state.settings.scene_options?.[field.key]??field.default);fields.push([field,select]);form.append(node('div',{class:'choice-field'},node('span',{},field.label),choiceControl(select,field.label)),node('p',{},(field.values||[]).map(row=>row.detail).filter(Boolean).join('；')));}
  if(state.settings?.paired_comparison)form.append(node('p',{},'本场景由服务器生成标准执行与Motif执行的对照结果。'));
  const save=button('保存选项',async()=>{save.disabled=true;try{await ensureSession();if(!state.settings.paired_comparison)await post('/api/harless/settings',{action:'select',session_id:state.session,selection:{mode:mode.value,rsi:rsi.checked}});if(fields.length)await post('/api/harless/settings',{action:'set_scene_options',session_id:state.session,options:Object.fromEntries(fields.map(([field,select])=>[field.key,JSON.parse(select.value)]))});state.settings=await request('/api/harless/settings?session_id='+encodeURIComponent(state.session));modal.close();}catch(error){fail(error);}finally{save.disabled=false;}},'primary');const modal=dialog('场景选项',form,[save]);}
function renderAttachments(){
  $('attachments').replaceChildren(...state.attachments.map((entry,index)=>{
    const remove=button(icon('close'),()=>{state.attachments.splice(index,1);renderAttachments();},'attachment-remove');
    remove.setAttribute('aria-label','移除附件：'+entry.name);
    return node('span',{class:'attachment'},icon('document'),node('span',{},(entry.uploading?'上传中 · ':'')+entry.name),remove);
  }));
}
async function attach(files){await ensureSession();const session=state.session,attachments=state.attachments;for(const file of files){const entry={name:file.name,uploading:true};attachments.push(entry);if(state.session===session)renderAttachments();try{const receipt=await upload(session,file);entry.receiptId=receipt.receiptId;entry.uploading=false;entry.session=session;}catch(error){entry.uploading=false;entry.error=true;fail(error);}if(state.session===session)renderAttachments();}}
function promoteWorkspaceDraft(sessionId){
  if(activeWorkspaceDraft?.sessionId!==sessionId)return;
  const group=state.workspaces.find(row=>row.workspaceId===activeWorkspaceDraft.workspaceId);
  if(group&&!group.sessionIds.includes(sessionId))group.sessionIds=[sessionId,...group.sessionIds];
  newWorkspaceDrafts.delete(activeWorkspaceDraft.workspaceId);
  activeWorkspaceDraft=null;
}
async function send(event){event?.preventDefault();if(state.submitting)return;const text=$('prompt').value;if(!text.trim()&&!state.attachments.length)return;if(state.attachments.some(row=>row.uploading||row.error)){toast('请等待上传完成，或移除失败附件。');return;}state.submitting=true;$('send').disabled=true;try{
    await selectionChange;const sessionId=await ensureSession();const content=promptContent(text,state.attachments,state.composerScene,state.settings.scenes);const signature=JSON.stringify(content);let pending=state.pending.get(sessionId);if(pending&&pending.signature!==signature)throw Error('上一条发送状态尚未确认，请先重新连接查看记录。');if(!pending){pending={signature,requestId:crypto.randomUUID()};state.pending.set(sessionId,pending);}await rpc('session/prompt',{sessionId,requestId:pending.requestId,mode:'queue',content,clientTimeZone:Intl.DateTimeFormat().resolvedOptions().timeZone});state.pending.delete(sessionId);promoteWorkspaceDraft(sessionId);const sentRow=state.sessions.find(row=>row.sessionId===sessionId);if(sentRow)sentRow.blank=false;renderSidebar();if(state.session===sessionId&&$('prompt').value===text){$('prompt').value='';state.attachments=[];renderAttachments();state.drafts.delete(sessionId);state.composerScene='new-scene';renderScenes();}state.conversation.running=true;scheduleRender();
  }catch(error){if(error.status>=400&&error.status<500)state.pending.delete(state.session);fail(error);}finally{state.submitting=false;$('send').disabled=false;}}
async function refreshTaskPanels(){const session=state.session;if(!session)return;const generation=state.generation;const [tasks,questions]=await Promise.allSettled([request('/api/harless/tasks'),request('/api/harless/questions?session_id='+encodeURIComponent(session))]);if(generation!==state.generation)return;
  if(questions.status==='fulfilled')renderQuestions(questions.value.questions||[]);
  const views=[];for(const event of state.conversation.events.values())if(event.type==='user/message'&&event.data.harless_comparison){const reference=event.data.harless_comparison;views.push({id:reference.id});if(reference.value&&!state.comparisons.has(reference.id))state.comparisons.set(reference.id,reference.value);}
  if(tasks.status==='fulfilled')for(const task of tasks.value.tasks||[])if(task.session_id===session&&task.task_id)views.push({id:'native-'+task.task_id,session_id:session,native:true});
  const files=[],presentations=[];
  for(const view of views){
    if(!view?.id)continue;
    const native=view.id.startsWith('native-');
    try{
      const path=deliveryPath(session,view.id),value=await request(path);
      if(generation!==state.generation)return;
      if(!native)state.comparisons.set(view.id,value);
      for(const [lane,result]of Object.entries(value.lanes||{})){
        const laneFiles=deliveryFiles(path,lane,result);
        files.push(...laneFiles);
        const deck=native&&presentation(laneFiles);
        if(deck)presentations.push({...deck,turn:value.turn});
      }
    }catch{}
  }
  if(generation!==state.generation)return;
  const hadPresentations=state.nativePresentations?.length;
  state.nativePresentations=presentations;
  state.deliveries=files;renderDeliveries();if(state.comparisons.size||presentations.length||hadPresentations)scheduleRender();
}
function renderDeliveries(){const target=$('delivery-list');target.replaceChildren();for(const file of state.deliveries||[])target.append(node('div',{class:'file-row'},button([icon('document'),node('span',{},file.name)],()=>preview(file)),node('a',{href:file.href,download:file.name,title:'下载','aria-label':'下载 '+file.name},icon('download'))));if(!target.children.length)target.append(node('p',{class:'empty'},'本对话的已验证交付文件会显示在这里。'));}
async function preview(file){try{const response=await fetch(file.href,{credentials:'same-origin'});if(!response.ok)throw Error('文件暂时不可用');const blob=await response.blob();if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(blob);const target=$('preview');target.replaceChildren(node('h3',{},file.name));const extension=file.name.split('.').pop().toLowerCase();if(['png','jpg','jpeg','gif','webp'].includes(extension))target.append(node('img',{src:previewUrl,alt:file.name}));else if(['mp4','webm'].includes(extension))target.append(node('video',{src:previewUrl,controls:true}));else if(extension==='pdf')target.append(node('iframe',{src:previewUrl,sandbox:'',title:file.name}));else if(['md','txt','json','csv','tsv','py','js','ts','tex','bib','log'].includes(extension)&&blob.size<2_000_000)target.append(node('pre',{},await blob.text()));else target.append(node('p',{},'此格式请下载后用本机应用打开。'));}catch(error){fail(error);}}
function renderQuestions(rows){const signature=JSON.stringify([state.session,rows]);if(signature===state.questionsSignature)return;state.questionsSignature=signature;const target=$('questions');target.replaceChildren();target.hidden=!rows.length;for(const row of rows){const form=node('form'),answers=[];for(const question of row.questions||[]){const selected=new Set(),custom=node('input',{placeholder:'补充说明'});const field=node('fieldset',{},node('legend',{},question.question));for(const option of question.options||[]){const value=typeof option==='string'?option:option.label;const input=node('input',{type:question.multiSelect?'checkbox':'radio',name:row.id+question.id,value,onchange:()=>{if(!question.multiSelect)selected.clear();if(input.checked)selected.add(value);else selected.delete(value);}});field.append(node('label',{},input,typeof option==='string'?option:option.label));}field.append(custom);form.append(field);answers.push(()=>({id:question.id,selected:[...selected],...(custom.value.trim()?{custom:custom.value}:{})}));}const submit=node('button',{class:'primary'},'提交回答');form.append(submit);form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{await post('/api/harless/questions',{session_id:state.session,id:row.id,answers:answers.map(read=>read())});await refreshTaskPanels();}catch(error){fail(error);submit.disabled=false;}};target.append(form);}}
async function handleEvent(frame){if(frame.type==='ready'){state.eventClientId=frame.clientId;return;}if(frame.type==='emit'){if(frame.event==='api-session/added'||frame.event==='api-session/activity'||frame.event==='api-session/removed')loadSessions().catch(()=>{});if(frame.event==='api-session/status'){const [id,running]=frame.args||[];const row=state.sessions.find(row=>row.sessionId===id);if(row)row.running=running;if(id===state.session)state.conversation.running=running;renderSidebar();scheduleRender();}if(frame.event==='api-session/error')warning(Error(frame.args?.[1]||'服务器任务未完成'));return;}if(frame.type==='cancel'){state.approvals?.get(frame.eventId)?.close();return;}if(frame.type!=='waterfall')return;
  const reply=outcome=>post('/api/$events/result',{type:'client-request',rpcId:crypto.randomUUID(),method:'$events/result',payload:{args:{clientId:state.eventClientId,eventId:frame.eventId,outcome}}});
  if(frame.event!=='approval/request'){await reply({kind:'next'});return;}
  state.approvals??=new Map();let answered=false;const answer=async value=>{if(answered)return;answered=true;await reply({kind:'result',value});modal.close();state.approvals.delete(frame.eventId);};const modal=dialog('操作需要你的确认',node('div',{},node('p',{},frame.request.reason||'服务器请求执行以下操作：'),node('pre',{},JSON.stringify(frame.request,null,2))),[button('拒绝',()=>answer('rejected').catch(fail),'secondary'),button('仅允许这一次',()=>answer('allowed-once').catch(fail),'primary')]);state.approvals.set(frame.eventId,modal);modal.addEventListener('close',()=>{if(!answered)answer('rejected').catch(fail);},{once:true});
}
function askText(title,label,initial,submit){const input=node('input',{value:initial||'',required:true}),form=node('form',{},node('label',{},label,input)),save=node('button',{class:'primary'},'确定');form.append(save);const modal=dialog(title,form);form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{await submit(input.value.trim());modal.close();}catch(error){fail(error);save.disabled=false;}};input.focus();}
function settings(initial='appearance'){return settingsPanel({user:state.user,sessions:state.sessions,archived:state.archived,titleOf,theme,fail,toast,refresh:connectWorkspace,logout:showAuth,changed:()=>{$('account-name').textContent=state.user.displayName;}},initial);}
function account(){settings('account');}
async function mutateSession(action,id){await post('/api/harless/session-trash',{action,session_id:id});if(action==='archive')state.archived.add(id);if(state.session===id)$('new-session').click();if(action==='delete'){state.drafts.delete(id);historyCache.delete(id);}await loadSessions();renderConversation();toast(action==='archive'?'对话已归档，可从设置恢复。':'对话已移入最近删除。');}
function renameSession(id){askText('重命名对话','对话名称',titleOf(state.sessions.find(row=>row.sessionId===id)),async title=>{await rpc('session/rename',{sessionId:id,title});await loadSessions();renderConversation();});}
function openSessionMenu(id,position){
  const row=state.sessions.find(row=>row.sessionId===id);if(!row)return;
  popupMenu([
    {id:'rename',label:'重命名',icon:'edit',action:()=>renameSession(id)},
    {id:'archive',label:'归档对话',icon:'archive',action:()=>mutateSession('archive',id).catch(fail)},
    {id:'copy-id',label:'复制会话 ID',icon:'copy',action:async()=>{try{await navigator.clipboard.writeText(id);toast('会话 ID 已复制。');}catch{const input=node('input',{value:id,readonly:true});dialog('复制会话 ID',node('div',{},input,node('p',{},'按 Ctrl+C 复制。')));input.focus();input.select();}}},
    {separator:true},
    {id:'trash',label:row.running?'执行中，暂不能删除':'移入最近删除',icon:'trash',danger:true,disabled:row.running,action:()=>{const confirm=dialog('移入最近删除',node('div',{},node('h3',{},titleOf(row)),node('p',{},'移入后可从设置的“最近删除”中恢复。')),[button('取消',()=>confirm.close(),'secondary'),button('确认移入',async()=>{try{await mutateSession('delete',id);confirm.close();}catch(error){fail(error);}},'primary')]);}}
  ],position);
}
function sessionActions(event){if(state.session)openSessionMenu(state.session,{anchor:event.currentTarget});}
$('login-form').onsubmit=async event=>{
  event.preventDefault();
  const submit=$('login-submit'),remember=$('remember-login').checked;
  submit.disabled=true;$('login-error').textContent='';
  try{
    const body=Object.fromEntries(new FormData(event.currentTarget));
    const result=await request('/api/account/'+(registering?'register':'login'),{
      method:'POST',headers:{'content-type':'application/json',...(remember?{'x-geneloop-remember-login':'1'}:{})},body:JSON.stringify(body),
    });
    $('login-pass').value='';
    localStorage.setItem('geneloop.desktop.remember-login',remember?'on':'off');
    if(remember)localStorage.setItem('geneloop.desktop.username',result.user?.username||body.username);
    else localStorage.removeItem('geneloop.desktop.username');
    await initialize();
  }catch(error){$('login-error').textContent=errorText(error);}
  finally{submit.disabled=false;}
};
$('auth-toggle').onclick=()=>{registering=!registering;$('display-name').hidden=$('invite-code').hidden=!registering;$('display-name').querySelector('input').required=$('invite-code').querySelector('input').required=registering;$('auth-title').textContent=registering?'加入 GeneLoop':'欢迎回来';$('login-submit').textContent=registering?'创建账号':'登录';$('auth-toggle').textContent=registering?'已有账号，返回登录':'使用邀请码注册';$('login-error').textContent='';};
$('connect-retry').onclick=()=>initialize();$('refresh-session').onclick=()=>connectWorkspace().catch(fail);$('connection-warning').onclick=()=>connectWorkspace().catch(fail);$('search').oninput=renderSidebar;
$('new-workspace').onclick=()=>askText('新建工作区','工作区名称','',async name=>{
  const {workspace}=await post('/api/harless/workspaces',{name,request_id:crypto.randomUUID()});
  if(!state.workspaces.some(row=>row.workspaceId===workspace.workspaceId))state.workspaces.push(workspace);
  openWorkspace(workspace.workspaceId);
});
$('new-session').onclick=()=>openWorkspace(state.workspace,{focus:true});
$('rename-session').onclick=()=>{if(state.session)renameSession(state.session);};
$('sidebar-toggle').onclick=()=>$('workspace').classList.toggle('sidebar-hidden');$('chat-tab').onclick=()=>{state.trace=false;renderConversation();};$('trace-tab').onclick=()=>{state.trace=true;renderConversation();};
$('scene-options').onclick=sceneOptions;
$('model-select').onchange=()=>{renderEfforts();changeModel().catch(fail);};$('effort-select').onchange=()=>changeModel().catch(fail);$('settings-nav').onclick=()=>settings();$('account-nav').onclick=account;
$('attach').onclick=()=>$('file-input').click();$('file-input').onchange=event=>{attach([...event.target.files]).catch(fail);event.target.value='';};$('composer').onsubmit=send;$('prompt').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();send();}};
$('stop').onclick=async()=>{try{await rpc('session/cancel',{sessionId:state.session});toast('已请求停止，等待服务器确认。');}catch(error){fail(error);}};
$('deliveries-toggle').onclick=()=>{$('deliveries').hidden=!$('deliveries').hidden;renderDeliveries();};$('deliveries-close').onclick=()=>$('deliveries').hidden=true;
for(const [id,name]of Object.entries({'sidebar-toggle':'sidebar','rename-session':'edit','deliveries-toggle':'files','refresh-session':'refresh','new-workspace':'plus','attach':'plus','send':'send','deliveries-close':'close'}))$(id).replaceChildren(icon(name));
$('new-session').replaceChildren(icon('plus'),'新会话');$('settings-nav').replaceChildren(icon('settings'),'设置');
for(const [id,label] of [['model-select','模型'],['effort-select','推理强度']]){
  const select=$(id),anchor=document.createComment('');
  select.before(anchor);anchor.replaceWith(choiceControl(select,label,true));
}
$('account-nav').lastElementChild.replaceChildren(icon('chevron-down'));
bindScenePicker({input:$('prompt'),select:$('scene-select'),container:$('composer'),getScenes:()=>state.settings?.scenes||[],choose:chooseScene,fail,label:scene=>labels[scene.id]||scene.label});
const actions=button(icon('more'),sessionActions,'icon');actions.id='session-actions';actions.title='管理对话';actions.setAttribute('aria-label','管理对话');$('rename-session').after(actions);
window.addEventListener('beforeunload',()=>{streams.close();clearInterval(pollTimer);if(previewUrl)URL.revokeObjectURL(previewUrl);});
initialize();
