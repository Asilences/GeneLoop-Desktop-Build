import {sceneCommand,sceneSuggestions,shortcutOf} from './composer.js';
import {node,button} from './components.js';

/** 下拉与斜杠菜单选择同一个本轮场景；文本里的已识别命令转换为选择状态。 */
export function bindScenePicker({input,select,container,getScenes,choose,fail,label}){
  let suggestions=[],active=0;
  const menu=node('div',{id:'scene-command-menu',class:'scene-command-menu',role:'listbox','aria-label':'选择当前消息的场景',hidden:true});
  container.prepend(menu);input.setAttribute('aria-controls',menu.id);input.setAttribute('aria-expanded','false');
  select.title='选择当前消息的场景，也可输入 / 快速选择';
  const close=()=>{menu.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');};
  function render(){
    menu.replaceChildren(node('div',{class:'scene-command-heading'},'选择场景'));
    suggestions.forEach((scene,index)=>{
      const control=button(node('span',{},node('strong',{},label(scene)),node('small',{},shortcutOf(scene))),()=>pick(scene.id),'scene-command-item'+(index===active?' active':''));
      control.id='scene-command-'+index;control.setAttribute('role','option');control.setAttribute('aria-selected',String(index===active));control.disabled=scene.available===false;control.title=scene.unavailable_reason||'';menu.append(control);
    });
    menu.hidden=false;input.setAttribute('aria-expanded','true');if(active>=0)input.setAttribute('aria-activedescendant','scene-command-'+active);
  }
  async function pick(id,body){
    const before=input.value,command=sceneCommand(before,getScenes());
    const next=body??(command?command.text:sceneSuggestions(before,getScenes()).length?'':before);
    input.value=next;close();
    try{await choose(id);}catch(error){if(input.value===next)input.value=before;fail(error);}
    input.focus();
  }
  input.addEventListener('input',event=>{
    if(event.isComposing)return;
    const command=sceneCommand(input.value,getScenes());
    if(command?.hasBodyBoundary){pick(command.scene,command.text);return;}
    suggestions=sceneSuggestions(input.value,getScenes());active=suggestions.findIndex(scene=>scene.available!==false);
    if(suggestions.length)render();else close();
  });
  input.addEventListener('keydown',event=>{
    if(menu.hidden||event.isComposing)return;
    if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close();return;}
    if(['ArrowDown','ArrowUp'].includes(event.key)){
      event.preventDefault();event.stopImmediatePropagation();const enabled=suggestions.map((scene,index)=>scene.available!==false?index:-1).filter(index=>index>=0);
      if(enabled.length){const at=enabled.indexOf(active);active=enabled[(at+(event.key==='ArrowDown'?1:-1)+enabled.length)%enabled.length];render();}return;
    }
    if(event.key==='Enter'&&!event.shiftKey){
      event.preventDefault();event.stopImmediatePropagation();
      if(active>=0)pick(suggestions[active].id);
    }
  },{capture:true});
  select.onchange=()=>pick(select.value);
  document.addEventListener('pointerdown',event=>{if(!menu.contains(event.target)&&event.target!==input)close();});
  return {close};
}
