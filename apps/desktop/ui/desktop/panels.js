import {request,post} from './api.js';
import {node,button,dialog,icon,choiceControl} from './components.js';

const conversationSizes=[12,14,16,18,20];
export function conversationPreferences(){
  const size=Number(localStorage.getItem('geneloop.desktop.conversation-size'));
  return {
    size:conversationSizes.includes(size)?size:14,
    display:localStorage.getItem('geneloop.desktop.conversation-display')==='detailed'?'detailed':'compact',
  };
}

function conversationSettings(apply){
  const prefs=conversationPreferences();
  const setting=(label,hint,key,value,options)=>{
    const select=node('select',{},options.map(([id,name])=>node('option',{value:id},name)));
    select.value=value;
    select.onchange=()=>{
      localStorage.setItem('geneloop.desktop.conversation-'+key,select.value);
      apply();
    };
    return node('div',{class:'settings-row'},node('div',{},node('strong',{},label),node('p',{},hint)),choiceControl(select,label));
  };
  return node('section',{class:'settings-connection'},node('h4',{},'对话阅读'),
    setting('对话字号','仅调整会话消息内容。','size',prefs.size,conversationSizes.map(size=>[size,size+' px'])),
    setting('过程显示','详细模式会默认展开已完成回复的思考过程。','display',prefs.display,[['compact','紧凑'],['detailed','详细']]));
}

function themeCards(apply){
  const cards=node('div',{class:'theme-cards',role:'group','aria-label':'主题'});
  const preview=kind=>node('span',{class:'theme-sample '+kind,'aria-hidden':'true'},
    node('i',{}),node('span',{},node('i',{}),node('i',{}),node('i',{}),node('b',{})));
  for(const [value,label,symbol] of [['light','浅色','sun'],['dark','深色','moon'],['system','跟随系统','monitor']]){
    const thumbnail=node('span',{class:'theme-preview '+value},value==='system'?[preview('light'),preview('dark')]:preview(value));
    const card=button([thumbnail,node('span',{class:'theme-caption'},icon(symbol),label),node('span',{class:'theme-check'},icon('check'))],()=>{
      localStorage.setItem('geneloop.desktop.theme',value);
      for(const item of cards.children)item.setAttribute('aria-pressed',String(item===card));
      apply();
    },'theme-card');
    card.dataset.theme=value;
    card.setAttribute('aria-pressed',String((localStorage.getItem('geneloop.desktop.theme')||'system')===value));
    cards.append(card);
  }
  return cards;
}

