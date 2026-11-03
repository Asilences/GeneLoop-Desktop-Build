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
export function bindScenePicker({input,select,container,getScenes,choose,fail,label}){
  let suggestions=[],active=0;
  let openedByButton=false;
  const menu=node('div',{id:'scene-command-menu',class:'scene-command-menu',role:'listbox','aria-label':'选择当前消息的场景',hidden:true});
  container.prepend(menu);input.setAttribute('aria-controls',menu.id);input.setAttribute('aria-expanded','false');
  select.title='选择当前消息的场景，也可输入 / 快速选择';
  select.setAttribute('aria-controls',menu.id);
  const close=()=>{menu.hidden=true;input.setAttribute('aria-expanded','false');select.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');};
  function render(){
    menu.replaceChildren(node('div',{class:'scene-command-heading'},'场景'));
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
      control.setAttribute('role','option');
      control.setAttribute('aria-selected',String(scene.id===select.value));
      if(scene.id===select.value)control.append(icon('check'));
      control.disabled=scene.available===false;control.title=scene.unavailable_reason||shortcut||'';menu.append(control);
    });
    menu.hidden=false;
    select.setAttribute('aria-expanded',String(openedByButton));
    input.setAttribute('aria-expanded',String(!openedByButton));
    if(openedByButton)menu.querySelectorAll('button')[active]?.focus();
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
    if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close();if(openedByButton)select.focus();return;}
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
  select.addEventListener('click',()=>{
    if(!menu.hidden&&openedByButton){close();return;}
    openedByButton=true;
    suggestions=getScenes();
    if(!suggestions.length)return;
    active=suggestions.findIndex(scene=>scene.id===select.value&&scene.available!==false);
    if(active<0)active=suggestions.findIndex(scene=>scene.available!==false);
    render();
  });
  document.addEventListener('pointerdown',event=>{if(!menu.contains(event.target)&&!select.contains(event.target)&&event.target!==input)close();});
  return {close};
}
