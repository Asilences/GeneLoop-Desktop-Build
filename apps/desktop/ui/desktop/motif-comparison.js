import {node,button,icon} from './components.js';

export const motifStatuses={certified:'已认证',pending_certification:'待认证',invalid:'已失效',registered:'旧格式已登记'};
const sampleNames=['材料提取','来源核验','格式整理','表格清洗','材料汇总','引用校验','报告构建','增量更新'];
const sampleStates=['certified','certified','certified','pending_certification','certified','invalid','certified','pending_certification'];
const sampleUses=[6,4,3,1,5,0,6,1];
const namespace='http://www.w3.org/2000/svg';
const make=(parent,tag,attrs={})=>{const el=document.createElementNS(namespace,tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,String(v));parent?.append(el);return el;};
const value=n=>n===null||n===undefined?'—':String(n);
const levelName=n=>n===null?'未分层':n===1?'L1 基础':n===2?'L2 组合':'L3+ 高阶';

/** 真实视图不从认证/次数/工具数猜测层级；示例完全独立，不写回能力库。 */
export function motifData(view,example=false){
  const caps=example?sampleNames.map((name,i)=>({id:'example-'+(i+1),name,status:sampleStates[i],level:i<4?1:i<6?2:3,reuses:sampleUses[i],tools:[],tool_flow:[],parents:({4:[0],5:[2],6:[4],7:[1,2]})[i]?.map(n=>'example-'+(n+1))||[],sample:true,index:i})):view?.capabilities.map(c=>({...c,tool_flow:c.toolFlow||c.tool_flow||[],level:null,sample:false,reuses:view.isPool?c.reuses:view.raw.source?null:c.events.filter(e=>e.kind==='invoke'&&e.status==='applied'&&e.actual_execution).length}))||[];
  return {known:example||Boolean(view&&(view.known??true)),example,caps,reuse:example?26:view?.isPool?view.summary.applied:view&&!view.raw.source?view.summary.applied:null,source:example?'示例数据':view?.isPool?'总 Motif 库':view?.raw.source?.label||'当前工作区',usageLabel:view?.isPool?'已记录复用':'实际复用'};
}

export function motifCardData(pool,state,view=pool){
  return motifData(view,state.example??(pool.capabilities.length===0));
}

export function motifExampleSwitch(type,data,onToggle){
  const control=button(data.example?'查看账号数据':'查看层级示例',()=>onToggle(!data.example),'motif-example-switch');
  control.dataset.motifExample=type;
  return control;
}

export function motifSummary(data){
  const counts=Object.fromEntries(Object.keys(motifStatuses).map(key=>[key,data.caps.filter(c=>c.status===key).length]));
  const bar=node('div',{class:'motif-status-bar','aria-hidden':true});
  for(const key of Object.keys(motifStatuses)){const part=node('i',{class:'motif-status-'+key});part.style.flexGrow=String(counts[key]);bar.append(part);}
  const stats=node('div',{class:'motif-comparison-counts'},node('span',{},node('small',{},'Motif 总量'),node('strong',{'data-motif-total':''},data.known?data.caps.length:'—')),
    node('span',{},node('small',{},data.usageLabel||'实际复用'),node('strong',{},value(data.reuse))));
  const legend=node('div',{class:'motif-status-counts'},...Object.entries(motifStatuses).map(([key,label])=>node('span',{class:'motif-status-'+key},node('i',{}),label+' ',node('b',{'data-status-count':key},data.known?counts[key]:'—'))));
  return node('div',{class:'motif-comparison-summary'},stats,bar,legend);
}

