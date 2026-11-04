/** Shared, version-bound export for Generate projects in an owning PPT task. */
import {spawn} from 'node:child_process';
import {appendFileSync,existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,realpathSync,renameSync,writeFileSync} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import {dirname,isAbsolute,join,posix,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {commandArgv,commandLayout} from './geneloop_shell.ts';
import {officeEvidenceVersion} from './geneloop_presentation.ts';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {deliveryProgress} from './ppt_delivery_state.ts';

const sha=(bytes:any)=>createHash('sha256').update(bytes).digest('hex');
const source=(name:string)=>readFileSync(new URL(name,import.meta.url),'utf8');
const locks=new Set<string>();
export const pptPreparationTool={name:'prepare_ppt',
 description:'在内容与设计规范写好后校准字体。输入/work/projects内project，宿主按spec_lock.md和design_spec.md测量常规/粗体角色，核验实际字体并缓存同版本结果。制作时使用返回的normal/bold测量表。',
 parameters:{type:'object',properties:{project:{type:'string'}},required:['project'],additionalProperties:false}};
export const pptDeliveryTool={name:'finalize_ppt',
 description:'导出已完成设计与来源核对的Generate项目。只需输入project，宿主按svg_output文件名顺序生成页面清单。也可提供manifest，pages列出{source:"svg_output/slide_01.svg"}，备注放项目notes/。统一执行官方检查、可编辑PPTX导出、实际PDF/逐页PNG渲染，相同依赖复用检查。返回后用read_image查看页面并present交付。',
 parameters:{type:'object',properties:{project:{type:'string'},manifest:{type:'string'},profile:{type:'string'}},required:['project'],additionalProperties:false}};

const exporterCommand=/(?:^|[;&|\n(])\s*(?:[^\s;&|]*\/)?python(?:3(?:\.\d+)?)?\s+(?:-(?:I|B|u)\s+)*["']?(?:\/opt\/geneloop\/ppt-master|\$\{?[a-zA-Z_][a-zA-Z0-9_]*\}?)\/scripts\/svg_to_pptx\.py["']?\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))/;
export function managedDefaultExport(command:unknown){
 if(typeof command!=='string'||/--(?:roundtrip|quick-generate)|\s--help(?:\s|$)/.test(command))return false;
 if(/(?:^|\s)(?:-s|--source)(?:\s|=)/.test(command)){
  const source=/(?:^|\s)(?:-s|--source)(?:\s+|=)["']?([^\s"';&|]+)/.exec(command)?.[1];
  if(!['output','svg_output'].includes(source??''))return false;
 }
 return exporterCommand.test(command);
}
export function managedExportProject(command:unknown){
 if(!managedDefaultExport(command))return null;
 const match=exporterCommand.exec(command as string);
 const project=match?.[1]??match?.[2]??match?.[3];
 return project?.startsWith('/work/projects/')?project:null;
}

export function pptDeliveryScene(scene:any,enabled:boolean){
 if(!enabled||scene.id!=='ppt'||scene.ppt_execution_strategy!=='ppt_master')return scene;
 return {...scene,allowed_tools:[...new Set([...scene.allowed_tools,pptPreparationTool.name,pptDeliveryTool.name])]};
}

export function pptDeliveryGraphTools(scene:any,tools:any[]){
 const names=[pptDeliveryTool,pptPreparationTool];
 const rows=tools.filter(row=>names.some(tool=>tool.name===row.name));
 if(!rows.length)return tools;
 for(const row of rows){
  const expected=names.find(tool=>tool.name===row.name)!;
  if(scene.id!=='ppt'||!scene.allowed_tools.includes(row.name)||rows.filter(other=>other.name===row.name).length!==1||digest(row.parameters)!==digest(expected.parameters))
   throw Error('delivery_native_schema_changed');
 }
 return tools.filter(row=>!names.some(tool=>tool.name===row.name));
}

export function pptWorkspacePath(workspace:string,path:string){
 if(typeof path!=='string'||!path.startsWith('/work/')||posix.normalize(path)!==path||path.includes('\\'))throw Error('delivery_path_invalid');
 const rel=path.slice(6);
 const host=join(workspace,rel.startsWith('outputs/')?'outputs/code/'+rel.slice(8):rel.startsWith('inputs/')?rel:'code/'+rel);
 if(!existsSync(host)||realpathSync(host)!==resolve(host)||lstatSync(host).isSymbolicLink()||
    (lstatSync(host).isFile()&&lstatSync(host).nlink!==1))throw Error('delivery_path_changed');
 return host;
}
const workspacePath=pptWorkspacePath;
function hasGenerateProject(task:any){
 const projects=join(task.workspace,'code/projects');
 return existsSync(projects)&&readdirSync(projects).some(name=>{
  const path=join(projects,name);
  return !lstatSync(path).isSymbolicLink()&&existsSync(join(path,'svg_output'))&&existsSync(join(path,'spec_lock.md'))&&
   !existsSync(join(path,'sources/source.pptx'));
 });
}

export function deliveryDependencies(workspace:string,project:string,manifest:string,resources:any={}){
 if(!project.startsWith('/work/projects/'))throw Error('delivery_project_required');
 const directory=workspacePath(workspace,project);
 if(!lstatSync(directory).isDirectory())throw Error('delivery_project_required');
 const manifestPath=workspacePath(workspace,manifest);
 if(!manifest.startsWith(project+'/')||!lstatSync(manifestPath).isFile())throw Error('delivery_manifest_outside_project');
 const files:any[]=[];
 const notesFromTotal=JSON.parse(readFileSync(manifestPath,'utf8')).notes_source==='total';
 let bytes=0;
 const visit=(path:string)=>{
  for(const leaf of readdirSync(path).sort()){
   const file=join(path,leaf),stat=lstatSync(file);
   if(stat.isSymbolicLink()||realpathSync(file)!==file)throw Error('delivery_dependency_changed');
   if(stat.isDirectory()){visit(file);continue;}
   const logicalPath=relative(directory,file).split('\\').join('/');
   // These official reports are export outputs, including run-specific paths.
   // Source/spec/notes and other validation files remain version dependencies.
   if(['validation/workflow.log','validation/svg_quality_report.json','validation/presentation.report.json'].includes(logicalPath))continue;
   if(notesFromTotal&&logicalPath.startsWith('notes/')&&file.endsWith('.md')&&leaf!=='total.md')continue;
   if(!stat.isFile()||stat.nlink!==1||files.length>=4096||(bytes+=stat.size)>200_000_000)throw Error('delivery_dependency_protocol_bound');
   files.push({path:logicalPath,sha256:sha(readFileSync(file))});
  }
 };
 visit(directory);
 for(const row of [...files]){
  if(!row.path.endsWith('.svg'))continue;
  const text=readFileSync(join(directory,row.path),'utf8');
  for(const match of text.matchAll(/(?:xlink:)?href\s*=\s*["']([^"']+)["']/g)){
   const reference=match[1];
   if(reference.startsWith('#')||reference.startsWith('data:'))continue;
   if(/^[a-z]+:/i.test(reference)||reference.includes('&'))throw Error('delivery_asset_reference_unsupported');
   const logical=posix.resolve(posix.dirname(project+'/'+row.path),reference);
   if(logical.startsWith(project+'/'))continue;
   if(!/\.(png|jpe?g|gif|webp)$/i.test(logical))throw Error('delivery_external_asset_unsupported');
   const asset=workspacePath(workspace,logical),stat=lstatSync(asset);
   if(!stat.isFile()||stat.nlink!==1||stat.size>30_000_000)throw Error('delivery_asset_changed');
   files.push({path:'@asset:'+logical,sha256:sha(readFileSync(asset))});
  }
 }
 const profileBytes=readFileSync(new URL('../../scenarios/ppt_master/design-profiles.json',import.meta.url));
 return {files,environment:officeEvidenceVersion(resources),profile_sha256:sha(profileBytes),
  runner_sha256:sha(source('./ppt_delivery_runner.py')),preflight_sha256:sha(source('./ppt_design_preflight.py')),
  annotation_repair_sha256:sha(source('./ppt_annotation_repair.py')),
  preparation_sha256:sha(source('./ppt_preparation_runner.py')),
  runtime_policy_sha256:sha(readFileSync(new URL('../../scenarios/ppt_master/runtime-policy.md',import.meta.url))),
  state_sha256:sha(source('./ppt_delivery_state.ts'))};
}

async function runInSession(task:any,request:any,resources:any,signal?:AbortSignal){
 const code=source('./ppt_design_preflight.py')+'\n'+(request.operation==='prepare'?source('./ppt_preparation_runner.py'):
  source('./ppt_annotation_repair.py')+'\n'+source('./ppt_delivery_runner.py'));
 const script=Buffer.from(code).toString('base64');
 const encoded=Buffer.from(JSON.stringify(request)).toString('base64');
 const python=process.env.SSS_PYTHON??'/usr/bin/python3';
 if(!/^\/[a-zA-Z0-9_./-]+$/.test(python))throw Error('delivery_python_invalid');
 const command=python+` -I -B -c "import base64;exec(base64.b64decode('${script}'))" '${encoded}'`;
 const session=task.request.session_id;
 const socket=process.env.GENELOOP_COMMAND_SOCKET;
 const argv=socket?[process.execPath,fileURLToPath(new URL('./geneloop_command_client.mjs',import.meta.url)),socket,
  Buffer.from(JSON.stringify({session,command,cwd:'/work',readOnly:false,network:'none'})).toString('base64url')]:
  commandArgv(commandLayout(resolve(task.workspace,'../../..'),session),command,'/work',python,process.execPath,false,{...resources,network:'none'});
 signal?.throwIfAborted();
 return await new Promise<any>((done,fail)=>{
  const child=spawn(argv[0],argv.slice(1),{stdio:['ignore','pipe','pipe'],detached:true,env:socket?process.env:{}});
  let stdout='',stderr='',overflow=false;
  const stop=()=>{try{if(child.pid)process.kill(-child.pid,'SIGTERM');}catch{child.kill();}};
  const abort=()=>stop();
  signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(stop,900000);
  child.stdout.on('data',value=>{stdout+=value;if(Buffer.byteLength(stdout)>4_000_000){overflow=true;stop();}});
  child.stderr.on('data',value=>{stderr=(stderr+value).slice(-8000);});
  child.on('error',fail);
  child.on('close',exit=>{
   clearTimeout(timer);signal?.removeEventListener('abort',abort);
   if(signal?.aborted)return fail(Error('delivery_cancelled'));
   if(exit!==0||overflow)return fail(Error('delivery_execution_failed: '+stderr));
   try{done(JSON.parse(stdout));}catch{fail(Error('delivery_receipt_invalid'));}
  });
 });
}

function verifiedArtifacts(task:any,receipt:any){
 if(!Array.isArray(receipt.artifacts)||!receipt.artifacts.length)return false;
 return receipt.artifacts.every((row:any)=>{
  try{
   const path=workspacePath(task.workspace,row.path),stat=lstatSync(path);
   return row.path.startsWith('/work/outputs/')&&stat.isFile()&&stat.nlink===1&&stat.size===row.bytes&&sha(readFileSync(path))===row.sha256;
  }catch{return false;}
 });
}

export function registerPptDeliveryTool(ctx:any,current:(session:string)=>any,resources:any={}){
 ctx.tools.guard?.((execution:any)=>{
  const session=execution.agent?.session?.id,task=current(session)?.task;
  if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene?.ppt_execution_strategy!=='ppt_master')return;
  if(execution.name==='present'){
   const problem=validatePptPublication(task,execution.arguments?.files??[],resources);
   if(problem)return problem;
  }
  if(execution.name!=='bash')return;
  const command=execution.arguments?.command;
  if(typeof command==='string'&&command.includes('svg_output/')&&
     /(?:\bsvg2png\s*\(|\brsvg-convert\b|\binkscape\b[^\n]*--export|\b(?:magick|convert)\b[^\n]*\.svg)/.test(command)&&hasGenerateProject(task))
   return '项目页面的预览由finalize_ppt统一生成。请先完成页面与备注，再调用finalize_ppt并用read_image查看其Office渲染PNG；源码SVG的独立渲染和反复换DPI预览会引入字体与坐标差异。按具体finding或清楚可见的缺陷修订。';
  if(typeof command==='string'&&/python(?:3(?:\.\d+)?)?\s+[^;&|\n]*svg_quality_checker\.py/.test(command)&&
     !/\s--help\b/.test(command)&&hasGenerateProject(task))
   return 'Generate的官方检查由finalize_ppt统一执行。请先完成页面与讲者备注，然后调用finalize_ppt。宿主处理明确错误并保留原始报告，warning按当前画面与任务要求评估，避免逐条猜测式微调。';
  if(typeof command==='string'&&/(?:\bfc-(?:match|list|query)\b|text_measure\.py(?:["']?\s)|fontTools|pdffonts\b)/.test(command)&&!/(?:\s--help\b)/.test(command))
   return '字体解析与角色测量由prepare_ppt完成。使用该工具当前回执中的字体与normal/bold表制作；实际输出检查使用finalize_ppt。需要管理员处理的环境故障请保留具体错误。';
  if(typeof command==='string'&&command.includes('/work/outputs/')&&
     /(?:get_text\s*\(\s*["'](?:rawdict|dict|words)["']|get_bboxlog\s*\(|get_texttrace\s*\()/.test(command))
   return '成品的字符框、span和字体度量诊断由共同交付检查处理。使用finalize_ppt的具体finding与read_image画面定位问题；字符框相交不单独触发修订。原始资料的文字抽取仍可按来源路径进行。';
  if(!managedDefaultExport(command))return;
  const project=managedExportProject(command);
  appendFileSync(join(task.output,'ppt-delivery-audit.jsonl'),JSON.stringify({kind:'ppt_export_redirected',
   task_id:task.request?.task_id,command_sha256:sha(command)})+'\n',{mode:0o600});
  return '此Generate导出通过finalize_ppt执行。传入完整project路径'+(project?' '+project:'，将当前命令中的项目变量换成其真实/work/projects路径')+'。宿主生成清单并运行官方检查、PPTX导出及PDF/PNG渲染。';
 });
 ctx.tools.register({...pptPreparationTool,output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any,execution:any){
   const task=current(execution?.agent?.session?.id)?.task;
   if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true)
    throw Error('preparation_task_not_authorized');
   workspacePath(task.workspace,args.project);
   if(locks.has(task.workspace))throw Error('delivery_already_running');
   locks.add(task.workspace);
   try{
    return await runInSession(task,{operation:'prepare',project:args.project,environment:officeEvidenceVersion(resources),
     implementation_sha256:sha(source('./ppt_preparation_runner.py')+source('./ppt_design_preflight.py'))},resources,execution.signal);
   }finally{locks.delete(task.workspace);}
  }});
 ctx.tools.register({...pptDeliveryTool,output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any,execution:any){
   const invocationArguments={...args};
   const session=execution?.agent?.session?.id;
   const context=current(session),task=context?.task;
   if(!task||task.status!=='running'||task.scene.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options.allow_output!==true)
    throw Error('delivery_task_not_authorized');
   if(locks.has(task.workspace))throw Error('delivery_already_running');
   locks.add(task.workspace);
   try{
    args={...args};
    if(typeof args.project!=='string'||!args.project.startsWith('/work/projects/'))throw Error('delivery_project_required');
    if(args.manifest===undefined){
     const project=workspacePath(task.workspace,args.project);
     const manifest=join(project,'delivery.json');
     if(existsSync(manifest))workspacePath(task.workspace,args.project+'/delivery.json');
     if(!existsSync(manifest)||JSON.parse(readFileSync(manifest,'utf8')).generated_by==='geneloop'){
      const pages=readdirSync(join(project,'svg_output')).filter(name=>name.endsWith('.svg')).sort().map(name=>({source:'svg_output/'+name}));
      const notes=join(project,'notes');
      const notesSource=existsSync(join(notes,'total.md'))&&readdirSync(notes).filter(name=>name.endsWith('.md')&&name!=='total.md').length===0?'total':undefined;
      if(existsSync(manifest))workspacePath(task.workspace,args.project+'/delivery.json');
      const next=JSON.stringify({generated_by:'geneloop',pages,notes_source:notesSource});
      if(!existsSync(manifest)||readFileSync(manifest,'utf8')!==next)writeFileSync(manifest,next,{mode:0o600});
     }
     args.manifest=args.project+'/delivery.json';
    }
    if(typeof args.manifest!=='string'||!args.manifest.startsWith(args.project+'/'))throw Error('delivery_manifest_outside_project');
    const manifestFile=workspacePath(task.workspace,args.manifest);
    const manifestValue=JSON.parse(readFileSync(manifestFile,'utf8'));
    if(manifestValue.notes_source===undefined&&existsSync(workspacePath(task.workspace,args.project)+'/notes/total.md')){
     manifestValue.notes_source='total';
     writeFileSync(manifestFile,JSON.stringify(manifestValue),{mode:0o600});
    }
    const profile=args.profile??'academic-readable-v1';
    const profiles=JSON.parse(readFileSync(new URL('../../scenarios/ppt_master/design-profiles.json',import.meta.url),'utf8'));
    if(!Object.hasOwn(profiles.profiles,profile))throw Error('delivery_profile_unknown');
    await runInSession(task,{operation:'prepare',project:args.project,environment:officeEvidenceVersion(resources),
     implementation_sha256:sha(source('./ppt_preparation_runner.py')+source('./ppt_design_preflight.py'))},resources,execution.signal);
    const dependencies=deliveryDependencies(task.workspace,args.project,args.manifest,resources);
    const fontRules=(context.fontRules??[]).filter((rule:any)=>rule.environment===dependencies.environment&&rule.training_task!==task.request.task_id);
    const ruleVersions=fontRules.map((rule:any)=>rule.id);
    const key=digest({project:args.project,manifest:args.manifest,profile,dependencies,ruleVersions});
    const folder=join(task.output,'ppt-delivery-receipts');mkdirSync(folder,{recursive:true,mode:0o700});
    const history=join(folder,'history-'+digest({project:args.project,profile})+'.json');
    const path=join(folder,key+'.json');
    if(existsSync(path)){
     const old=JSON.parse(readFileSync(path,'utf8'));
     if(old.key===key&&verifiedArtifacts(task,old))return {...old,reused_checks:true,next_action:'read_image'};
     if(old.key===key&&old.mechanical_status==='failed'&&old.retryable!==true)
      return {...old,reused_checks:true,convergence_status:'unchanged',next_action:'repair_specific_findings_before_rechecking'};
    }
    const output='/work/outputs/ppt-delivery-'+randomUUID();
    const result=await runInSession(task,{...args,profile,output,font_rules:fontRules},resources,execution.signal);
    const after=deliveryDependencies(task.workspace,args.project,args.manifest,resources);
    const afterVersions=new Map(after.files.map(row=>[row.path,row.sha256]));
    for(const file of dependencies.files){
     if(afterVersions.get(file.path)!==file.sha256){
      const repair=result.applied_font_rules?.find((row:any)=>row.source===args.project+'/'+file.path&&row.before_sha256===file.sha256&&row.after_sha256===afterVersions.get(file.path));
      const annotation=result.applied_annotation_repairs?.find((row:any)=>row.source===args.project+'/'+file.path&&row.before_sha256===file.sha256&&
       (row.after_sha256===afterVersions.get(file.path)||result.applied_font_rules?.some((font:any)=>font.source===row.source&&
         font.before_sha256===row.after_sha256&&font.after_sha256===afterVersions.get(file.path)&&fontRules.some((rule:any)=>rule.id===font.rule_id))));
      if(!annotation&&(!repair||!fontRules.some((rule:any)=>rule.id===repair.rule_id)))throw Error('delivery_source_changed_during_export');
     }
    }
    if(after.environment!==dependencies.environment)throw Error('delivery_environment_changed_during_export');
    // The official exporter may create bound reports. Store the resulting
    // dependency version so unchanged retries can reuse its current output.
    const afterKey=digest({project:args.project,manifest:args.manifest,profile,dependencies:after,ruleVersions});
    const previous=existsSync(history)?JSON.parse(readFileSync(history,'utf8')):null;
    const progress=deliveryProgress(previous,result);
    const receipt={...result,key:afterKey,delivery_id:randomUUID(),dependencies:after,project:args.project,manifest:args.manifest,profile,reused_checks:false,
     convergence_status:progress.status,next_action:progress.next_action};
    if(result.mechanical_status==='passed'&&!verifiedArtifacts(task,receipt))throw Error('delivery_artifacts_changed');
    if(result.mechanical_status==='passed')for(const page of result.page_receipts??[]){
     appendFileSync(join(task.output,'ppt-native-pages.jsonl'),JSON.stringify({call_id:execution.callId,
      arguments_sha256:digest(invocationArguments),native_path:page.source,sha256:page.source_sha256,
      mode:'native_managed_delivery_source',delivery_id:receipt.delivery_id})+'\n',{mode:0o600});
    }
    const target=join(folder,afterKey+'.json'),temp=target+'.'+randomUUID()+'.tmp';
    writeFileSync(temp,JSON.stringify(receipt),{mode:0o600,flag:'wx'});renameSync(temp,target);
    const historyTemp=history+'.'+randomUUID()+'.tmp';writeFileSync(historyTemp,JSON.stringify(receipt),{mode:0o600,flag:'wx'});renameSync(historyTemp,history);
    for(const repair of result.applied_font_rules??[]){
     appendFileSync(join(task.output,'ppt-delivery-audit.jsonl'),JSON.stringify({kind:'ppt_font_rule_used',task_id:task.request.task_id,
      delivery_id:receipt.delivery_id,...repair,model_requests_skipped_verified:0})+'\n',{mode:0o600});
    }
    return receipt;
   }finally{locks.delete(task.workspace);}
  }});
}

/** Match immutable native present bytes against host-owned export receipts. */
export function recordPptDeliveryReuse(task:any,files:any[]){
 const receipts=join(task.output,'ppt-delivery-receipts');
 const audit=join(task.output,'artifact-motif-audit.jsonl');
 if(!existsSync(receipts)||!existsSync(audit))return;
 const events=readFileSync(audit,'utf8').split('\n').filter(Boolean).map(line=>JSON.parse(line));
 const executions=events.filter(row=>row.kind==='component_executed');
 const history=readdirSync(receipts).filter(name=>/^[a-f0-9]{64}\.json$/.test(name)).map(name=>JSON.parse(readFileSync(join(receipts,name),'utf8')));
 for(const receipt of history){
  if(receipt.mechanical_status!=='passed'||!receipt.artifacts.some((a:any)=>a.path.endsWith('.pptx')&&files.some(f=>f.sha256===a.sha256)))continue;
  for(const page of receipt.page_receipts??[]){
   const versions=new Set([page.source_sha256,page.source_initial_sha256].filter(Boolean));
   // A failed export can still repair annotations before returning a different
   // defect. Follow only host-proven, non-rendering repairs across those runs.
   let size;
   do{
    size=versions.size;
    for(const previous of history.filter(row=>row.project===receipt.project))for(const repair of previous.applied_annotation_repairs??[]){
     if(repair.source===page.source&&repair.operation==='module_annotations_only_v1'&&
        /^[a-f0-9]{64}$/.test(repair.before_sha256??'')&&/^[a-f0-9]{64}$/.test(repair.after_sha256??'')&&versions.has(repair.after_sha256))
      versions.add(repair.before_sha256);
    }
   }while(versions.size!==size);
   const execution=executions.find(row=>row.receipt?.files?.some((f:any)=>f.path==='page.svg'&&
    versions.has(f.sha256)));
   if(!execution||events.some(row=>row.kind==='component_used_in_delivery'&&row.delivery_id===receipt.delivery_id&&row.page===page.page))continue;
   const row={kind:'component_used_in_delivery',program_id:execution.program_id,delivery_id:receipt.delivery_id,page:page.page,
    source_sha256:page.source_sha256,pptx:receipt.artifacts.find((a:any)=>a.path.endsWith('.pptx'))};
   appendFileSync(audit,JSON.stringify(row)+'\n',{mode:0o600});events.push(row);
   task.stats.component_used_in_delivery=Number(task.stats.component_used_in_delivery??0)+1;
  }
 }
}

/** A model cannot publish a stale export after changing its editable source. */
export function validatePptPublication(task:any,files:any[],resources:any={}){
 const generated=hasGenerateProject(task);
 const folder=join(task.output,'ppt-delivery-receipts');
 if(!generated&&!existsSync(folder))return;
 const receipts=existsSync(folder)?readdirSync(folder).filter(name=>/^[a-f0-9]{64}\.json$/.test(name)).flatMap(name=>{
  try{
   const file=join(folder,name),stat=lstatSync(file);
   if(stat.isSymbolicLink()||stat.nlink!==1)return [];
   const row=JSON.parse(readFileSync(file,'utf8'));
   if(row.mechanical_status!=='passed'||!verifiedArtifacts(task,row)||
      digest(row.dependencies)!==digest(deliveryDependencies(task.workspace,row.project,row.manifest??row.project+'/delivery.json',resources)))return [];
   return [row];
  }catch{return [];}
 }):[];
 for(const file of files){
  if(!/\.(?:pptx|pdf|png)$/i.test(file.path??''))continue;
  try{
   const path=workspacePath(task.workspace,file.path),version=sha(readFileSync(path));
   if(receipts.some(row=>row.artifacts.some((artifact:any)=>artifact.sha256===version)))continue;
  }catch{/* A native filesystem guard will also reject invalid paths. */}
  return '此Generate交付缺少与当前源文件匹配的成功finalize_ppt回执。请修复回执中的明确问题并通过finalize_ppt后，交付其返回文件。';
 }
}
