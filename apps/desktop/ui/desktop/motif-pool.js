/** 输入仅为已通过原证据协议校验的账号目录；不创建新认证或执行权限。 */
const priority={local_learning:4,account_learning:3,scene_library:2,workspace_records:1};
const severity={invalid:4,pending_certification:3,registered:2,certified:1};
const applied=e=>e.kind==='invoke'&&e.status==='applied'&&e.actual_execution;
export const sceneLabels={ppt:'演示文稿',paper:'论文校对','paper-proofreading':'论文校对',data:'数据分析','research-data-analysis':'数据分析',files:'文件管理',chat:'通用对话',video:'视频剪辑','video-editing':'视频剪辑',coding:'代码'};
export const sceneLabel=id=>sceneLabels[id]||id||'场景未提供';
const rank=row=>priority[row.kind]||0;

const localTools={local_list:'列出材料',local_search:'搜索文本',local_document_pin:'固定材料版本',local_document_read:'读取材料页面'};

export function buildMotifPool(workspaces,runtime,{ready=false,partial=false,title=id=>id,localCatalog=null}={}){
  const sources=[...runtime.map(row=>({id:row.id,title:row.title,scene:row.scene,kind:row.evidence?.source?.kind==='account_learning'?'account_learning':'scene_library',status:row.status,view:row.view})),
    ...workspaces.map(row=>({id:'workspace:'+row.workspaceId,title:'工作区回执 · '+title(row.workspaceId),scene:row.view?.raw.scenario,kind:'workspace_records',status:row.status,view:row.view}))];
  if(Array.isArray(localCatalog)){
    const byScene=new Map();
    for(const row of localCatalog){
      if(!row||!/^motif-[0-9a-f]{24}$/.test(row.id)||!Object.hasOwn(sceneLabels,row.scene)||
        !/^[0-9a-f]{64}$/.test(row.certificate)||!Array.isArray(row.tools)||
        !row.tools.length||!row.tools.every(tool=>Object.hasOwn(localTools,tool)))continue;
      if(!byScene.has(row.scene))byScene.set(row.scene,[]);
      byScene.get(row.scene).push({id:'local:'+row.id,name:row.tools.map(tool=>localTools[tool]).join(' → '),
        status:'certified',tools:row.tools,localStructure:true,
        localReuses:Number.isSafeInteger(row.reuses)&&row.reuses>=0?row.reuses:null,
        version:{certificate_digest:row.certificate},witnesses:row.witnesses});
    }
    if(!byScene.size)byScene.set(null,[]);
    for(const [scene,capabilities] of byScene){
      sources.push({id:'local:'+String(scene??'all'),title:'本机学习库'+(scene?' · '+sceneLabel(scene):''),
        scene,kind:'local_learning',status:'ready',view:{capabilities,raw:{source:{kind:'local_learning'}}}});
    }
  }
  const byId=new Map();let hasReceipts=false;
  for(const source of sources){if(!source.view)continue;const {view}=source;
    const timestamp=Date.parse(view.raw.generated_at)||0;
    for(const cap of view.capabilities){
      const origin={id:source.id,title:source.title,scene:source.scene,kind:source.kind,status:cap.status,release:view.raw.source?.release||cap.version?.library_generation};
      let item=byId.get(cap.id);
      if(!item){item={...cap,origins:[],events:[],tool_flow:cap.toolFlow||cap.tool_flow||[],reuses:null,_rank:-1,_time:0,_hasReceipts:false,_events:new Map()};byId.set(cap.id,item);}
      const replace=rank(source)>item._rank||rank(source)===item._rank&&(timestamp>item._time||timestamp===item._time&&severity[cap.status]>severity[item.status]);
      if(replace){Object.assign(item,{...cap,events:item.events,tool_flow:cap.toolFlow||cap.tool_flow||[],_rank:rank(source),_time:timestamp});}
      item.origins.push(origin);
      if(!view.raw.source){item._hasReceipts=true;hasReceipts=true;for(const event of cap.events||[])item._events.set(event.id,event);}
    }
  }
  const capabilities=[...byId.values()].map(item=>{
    item.events=[...item._events.values()];
    item.reuses=item.localStructure?item.localReuses:item._hasReceipts?item.events.filter(applied).length:null;
    if(item.reuses!==null)hasReceipts=true;
    item.statusConflict=new Set(item.origins.map(o=>o.status)).size>1;
    delete item._events;delete item._rank;delete item._time;delete item._hasReceipts;return item;
  }).sort((a,b)=>a.id.localeCompare(b.id));
  const incomplete=partial||sources.some(s=>s.status!=='ready');
  return {isPool:true,known:ready&&(!incomplete||sources.some(s=>s.view)),partial:incomplete,capabilities,sources:sources.map(({view,...row})=>row),
    summary:{applied:hasReceipts?capabilities.reduce((n,c)=>n+(c.reuses||0),0):null}};
}

export function filterMotifPool(pool,{scene='all',source='all',status='all',query=''}={}){
  const text=query.trim().toLocaleLowerCase();
  const capabilities=pool.capabilities.filter(c=>(status==='all'||c.status===status)&&(!text||(c.name+' '+c.id).toLocaleLowerCase().includes(text))&&
    c.origins.some(o=>(scene==='all'||o.scene===scene)&&(source==='all'||o.id===source)));
  return {...pool,capabilities,summary:{applied:!capabilities.length?0:capabilities.some(c=>c.reuses!==null)?capabilities.reduce((n,c)=>n+(c.reuses||0),0):null}};
}