function symbol(cap){
  const svg=make(null,'svg',{viewBox:'0 0 100 58',class:'motif-unit-symbol','aria-hidden':'true'});
  if(cap.sample){
    const steps=cap.level===1?4+cap.index%3:cap.level===2?24+cap.index%3:96+cap.index*4,points=[[0,0],[1,0]],dirs=[[1,0],[0,1],[-1,0],[0,-1]];
    let heading=0;for(let i=1;i<steps;i++){let odd=i;while(odd%2===0)odd/=2;heading=(heading+(odd%4===1?1:3))%4;const p=points.at(-1),d=dirs[heading];points.push([p[0]+d[0],p[1]+d[1]]);}
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys),s=Math.min(80/(x1-x0||1),43/(y1-y0||1));
    make(svg,'path',{d:points.map(([x,y],i)=>(i?'L':'M')+(50+(x-(x0+x1)/2)*s)+' '+(29+(y-(y0+y1)/2)*s)).join('')});
  }else{
    const tools=[...new Set([...(cap.tools||[]),...(cap.tool_flow||[]).flatMap(e=>[e.from_tool,e.to_tool])])],visible=tools.slice(0,12),positions=new Map(visible.map((t,i)=>[t,[15+(i%4)*23,12+Math.floor(i/4)*16]]));
    for(const e of cap.tool_flow||[]){const a=positions.get(e.from_tool),b=positions.get(e.to_tool);if(a&&b)make(svg,'path',{d:`M${a[0]} ${a[1]}H${b[0]}V${b[1]}`});}
    for(const p of positions.values())make(svg,'rect',{x:p[0]-3,y:p[1]-3,width:6,height:6});
    if(!tools.length)make(svg,'path',{d:'M36 18H28V40H36M64 18H72V40H64M46 16L54 42'});
  }
  return svg;
}

export function motifInformation(data,cap){
  if(!cap)return node('div',{class:'motif-selected-info'},node('p',{},'选择一个 Motif 查看信息。'));
  const info=node('div',{class:'motif-selected-info'},node('h3',{},cap.name),node('span',{class:'motif-state-label motif-status-'+cap.status},motifStatuses[cap.status]),
    node('dl',{},node('dt',{},'层级'),node('dd',{},levelName(cap.level)),node('dt',{},data.usageLabel||'实际复用'),node('dd',{},value(cap.reuses)),node('dt',{},'能力 ID'),node('dd',{title:cap.id},cap.sample?'M'+String(cap.index+1).padStart(2,'0'):cap.id.slice(0,12)+'…')));
  if(cap.origins?.length){info.append(node('h4',{},'来源'),...cap.origins.map(o=>node('p',{},o.title+' · '+(o.release??'版本未提供'))));if(cap.statusConflict)info.append(node('p',{class:'motif-preview-note'},'来源状态有差异；显示当前目录优先的状态。'));}
  if(cap.sample){
    const lineage=[];const visit=(c,depth=0)=>{if(depth>2||lineage.some(row=>row.id===c.id))return;for(const id of c.parents||[]){const parent=data.caps.find(row=>row.id===id);if(parent)visit(parent,depth+1);}lineage.push(c);};visit(cap);
    info.append(node('h4',{},'示例来源与演化'),node('div',{class:'motif-selected-lineage'},...lineage.flatMap((c,i)=>[i?node('span',{'aria-hidden':true},'→'):null,node('span',{class:'motif-status-'+c.status},symbol(c),node('small',{},c.name))])),node('p',{class:'motif-preview-note'},'示例数据 · 非工作区结果'));
  }else{
    info.append(node('h4',{},'内部工具结构'),symbol(cap),node('p',{},(cap.tools||[]).join('、')||'当前来源未提供工具列表。'),node('p',{class:'motif-preview-note'},'当前来源未提供结构层级和 Motif 组合谱系。'));
    if(cap.localStructure)info.append(node('h4',{},'本机结构认证'),node('p',{},'独立轨迹 '+value(cap.witnesses)+' 项 · 质量和费用待验证'),
      node('p',{class:'motif-small-id'},'证书 '+cap.version.certificate_digest.slice(0,16)+'…'));
    else if(cap.version)info.append(node('h4',{},'版本与认证'),node('p',{},'库版本 '+value(cap.version.library_generation)),node('p',{class:'motif-small-id'},cap.version.certificate_digest?'证书 '+cap.version.certificate_digest.slice(0,16)+'…':'证书未提供'));
  }
  return info;
}

