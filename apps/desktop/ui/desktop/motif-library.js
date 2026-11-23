import {node,button,icon,choiceControl,dialog} from './components.js';
import {readMotifEvidence,usd} from './motif-evidence.js';
import {request} from './api.js';
import {workspaceRunView} from './workspace-run.js';
import {motifData,motifCardData,motifExampleSwitch,motifSummary,motifInformation,motifComparisonBody,motifComparisonCards,drawMotifRelations} from './motif-comparison.js';
import {buildMotifPool,filterMotifPool,sceneLabel} from './motif-pool.js';
const statusLabel={certified:'已认证',pending_certification:'待认证',invalid:'已失效',registered:'旧格式已登记'};
const dependencyLabel={environment:'运行环境',dependency_lock:'依赖锁',effect_contract:'读写约束',artifact:'绑定原件'};
const eventLabel={match:'匹配',invoke:'执行',fallback:'回退'};
const short=value=>value?value.slice(0,10)+'…':'未知';
const count=value=>value===null||value===undefined?'未知':String(value);
const badge=(text,kind='')=>node('span',{class:'motif-badge '+kind},text);
const card=(label,value,note)=>node('div',{class:'motif-stat'},node('span',{},label),node('strong',{},value),node('small',{},note));
const section=(title,...children)=>node('section',{class:'motif-section'},node('h3',{},title),...children);
const empty=(title,text)=>node('div',{class:'motif-empty'},icon('scenes'),node('h2',{},title),node('p',{},text));
const hash=(label,value)=>node('div',{class:'motif-hash'},node('span',{},label),node('code',{title:value||'未知'},value||'未知'));

function poolControls(pool,selection,onChange){
  const scenes=[...new Set(pool.sources.map(s=>s.scene).filter(Boolean))].sort();
  const fields=[['scene','场景',[['all','全部场景'],...scenes.map(id=>[id,sceneLabel(id)])]],['source','来源',[['all','全部来源'],...pool.sources.map(s=>[s.id,s.title+(s.status==='ready'?'':' · 暂不可用')])]],['status','状态',[['all','全部状态'],...Object.entries(statusLabel)]]];
  return node('div',{class:'motif-pool-controls'},...fields.map(([key,label,items])=>{
    const select=node('select',{'aria-label':'筛选 Motif '+label,'data-pool-filter':key},...items.map(([value,text])=>node('option',{value},text)));
    select.value=selection[key]||'all';select.addEventListener('change',()=>{selection[key]=select.value;onChange();});return node('label',{},node('span',{},label),choiceControl(select,'筛选 Motif '+label,true));
  }));
}

