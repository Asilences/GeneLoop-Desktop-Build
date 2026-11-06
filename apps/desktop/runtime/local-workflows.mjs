// Reuse the actual scene MCP tools. This adapter only owns source snapshots,
// managed process lifetime, discovery and publication into the native writer.
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {createHash,randomUUID} from 'node:crypto';
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync,lstatSync,realpathSync,readdirSync} from 'node:fs';
import {basename,dirname,join,relative,resolve,sep} from 'node:path';
import JSZip from 'jszip';
import {NativeMcpTransport} from './local-mcp-transport.mjs';
import {removeScratchDirectory,publishArtifacts} from './local-artifacts.mjs';
import {workflowTools,workflowKinds as kinds,workflowToolName} from './native-workflow-catalog.mjs';
import {ocrData} from './native-ocr-data.mjs';
import {ensureNativeFonts} from './local-fonts.mjs';

const sha=data=>createHash('sha256').update(data).digest('hex');
// Python's canonical representation is shared with the existing file planner.
const canonical=value=>Array.isArray(value)?'['+value.map(canonical).join(',')+']':
  value&&typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);
const deliveredBy=new Set(['deliver_report','deliver_deck','build_delivery','render_delivery','revise_delivery',
  'export_current_audit_pdf','export_review_report','export_input_review','submit_report','create_text','edit_text','execute_code']);
const extensions=new Set(['md','txt','json','pdf','pptx','csv','zip','docx','xlsx','png']);
const maxSource=32*1024*1024,maxTotal=128*1024*1024;
function object(value){return value!==null&&typeof value==='object'&&!Array.isArray(value);}
function payload(result) {
  if(result.structuredContent)return result.structuredContent;
  const text=result.content?.filter(x=>x.type==='text').map(x=>x.text).join('\n');
  try{return JSON.parse(text);}catch{return {text};}
}
function plainFile(root,path) {
  const full=resolve(path),rel=relative(root,full);
  if(rel==='..'||rel.startsWith('..'+sep)||resolve(root)===full)throw Error('场景产物超出当前任务。');
  for(let at=full;at!==root;at=dirname(at))if(lstatSync(at).isSymbolicLink())throw Error('场景产物不能通过链接读取。');
  const info=lstatSync(full);
  if(!info.isFile()||info.nlink!==1||info.size<1||info.size>80*1024*1024||realpathSync(full)!==full)throw Error('场景产物类型或大小无效。');
  return full;
}

