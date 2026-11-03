import {request,post} from './api.js';
import {node,button,dialog} from './components.js';

export function settingsPanel(context,initial='appearance'){
  const body=node('div',{class:'settings-body'}),menu=node('nav',{class:'settings-nav'});
  const modal=dialog('设置',node('div',{class:'settings-layout'},menu,body));
  modal.classList.add('settings-dialog');
  const guard=fn=>async()=>{try{await fn();}catch(error){context.fail(error);}};
  async function page(id){
    for(const tab of menu.children)tab.setAttribute('aria-current',String(tab.dataset.page===id));
    body.scrollTop=0;
    body.replaceChildren();
    if(id==='appearance'){
      const preference=node('select',{},...['system','light','dark'].map(value=>node('option',{value},({system:'跟随系统',light:'浅色',dark:'深色'})[value])));
      preference.value=localStorage.getItem('geneloop.desktop.theme')||'system';preference.onchange=()=>{localStorage.setItem('geneloop.desktop.theme',preference.value);context.theme();};
      body.append(node('h3',{},'桌面外观'),node('label',{},'主题',preference),node('p',{},'服务器：'+location.origin),node('p',{},'从「文件」菜单的连接设置修改服务器地址。'),button('刷新服务器状态',guard(async()=>{modal.close();await context.refresh();}),'secondary'));
    }else if(id==='archive'){
      body.append(node('h3',{},'已归档对话'));const rows=context.sessions.filter(row=>context.archived.has(row.sessionId));
      if(!rows.length)body.append(node('p',{},'暂无归档对话。'));
      for(const row of rows)body.append(node('div',{class:'settings-row'},node('span',{},context.titleOf(row)),button('恢复',guard(async()=>{await post('/api/harless/session-trash',{action:'unarchive',session_id:row.sessionId});context.archived.delete(row.sessionId);await context.refresh();await page(id);}),'secondary')));
    }else if(id==='trash'){
      body.append(node('h3',{},'最近删除'));const value=await request('/api/harless/session-trash');
      if(!value.sessions.length)body.append(node('p',{},'暂无最近删除的对话。'));
      for(const row of value.sessions)body.append(node('div',{class:'settings-row'},node('span',{},row.title||'未命名对话'),button('恢复',guard(async()=>{await post('/api/harless/session-trash',{action:'restore',session_id:row.session_id});await context.refresh();await page(id);}),'secondary')));
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
  }
  for(const [id,label]of [['appearance','外观'],['archive','已归档对话'],['trash','最近删除'],['account','账户与安全']]){
    const tab=button(label,guard(()=>page(id)));
    tab.dataset.page=id;
    menu.append(tab);
  }
  page(initial).catch(context.fail);return modal;
}