let cultureSequence=0;
/** 本地 SVG 玻璃插画；球体只投影当前快照中的能力，不生成装饰性能力或关系。 */
function cultureGraphic(capabilities=[],interaction=null){
  const namespace='http://www.w3.org/2000/svg',prefix='motif-culture-'+cultureSequence++;
  const make=(parent,tag,attrs={})=>{const el=document.createElementNS(namespace,tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,v);parent?.append(el);return el;};
  const svg=make(null,'svg',{viewBox:'0 0 300 210',class:'motif-culture','pointer-events':'none',...(interaction?{role:'group','aria-label':'Motif 鱼缸，聚焦或悬浮节点查看信息'}:{'aria-hidden':'true'})}),defs=make(svg,'defs');
  const url=name=>'url(#'+prefix+'-'+name+')';
  function gradient(name,radial,attrs,stops){const g=make(defs,radial?'radialGradient':'linearGradient',{id:prefix+'-'+name,...attrs});for(const[offset,color,opacity=1]of stops)make(g,'stop',{offset,'stop-color':color,'stop-opacity':opacity});}
  gradient('body',false,{x2:'100%',y2:'0%'},[['0%','#284e61',.48],['1.8%','#f2fbff',.9],['4%','#9fc5cf',.36],['9%','#fff',.34],['17%','#fff',.05],['48%','#fcfeff',.02],['83%','#d6eef0',.06],['94%','#9fbdc5',.36],['98%','#f0fbff',.85],['100%','#385a66',.53]]);
  gradient('water',false,{x2:'0%',y2:'100%'},[['0%','var(--culture-water-top)',.37],['28%','#b5dcde',.07],['70%','var(--culture-water-mid)',.10],['94%','var(--culture-water-bottom)',.26],['100%','#62989e',.27]]);
  gradient('surface',false,{x2:'100%',y2:'35%'},[['0%','#87b3bc',.40],['17%','#eafcff',.58],['50%','#f8feff',.10],['78%','#b6dce0',.19],['100%','#7cabb6',.44]]);
  gradient('back-rim',false,{x2:'0%',y2:'100%'},[['0%','#f9ffff',.96],['20%','#789ca8',.74],['54%','#d4e9ed',.55],['82%','#fff',.92],['100%','#7ca6af',.48]]);
  gradient('front-rim',false,{x2:'0%',y2:'100%'},[['0%','#4b7180',.55],['27%','#e4f3f7',.81],['46%','#fff',.98],['70%','#9cbdc6',.57],['100%','#4a717d',.67]]);
  gradient('base',false,{x2:'0%',y2:'100%'},[['0%','#8badb6',.35],['18%','#f6ffff',.88],['43%','#bbd4db',.58],['68%','#537989',.49],['88%','#dff5f7',.75],['100%','#668996',.69]]);
  gradient('reflection',false,{x2:'100%',y2:'0%'},[['0%','#effdff',0],['25%','#f8feff',.56],['48%','#fff',.9],['58%','#fff',.17],['100%','#fff',0]]);
  gradient('ground',true,{cx:'50%',cy:'50%',r:'50%'},[['0%','#243f4a',.3],['57%','#426574',.14],['100%','#426574',0]]);
  gradient('glint',false,{x2:'100%',y2:'0%'},[['0%','#fff',0],['24%','#fff',.9],['53%','#f8feff',.66],['90%','#dcf8fc',.25],['100%','#fff',0]]);
  for(const[name,light,mid,edge]of [['certified','#e8ffc3','#66da80','#119a78'],['pending_certification','#e5e9ff','#83a7f9','#496fc0'],['invalid','#ffe6ed','#d990b2','#9c5d87'],['registered','#fff0d7','#d8bf8c','#9b8152']])
    gradient(name,true,{cx:'31%',cy:'24%',r:'80%'},[['0%','#fff'],['12%',light],['40%',mid],['81%',edge],['100%',edge,.91]]);
  const trace=(parent,d,stroke,width,opacity=1)=>make(parent,'path',{d,fill:'none',stroke,'stroke-width':width,'stroke-opacity':opacity,'stroke-linecap':'round'});
  const wall='M26 43L34 147C36 168 54 178 82 184C118 191 182 191 218 184C246 178 264 168 266 147L274 43';
  const water='M36 67C45 51 255 51 264 67L256 146C254 164 230 174 203 179C172 184 128 184 97 179C70 174 46 164 44 146Z';
  const waterClip=make(defs,'clipPath',{id:prefix+'-inside'});make(waterClip,'path',{d:water});
  make(svg,'ellipse',{cx:152,cy:193,rx:145,ry:16,fill:url('ground')});
  make(svg,'ellipse',{cx:150,cy:191,rx:100,ry:5,fill:url('ground')});
  make(svg,'path',{d:wall+'C274 74 26 74 26 43Z',fill:url('body')});
  trace(svg,wall,'#627e89',.75,.45);
  make(svg,'ellipse',{cx:150,cy:43,rx:124,ry:25,fill:url('back-rim'),'fill-opacity':.21});
  trace(svg,'M26 43C26 10 274 10 274 43M33 43C33 18 267 18 267 43',url('back-rim'),2.6,.92);
  trace(svg,'M37 38C63 16 182 14 242 26',url('glint'),2.3);
  make(svg,'path',{d:water,fill:url('water')});
  make(svg,'ellipse',{cx:150,cy:67,rx:114,ry:16,fill:url('surface')});
  trace(svg,'M36 67C40 48 259 48 264 67','#7da9b5',.8,.51);
  trace(svg,'M40 70C62 86 238 86 260 70',url('glint'),1.3,.82);
  const inside=make(svg,'g',{'clip-path':url('inside')});
  // Light bands suggest refraction at the curved wall and the thick base.
  trace(inside,'M34 145C46 162 58 173 96 176S206 187 269 154',url('glint'),4,.53);
  trace(inside,'M56 161C81 177 135 167 157 179C187 187 233 169 252 160',url('glint'),1.6,.81);
  trace(inside,'M59 77C48 99 53 128 69 151M243 79C250 99 246 130 238 147','#eefcff',1.15,.39);
  const positions=[[150,116,15],[215,91,11],[82,137,12],[109,83,8],[194,149,12],[62,100,8],[232,139,10],[133,157,10],[173,81,8],[118,123,9],[203,121,8],[165,143,8],[78,166,8],[245,111,7],[51,145,7],[142,89,7],[98,159,7],[184,107,7]];
  const samplePositions=[[72,153,10],[124,153,10],[176,153,10],[228,153,10],[105,115,12],[195,115,12],[121,86,14],[179,86,14]];
  const columns=Math.ceil(Math.sqrt(capabilities.length*1.8)),rows=Math.ceil(capabilities.length/columns),spread=capabilities.map((_,i)=>[55+(i%columns)*190/Math.max(1,columns-1),80+Math.floor(i/columns)*80/Math.max(1,rows-1),Math.min(13,65/Math.max(1,rows),70/Math.max(1,columns))]);
  capabilities.slice(0,interaction?48:18).map((capability,i)=>({capability,position:capability.sample?samplePositions[capability.index]:interaction?(capabilities.length===1?[150,116,15]:spread[i]):positions[i],i})).sort((a,b)=>a.position[1]-b.position[1]).forEach(({capability,position:[x,y,r],i})=>{
    const anchor=make(inside,'g',{transform:`translate(${x} ${y})`}),particle=make(anchor,'g',{class:'culture-particle phase-'+i%4,'data-capability-id':capability.id});
    const label=capability.name+' · '+statusLabel[capability.status];make(particle,'title').textContent=label;
    if(interaction){particle.setAttribute('role','button');particle.setAttribute('tabindex','0');particle.setAttribute('pointer-events','all');particle.setAttribute('aria-label',label);particle.addEventListener('pointerenter',()=>interaction.inspect(capability));particle.addEventListener('focus',()=>interaction.inspect(capability));particle.addEventListener('click',()=>interaction.select(capability));particle.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();interaction.select(capability);}});}
    make(particle,'circle',{r:r+1.8,fill:url(capability.status),opacity:.11});
    make(particle,'circle',{r,fill:url(capability.status),stroke:'#f6ffff','stroke-opacity':.68,'stroke-width':.65});
    make(particle,'ellipse',{cx:-r*.28,cy:-r*.43,rx:r*.28,ry:r*.135,fill:'#fff',opacity:.86,transform:'rotate(-30)'});
    trace(particle,`M${r*.25} ${r*.82}Q${r*.72} ${r*.64} ${r*.82} ${r*.29}`,'#f5fdff',.68,.7);
  });
  const front=make(svg,'g',{'pointer-events':'none'});
  make(front,'path',{d:'M29 49L38 148Q41 163 59 169L49 156L41 53Z',fill:url('reflection')});
  make(front,'path',{d:'M261 53L252 145Q249 163 231 173Q261 163 264 148L272 49Z',fill:url('reflection'),'fill-opacity':.66});
  trace(front,'M34 53L42 141Q44 158 62 167','#f9ffff',1.2,.90);
  trace(front,'M268 53L259 142Q256 157 244 162','#537e8b',.8,.42);
  make(front,'path',{d:'M39 159C56 191 244 191 261 159C258 178 225 187 207 190C171 196 129 196 93 190C75 187 42 178 39 159Z',fill:url('base')});
  trace(front,'M49 172C84 194 218 194 250 171','#608491',1.2,.63);
  trace(front,'M57 174C94 190 199 190 237 177',url('glint'),2.1,.95);
  trace(front,'M78 185C114 195 184 194 220 185','#ecffff',.9,.79);
  make(front,'path',{d:'M26 42C27 72 273 72 274 42L273 47C270 79 30 79 27 47Z',fill:url('front-rim')});
  trace(front,'M27 43C27 74 273 74 273 43',url('glint'),1.6,.95);
  trace(front,'M35 48C53 68 155 72 218 63',url('glint'),2.2,.9);
  return svg;
}