export function createNativeWorkflows(ctx,reader,writer,tools,scene,signal,onReport,onCatalog) {
  const active=new Map(),parent=realpathSync(process.cwd());let pending=false,closed=false;
  function checkSources(sources){
    signal.throwIfAborted();
    const root=join(dirname(tools.sourceRoot),'ocr');
    for(const [name,version]of Object.entries(ocrData))
      if(sha(readFileSync(plainFile(root,join(root,name))))!==version)throw Error('本机OCR资源版本已变化。');
    for(const source of sources)if(sha(reader.readBytes(source.path,maxSource))!==source.sha256)throw Error('工作区来源已变化，请重新打开该工作流。');
  }
  async function closeOne(row) {
    await row.client?.close().catch(()=>{});
    try{removeScratchDirectory(row.root,parent);}catch{/* The worker parent retries cleanup after exit. */}
  }
  const workflows={
    async open(sourcesJSON,request,settingsJSON='{}') {
      if(closed||pending)throw Error('工作流正在打开或已关闭。');
      if(active.size>=3)throw Error('本轮最多同时打开三个场景工作流。');
      if(typeof request!=='string'||!request.trim()||Buffer.byteLength(request)>256*1024)throw Error('请输入本轮实际任务说明。');
      const settings=JSON.parse(settingsJSON),sources=JSON.parse(sourcesJSON);
      if(!object(settings)||Object.keys(settings).some(k=>!['workflow','slides','template','operation'].includes(k)))throw Error('工作流设置包含未知字段。');
      const kind=settings.workflow??kinds[scene]?.[0];
      if(!kinds[scene]?.includes(kind))throw Error('该工作流不在当前场景内。');
      if(!Array.isArray(sources)||sources.length>16||sources.some(s=>!object(s)||Object.keys(s).sort().join(',')!=='path,sha256'||typeof s.path!=='string'||!/^[a-f0-9]{64}$/.test(s.sha256)))throw Error('来源必须为最多16项的路径和SHA-256数组。');
      const aliases=new Map();let total=0;
      const snapshots=sources.map(source=>{
        const bytes=reader.readBytes(source.path,maxSource);total+=bytes.length;
        if(sha(bytes)!==source.sha256||total>maxTotal)throw Error('来源已变化或超过本轮128MiB处理限制。');
        const name=basename(source.path.replaceAll('\\','/'));
        if(name.startsWith('.')||name.includes(':')||aliases.has(name.toLowerCase()))throw Error('来源文件名重复或无效，请分批打开。');
        aliases.set(name.toLowerCase(),source.path);return {...source,name,bytes};
      });
      const root=mkdtempSync(join(parent,'workflow-')),work=join(root,'.local','turn','work'),inputs=join(work,'inputs');
      mkdirSync(inputs,{recursive:true,mode:0o700});mkdirSync(join(work,'outputs'),{mode:0o700});
      const task=randomUUID(),approved={},mapping={};let client;
      const row={root,work,kind,sources:snapshots.map(({path,sha256})=>({path,sha256})),published:new Map()};
      pending=true;
      try {
        await ensureNativeFonts(ctx,tools,root,signal);
        // A TeX tree is supplied as one approved archive to preserve includes.
        if(kind==='paper'&&snapshots.some(s=>s.name.endsWith('.tex'))&&snapshots.some(s=>s.path.includes('/')||s.path.includes('\\'))) {
          const archive=new JSZip();for(const item of snapshots)archive.file(item.path.replaceAll('\\','/'),item.bytes);
          const bytes=await archive.generateAsync({type:'nodebuffer',compression:'DEFLATE'});
          writeFileSync(join(inputs,'paper-sources.zip'),bytes,{flag:'wx',mode:0o600});approved['paper-sources.zip']=sha(bytes);
          mapping['paper-sources.zip']=row.sources;
        } else for(const item of snapshots) {
          writeFileSync(join(inputs,item.name),item.bytes,{flag:'wx',mode:0o600});approved[item.name]=item.sha256;mapping[item.name]=item.path;
        }
        const save=(name,value)=>writeFileSync(join(work,name),JSON.stringify(value,null,2),{flag:'wx',mode:0o600});
        save('approved-inputs.json',{files:approved});save('paper-output-grant.json',{schema_version:1,task_id:task,allow_output:true});
        save('general-task.json',{allow_output:true});
        if(kind==='report') {mkdirSync(join(work,'report'));writeFileSync(join(work,'report','request.txt'),request,{mode:0o600});}
        if(kind==='ppt') {
          const slides=settings.slides??8;
          if(!Number.isInteger(slides)||slides<1||slides>30||!['academic','lab'].includes(settings.template??'academic')||!['generate','restyle'].includes(settings.operation??'generate'))throw Error('PPT设置需要1至30页、academic/lab模板和generate/restyle操作。');
          save('job.json',{job_id:task,instruction:request,slides,template:settings.template??'academic',operation:settings.operation??'generate',
            allow_output:true,allow_rsi_update:false,execution_policy:{schema_version:1,strategy:'host_delivery'},
            inputs:Object.entries(approved).map(([name,version_sha256],i)=>({document_id:'document-'+(i+1),name,version_sha256,path:join(inputs,name)}))});
        }
        const nativeSettings={};
        if(kind==='files') {
          writeFileSync(join(inputs,'.experiment-copy'),'native-scene-snapshot',{flag:'wx',mode:0o600});
          const initial={...approved,'.experiment-copy':sha(Buffer.from('native-scene-snapshot'))};
          nativeSettings.file_task={scope_kind:'harless_web_task',task_id:task,workspace:inputs,family:'native_workspace',objective:request,
            rules:['只整理当前任务副本；原工作区资料不会被移动、覆盖或删除。','先preview_actions，再由用户确认，最后执行。'],
            allowed_operations:['copy','move','quarantine'],initial_snapshot:initial,
            write_grant:{schema_version:1,allow_restore:true,max_actions:6,allowed_ops:['copy','move','quarantine'],
              source_paths:Object.keys(approved),destination_prefixes:['整理/','quarantine/']}};
        }
        save('native-settings.json',nativeSettings);
        const bootstrap="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')";
        let argv=[tools.python,'-E','-s','-B','-X','utf8','-c',bootstrap,tools.sourceRoot,'src.adapters.desktop_workflow_server',kind,work];
        const env={PATH:[dirname(tools.python),dirname(tools.soffice)].join(process.platform==='win32'?';':':'),
          HOME:root,USERPROFILE:root,APPDATA:root,LOCALAPPDATA:root,TEMP:root,TMP:root,TMPDIR:root,PYTHONUTF8:'1',
          SSS_PPT_NODE_EXECUTABLE:process.execPath,
          ELECTRON_RUN_AS_NODE:'1',NODE_OPTIONS:undefined,NODE_PATH:undefined,FM_NATIVE_PDF:'1',GENELOOP_PPT_MASTER_ROOT:tools.skill,
          GENELOOP_PDF_OCR_ROOT:join(dirname(tools.sourceRoot),'ocr'),GENELOOP_DESKTOP_OCR_LOCK:'1'};
        const {fileURLToPath}=await import('node:url');
        env.GENELOOP_NATIVE_CODE_RUNNER=join(dirname(fileURLToPath(import.meta.url)),'local-code.mjs');
        // The top-level PPT proxy is the same typed delivery/recovery adapter as Web.
        if(kind==='ppt') {
          const runtime=dirname(fileURLToPath(import.meta.url));env.SSS_PPT_NODE_ROOT=runtime;
          env.GENELOOP_PPT_SOURCE_ROOT=tools.sourceRoot;env.SSS_PPT_DELIVERY_PYTHON=tools.python;env.SSS_PPT_JOB=join(work,'job.json');env.HARLESS_PRIVATE_ROOT=work;
          argv=[process.execPath,join(runtime,'research-ppt','mcp-adapter.js'),'--web-session'];
        }
        client=new Client({name:'geneloop-native-scene',version:'1.0.0'},{capabilities:{}});row.client=client;
        row.transport=new NativeMcpTransport(ctx,argv,work,env,signal);
        await client.connect(row.transport,{signal,timeout:60000});
        const catalog=[];let cursor;const seen=new Set();
        do {const page=await client.listTools(cursor?{cursor}:undefined,{signal,timeout:60000});catalog.push(...page.tools);cursor=page.nextCursor;
          if(cursor&&seen.has(cursor))throw Error('场景工具目录分页无效。');if(cursor)seen.add(cursor);
        }while(cursor);
        if(catalog.some(tool=>!workflowTools[kind].includes(tool.name))||new Set(catalog.map(t=>t.name)).size!==workflowTools[kind].length)throw Error('场景工具目录与锁定版本不一致。');
        checkSources(row.sources);row.catalog=catalog;row.allowed=new Set(catalog.map(tool=>tool.name));
        for(const [previousId,previous]of active)if(previous.kind===kind){if(previous.busy)throw Error('请等待该工作流完成当前操作。');await closeOne(previous);active.delete(previousId);}
        const id=randomUUID();active.set(id,row);
        try {onCatalog?.(kind,id,catalog);}catch(error){active.delete(id);throw error;}
        return {workflow_id:id,workflow:kind,source_mapping:mapping,tools:catalog.map(tool=>({...tool,public_name:workflowToolName(kind,tool.name)})),execution:'local',originals_modified:false};
      } catch(error) {
        const diagnostic=row.transport?.child?.collected.stderr?.readFrom(0).text;
        await closeOne({...row,client});
        throw Error('本机场景连接未就绪。',{cause:diagnostic?Error(diagnostic):error});
      }
      finally {pending=false;}
    },
    async call(id,name,argsJSON,approve) {
      const row=active.get(id);if(closed||!row)throw Error('工作流不存在，请重新打开。');
      if(row.busy)throw Error('请等待该工作流当前操作完成。');
      if(!row.allowed.has(name))throw Error('该工具不属于已发现的场景。');
      const args=JSON.parse(argsJSON);if(!object(args)||Buffer.byteLength(argsJSON)>1024*1024)throw Error('工具参数需要JSON对象。');
      row.busy=true;
      try {
        checkSources(row.sources);
        if(row.kind==='files'&&['authorize_plan','execute_plan','restore_plan'].includes(name)) {
          // A model cannot issue its own UI approval by calling authorize_plan.
          if(name==='authorize_plan'||name==='restore_plan') {
            const preview=row.previews?.get(args.plan_id);
            if(!preview||!approve||!await approve({kind:'files',preview:{operation:name==='restore_plan'?'restore':'execute',...preview}}))throw Error('用户尚未确认该文件整理方案。');
          }
        }
        const result=await row.client.callTool({name,arguments:args},undefined,{signal,timeout:450000});
        checkSources(row.sources);
        const value=payload(result);
        if(result.isError)return {isError:true,...value};
        if(row.kind==='files'&&name==='preview_actions'&&value.plan_id){row.previews??=new Map();row.previews.set(value.plan_id,value);}
        const artifacts=[];
        if(row.kind==='files'&&name==='execute_plan'&&value.status==='executed_verified') {
          const archive=new JSZip(),inputRoot=join(row.work,'inputs');
          const walk=(directory,prefix='')=>{
            for(const entry of readdirSync(directory,{withFileTypes:true})) {
              if(entry.name==='.experiment-copy')continue;
              const path=join(directory,entry.name),name=prefix+entry.name;
              if(entry.isSymbolicLink())throw Error('整理结果出现链接，停止交付。');
              if(entry.isDirectory())walk(path,name+'/');
              else archive.file(name,readFileSync(plainFile(inputRoot,path)));
            }
          };
          walk(inputRoot);archive.file('GeneLoop-整理回执.json',JSON.stringify({receipt:value,source_versions:row.sources,originals_modified:false},null,2));
          const bytes=await archive.generateAsync({type:'nodebuffer',compression:'DEFLATE'});
          artifacts.push(...publishArtifacts(writer,onReport,signal,[{extension:'zip',bytes}]));
        }
        if(deliveredBy.has(name)||row.kind==='ppt'&&value.delivered===true) {
          const candidates=new Map();
          const add=(name,version)=>{
            if(typeof name!=='string'||name.length>2048||typeof version!=='string'||!/^[a-f0-9]{64}$/.test(version))return;
            const path=resolve(row.work,name),roots=[join(row.work,'outputs')];
            if(row.kind==='ppt'&&value.delivered===true)roots.push(join(row.work,'validation'));
            const boundary=roots.find(root=>{const rel=relative(root,path);return rel!==''&&rel!=='..'&&!rel.startsWith('..'+sep);});
            if(boundary&&extensions.has(path.split('.').at(-1).toLowerCase()))candidates.set(path,{boundary,version});
          };
          const visit=item=>{
            if(Array.isArray(item))item.forEach(visit);
            else if(object(item)) {
              add(item.path??item.name,item.sha256??item.file_sha256);
              if(item.artifact_file)add(item.artifact_file,item.pdf_sha256);
              Object.values(item).filter(child=>object(child)||Array.isArray(child)).forEach(visit);
            }
          };
          visit(value);
          for(const [candidate,declared]of candidates) {
            const path=plainFile(declared.boundary,candidate),bytes=readFileSync(path),version=sha(bytes),key=relative(row.work,path);
            if(version!==declared.version)throw Error('已核验产物发生变化，停止交付。');
            if(row.published.get(key)===version)continue;
            const report=publishArtifacts(writer,onReport,signal,[{extension:path.split('.').at(-1).toLowerCase(),bytes}]);
            row.published.set(key,version);artifacts.push(...report);
          }
        }
        // Keep the complete MCP blocks; never reconstruct authority from display text.
        return {result:value,content:result.content,artifacts,execution:'local'};
      } finally {row.busy=false;}
    },
    async release(id){const row=active.get(id);if(!row||row.busy)throw Error('工作流不存在或正在执行。');onCatalog?.(row.kind,id,[]);active.delete(id);await closeOne(row);return {closed:true};},
    async close(){closed=true;await Promise.allSettled([...active.values()].map(closeOne));active.clear();},
  };
  return workflows;
}
