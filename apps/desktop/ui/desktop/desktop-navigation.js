import {node,button,icon} from './components.js';

/** 桌面交互层只导航已接通页面，不创建新的 Agent、终端或远程浏览能力。 */
export function bindDesktopNavigation({home,settings}){
  const $=id=>document.getElementById(id),workspace=$('workspace'),conversation=document.querySelector('.conversation'),history=$('history');
  const action=(label,symbol,run,id)=>{const el=button(icon(symbol),run,'rail-action');el.title=label;el.setAttribute('aria-label',label);if(id)el.id=id;return el;};
  const showSidebar=()=>workspace.classList.remove('sidebar-hidden');
  const rail=node('nav',{class:'primary-rail','aria-label':'快捷导航'});
  const homeButton=action('工作区首页','folder-open',()=>{showSidebar();home();},'rail-home');
  const motif=$('motif-nav');motif.title='总 Motif 库';motif.setAttribute('aria-label','总 Motif 库');
  rail.append(homeButton,motif,action('搜索对话','clock',()=>{showSidebar();$('search').focus();},'rail-search'),action('新会话','message-circle',()=>$('new-session').click(),'rail-new'),node('span',{class:'rail-spacer'}),action('设置','settings',settings,'rail-settings'));
  workspace.prepend(rail);

  const ticks=node('nav',{class:'turn-rail','aria-label':'逐轮对话定位',hidden:true});conversation.append(ticks);
  const outline=node('div',{class:'turn-outline',popover:'auto','aria-label':'对话目录'});document.body.append(outline);
  let turns=[],current=-1,frame=0,resize,scope='';
  const jump=index=>{const target=turns[index];if(!target?.isConnected)return;const top=target.getBoundingClientRect().top-history.getBoundingClientRect().top+history.scrollTop-18;history.scrollTo({top,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});};
  function mark(){frame=0;const at=history.getBoundingClientRect().top+Math.min(100,history.clientHeight*.2);let next=0;for(let i=0;i<turns.length;i++){if(turns[i].getBoundingClientRect().top<=at)next=i;else break;}if(next!==current){current=next;[...ticks.children].forEach((b,i)=>b.setAttribute('aria-current',String(i===next)));}}
  const scroll=()=>{if(!frame)frame=requestAnimationFrame(mark);};
  function refresh(){
    const next=[...history.querySelectorAll('article.message.user')];
    turns=next;current=-1;ticks.hidden=conversation.dataset.page==='workspace-home'||!turns.length||conversation.hidden;
    ticks.style.top=Math.max(82,history.getBoundingClientRect().top-conversation.getBoundingClientRect().top+24)+'px';
    ticks.replaceChildren(...turns.map((row,i)=>{const text=row.innerText.trim().replace(/\s+/g,' '),label='第 '+(i+1)+' 轮 · '+text.slice(0,70),b=button(node('i',{}),()=>jump(i),'turn-mark');b.title=label;b.setAttribute('aria-label',label);return b;}));
    directory.disabled=!turns.length;mark();
    homeButton.setAttribute('aria-current',!$('motif-library').hidden?'false':conversation.dataset.page==='workspace-home'?'page':'false');
    const nextScope=$('session-title').textContent;if(outline.matches(':popover-open')&&(nextScope!==scope||!turns.length||conversation.hidden))outline.hidePopover();scope=nextScope;
    if(document.body.dataset.desktopScreen!=='workspace'){hideTools();outline.hidePopover();turns=[];ticks.replaceChildren();ticks.hidden=true;}
  }
  const directory=action('对话目录','trace',()=>{
    if(outline.matches(':popover-open')){outline.hidePopover();return;}
    outline.replaceChildren(node('h3',{},'对话目录'),...turns.map((row,i)=>button(node('span',{},node('small',{},String(i+1).padStart(2,'0')),row.innerText.trim().replace(/\s+/g,' ').slice(0,100)),()=>{jump(i);outline.hidePopover();},'turn-outline-item')));
    const r=directory.getBoundingClientRect();outline.style.left=Math.max(8,Math.min(r.right-320,innerWidth-328))+'px';outline.style.top=r.bottom+8+'px';outline.showPopover();
  },'turns-toggle');
  directory.setAttribute('aria-haspopup','dialog');
  ticks.addEventListener('keydown',event=>{if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;event.preventDefault();const index=[...ticks.children].indexOf(document.activeElement),next=event.key==='Home'?0:event.key==='End'?turns.length-1:Math.max(0,Math.min(turns.length-1,index+(event.key==='ArrowDown'?1:-1)));ticks.children[next]?.focus();jump(next);});

  const tools=node('aside',{id:'desktop-tools',class:'desktop-tools',hidden:true,'aria-label':'工作台'});
  const close=action('关闭工作台','close',()=>{hideTools();toolButton.setAttribute('aria-expanded','false');});
  const openFile=()=>{hideTools();if($('deliveries').hidden)$('deliveries-toggle').click();};
  const tile=(label,symbol,description,run)=>button([icon(symbol),node('span',{},node('strong',{},label),node('small',{},description))],run,'tool-launcher');
  tools.append(node('header',{},node('h2',{},'工作台'),close),node('p',{},'让资料、过程和能力触手可及。'),node('div',{class:'tool-launchers'},
    tile('交付文件','files','查看当前对话的文件与预览',openFile),
    tile('执行轨迹','trace','核对当前对话的工具调用',()=>{hideTools();$('trace-tab').click();}),
    tile('工作区','folder-open','返回当前工作区与任务记录',()=>{hideTools();home();}),
    tile('总 Motif 库','scenes','查看跨场景能力与来源',()=>{hideTools();motif.click();})),
    node('section',{class:'workbench-current'},node('h3',{},'当前对话'),node('p',{id:'workbench-title'}),node('p',{},'交付文件沿用原有访问权限与预览。')));
  workspace.append(tools);
  function hideTools(){tools.hidden=true;toolButton.setAttribute('aria-expanded','false');}
  rail.addEventListener('click',hideTools);
  const reconnect=button('重新连接',()=>$('refresh-session').click(),'secondary');reconnect.classList.add('workbench-reconnect');tools.append(reconnect);
  const toolButton=action('打开工作台','sidebar',()=>{const opening=tools.hidden;tools.hidden=!opening;toolButton.setAttribute('aria-expanded',String(opening));if(opening){$('deliveries').hidden=true;$('workspace-inspector').hidden=true;$('workbench-title').textContent=$('session-title').textContent;}},'tools-toggle');
  toolButton.setAttribute('aria-controls','desktop-tools');toolButton.setAttribute('aria-expanded','false');
  const actions=document.querySelector('.header-actions');actions.append(directory,node('span',{class:'header-action-divider','aria-hidden':true}),toolButton);
  $('deliveries-toggle').addEventListener('click',()=>{hideTools();});
  $('workspace-inspector-toggle').addEventListener('click',()=>{hideTools();$('deliveries').hidden=true;});
  const mutation=new MutationObserver(()=>{if(!resize)resize=requestAnimationFrame(()=>{resize=0;refresh();});});
  mutation.observe(history,{childList:true,subtree:true,characterData:true});
  const screen=new MutationObserver(refresh);screen.observe(document.body,{attributes:true,attributeFilter:['data-desktop-screen']});screen.observe(conversation,{attributes:true,attributeFilter:['hidden','data-page']});
  history.addEventListener('scroll',scroll,{passive:true});window.addEventListener('resize',refresh);refresh();
  return ()=>{mutation.disconnect();screen.disconnect();history.removeEventListener('scroll',scroll);window.removeEventListener('resize',refresh);cancelAnimationFrame(frame);cancelAnimationFrame(resize);outline.remove();};
}