/** 导入仅驻留当前页面内存；不发送资料、不改变 Agent 和工作区。 */
function createMotifView({trigger,host,conversation,deliveries,navigation=[],embedded=false,inspector=null,isActive=()=>true,onVisibility=()=>{},scopeChoices=()=>[],onScope=()=>{},onReset=()=>{}}) {
  let model=null,selected=null,tab='library',filter='all',query='',source='',opened=false,loading=false,error='',revision=0;
  let workspace=null,live=false,choices=[],choiceId=null,accountPool=null;
  const poolSelection={scene:'all',source:'all',status:'all',query:'',selected:null};
  const runState={taskId:null,planOpen:true,contextOpen:true,recentOpen:false};
  const input=node('input',{type:'file',accept:'.json,application/json',hidden:true,'aria-label':'导入 Motif 证据快照'});
  const changeTab=next=>{tab=next;render();};
  const version=()=>model?.raw.source?.release||count(model?.libraryVersion);
  function choose(row){choiceId=row?.id;model=row?.evidence?readMotifEvidence(row.evidence):null;selected=model?.capabilities[0]?.id||null;source=row?.title||'';live=true;error=row?.status==='unavailable'?'此场景库当前不可读取，请检查服务端库与认证配置。':'';render();onReset();}
  function sourcePicker(){if(choices.length<2)return null;const picker=node('select',{'aria-label':'选择 Motif 数据来源'});for(const row of choices)picker.append(node('option',{value:row.id},row.title+(row.status==='unavailable'?' · 暂不可用':'')));picker.value=choiceId;picker.addEventListener('change',()=>choose(choices.find(row=>row.id===picker.value)));return node('div',{class:'motif-source-selector'},node('span',{},'数据来源'),choiceControl(picker,'选择 Motif 数据来源',true));}
  const back=()=>{opened=false;host.hidden=true;if(conversation)conversation.hidden=false;trigger.removeAttribute('aria-current');onVisibility();};
  const open=()=>{opened=true;conversation.hidden=true;deliveries.hidden=true;host.hidden=false;trigger.setAttribute('aria-current','page');onVisibility();render();};
  trigger.replaceChildren(icon('scenes'),node('span',{},'Motif 库'));
  trigger.addEventListener('click',open);
  for(const el of navigation)el?.addEventListener('click',()=>{if(opened)back();},{capture:true});
  if(!embedded)new MutationObserver(()=>{if(document.body.dataset.desktopScreen!=='workspace'){
    revision++;model=null;selected=null;error='';loading=false;source='';back();
  }}).observe(document.body,{attributes:true,attributeFilter:['data-desktop-screen']});

  async function load(read,label) {
    const ticket=++revision;loading=true;error='';render();
    try{const text=await read();if(text.length>4*1024*1024)throw Error('快照超过 4 MB，请缩小导出范围。');
      const parsed=readMotifEvidence(JSON.parse(text));if(ticket!==revision)return;
      model=parsed;selected=model.capabilities[0]?.id||null;source=label;live=false;tab='library';filter='all';query='';
    }catch(cause){if(ticket!==revision)return;error=cause.message.startsWith('快照超过')?cause.message:'无法读取这份证据。请使用 coding-motif-evidence-v1 格式，并核对认证及证据引用。';}
    finally{if(ticket===revision){loading=false;render();}}
  }
  input.addEventListener('change',()=>{const file=input.files[0];input.value='';if(file)load(async()=>{if(file.size>4*1024*1024)throw Error('快照超过 4 MB，请缩小导出范围。');return file.text();},'导入的证据快照');});
  const sample=()=>load(async()=>{const response=await fetch('/desktop/motif-example.json',{credentials:'omit'});if(!response.ok)throw Error('Sample unavailable');return response.text();},'公开脱敏验收样例 · #150');
  function evidence(refs) {
    const list=refs.map(id=>model.raw.evidence.find(e=>e.id===id));
    return node('div',{class:'motif-evidence-list'},...list.map(row=>node('details',{},node('summary',{},icon('document'),row.kind,node('code',{},short(row.id))),
      hash('记录 ID',row.id),hash('内容 SHA-256',row.sha256),node('p',{class:'motif-muted'},'核验范围：'+row.verification_scope+'；此页未读取原始材料。'))));
  }
  function detail() {
    const c=model.capabilities.find(c=>c.id===selected);if(!c)return empty('选择一项 Motif','查看适用范围、认证和来源证据。');
    return node('aside',{class:'motif-detail','aria-label':'Motif 详情'},
      node('div',{class:'motif-detail-title'},icon('scenes'),node('h2',{},c.name)),badge(statusLabel[c.status],c.status),badge(model.raw.source?(live?(model.raw.source.compatibility==='available'?'当前服务已准入':'当前服务不可用'):'导入快照，当前服务可用性待核验'):'当前电脑可用性待核验'),model.raw.source?badge('本机可用性待核验'):null,badge('层级未提供'),
      section('适用范围',node('dl',{},node('dt',{},'场景'),node('dd',{},model.raw.scenario),node('dt',{},'实现'),node('dd',{},c.contract.language),
        node('dt',{},'读取'),node('dd',{},c.contract.read_scope.join('、')||(model.raw.source?'未单独导出':'无')),node('dt',{},'写入'),node('dd',{},c.contract.write_scope.join('、')||(model.raw.source?'未单独导出':'无'))),
        node('details',{},node('summary',{},model.raw.source?'入口工具参数契约':'参数契约'),node('pre',{},JSON.stringify(c.contract.parameters_schema,null,2)))),
      section('认证与版本',hash('能力 ID',c.id),hash('证书',c.version.certificate_digest),
        node('p',{},'库版本 '+(model.raw.source?.release||count(c.version.library_generation))),
        node('p',{class:'motif-muted'},'认证见证 '+count(c.certification.native_witness_tasks)+' 项 · 候选执行验证 '+count(c.certification.candidate_execution_tasks)+' 项'),
        node('p',{class:'motif-muted'},model.raw.source?'来源任务 '+count(c.sourceTaskCount)+' 项；当前展示不新增认证或执行授权。':''),
        node('p',{class:'motif-muted'},'负向检查：'+(c.certification.negative_kinds.join('、')||'未记录'))),
      section('成本边界',node('strong',{},c.cost),node('p',{class:'motif-muted'},'此项能力的独立归因费用。任务总费用另列；没有同质量基线时不显示预计节省。')),
      section('证据入口',evidence(c.evidenceRefs)));
  }
  function library() {
    const search=node('input',{type:'search',placeholder:'搜索名称或能力 ID','aria-label':'搜索 Motif',value:query});
    search.addEventListener('input',()=>{query=search.value;renderList();});
    const list=node('div',{class:'motif-list','aria-label':'Motif 列表'});
    function renderList(){list.replaceChildren(...(rowsForQuery().length?rowsForQuery().map(c=>{
      const row=button('',()=>{selected=c.id;render();},'motif-item');row.setAttribute('aria-pressed',String(c.id===selected));
      row.append(node('div',{class:'motif-item-symbol'},icon('scenes')),node('div',{},node('strong',{},c.name),node('p',{},'版本 '+(model.raw.source?.release||count(c.version.library_generation))+' · '+(c.contract.language||'实现未记录')),node('code',{},short(c.id))),
        badge(statusLabel[c.status],c.status));return row;
    }):[empty('没有符合条件的 Motif','尝试其他名称或状态。')]));}
    function rowsForQuery(){return model.capabilities.filter(c=>(filter==='all'||c.status===filter)&&[c.name,c.id].some(x=>x.toLowerCase().includes(query.toLowerCase())));}
    const filters=node('div',{class:'motif-filters',role:'group','aria-label':'认证状态'},...Object.entries({all:'全部',...statusLabel}).filter(([key])=>!model.raw.source||key!=='pending_certification').map(([key,label])=>{
      const b=button(label,()=>{filter=key;render();});b.setAttribute('aria-pressed',String(filter===key));return b;}));renderList();
    return node('div',{class:'motif-split'},node('section',{class:'motif-catalog'},node('div',{class:'motif-list-tools'},search,filters),list),detail());
  }
  function timeline() {
    const tasks=(workspace?.tasks||[]).flatMap(task=>(task.trace||[]).filter(row=>row.kind==='motif').map(row=>({...row,taskTitle:task.input_summary||task.task_id})));
    const actual=section('当前工作区 Runtime 记录',...(tasks.length?tasks.map(row=>node('article',{class:'motif-task-usage'},node('strong',{},row.label||'Motif 记录'),badge(row.status),node('p',{},row.taskTitle),node('small',{},row.time||'时间未提供'))):[node('p',{},'暂无此工作区的 Motif 执行记录。')]));
    if(!model?.raw.events.length)return node('div',{},actual,empty('尚无学习或发布事件','以上仅来自实际任务轨迹；未绑定具体能力时不推测层级、学习或发布次数。'));
    return node('div',{class:'motif-timeline'},actual,node('p',{class:'motif-muted'},'按快照顺序展示实际执行事件。缺少时间戳时不推测耗时；学习、认证和发布事件待来源提供。'),
      ...model.raw.events.map((e,index)=>{const cap=model.capabilities.find(c=>c.id===e.capability_id);
        return node('article',{class:'motif-event'},node('div',{class:'motif-event-dot '+(e.actual_execution?'applied':'')},icon(e.kind==='fallback'?'refresh':'check')),
          node('div',{},node('div',{class:'motif-event-heading'},node('h3',{},eventLabel[e.kind]+' · '+cap.name),badge(e.status)),
          node('p',{},e.reason|| (e.actual_execution?'已记录实际执行':'未执行能力')),
          node('small',{class:'motif-muted'},e.occurred_at||'时间未记录 · 记录 '+(index+1)),
          node('details',{},node('summary',{},'核对执行证据'),hash('调用',e.call_ref),hash('任务运行',e.run_id),node('p',{},'单次费用：'+usd(e.cost_usd)),evidence(e.evidence_refs))));}));
  }
  function flows(c){return c.toolFlow?.length?section('实际工具参数流',...c.toolFlow.map(flow=>node('p',{},node('code',{},flow.from_tool+' · '+flow.from_field), ' → ',node('code',{},flow.to_tool+' · '+flow.to_param)))):null;}
  function relations() {
    if(!model.capabilities.length)return empty('库中暂无关系','有能力和依赖记录后显示，少量节点也可以逐项核对。');
    return node('div',{},node('p',{class:'motif-muted'},'当前协议提供环境、依赖锁与读写约束；未提供 Motif 之间的组合关系，不推测父子层级。'),
      ...model.capabilities.map(c=>node('article',{class:'motif-relation'},node('div',{class:'motif-relation-root'},icon('scenes'),node('strong',{},c.name),badge(statusLabel[c.status],c.status)),
        node('div',{class:'motif-dependencies'},flows(c),...(c.dependencies.length?c.dependencies.map(d=>node('div',{class:'motif-dependency'},node('span',{},d.name||dependencyLabel[d.kind]||d.kind),node('code',{title:d.sha256},short(d.sha256)))):[node('p',{},'尚无依赖记录')])))));
  }
  function runs() {
    const tasks=workspace?.tasks||[];
    const actual=section('当前工作区任务用量',...(tasks.length?tasks.map(task=>{const stats=task.stats||{},known=v=>Number.isFinite(v)?v:'未知';return node('div',{class:'motif-task-usage'},node('strong',{},task.input_summary||task.task_id),node('p',{},'模型请求 '+known(stats.model_requests)+' · 输入 '+known(stats.input_tokens??stats.prompt_tokens)+' / 输出 '+known(stats.output_tokens??stats.completion_tokens)+' tokens · 任务估费 '+usd(stats.cost_usd??null)),node('small',{},'来自当前账号任务接口；不是单项 Motif 费用或节省。'));}):[node('p',{},'本工作区尚无任务用量记录。')]));
    const comparison=workspace?.assessment;
    const paired=comparison?section('最近对照的原始用量',...Object.entries(comparison.lanes||{}).map(([lane,result])=>{const stats=result.stats||{};return node('div',{class:'motif-task-usage'},node('strong',{},lane==='motif'?'Motif 执行':'标准执行'),badge(result.status),node('p',{},'模型请求 '+count(stats.model_requests)+' · 输入 '+count(stats.input_tokens??stats.prompt_tokens)+' / 输出 '+count(stats.output_tokens??stats.completion_tokens)+' tokens · 任务估费 '+usd(stats.cost_usd??null)));}),node('p',{class:'motif-muted'},'来自原对照接口；尚未判定质量等价，不自动换算成节省或效率提升。')):null;
    return node('div',{},actual,paired,node('p',{class:'motif-muted'},'以下为任务整体用量，包含普通 Agent 与恢复过程；不能归因成某个 Motif 的成本或节省。'),
      ...(model?.runs||[]).map(r=>section('任务 '+short(r.id),node('div',{class:'motif-run-stats'},card('模型请求',count(r.cost.requests),'原任务记录'),card('任务估费',r.costLabel,'原账本估费 · 非供应商账单'),card('完整耗时',r.elapsedLabel,'缺少数据时保持未知')),
        node('p',{},'质量检查：'+(r.quality.task_qualified===true?'通过':r.quality.task_qualified===false?'未通过':'未知')+' · 已执行 '+count(r.quality.executed_count)+' / '+count(r.quality.required_count)),
        node('p',{class:'motif-muted'},'输入 '+count(r.cost.tokens.prompt_tokens)+' tokens · 输出 '+count(r.cost.tokens.completion_tokens)+' tokens'),evidence(r.evidence_refs))),
      section('同质量收益',node('p',{},'待提供可比基线'),node('p',{class:'motif-muted'},'当前快照不包含配对成本及质量比较，不显示节省金额或效率百分比。')));
  }
  function versions(){return section('当前库版本 '+version(),hash('快照摘要',model.raw.library.snapshot_sha256),hash('Registry 摘要',model.raw.library.registry_digest),
    ...(model.raw.source?.revisions?.length?[node('p',{class:'motif-muted'},'以下来自原学习报告中的兼容来源记录，不代表新增学习或演化次数。'),...model.raw.source.revisions.map(row=>section(row.label+(row.current?' · 当前':''),hash('证书摘要',row.certificate_digest),evidence([row.evidence_ref])))]:[node('p',{class:'motif-muted'},'当前来源仅含此版本。历史、版本差异和回滚记录待接入；本页不修改运行能力。')]),
    ...model.capabilities.map(c=>section(c.name,hash(model.raw.source?'结构摘要':'候选摘要',c.version.candidate_digest),hash('证书摘要',c.version.certificate_digest))));}
  function render() {
    if(!opened)return;
    const actions=node('div',{class:'motif-toolbar'},button('导入证据快照',()=>input.click(),'secondary'),button('公开验收样例',sample,'secondary'));
    for(const b of actions.children)b.disabled=loading;
    if(model&&!live)actions.append(button('返回账户数据',()=>{revision++;model=null;selected=null;source='';error='';live=true;onReset();render();},'motif-text-button'));
    const header=node('header',{class:'motif-header'},node('div',{},node('div',{class:'motif-eyebrow'},'GeneLoop / 能力与经历'),node('h1',{},'Motif 库'),node('p',{},'每一项可复用能力，都有来处。')),actions);
    const body=node('div',{class:'motif-content'});
    if(!embedded){const sources=node('div',{class:'motif-scope-picker','aria-label':'核对来源快照'},...scopeChoices().map(row=>button(row.title,()=>onScope(row.workspaceId),'secondary')));body.append(accountPool&&live?node('details',{class:'motif-source-records'},node('summary',{},'核对来源快照'),sources):sources);}
    if(loading)body.append(node('p',{role:'status',class:'motif-notice'},'正在读取并校验证据…'));
    if(error)body.append(node('p',{role:'alert',class:'motif-error'},error));
    if(accountPool&&live){
      const search=node('input',{type:'search','aria-label':'搜索总 Motif 库',placeholder:'搜索名称或能力 ID',value:poolSelection.query});
      search.addEventListener('input',()=>{poolSelection.query=search.value;render();host.querySelector('[aria-label="搜索总 Motif 库"]')?.focus({preventScroll:true});});
      body.classList.add('motif-pool-library','motif-detail-body');body.append(...[node('p',{class:'motif-muted'},'总 Motif 库 · 当前账号可见的场景库、个人学习库和已登记回执，同一能力仅计一次。'),poolControls(accountPool,poolSelection,render),search,
        accountPool.partial?node('p',{class:'motif-error',role:'status'},'部分来源暂不可用，当前展示已读取的数据。'):null,
        motifComparisonBody('distribution',motifData(filterMotifPool(accountPool,poolSelection)),poolSelection,render,{expanded:true,preview:false})].filter(Boolean));
      host.replaceChildren(node('div',{class:'motif-topbar'},button('返回工作区',back,'motif-text-button'),node('span',{},'Motif Library')),header,body,input);return;
    }
    const scopeNote=model?node('div',{class:'motif-source'},badge('只读证据'),node('span',{},source),node('span',{},'库版本 '+version()),node('small',{},live?'认证状态不代表当前电脑可用':'与当前账号及工作区无关联')):null;
    if(embedded){
      const run=workspaceRunView({workspace,model,viewState:runState,onTab:changeTab,onTask:id=>{runState.taskId=id;render();}});
      const names={run:'运行',combination:'能力组合',evaluation:'评估',evolution:'演化',versions:'版本'};
      const tabIcons={run:'folder-open',combination:'scenes',evaluation:'chart-column-increasing',evolution:'refresh',versions:'trace'};
      const tabs=node('div',{class:'motif-tabs',role:'tablist','aria-label':'工作区视图'},...Object.entries(names).map(([id,label])=>{const b=button([icon(tabIcons[id]),label],()=>changeTab(id));b.setAttribute('role','tab');b.setAttribute('aria-selected',String(tab===id));return b;}));
      const content=node('div',{class:'motif-tab-body',role:'tabpanel','aria-label':names[tab]});
      if(tab==='run')content.append(run.main);
      else if(tab==='evaluation'&&!model)content.append(runs());
      else if(tab==='evolution'&&!model)content.append(timeline());
      else if(!model)content.append(empty('这个工作区尚无 Motif 证据','宿主接入实际证据导出后，会在这里显示能力、评估和演化记录。'));
      else{content.append(scopeNote,({combination:()=>node('div',{},relations(),library()),evaluation:runs,evolution:timeline,versions})[tab]());}
      if(error)content.prepend(node('p',{class:'motif-error',role:'alert'},error));host.replaceChildren(...[workspace.heading,sourcePicker(),tabs,content].filter(Boolean));
      if(inspector&&isActive()){const top=inspector.scrollTop;inspector.replaceChildren(run.inspector);inspector.scrollTop=top;}return;
    }
    if(!model)body.append(empty('让经历成为可追溯的能力','当前服务尚无可展示的数据。可导入证据快照或查看明确标注的公开验收样例。'));
    else {
      const picker=sourcePicker();if(picker)body.append(picker);
      body.append(scopeNote,
        node('div',{class:'motif-stats'},...(model.raw.source?[card('已认证',model.summary.certified,'当前准入目录的状态'),card('旧格式登记',model.summary.registered,'保留原格式与证据边界'),card('实际复用','—','需核对实际任务回执'),card('服务端准入',model.raw.source.compatibility==='available'?'可用':'不可用','不代表当前电脑已认证')]:[card('已认证',model.summary.certified,'快照内的认证状态'),card('待认证',model.summary.pending,'保留候选与失败边界'),card('实际复用',model.summary.applied,'仅统计实际 invoke 回执'),card('安全回退',model.summary.fallbacks,'保留不适用记录')])));
      body.append(library());
    }
    host.replaceChildren(node('div',{class:'motif-topbar'},button('返回工作区',back,'motif-text-button'),node('span',{},'Motif Library')),header,body,input);
  }
  return {open,close:back,getModel:()=>model,setPool(value){accountPool=value;model=null;live=true;render();},setSources(values){choices=values;if(!live&&model)return;const row=choices.find(r=>r.id===choiceId)||choices.find(r=>r.status==='ready')||choices[0];choiceId=row?.id;model=row?.evidence?readMotifEvidence(row.evidence):null;source=row?.title||'';live=true;if(!model?.capabilities.some(c=>c.id===selected))selected=model?.capabilities[0]?.id||null;render();},setWorkspace(value){workspace=value;if(tab==='library')tab='run';opened=true;render();},setEvidence(data,label){accountPool=null;model=data?readMotifEvidence(data):null;source=label;live=true;if(!model?.capabilities.some(c=>c.id===selected))selected=model?.capabilities[0]?.id||null;render();},setError(text){error=text||(choices.find(row=>row.id===choiceId)?.status==='unavailable'?'此场景库当前不可读取，请检查服务端库与认证配置。':'');render();},setTab(value){tab=value;render();},isPreview(){return model&&!live;},clear(){model=null;accountPool=null;Object.assign(poolSelection,{scene:'all',source:'all',status:'all',query:'',selected:null});error='';revision++;if(embedded){workspace=null;opened=false;runState.taskId=null;host.replaceChildren();return;}render();}};
}