function units(type,data,state,onSelect,expanded){
  if(!data.known)return node('p',{class:'motif-preview-note'},'正在读取账号可见的 Motif 数据。');
  if(!data.caps.length)return node('p',{class:'motif-preview-note'},'当前来源尚无 Motif。');
  const groups=type==='hierarchy'?[3,2,1,null].map(level=>({level,caps:data.caps.filter(c=>c.level===level)})).filter(g=>g.caps.length):[{caps:data.caps}];
  const container=node('div',{class:'motif-unit-groups'});
  for(const group of groups){
    const limit=expanded?120:4,shown=group.caps.slice(0,limit),grid=node('div',{class:'motif-unit-grid '+(type==='hierarchy'?'motif-unit-tier':'')});
    for(const c of shown){const tile=button([symbol(c),node('span',{class:'motif-unit-name'},c.name),node('small',{class:'motif-unit-level'},c.sample?'M'+String(c.index+1).padStart(2,'0')+' · '+levelName(c.level):'层级未提供')],()=>onSelect(c.id),'motif-unit motif-status-'+c.status);
      if(expanded&&type==='hierarchy'&&c.sample)tile.dataset.motifParents=c.parents.join(' ');
      tile.dataset.motifId=c.id;tile.setAttribute('aria-pressed',String(state.selected===c.id));tile.title=c.name+' · '+motifStatuses[c.status]+' · '+levelName(c.level);grid.append(tile);}
    const section=node('section',{class:'motif-unit-group'});
    if(type==='hierarchy')section.append(node('h4',{},levelName(group.level),node('span',{},String(group.caps.length))));
    section.append(grid);
    if(shown.length<group.caps.length)section.append(node('p',{class:'motif-preview-note'},'显示 '+shown.length+' / '+group.caps.length+'，其余请在 Motif 库查看。'));
    container.append(section);
  }
  if(expanded&&type==='hierarchy'&&data.example)container.append(make(null,'svg',{class:'motif-relation-overlay','aria-hidden':'true'}));
  return container;
}

/** 只绘制来源明确提供的组合边，当前为独立示例；认证和工具依赖不能产生组合边。 */
export function drawMotifRelations(root){
  const svg=root.querySelector('.motif-relation-overlay');if(!svg)return;
  const bounds=svg.parentElement.getBoundingClientRect();svg.setAttribute('viewBox',`0 0 ${bounds.width} ${bounds.height}`);svg.replaceChildren();
  const tiles=[...root.querySelectorAll('[data-motif-parents]')];
  for(const child of tiles)for(const id of child.dataset.motifParents.split(' ').filter(Boolean)){
    const parent=tiles.find(t=>t.dataset.motifId===id);if(!parent)continue;
    const a=child.getBoundingClientRect(),b=parent.getBoundingClientRect(),x1=a.x+a.width/2-bounds.x,y1=a.bottom-bounds.y,x2=b.x+b.width/2-bounds.x,y2=b.top-bounds.y;
    make(svg,'path',{d:`M${x1} ${y1}V${(y1+y2)/2}H${x2}V${y2}`});
  }
}

export function motifComparisonBody(type,data,state,onChange,{expanded=false,onOpen=()=>{},preview=true}={}){
  const select=id=>{state.selected=id;onChange();if(!expanded)onOpen();};
  const source=expanded&&preview?motifExampleSwitch(type,data,example=>{state.example=example;state.selected=example?'example-7':null;onChange();}):null;
  const note=node('p',{class:'motif-preview-note'},data.example?'示例数据 · 非工作区结果':data.known?'颜色表示认证状态 · 层级未提供的单独归类':'当前工作区数据尚未提供');
  const content=node('div',{class:'motif-comparison-content','data-source':data.example?'example':data.source==='总 Motif 库'?'account':'workspace'},motifSummary(data),source,units(type,data,state,select,expanded),expanded||data.example?note:null);
  if(expanded)content.append(motifInformation(data,data.caps.find(c=>c.id===state.selected)||data.caps[0]));
  return content;
}

export function motifComparisonCards(view,states,onChange,onOpen,onCollapse){
  return ['hierarchy','distribution'].map(type=>{
    const state=states[type],name=type==='hierarchy'?'结构演化':'能力分布',letter=type==='hierarchy'?'A':'B',id='motif-'+type+'-content';
    const data=motifCardData(view,state),collapsed=data.example?state.exampleCollapsed:state.collapsed;
    const toggle=button([node('span',{},name),node('span',{class:'motif-summary-tag'},letter),data.example?node('span',{class:'motif-summary-tag'},'示例'):null,icon(collapsed?'chevron-right':'chevron-down')],()=>onCollapse(type,data.example),'motif-comparison-toggle motif-'+type+'-toggle');toggle.setAttribute('aria-expanded',String(!collapsed));toggle.setAttribute('aria-controls',id);
    const expand=button('↗',()=>onOpen(type),'motif-card-expand');expand.dataset.motifExpand=type;expand.setAttribute('aria-label','放大'+name);
    const body=motifComparisonBody(type,data,state,onChange,{onOpen:()=>onOpen(type)});body.id=id;body.hidden=collapsed;
    return node('section',{class:'motif-comparison-card motif-'+type+'-card','data-summary-card':type,'aria-label':name+' '+letter},node('header',{},toggle,expand),body);
  });
}