export function settingsPanel(context,initial='appearance'){
  const body=node('div',{class:'settings-body'}),menu=node('nav',{class:'settings-nav'});
  const modal=dialog('设置',node('div',{class:'settings-layout'},menu,body));
  modal.classList.add('settings-dialog');
  const guard=fn=>async()=>{try{await fn();}catch(error){context.fail(error);}};
  let activePage, pageRevision=0;
  async function page(id,{preserveScroll=false}={}){
    activePage=id;
    const revision=++pageRevision,scroll=body.scrollTop;
    const current=()=>modal.open&&revision===pageRevision;
    for(const tab of menu.children)tab.setAttribute('aria-current',String(tab.dataset.page===id));
    if(!preserveScroll){body.replaceChildren();body.scrollTop=0;}
    if(id==='appearance'){
      body.append(node('h3',{},'桌面外观'),node('p',{},'选择桌面主题，点击后立即应用。'),themeCards(context.theme),conversationSettings(context.applyConversationPreferences),
        node('section',{class:'settings-connection'},node('h4',{},'服务器连接'),node('p',{},location.origin),
          node('p',{},'可在「文件」菜单中修改连接设置。'),button('刷新服务器状态',guard(async()=>{modal.close();await context.refresh();}),'secondary')));
    }else if(id==='models'){
      body.append(node('h3',{},'模型'),node('p',{},'查看服务器开放的模型和推理档位。当前会话的模型可在输入框旁切换。'));
      const models=context.models();
      if(!models.length)body.append(node('p',{},'当前服务器没有返回可显示的模型。'));
      for(const model of models){
        const modes=(model.reasoning_modes||[]).filter(mode=>mode.available!==false).map(mode=>mode.label||mode.id);
        body.append(node('section',{class:'settings-connection'},node('h4',{},model.label||model.model),
          node('p',{},model.available===false?(model.unavailable_reason||'暂不可用'):(modes.join(' · ')||'由服务器管理推理档位'))));
      }
    }else if(id==='archive'){
      body.replaceChildren(node('h3',{},'已归档对话'));const rows=context.archivedSessions();
      if(!rows.length)body.append(node('p',{},'暂无归档对话。'));
      for(const row of rows)body.append(node('div',{class:'settings-row'},node('span',{},context.titleOf(row)),button('恢复',guard(()=>context.restoreSession('unarchive',row.sessionId)),'secondary')));
    }else if(id==='trash'){
      if(!preserveScroll)body.append(node('h3',{},'最近删除'),node('p',{role:'status'},'正在加载最近删除…'));
      const value=await request('/api/harless/session-trash');
      if(!current())return;
      body.replaceChildren(node('h3',{},'最近删除'));
      if(!value.sessions.length)body.append(node('p',{},'暂无最近删除的对话。'));
      for(const row of value.sessions)body.append(node('div',{class:'settings-row'},node('span',{},row.title||'未命名对话'),button('恢复',guard(()=>context.restoreSession('restore',row.session_id)),'secondary')));
      if(value.sessions.length)body.append(button('清空最近删除',()=>{
        const confirm=dialog('核对后永久清空',node('div',{},node('p',{},'以下对话清空后无法从应用访问或恢复。服务器底层留存策略保持不变。'),node('ul',{},...value.sessions.map(row=>node('li',{},row.title||'未命名对话')))),[button('确认清空',guard(async()=>{await post('/api/harless/session-trash',{action:'clear',revision:value.revision});confirm.close();await page('trash');}),'primary')]);
      },'secondary'));
    }else if(id==='account'){
      body.append(node('h3',{},'账户与安全'));
      if(context.user.standalone){body.append(node('p',{},'当前连接为独立工作空间，账号由服务部署方管理。'));return;}
      const profile=node('form'),display=node('input',{value:context.user.displayName,required:true,maxlength:40}),username=node('input',{value:context.user.username,required:true,autocomplete:'username'});
      profile.append(node('label',{},'显示名称',display),node('label',{},'用户名',username),node('button',{class:'secondary'},'保存资料'));
      profile.onsubmit=async event=>{event.preventDefault();try{const value=await post('/api/account/profile',{displayName:display.value,username:username.value});Object.assign(context.user,value.user||{});context.changed();context.toast('账户资料已保存。');}catch(error){context.fail(error);}};
      const form=node('form'),current=node('input',{type:'password',autocomplete:'current-password',required:true}),next=node('input',{type:'password',autocomplete:'new-password',required:true,minlength:10}),again=node('input',{type:'password',autocomplete:'new-password',required:true,minlength:10});
      form.append(node('h4',{},'修改密码'),node('label',{},'当前密码',current),node('label',{},'新密码',next),node('label',{},'再次输入新密码',again),node('button',{class:'secondary'},'确认修改密码'));
      form.onsubmit=async event=>{event.preventDefault();if(next.value!==again.value){context.toast('两次新密码不一致。');return;}try{await post('/api/account/password',{currentPassword:current.value,newPassword:next.value});form.reset();modal.close();context.logout();context.toast('密码已修改，请重新登录。');}catch(error){context.fail(error);}};
      body.append(profile,form,button('退出登录',guard(async()=>{await post('/api/account/logout',{});modal.close();context.logout();}),'secondary'));
    }
    if(preserveScroll)body.scrollTop=scroll;
  }
  const updateSessionPage=()=>{
    if(modal.open&&(activePage==='archive'||activePage==='trash'))page(activePage,{preserveScroll:true}).catch(context.fail);
  };
  context.sessionChanges.addEventListener('change',updateSessionPage);
  modal.addEventListener('close',()=>context.sessionChanges.removeEventListener('change',updateSessionPage),{once:true});
  for(const [id,label,symbol]of [['appearance','通用设置','sun'],['models','模型','files'],['archive','已归档对话','archive'],['trash','最近删除','trash'],['account','账户与安全','user']]){
    const tab=button([icon(symbol),label],guard(()=>page(id)));
    tab.dataset.page=id;
    menu.append(tab);
  }
  page(initial).catch(context.fail);return modal;
}
