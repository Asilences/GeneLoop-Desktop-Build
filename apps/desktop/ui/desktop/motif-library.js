import {node,button,icon,choiceControl} from './components.js';
import {readMotifEvidence,usd} from './motif-evidence.js';
import {request} from './api.js';
import {workspaceRunView} from './workspace-run.js';
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

let cultureSequence=0;
/** 本地 SVG 玻璃插画；球体只投影当前快照中的能力，不生成装饰性能力或关系。 */
function cultureGraphic(capabilities=[]){
  const namespace='http://www.w3.org/2000/svg',prefix='motif-culture-'+cultureSequence++;
  const make=(parent,tag,attrs={})=>{const el=document.createElementNS(namespace,tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,v);parent?.append(el);return el;};
  const svg=make(null,'svg',{viewBox:'0 0 300 210',class:'motif-culture','aria-hidden':'true'}),defs=make(svg,'defs');
  const url=name=>'url(#'+prefix+'-'+name+')';
  function gradient(name,radial,attrs,stops){const g=make(defs,radial?'radialGradient':'linearGradient',{id:prefix+'-'+name,...attrs});for(const[offset,color,opacity=1]of stops)make(g,'stop',{offset,'stop-color':color,'stop-opacity':opacity});}
  gradient('body',false,{x1:'0%',y1:'0%',x2:'100%',y2:'0%'},[['0%','#a6dadd',.68],['7%','#ffffff',.8],['22%','#c4f5ec',.12],['67%','#89d9d4',.15],['94%','#ffffff',.76],['100%','#6fb8c3',.58]]);
  gradient('water',false,{x1:'0%',y1:'0%',x2:'0%',y2:'100%'},[['0%','var(--culture-water-top)',.4],['52%','var(--culture-water-mid)',.36],['100%','var(--culture-water-bottom)',.63]]);
  gradient('surface',false,{x1:'0%',y1:'0%',x2:'100%',y2:'50%'},[['0%','#ffffff',.88],['25%','#b8e9e5',.35],['65%','#c2f5eb',.34],['100%','#ffffff',.8]]);
  gradient('rim',false,{x1:'0%',y1:'0%',x2:'0%',y2:'100%'},[['0%','#ffffff',.96],['28%','#89c7cf',.62],['50%','#ffffff',.96],['80%','#a7e1df',.63],['100%','#ffffff',.8]]);
  gradient('front',false,{x1:'0%',y1:'0%',x2:'100%',y2:'0%'},[['0%','#ffffff',.5],['12%','#ffffff',.04],['63%','#ffffff',0],['88%','#ffffff',.08],['100%','#ffffff',.48]]);
  for(const[name,light,mid,edge]of [['certified','#e8ffc3','#66da80','#119a78'],['pending_certification','#e5e9ff','#83a7f9','#496fc0'],['invalid','#ffe6ed','#d990b2','#9c5d87'],['registered','#fff0d7','#d8bf8c','#9b8152']])
    gradient(name,true,{cx:'31%',cy:'23%',r:'78%'},[['0%','#ffffff'],['13%',light],['43%',mid],['100%',edge]]);
  const blur=make(defs,'filter',{id:prefix+'-blur',x:'-60%',y:'-60%',width:'220%',height:'220%'});make(blur,'feGaussianBlur',{stdDeviation:6});
  const soft=make(defs,'filter',{id:prefix+'-soft',x:'-50%',y:'-50%',width:'200%',height:'200%'});make(soft,'feGaussianBlur',{stdDeviation:2});
  const clip=make(defs,'clipPath',{id:prefix+'-inside'});make(clip,'path',{d:'M38 58Q150 23 262 58L267 153C267 190 33 190 33 153Z'});
  make(svg,'ellipse',{cx:150,cy:193,rx:115,ry:8,fill:'#73b9b5',opacity:.2,filter:url('blur')});
  make(svg,'ellipse',{cx:150,cy:164,rx:123,ry:31,fill:'#c3f9e5',opacity:.17,filter:url('blur')});
  make(svg,'path',{d:'M31 40C31 12 269 12 269 40L275 155C275 208 25 208 25 155Z',fill:url('body'),stroke:'#9fcfd0','stroke-width':1,'stroke-opacity':.55});
  make(svg,'path',{d:'M38 58Q150 23 262 58L267 153C267 190 33 190 33 153Z',fill:url('water')});
  make(svg,'ellipse',{cx:150,cy:58,rx:112,ry:19,fill:url('surface'),stroke:'#d3f8ef','stroke-opacity':.7,'stroke-width':1.2});
  const inside=make(svg,'g',{'clip-path':url('inside')});
  make(inside,'path',{d:'M21 151C89 100 186 179 282 127M32 175C115 132 182 180 267 157',fill:'none',stroke:'#e2fff2','stroke-width':2.5,'stroke-opacity':.32,filter:url('soft')});
  make(inside,'ellipse',{cx:151,cy:170,rx:110,ry:15,fill:'none',stroke:'#d4fff0','stroke-width':1.1,'stroke-opacity':.6});
  const positions=[[150,116,15],[215,91,11],[82,137,12],[109,83,8],[194,149,12],[62,100,8],[232,139,10],[133,157,10],[173,81,8],[118,123,9],[203,121,8],[165,143,8],[78,166,8],[245,111,7],[51,145,7],[142,89,7],[98,159,7],[184,107,7]];
  capabilities.slice(0,18).map((capability,i)=>({capability,position:positions[i],i})).sort((a,b)=>a.position[1]-b.position[1]).forEach(({capability,position:[x,y,r],i})=>{
    const anchor=make(inside,'g',{transform:`translate(${x} ${y})`}),particle=make(anchor,'g',{class:'culture-particle phase-'+i%4,'data-capability-id':capability.id});
    make(particle,'circle',{r:r*1.7,fill:capability.status==='certified'?'#7fe3a8':capability.status==='invalid'?'#d5a0bf':'#9eb9ff',opacity:.22,filter:url('blur')});
    make(particle,'circle',{r,fill:url(capability.status),stroke:'#ffffff','stroke-opacity':.46,'stroke-width':.7});
    make(particle,'ellipse',{cx:-r*.3,cy:-r*.42,rx:r*.34,ry:r*.18,fill:'#ffffff',opacity:.8,transform:'rotate(-30)'});
    make(particle,'path',{d:`M${-r*.65} ${r*.25}Q0 ${r*.96} ${r*.65} ${r*.15}`,fill:'none',stroke:'#efffe5','stroke-opacity':.4,'stroke-width':.8});
  });
  make(svg,'path',{d:'M31 42L25 155C25 208 275 208 275 155L269 42',fill:url('front'),stroke:'#e7ffff','stroke-width':1.7,'stroke-opacity':.7});
  make(svg,'ellipse',{cx:150,cy:174,rx:119,ry:21,fill:'none',stroke:'#bdede4','stroke-width':2,'stroke-opacity':.75});
  make(svg,'ellipse',{cx:150,cy:177,rx:111,ry:15,fill:'none',stroke:'#ffffff','stroke-width':1.8,'stroke-opacity':.7});
  make(svg,'path',{d:'M39 66Q29 120 37 153M262 70Q271 120 263 145',fill:'none',stroke:'#ffffff','stroke-width':5,'stroke-linecap':'round','stroke-opacity':.65,filter:url('soft')});
  make(svg,'ellipse',{cx:150,cy:39,rx:119,ry:22,fill:'none',stroke:url('rim'),'stroke-width':7});
  make(svg,'ellipse',{cx:150,cy:36,rx:119,ry:21,fill:'none',stroke:'#ffffff','stroke-width':1.3,'stroke-opacity':.9});
  make(svg,'path',{d:'M52 31C93 14 204 14 246 31',fill:'none',stroke:'#ffffff','stroke-width':2.8,'stroke-linecap':'round','stroke-opacity':.88});
  return svg;
}

