import {sceneCommand,sceneSuggestions,shortcutOf} from './composer.js';
import {node,button,icon} from './components.js';

const sceneSymbols={
  ppt:'presentation',
  'paper-proofreading':'document',
  'research-data-analysis':'chart-column-increasing',
  files:'paperclip',
  'new-scene':'message-circle',
  'video-editing':'film',
};

/** 下拉与斜杠菜单选择同一个本轮场景；文本里的已识别命令转换为选择状态。 */
export function bindScenePicker({input,trigger,container,getScenes,getSelected,choose,fail,label,upload,options}){
  let suggestions=[],active=0;
  let openedByButton=false;
  const menu=node('div',{id:'scene-command-menu',class:'scene-command-menu',role:'listbox','aria-label':'选择当前消息的场景',hidden:true});
  container.prepend(menu);input.setAttribute('aria-controls',menu.id);input.setAttribute('aria-expanded','false');
  trigger.setAttribute('aria-controls',menu.id);
  const close=()=>{menu.hidden=true;input.setAttribute('aria-expanded','false');trigger.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');};
  function action(id,symbol,title,hint,run){
    const control=button([node('span',{class:'scene-command-symbol'},icon(symbol)),
      node('span',{class:'scene-command-label'},node('span',{class:'scene-command-name'},title),hint?node('small',{},hint):null)],
      ()=>{close();trigger.focus();run();},'scene-command-item');
    control.dataset.action=id;control.setAttribute('role','menuitem');return control;
  }
  function render(){
    menu.setAttribute('role',openedByButton?'menu':'listbox');
    menu.setAttribute('aria-label',openedByButton?'添加':'选择当前消息的场景');
    menu.classList.toggle('composer-add-menu',openedByButton);
    menu.replaceChildren(node('div',{class:'scene-command-heading'},'场景'));
    if(openedByButton)menu.prepend(node('div',{class:'scene-command-heading'},'添加'),
      action('composer-upload','paperclip','添加照片或文件','从电脑上传',upload));
    suggestions.forEach((scene,index)=>{
      const shortcut=shortcutOf(scene);
      const description=scene.id==='new-scene'?'通用对话':scene.id==='ppt'?'演示文稿':label(scene);
      const code=scene.id==='files'?'file':shortcut?.slice(1)||scene.id;
      const control=button([
        node('span',{class:'scene-command-symbol'},icon(sceneSymbols[scene.id]||'scenes')),
        node('span',{class:'scene-command-label'},node('span',{class:'scene-command-name'},code),node('small',{},description)),
      ],()=>pick(scene.id),'scene-command-item'+(index===active?' active':''));
      control.id='scene-command-'+index;
      control.dataset.scene=scene.id;
      if(shortcut)control.dataset.shortcut=shortcut;
      control.setAttribute('role',openedByButton?'menuitemradio':'option');
      const selected=scene.id===getSelected();
      control.setAttribute(openedByButton?'aria-checked':'aria-selected',String(selected));
      if(selected)control.append(icon('check'));
      control.disabled=scene.available===false;control.title=scene.unavailable_reason||shortcut||'';menu.append(control);
    });
    if(openedByButton&&getSelected()!=='new-scene'){
      menu.append(action('composer-clear-scene','close','清除已选场景',null,()=>pick('new-scene',input.value)));
    }
    if(openedByButton)menu.append(action('composer-options','settings','场景选项',null,options));
    menu.hidden=false;
    trigger.setAttribute('aria-expanded',String(openedByButton));
    input.setAttribute('aria-expanded',String(!openedByButton));
    if(openedByButton)menu.querySelector('button')?.focus();
    else if(active>=0)input.setAttribute('aria-activedescendant','scene-command-'+active);
  }
  async function pick(id,body){
    const before=input.value,command=sceneCommand(before,getScenes());
    const next=body??(command?command.text:sceneSuggestions(before,getScenes()).length?'':before);
    input.value=next;close();input.focus();
    try{await choose(id);}catch(error){if(input.value===next)input.value=before;fail(error);}
  }
  input.addEventListener('input',event=>{
    if(event.isComposing)return;
    openedByButton=false;
    const command=sceneCommand(input.value,getScenes());
    if(command?.hasBodyBoundary){pick(command.scene,command.text);return;}
    suggestions=sceneSuggestions(input.value,getScenes());active=suggestions.findIndex(scene=>scene.available!==false);
    if(suggestions.length)render();else close();
  });
  function keys(event){
    if(menu.hidden||event.isComposing)return;
    if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close();if(openedByButton)trigger.focus();return;}
    if(openedByButton){
      if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
        event.preventDefault();
        const controls=[...menu.querySelectorAll('button:not(:disabled)')],at=controls.indexOf(document.activeElement);
        const next=event.key==='Home'?0:event.key==='End'?controls.length-1:(at+(event.key==='ArrowDown'?1:-1)+controls.length)%controls.length;
        controls[next]?.focus();
      }
      return;
    }
    if(['ArrowDown','ArrowUp'].includes(event.key)){
      event.preventDefault();event.stopImmediatePropagation();const enabled=suggestions.map((scene,index)=>scene.available!==false?index:-1).filter(index=>index>=0);
      if(enabled.length){const at=enabled.indexOf(active);active=enabled[(at+(event.key==='ArrowDown'?1:-1)+enabled.length)%enabled.length];render();}return;
    }
    if(event.key==='Enter'&&!event.shiftKey){
      event.preventDefault();event.stopImmediatePropagation();
      if(active>=0)pick(suggestions[active].id);
    }
  }
  input.addEventListener('keydown',keys,{capture:true});
  menu.addEventListener('keydown',keys);
  trigger.addEventListener('click',()=>{
    if(!menu.hidden&&openedByButton){close();return;}
    openedByButton=true;
    suggestions=getScenes().filter(scene=>scene.id!=='new-scene');
    active=-1;
    render();
  });
  document.addEventListener('pointerdown',event=>{if(!menu.contains(event.target)&&!trigger.contains(event.target)&&event.target!==input)close();});
  return {close};
}
