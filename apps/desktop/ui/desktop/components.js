import {icons} from "./lucide-icons.js";
/** 服务器/模型内容只进入安全DOM，不执行HTML、脚本或未校验链接。 */
export const node=(tag,attributes={},...children)=>{const el=document.createElement(tag);for(const[key,value]of Object.entries(attributes)){if(key==='class')el.className=value;else if(key.startsWith('on'))el.addEventListener(key.slice(2),value);else if(value!==undefined&&value!==false)el.setAttribute(key,value===true?'':String(value));}for(const child of children.flat(Infinity))if(child!==null&&child!==undefined)el.append(child instanceof Node?child:document.createTextNode(String(child)));return el;};
export const button=(label,click,cls='')=>node('button',{type:'button',class:cls,onclick:click},label);
export const replyAction=(label,symbol,action)=>node('button',{
  type:'button',class:'result-icon','aria-label':label,'data-tooltip':label,onclick:action,
},icon(symbol));
export function icon(name){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  const attributes={viewBox:'0 0 24 24',width:20,height:20,fill:'none',stroke:'currentColor',
    'stroke-width':1.75,'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':true};
  for(const [key,value] of Object.entries(attributes))svg.setAttribute(key,value);
  for(const [tag,attributes] of icons[name]||icons.more){
    const part=document.createElementNS(svg.namespaceURI,tag);
    for(const [key,value] of Object.entries(attributes))part.setAttribute(key,value);
    svg.append(part);
  }
  return svg;
}
const choices=new WeakMap();
let choiceNumber=0;
export function choiceControl(select,label,compact=false){
  const trigger=button('',toggle,'choice-trigger');
  const menu=node('div',{class:'choice-menu',popover:'auto',role:'listbox','aria-label':label});
  menu.id='choice-menu-'+(++choiceNumber);
  trigger.setAttribute('aria-label',label);
  trigger.setAttribute('aria-haspopup','listbox');
  trigger.setAttribute('aria-expanded','false');
  trigger.setAttribute('aria-controls',menu.id);
  select.hidden=true;
  function refresh(){
    trigger.disabled=select.disabled||!select.options.length;
    trigger.replaceChildren(node('span',{},select.selectedOptions[0]?.textContent||'暂无选项'),icon('chevron-down'));
    if(menu.matches(':popover-open'))menu.hidePopover();
  }
  function toggle(){
    if(menu.matches(':popover-open')){menu.hidePopover();return;}
    menu.replaceChildren(...[...select.options].map(option=>{
      const control=button(option.textContent,()=>{
        const changed=select.value!==option.value;
        select.value=option.value;refresh();trigger.focus();
        if(changed)select.dispatchEvent(new Event('change',{bubbles:true}));
      },'choice-option');
      control.disabled=option.disabled;
      control.title=option.title;
      control.setAttribute('role','option');
      control.setAttribute('aria-selected',String(option.selected));
      if(option.selected)control.append(icon('check'));
      return control;
    }));
    const rect=trigger.getBoundingClientRect();
    const width=Math.min(Math.max(rect.width,186),innerWidth-24);
    menu.style.width=width+'px';
    menu.style.left=Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px';
    const above=rect.top>innerHeight-rect.bottom;
    const height=Math.min(260,Math.max(70,above?rect.top-16:innerHeight-rect.bottom-16));
    menu.style.maxHeight=height+'px';
    menu.style.top=above?'auto':rect.bottom+6+'px';
    menu.style.bottom=above?innerHeight-rect.top+6+'px':'auto';
    menu.showPopover();
    trigger.setAttribute('aria-expanded','true');
    (menu.querySelector('[aria-selected=true]:not(:disabled)')||menu.querySelector('button:not(:disabled)'))?.focus();
  }
  menu.addEventListener('toggle',()=>trigger.setAttribute('aria-expanded',String(menu.matches(':popover-open'))));
  menu.addEventListener('keydown',event=>{
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();menu.hidePopover();trigger.focus();return;}
    if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
    event.preventDefault();
    const items=[...menu.querySelectorAll('button:not(:disabled)')];
    if(!items.length)return;
    const at=items.indexOf(document.activeElement);
    const next=event.key==='Home'?0:event.key==='End'?items.length-1:(at+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;
    items[next].focus();
  });
  trigger.addEventListener('keydown',event=>{if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();toggle();}});
  select.addEventListener('change',refresh);
  choices.set(select,refresh);
  refresh();
  return node('div',{class:'choice-control'+(compact?' compact':'')},select,trigger,menu);
}
export function refreshChoice(select){choices.get(select)?.();}
export function markdown(text){const container=node('div',{class:'markdown'});let fence=false,code=[],paragraph=[];const flush=()=>{if(paragraph.length){const p=node('p');inline(p,paragraph.join('\n'));container.append(p);paragraph=[];}};for(const line of String(text).split('\n')){if(line.startsWith('```')){flush();if(fence){const stable=code.join('\n');container.append(node('div',{class:'code-block'},button('复制',()=>navigator.clipboard.writeText(stable),'copy'),node('pre',{},node('code',{},stable))));code=[];}fence=!fence;continue;}if(fence){code.push(line);continue;}if(!line.trim()){flush();continue;}const heading=/^(#{1,4})\s+(.+)$/.exec(line);if(heading){flush();container.append(node('h'+Math.min(heading[1].length+1,5),{},heading[2]));continue;}if(/^[-*]\s/.test(line)){flush();const item=node('p',{class:'list-line'});inline(item,'• '+line.slice(2));container.append(item);continue;}paragraph.push(line);}flush();if(fence)container.append(node('pre',{},node('code',{},code.join('\n'))));return container;}
function inline(parent,text){const pattern=/(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/g;let from=0;for(const match of text.matchAll(pattern)){parent.append(document.createTextNode(text.slice(from,match.index)));if(match[2])parent.append(node('strong',{},match[2]));else if(match[3])parent.append(node('code',{},match[3]));else parent.append(node('a',{href:match[5],target:'_blank',rel:'noopener noreferrer'},match[4]));from=match.index+match[0].length;}parent.append(document.createTextNode(text.slice(from)));}
export function blocks(content){const output=node('div');for(const block of content||[]){if(block.type==='text')output.append(markdown(block.text));else if(block.type==='reasoning')output.append(node('details',{class:'reasoning'},node('summary',{},'思考过程'),node('pre',{},block.text)));else if(block.type==='file'||block.type==='image')output.append(node('div',{class:'attachment'},icon(block.type==='image'?'image':'document'),block.attachment?.name||(block.type==='file'?'文件':'图片')));else if(block.type==='tool-result')output.append(blocks(block.content));else if(block.type==='tool-call')output.append(node('details',{},node('summary',{},block.name),node('pre',{},block.arguments)));}return output;}
export function dialog(title,body,actions=[]){const close=button(icon('close'),()=>element.close(),'icon');close.setAttribute('aria-label','关闭');const element=node('dialog',{},node('header',{},node('h2',{},title),close),body,node('footer',{},actions));document.body.append(element);element.addEventListener('close',()=>element.remove(),{once:true});element.showModal();return element;}
let activePopup;
export function popupMenu(items,{x,y,anchor,above=false}={}){
  activePopup?.();const previous=anchor||document.activeElement,element=node('div',{class:'context-menu',role:'menu'});let closed=false;
  const close=()=>{if(closed)return;closed=true;element.remove();document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',keys,true);anchor?.setAttribute('aria-expanded','false');if(previous?.isConnected)previous.focus();if(activePopup===close)activePopup=null;};
  for(const item of items){if(item.separator){element.append(node('div',{role:'separator',class:'menu-separator'}));continue;}const control=button(node('span',{class:'menu-label'},icon(item.icon),item.label),()=>{close();item.action();},item.danger?'danger':'');control.setAttribute('role','menuitem');control.dataset.action=item.id;control.disabled=Boolean(item.disabled);if(item.shortcut)control.append(node('kbd',{},item.shortcut));element.append(control);}
  document.body.append(element);const bounds=element.getBoundingClientRect(),at=anchor?.getBoundingClientRect();
  const left=x??(above?at?.left:at?.right)??8,top=y??(above&&at?at.top-bounds.height-6:at?.bottom)??8;
  element.style.left=Math.max(8,Math.min(left,innerWidth-bounds.width-8))+'px';element.style.top=Math.max(8,Math.min(top,innerHeight-bounds.height-8))+'px';
  function outside(event){if(!element.contains(event.target))close();}
  function keys(event){if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close();}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const controls=[...element.querySelectorAll('button:not(:disabled)')],at=controls.indexOf(document.activeElement),index=event.key==='Home'?0:event.key==='End'?controls.length-1:(at+(event.key==='ArrowDown'?1:-1)+controls.length)%controls.length;controls[index]?.focus();}}
  document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',keys,true);anchor?.setAttribute('aria-expanded','true');element.querySelector('button:not(:disabled)')?.focus();activePopup=close;return close;
}