/** 导入仅驻留当前页面内存；不发送资料、不改变 Agent 和工作区。 */
function createMotifView({trigger,host,conversation,deliveries,navigation=[],embedded=false,inspector=null,isActive=()=>true,onVisibility=()=>{},scopeChoices=()=>[],onScope=()=>{},onReset=()=>{}}) {
  let model=null,selected=null,tab='library',filter='all',query='',source='',opened=false,loading=false,error='',revision=0;
  let workspace=null,live=false,choices=[],choiceId=null;
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
    if(!embedded)body.append(node('div',{class:'motif-scope-picker','aria-label':'库所属工作区'},...scopeChoices().map(row=>button(row.title,()=>onScope(row.workspaceId),'secondary'))));
    if(loading)body.append(node('p',{role:'status',class:'motif-notice'},'正在读取并校验证据…'));
    if(error)body.append(node('p',{role:'alert',class:'motif-error'},error));
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
  return {open,close:back,getModel:()=>model,setSources(values){choices=values;if(!live&&model)return;const row=choices.find(r=>r.id===choiceId)||choices.find(r=>r.status==='ready')||choices[0];choiceId=row?.id;model=row?.evidence?readMotifEvidence(row.evidence):null;source=row?.title||'';live=true;if(!model?.capabilities.some(c=>c.id===selected))selected=model?.capabilities[0]?.id||null;render();},setWorkspace(value){workspace=value;if(tab==='library')tab='run';opened=true;render();},setEvidence(data,label){model=data?readMotifEvidence(data):null;source=label;live=true;if(!model?.capabilities.some(c=>c.id===selected))selected=model?.capabilities[0]?.id||null;render();},setError(text){error=text||(choices.find(row=>row.id===choiceId)?.status==='unavailable'?'此场景库当前不可读取，请检查服务端库与认证配置。':'');render();},setTab(value){tab=value;render();},isPreview(){return model&&!live;},clear(){model=null;error='';revision++;if(embedded){workspace=null;opened=false;runState.taskId=null;host.replaceChildren();return;}render();}};
}