/** 一份账号目录，投影到当前工作区和全局库；公开样例不会绑定工作区。 */
export function bindMotifLibrary(options){
  const panels=new Map();let rows=[],runtimeRows=[],localCatalog=null,revision='',epoch=0,pending=null,abort=null,error='',ready=false,globalScope=null;
  const sourceRows=id=>{const own=rows.filter(r=>r.workspaceId===id).map(r=>({...r,id:r.workspaceId,title:'工作区导出 · '+(options.getWorkspaceTitle?.(id)||id)}));return [...own,...runtimeRows.map(r=>({...r,id:r.workspaceId}))];};
  const compact=matchMedia('(max-width:1180px)');
  let inspectorPreference=localStorage.getItem('geneloop.desktop.workspace-inspector'),authorized=true;
  function syncInspector(){
    const eligible=authorized&&document.body.dataset.desktopScreen==='workspace'&&!options.conversation.hidden&&options.conversation.dataset.page==='workspace-home'&&Boolean(options.getWorkspace?.());
    const visible=eligible&&(inspectorPreference===null?!compact.matches:inspectorPreference==='yes');
    if(options.inspector)options.inspector.hidden=!visible;
    if(options.inspectorToggle){options.inspectorToggle.hidden=!eligible;options.inspectorToggle.setAttribute('aria-expanded',String(Boolean(visible)));}
  }
  if(options.inspectorToggle){options.inspectorToggle.replaceChildren(icon('sidebar'));options.inspectorToggle.addEventListener('click',()=>{inspectorPreference=options.inspector.hidden?'yes':'no';localStorage.setItem('geneloop.desktop.workspace-inspector',inspectorPreference);syncInspector();});}
  compact.addEventListener('change',syncInspector);
  const collapseKey=(type,example)=>'geneloop.desktop.motif-'+(type==='aquarium'?'summary':type)+(example?'-example':'')+'-collapsed';
  const cardStates=Object.fromEntries(['aquarium','hierarchy','distribution'].map(type=>[type,{
    collapsed:localStorage.getItem(collapseKey(type,false))==='yes',
    exampleCollapsed:localStorage.getItem(collapseKey(type,true))==='yes',example:null,selected:null,
  }]));
  let detail=null;
  const global=createMotifView({...options,onVisibility:syncInspector,onReset:project,scopeChoices:()=>[{workspaceId:'all',title:'总 Motif 库'},...[...runtimeRows,...rows].map(r=>({...r,title:r.title||options.getWorkspaceTitle?.(r.workspaceId)||r.workspaceId}))],onScope:id=>{globalScope=id;project();}});
  const getWorkspace=options.getWorkspace||(()=>null);
  function summaryModel(){return {view:buildMotifPool(rows,runtimeRows,{ready,partial:Boolean(error),localCatalog,title:id=>options.getWorkspaceTitle?.(id)||id})};}
  function toggleCollapse(type,example){
    const state=cardStates[type],key=example?'exampleCollapsed':'collapsed';
    state[key]=!state[key];localStorage.setItem(collapseKey(type,example),state[key]?'yes':'no');renderSummary();
  }
  function openDetail(type){
    if(detail){const previous=detail;detail=null;previous.element.close();previous.element.remove();}
    const body=node('div',{class:'motif-detail-body'}),title=type==='aquarium'?'Motif 鱼缸':type==='hierarchy'?'结构演化 · A':'能力分布 · B';
    const library=button('打开 Motif 库',()=>{detail?.element.close();global.open();},'secondary');
    const element=dialog(title,body,[library]);element.classList.add('motif-detail-dialog');element.dataset.motifDetail=type;element.setAttribute('aria-label',title);
    const maximize=button('⤢',()=>{const maximized=element.classList.toggle('maximized');maximize.setAttribute('aria-label',maximized?'还原详情窗':'放大详情窗');maximize.setAttribute('aria-pressed',String(maximized));},'icon motif-detail-maximize');
    maximize.setAttribute('aria-label','放大详情窗');maximize.setAttribute('aria-pressed','false');element.querySelector('header h2').after(maximize);
    detail={element,body,type,query:'',page:0,selected:null,filters:{scene:'all',source:'all',status:'all'}};
    const resize=new ResizeObserver(()=>drawMotifRelations(body));resize.observe(body);
    element.addEventListener('close',()=>{resize.disconnect();if(detail?.element===element)detail=null;},{once:true});renderDetail();
  }
  function renderDetail(){
    if(!detail)return;const current=detail,{view:total}=summaryModel(),{body,type}=current,view=filterMotifPool(total,current.filters);
    const focused=document.activeElement,focusId=body.contains(focused)?focused.dataset.motifId:null,focusExample=body.contains(focused)&&focused.hasAttribute('data-motif-example');
    const state=cardStates[type],data=motifCardData(total,state,view);
    const scope=node('p',{class:'motif-detail-scope'},data.example?'层级示例 · 非工作区结果':'总 Motif 库 · 当前账号可见');
    const controls=data.example?null:poolControls(total,current.filters,()=>{current.page=0;renderDetail();});
    const warning=!data.example&&(error||total.partial)?node('p',{class:'motif-error',role:'status'},'部分来源暂不可用，当前展示已读取的数据。'):null;
    if(type!=='aquarium'){
      body.replaceChildren(...[scope,controls,warning,motifComparisonBody(type,data,state,renderSummary,{expanded:true})].filter(Boolean));
      requestAnimationFrame(()=>{if(!body.isConnected)return;drawMotifRelations(body);if(focusId)[...body.querySelectorAll('[data-motif-id]')].find(t=>t.dataset.motifId===focusId)?.focus({preventScroll:true});else if(focusExample)body.querySelector('[data-motif-example]')?.focus({preventScroll:true});});return;
    }
    const source=motifExampleSwitch(type,data,example=>{state.example=example;current.page=0;current.query='';current.selected=null;renderSummary();body.querySelector('[data-motif-example]')?.focus({preventScroll:true});});
    const query=current.query.toLocaleLowerCase(),caps=data.caps.filter(c=>(c.name+' '+c.id).toLocaleLowerCase().includes(query));
    const pages=Math.max(1,Math.ceil(caps.length/48));current.page=Math.min(current.page,pages-1);
    const shown=caps.slice(current.page*48,(current.page+1)*48),info=node('aside',{class:'motif-aquarium-info','aria-label':'所选 Motif 信息'});
    const inspect=cap=>{info.replaceChildren(motifInformation(data,cap));};
    const select=cap=>{current.selected=cap.id;inspect(cap);for(const p of body.querySelectorAll('.culture-particle'))p.setAttribute('aria-pressed',String(p.dataset.capabilityId===cap.id));};
    const graphic=cultureGraphic(shown,{inspect,select});graphic.classList.add('motif-culture-large');
    const search=node('input',{type:'search',placeholder:'查找 Motif',value:current.query,'aria-label':'查找鱼缸 Motif'});
    search.addEventListener('input',()=>{current.query=search.value;current.page=0;renderDetail();const replacement=body.querySelector('input');replacement.focus({preventScroll:true});});
    const previous=button('上一页',()=>{current.page--;renderDetail();},'secondary'),next=button('下一页',()=>{current.page++;renderDetail();},'secondary');previous.disabled=!current.page;next.disabled=current.page>=pages-1;
    const pager=node('div',{class:'motif-aquarium-pages'},node('span',{},caps.length?`${current.page*48+1}–${Math.min((current.page+1)*48,caps.length)} / ${caps.length}`:'0 / 0'),previous,next);
    const picture=node('div',{class:'motif-aquarium-picture motif-evolution-shell'},graphic,node('p',{class:'motif-preview-note'},'每个球体是一个 Motif · 颜色表示认证状态'),pager);
    if(!shown.length)picture.prepend(node('p',{class:'motif-preview-note'},data.known?'暂无匹配的 Motif。':'账号 Motif 数据暂不可用。'));
    body.replaceChildren(...[scope,source,controls,warning,motifSummary(data),search,node('div',{class:'motif-aquarium-layout'},picture,info)].filter(Boolean));
    const selected=shown.find(c=>c.id===current.selected)||shown[0];if(selected)select(selected);else inspect(null);
  }
  function renderSummary(){const host=options.summaryHost;if(!host)return;const {view}=summaryModel();
    const state=cardStates.aquarium,data=motifCardData(view,state),collapsed=data.example?state.exampleCollapsed:state.collapsed;
    const b=node('section',{class:'motif-evolution-card','aria-label':'Motif 鱼缸','data-source':data.example?'example':'account'});
    const svg=cultureGraphic(data.caps),status=error||view.partial?'部分来源暂不可用':ready?'尚无证据记录':'正在读取…';
    const arrow=button('↗',()=>openDetail('aquarium'),'motif-card-expand');arrow.dataset.motifExpand='aquarium';arrow.setAttribute('aria-label','放大 Motif 鱼缸');
    const scope=node('small',{class:'motif-summary-scope'},data.example?'层级示例 · 非工作区结果':'总 Motif 库 · 当前账号可见');
    const legend=node('span',{class:'motif-culture-legend'},...Object.entries(statusLabel).map(([key,label])=>node('span',{},node('i',{class:key}),label+' '+(data.known?data.caps.filter(c=>c.status===key).length:'—'))));
    const stat=(label,value,cls='')=>node('span',{class:'motif-culture-stat '+cls},node('small',{},label),node('strong',{},value));
    const stats=node('span',{class:'motif-culture-stats'},stat('Motif 数量',data.known?data.caps.length:'—'),stat('已记录复用',data.reuse??'—','reuse'));
    b.dataset.collapsed=String(collapsed);
    b.dataset.summaryCard='aquarium';
    const toggle=button([node('span',{},'Motif Evolution'),node('small',{class:'motif-summary-tag'},'鱼缸'),data.example?node('small',{class:'motif-summary-tag'},'示例'):null,icon(collapsed?'chevron-right':'chevron-down')],()=>toggleCollapse('aquarium',data.example),'motif-comparison-toggle motif-summary-toggle');toggle.setAttribute('aria-label',collapsed?'展开演化摘要':'收起演化摘要');toggle.setAttribute('aria-expanded',String(!collapsed));
    b.append(node('header',{},toggle,arrow),scope,svg,legend,stats);
    if(!data.example&&(!view.known||view.partial))b.append(node('span',{class:'motif-culture-status'},status));
    svg.toggleAttribute('hidden',collapsed);scope.hidden=collapsed;legend.hidden=collapsed;
    host.replaceChildren(node('div',{class:'motif-evolution-shell'},b),...motifComparisonCards(view,cardStates,renderSummary,openDetail,toggleCollapse));renderDetail();
  }
  function project(){for(const[id,panel]of panels){const row=rows.find(r=>r.workspaceId===id);panel.view.setSources(sourceRows(id));panel.view.setError(error);}
    const row=[...runtimeRows,...rows].find(r=>r.workspaceId===globalScope);if(!global.isPreview()){if(!globalScope||globalScope==='all')global.setPool(summaryModel().view);else global.setEvidence(row?.evidence||null,row?(row.title||'账户工作区 '+(options.getWorkspaceTitle?.(row.workspaceId)||row.workspaceId)):'');}global.setError(error||(!global.isPreview()&&row?.status==='unavailable'?'证据暂时无法读取，请重试。':''));renderSummary();}
  async function refresh(){if(document.body.dataset.desktopScreen!=='workspace'||document.hidden||pending)return pending;const token=epoch;abort=new AbortController();
    pending=(async()=>{try{const localBridge=window.desktopWorkspaces?.rsiCatalog;
      const [snapshotResult,runtimeResult,localResult]=await Promise.allSettled([request('/api/harless/motif-library',{signal:abort.signal}),request('/api/harless/motif-catalog',{signal:abort.signal}),localBridge?.()]);
      if(snapshotResult.status==='rejected'&&snapshotResult.reason.status===401)throw snapshotResult.reason;if(runtimeResult.status==='rejected'&&runtimeResult.reason.status===401)throw runtimeResult.reason;
      const data=snapshotResult.status==='fulfilled'?snapshotResult.value:{format:'geneloop-motif-catalog-v1',workspaces:[],revision:'0'.repeat(64)};
      const nextLocal=localResult.status==='fulfilled'&&Array.isArray(localResult.value)?localResult.value:null;
      const runtime=runtimeResult.status==='fulfilled'?runtimeResult.value:null;
      if(runtime&&(runtime.format!=='geneloop-runtime-motif-catalog-v1'||!Array.isArray(runtime.libraries)))throw Error('Invalid runtime catalog');
      const nextRuntime=(runtime?.libraries||[]).map(row=>{if(typeof row.id!=='string'||typeof row.scene!=='string'||!['ready','unavailable'].includes(row.status))throw Error('Invalid runtime library');return {...row,workspaceId:row.id,title:(row.evidence?.source?.kind==='account_learning'?'账号学习库 · ':'服务端场景库 · ')+row.title,view:row.status==='ready'?readMotifEvidence(row.evidence):null};});
      const resolvedRuntime=runtime?nextRuntime:runtimeRows;
      const warning=runtimeResult.status==='rejected'?(runtimeResult.reason.status===404?'当前服务尚未提供场景库接口，请更新服务端。':'场景库接口暂不可用；已有数据可能不是最新状态。'):snapshotResult.status==='rejected'?'工作区证据接口暂不可用。':localBridge&&!nextLocal?'本机学习库暂不可用。':'';
      const runtimeRevision=JSON.stringify(resolvedRuntime.map(row=>[row.id,row.status,row.evidence?.export_digest]));if(token!==epoch)return;
      if(data.format!=='geneloop-motif-catalog-v1'||!Array.isArray(data.workspaces)||!/^[a-f0-9]{64}$/.test(data.revision)||new Set(data.workspaces.map(r=>r.workspaceId)).size!==data.workspaces.length)throw Error('Invalid catalog');
      const next=data.workspaces.map(r=>{if(typeof r.workspaceId!=='string'||!['ready','unavailable'].includes(r.status)||!['local','cloud'].includes(r.executionLocation)||r.compatibility!=='unverified')throw Error('Invalid scope');return {...r,view:r.status==='ready'?readMotifEvidence(r.evidence):null};});
      const nextRevision=data.revision+runtimeRevision+JSON.stringify(nextLocal);const changed=revision!==nextRevision||error!==warning;rows=next;runtimeRows=resolvedRuntime;localCatalog=nextLocal;revision=nextRevision;error=warning;ready=true;authorized=true;if(changed)project();syncInspector();
    }catch(cause){if(token!==epoch)return;if(cause.status===401){reset();options.onAuthorizationLost?.();error='请重新登录后读取 Motif 数据。';project();return;}error=cause.status===404?'所连接的服务尚未提供 Motif 展示接口。':'证据暂时无法读取，请重试。';project();}finally{if(token===epoch){pending=null;abort=null;}}})();return pending;
  }
  function reset(){detail?.element.close();detail=null;for(const state of Object.values(cardStates)){state.example=null;state.selected=null;}epoch++;abort?.abort();pending=null;abort=null;rows=[];runtimeRows=[];localCatalog=null;revision='';error='';globalScope=null;ready=false;authorized=false;for(const panel of panels.values())panel.view.clear();panels.clear();global.clear();options.inspector?.replaceChildren();syncInspector();renderSummary();}
  new MutationObserver(()=>{if(document.body.dataset.desktopScreen==='workspace'){authorized=true;syncInspector();renderSummary();refresh();}else reset();}).observe(document.body,{attributes:true,attributeFilter:['data-desktop-screen']});
  setInterval(refresh,10000);document.addEventListener('visibilitychange',refresh);
  options.trigger.addEventListener('click',()=>{project();refresh();});
  return {open:global.open,close:global.close,refresh,syncInspector,workspaceHome(group,content){let panel=panels.get(group.workspaceId);if(!panel){const root=node('div',{class:'workspace-home motif-workspace'});panel={root,view:createMotifView({trigger:button('',()=>{}),host:root,embedded:true,inspector:options.inspector,onReset:renderSummary,isActive:()=>authorized&&getWorkspace()?.workspaceId===group.workspaceId&&!options.conversation.hidden&&options.conversation.dataset.page==='workspace-home'})};panels.set(group.workspaceId,panel);}panel.view.setWorkspace(content);const row=rows.find(r=>r.workspaceId===group.workspaceId);panel.view.setSources(sourceRows(group.workspaceId));syncInspector();renderSummary();return panel.root;}};
}