/** 一份账号目录，投影到当前工作区和全局库；公开样例不会绑定工作区。 */
export function bindMotifLibrary(options){
  const panels=new Map();let rows=[],runtimeRows=[],revision='',epoch=0,pending=null,abort=null,error='',ready=false,globalScope=null;
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
  let collapsed=localStorage.getItem('geneloop.desktop.motif-summary-collapsed')==='yes';
  const global=createMotifView({...options,onVisibility:syncInspector,onReset:project,scopeChoices:()=>[...runtimeRows,...rows].map(r=>({...r,title:r.title||options.getWorkspaceTitle?.(r.workspaceId)||r.workspaceId})),onScope:id=>{globalScope=id;const row=[...runtimeRows,...rows].find(r=>r.workspaceId===id);global.setEvidence(row?.evidence||null,row?.title||'账户工作区 '+(options.getWorkspaceTitle?.(id)||id));global.setError(error||(row?.status==='unavailable'?'证据暂时无法读取，请重试。':''));}});
  const getWorkspace=options.getWorkspace||(()=>null);
  function renderSummary(){const host=options.summaryHost;if(!host)return;const group=getWorkspace(),row=rows.find(r=>r.workspaceId===group?.workspaceId),view=panels.has(group?.workspaceId)?panels.get(group.workspaceId).view.getModel():row?.view;
    const b=button('',async()=>{if(group){panels.get(group.workspaceId)?.view.setTab('evolution');global.close();await options.onWorkspace?.(group.workspaceId);}else global.open();},'motif-evolution-card');
    const svg=cultureGraphic(view?.capabilities),status=error||row?.status==='unavailable'?'证据暂不可用':ready?'尚无证据记录':'正在读取…';
    const arrow=node('span',{class:'motif-evolution-open','aria-hidden':true},'↗');
    const scope=node('small',{class:'motif-summary-scope',title:group?.title||''},group?(group.title+(view?.raw.source?' · '+view.raw.source.label+'库':'')):'选择工作区查看能力');
    const legend=node('span',{class:'motif-culture-legend'},...Object.entries({certified:'已认证',pending_certification:'待认证',invalid:'已失效',registered:'旧格式已登记'}).map(([key,label])=>node('span',{},node('i',{class:key}),label)));
    const stat=(label,value,cls='')=>node('span',{class:'motif-culture-stat '+cls},node('small',{},label),node('strong',{},value));
    const stats=node('span',{class:'motif-culture-stats'},stat('Motif 数量',view?view.capabilities.length:'—'),stat('实际复用',view&&!view.raw.source?view.summary.applied:'—','reuse'));
    b.dataset.collapsed=String(collapsed);
    b.append(node('span',{class:'motif-evolution-title'},'Motif Evolution',arrow),scope,svg,legend,stats);
    if(!view)b.append(node('span',{class:'motif-culture-status'},status));
    svg.toggleAttribute('hidden',collapsed);scope.hidden=collapsed;legend.hidden=collapsed;
    const toggle=button(icon(collapsed?'chevron-right':'chevron-down'),()=>{collapsed=!collapsed;localStorage.setItem('geneloop.desktop.motif-summary-collapsed',collapsed?'yes':'no');renderSummary();},'icon motif-summary-toggle');toggle.setAttribute('aria-label',collapsed?'展开演化摘要':'收起演化摘要');toggle.setAttribute('aria-expanded',String(!collapsed));
    host.replaceChildren(node('div',{class:'motif-evolution-shell'},b,toggle));
  }
  function project(){for(const[id,panel]of panels){const row=rows.find(r=>r.workspaceId===id);panel.view.setSources(sourceRows(id));panel.view.setError(error);}
    const row=[...runtimeRows,...rows].find(r=>r.workspaceId===(globalScope||getWorkspace()?.workspaceId))||rows.find(r=>r.status==='ready')||runtimeRows.find(r=>r.status==='ready')||rows[0]||runtimeRows[0];if(!global.isPreview())global.setEvidence(row?.evidence||null,row?(row.title||'账户工作区 '+(options.getWorkspaceTitle?.(row.workspaceId)||row.workspaceId)):'');global.setError(error||(!global.isPreview()&&row?.status==='unavailable'?'证据暂时无法读取，请重试。':''));renderSummary();}
  async function refresh(){if(document.body.dataset.desktopScreen!=='workspace'||document.hidden||pending)return pending;const token=epoch;abort=new AbortController();
    pending=(async()=>{try{const [snapshotResult,runtimeResult]=await Promise.allSettled([request('/api/harless/motif-library',{signal:abort.signal}),request('/api/harless/motif-catalog',{signal:abort.signal})]);
      if(snapshotResult.status==='rejected'&&snapshotResult.reason.status===401)throw snapshotResult.reason;if(runtimeResult.status==='rejected'&&runtimeResult.reason.status===401)throw runtimeResult.reason;
      const data=snapshotResult.status==='fulfilled'?snapshotResult.value:{format:'geneloop-motif-catalog-v1',workspaces:[],revision:'0'.repeat(64)};
      if(snapshotResult.status==='rejected'&&runtimeResult.status==='rejected')throw runtimeResult.reason;
      const runtime=runtimeResult.status==='fulfilled'?runtimeResult.value:null;
      if(runtime&&(runtime.format!=='geneloop-runtime-motif-catalog-v1'||!Array.isArray(runtime.libraries)))throw Error('Invalid runtime catalog');
      const nextRuntime=(runtime?.libraries||[]).map(row=>{if(typeof row.id!=='string'||typeof row.scene!=='string'||!['ready','unavailable'].includes(row.status))throw Error('Invalid runtime library');return {...row,workspaceId:row.id,title:(row.evidence?.source?.kind==='account_learning'?'账号学习库 · ':'服务端场景库 · ')+row.title,view:row.status==='ready'?readMotifEvidence(row.evidence):null};});
      const resolvedRuntime=runtime?nextRuntime:runtimeRows;
      const warning=runtimeResult.status==='rejected'?(runtimeResult.reason.status===404?'当前服务尚未提供场景库接口，请更新服务端。':'场景库接口暂不可用；已有数据可能不是最新状态。'):snapshotResult.status==='rejected'?'工作区证据接口暂不可用；仍可查看当前服务的场景库。':'';
      const runtimeRevision=JSON.stringify(resolvedRuntime.map(row=>[row.id,row.status,row.evidence?.export_digest]));if(token!==epoch)return;
      if(data.format!=='geneloop-motif-catalog-v1'||!Array.isArray(data.workspaces)||!/^[a-f0-9]{64}$/.test(data.revision)||new Set(data.workspaces.map(r=>r.workspaceId)).size!==data.workspaces.length)throw Error('Invalid catalog');
      const next=data.workspaces.map(r=>{if(typeof r.workspaceId!=='string'||!['ready','unavailable'].includes(r.status)||!['local','cloud'].includes(r.executionLocation)||r.compatibility!=='unverified')throw Error('Invalid scope');return {...r,view:r.status==='ready'?readMotifEvidence(r.evidence):null};});
      const nextRevision=data.revision+runtimeRevision;const changed=revision!==nextRevision||error!==warning;rows=next;runtimeRows=resolvedRuntime;revision=nextRevision;error=warning;ready=true;authorized=true;if(changed)project();syncInspector();
    }catch(cause){if(token!==epoch)return;if(cause.status===401){reset();options.onAuthorizationLost?.();error='请重新登录后读取 Motif 数据。';project();return;}error=cause.status===404?'所连接的服务尚未提供 Motif 展示接口。':'证据暂时无法读取，请重试。';project();}finally{if(token===epoch){pending=null;abort=null;}}})();return pending;
  }
  function reset(){epoch++;abort?.abort();pending=null;abort=null;rows=[];runtimeRows=[];revision='';error='';globalScope=null;ready=false;authorized=false;for(const panel of panels.values())panel.view.clear();panels.clear();global.clear();options.inspector?.replaceChildren();syncInspector();renderSummary();}
  new MutationObserver(()=>{if(document.body.dataset.desktopScreen==='workspace'){authorized=true;syncInspector();refresh();}else reset();}).observe(document.body,{attributes:true,attributeFilter:['data-desktop-screen']});
  setInterval(refresh,10000);document.addEventListener('visibilitychange',refresh);
  options.trigger.addEventListener('click',()=>{project();refresh();});
  return {open:global.open,close:global.close,refresh,syncInspector,workspaceHome(group,content){let panel=panels.get(group.workspaceId);if(!panel){const root=node('div',{class:'workspace-home motif-workspace'});panel={root,view:createMotifView({trigger:button('',()=>{}),host:root,embedded:true,inspector:options.inspector,onReset:renderSummary,isActive:()=>authorized&&getWorkspace()?.workspaceId===group.workspaceId&&!options.conversation.hidden&&options.conversation.dataset.page==='workspace-home'})};panels.set(group.workspaceId,panel);}panel.view.setWorkspace(content);const row=rows.find(r=>r.workspaceId===group.workspaceId);panel.view.setSources(sourceRows(group.workspaceId));syncInspector();renderSummary();return panel.root;}};
}
