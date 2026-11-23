/** Shared, version-bound export for Generate projects in an owning PPT task. */
import {spawn} from 'node:child_process';
import {appendFileSync,existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,realpathSync,renameSync,writeFileSync} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import {basename,dirname,isAbsolute,join,posix,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {commandArgv,commandLayout} from '../../geneloop_shell.ts';
import {officeEvidenceVersion} from '../../geneloop_presentation.ts';
import {digest} from '../../../motif_core/runtime/online_skill_runtime.mjs';
import {deliveryProgress} from './ppt_delivery_state.ts';
import {pptDesignTool,pptStartTool,pptPageTool} from '../authoring/ppt_design.ts';
import {pptDeckBuildTool,pptDeckPatchTool} from '../authoring/ppt_deck_contract.ts';
import {offloadedImagePrefixCount} from '@deepseek-ai/dsh-llm';
import {resolveRequestImagePolicy} from '@deepseek-ai/dsh-llm-deepseek';
import {pptAssetBudget} from './ppt_asset_budget.ts';
import {pptLiteralEdit,verifiedLiteralPptEdits} from '../authoring/ppt_input_policy.ts';

const sha=(bytes:any)=>createHash('sha256').update(bytes).digest('hex');
const source=(name:string)=>readFileSync(new URL(name,import.meta.url),'utf8');
const locks=new Set<string>();
/** Freeze eligible delivered source bytes before a later chat turn edits them. */
export function recordPptDeliverySources(task:any,receipt:any,execution:any,args:any){
 for(const page of receipt.page_receipts??[]){
  if(task.request?.learning_eligible!==false){
   const source=workspacePath(task.workspace,page.source);
   if(lstatSync(source).size<=100_000){
    const raw=readFileSync(source);
    if(sha(raw)!==page.source_sha256)throw Error('ppt_learning_delivery_source_changed');
    const directory=join(task.output,'reuse-evidence');mkdirSync(directory,{recursive:true,mode:0o700});
    const target=join(directory,page.source_sha256);
    if(existsSync(target)){
     if(lstatSync(target).isSymbolicLink()||sha(readFileSync(target))!==page.source_sha256)throw Error('ppt_learning_source_snapshot_changed');
    }else writeFileSync(target,raw,{flag:'wx',mode:0o400});
   }
  }
  appendFileSync(join(task.output,'ppt-native-pages.jsonl'),JSON.stringify({call_id:execution.callId,
   arguments_sha256:digest(args),native_path:page.source,sha256:page.source_sha256,
   mode:'native_managed_delivery_source',delivery_id:receipt.delivery_id})+'\n',{mode:0o600});
 }
}

/** Training evidence is optional; delivery checks above remain authoritative. */
export function capturePptLearningSources(task:any,receipt:any,execution:any,args:any){
 try{recordPptDeliverySources(task,receipt,execution,args);return true;}
 catch(error){
  (task.stats??(task.stats={})).ppt_learning_capture_failed=true;
  try{appendFileSync(join(task.output,'ppt-delivery-audit.jsonl'),JSON.stringify({kind:'ppt_learning_source_capture_failed',
   delivery_id:receipt.delivery_id,reason:String((error as Error).message).slice(0,200)})+'\n',{mode:0o600});}catch{}
  return false;
 }
}
export const pptPreparationTool={name:'prepare_ppt',
 description:'在内容与设计规范写好后校准字体。输入/work/projects内project，宿主按spec_lock.md和design_spec.md测量常规/粗体角色，核验实际字体并缓存同版本结果。制作时使用返回的normal/bold测量表。',
 parameters:{type:'object',properties:{project:{type:'string'}},required:['project'],additionalProperties:false}};
export const pptDeliveryTool={name:'finalize_ppt',
 description:'导出已完成设计与来源核对的Generate项目。只需输入project，宿主按svg_output文件名顺序生成页面清单。也可提供manifest，pages列出{source:"svg_output/slide_01.svg"}，备注放项目notes/。统一检查、可编辑PPTX导出、PDF/PNG渲染，同版本复用检查。若已返回图片，直接查看；仅对review_pages中尚未返回的图片调用read_image。随后直接present返回的artifacts，不必复制改名或再次检查原生对象。',
 parameters:{type:'object',properties:{project:{type:'string'},manifest:{type:'string'},profile:{type:'string'}},required:['project'],additionalProperties:false}};
export const pptPreviewTool={name:'inspect_ppt_region',
 description:'按需看一页上传的PDF，传path=/work/inputs/文件名.pdf及source_page（从1开始）；图片可用于核对本页图表。或对当前成品的PNG做局部放大，crop为原图像素left/top/right/bottom，scale为1至4。均返回图片，不修改稿件。只读需要的页面或区域，已查看同版本无需再检查。',
 parameters:{type:'object',properties:{path:{type:'string'},source_page:{type:'integer'},crop:{type:'object',properties:{left:{type:'integer'},top:{type:'integer'},right:{type:'integer'},bottom:{type:'integer'}},required:['left','top','right','bottom'],additionalProperties:false},scale:{type:'integer',enum:[1,2,3,4]}},required:['path'],additionalProperties:false}};

export const pptNativeEditTool={name:'edit_ppt_native',
 description:'直接编辑原生PPTX的文字、字号或段落对齐。附件上下文已有native_edit_targets时直接operation=apply，传source_sha256及edits；没有目标信息时才operation=inspect。每项指定page、shape_id、expected_text及action（replace_text另传text，set_alignment另传alignment，set_font_size另传font_size_pt）。保留非目标部件，返回可编辑PPTX、PDF和PNG；宿主确认完成时无需另调用present。',
 parameters:{type:'object',properties:{operation:{type:'string',enum:['inspect','apply']},source:{type:'string'},source_sha256:{type:'string'},
  edits:{type:'array',maxItems:500,items:{type:'object',properties:{page:{type:'integer'},shape_id:{type:'integer'},expected_text:{type:'string'},
   action:{type:'string',enum:['replace_text','set_alignment','set_font_size']},text:{type:'string'},alignment:{type:'string',enum:['left','center','right']},font_size_pt:{type:'number'}},
   required:['page','shape_id','expected_text','action'],additionalProperties:false}}},required:['operation','source'],additionalProperties:false}};

export const pptAssetTool={name:'prepare_ppt_asset',description:'准备已有PPT图片素材：将本会话/work或/tmp的PNG/JPEG/WebP安全复制、裁剪或等比缩放到project/images，保留源图SHA，不修改页面。crop是源图像素left/top/right/bottom；width可选，最大4096。不需要写Python或Bash图像脚本。',
 parameters:{type:'object',properties:{source:{type:'string'},project:{type:'string'},width:{type:'integer'},
  crop:{type:'object',properties:{left:{type:'integer'},top:{type:'integer'},right:{type:'integer'},bottom:{type:'integer'}},required:['left','top','right','bottom'],additionalProperties:false}},required:['source','project'],additionalProperties:false}};

const exporterCommand=/(?:^|[;&|\n(])\s*(?:[^\s;&|]*\/)?python(?:3(?:\.\d+)?)?\s+(?:-(?:I|B|u)\s+)*["']?(?:\/opt\/geneloop\/ppt-master|\$\{?[a-zA-Z_][a-zA-Z0-9_]*\}?)\/scripts\/svg_to_pptx\.py["']?\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))/;
export function managedDefaultExport(command:unknown){
 if(typeof command!=='string'||/--roundtrip|\s--help(?:\s|$)/.test(command))return false;
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

/** Only a complete, literal Generate command can be continued without a shell. */
export function directManagedProject(command:unknown){
 if(typeof command!=='string')return null;
 const match=/^\s*(?:python|python3)\s+["']?\/opt\/geneloop\/ppt-master\/scripts\/svg_to_pptx\.py["']?\s+(?:"(\/work\/projects\/[\w\/-]+)"|'(\/work\/projects\/[\w\/-]+)'|(\/work\/projects\/[\w\/-]+))(?:\s+--(?:with-notes|no-animations))*\s*$/.exec(command);
 return match?.[1]??match?.[2]??match?.[3]??null;
}

export function pptDeliveryScene(scene:any,enabled:boolean){
 if(!enabled||scene.id!=='ppt'||scene.ppt_execution_strategy!=='ppt_master')return scene;
 return {...scene,allowed_tools:[...new Set([...scene.allowed_tools,pptPreparationTool.name,pptDeliveryTool.name,pptPreviewTool.name,pptNativeEditTool.name,pptAssetTool.name,pptDesignTool.name,pptStartTool.name,pptPageTool.name,pptDeckBuildTool.name,pptDeckPatchTool.name])]};
}

export function pptDeliveryGraphTools(scene:any,tools:any[]){
 const names=[pptDeliveryTool,pptPreparationTool,pptPreviewTool,pptNativeEditTool,pptAssetTool,pptDesignTool,pptStartTool,pptPageTool,pptDeckBuildTool,pptDeckPatchTool];
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

/** Conversation source versions, excluding generated previews and reports. */
export function pptSourceState(workspace:string){
 const root=join(workspace,'code/projects'),versions:Record<string,string>={};
 if(!existsSync(root))return versions;
 if(lstatSync(root).isSymbolicLink()||realpathSync(root)!==resolve(root))throw Error('ppt_sources_changed');
 for(const name of readdirSync(root).sort()){
  const project=join(root,name),stat=lstatSync(project);
  if(stat.isSymbolicLink()||!stat.isDirectory())continue;
  const files:any[]=[];
  const add=(file:string)=>{
   const s=lstatSync(file);if(s.isSymbolicLink()||!s.isFile()||s.nlink!==1||s.size>30_000_000||files.length>=4096)throw Error('ppt_sources_changed');
   files.push([relative(project,file).split('\\').join('/'),sha(readFileSync(file))]);
  };
  for(const file of ['geneloop-project.json','geneloop-deck.json','deck.json','spec_lock.md','design_spec.md','delivery.json'])if(existsSync(join(project,file)))add(join(project,file));
  for(const folder of ['svg_output','notes']){
   const dir=join(project,folder);if(!existsSync(dir))continue;
   if(lstatSync(dir).isSymbolicLink()||!lstatSync(dir).isDirectory())throw Error('ppt_sources_changed');
   for(const file of readdirSync(dir).sort())if(/\.(svg|md)$/.test(file))add(join(dir,file));
  }
  if(files.length)versions['/work/projects/'+name]=digest(files);
 }
 return versions;
}

/** Check only the registered manuscript inputs, not the exporter or its reports.
 * Export/cache certification still uses deliveryDependencies at finalize_ppt.
 * At delivery, changed source bytes or page membership invalidate the export;
 * scratch files, generated diagnostics and runtime upgrades do not rewrite it.
 */
function currentManuscript(task:any,row:any){
 if(row.kind==='ppt_native_json_v1'){
  const ref=row.deck_source;
  if(!ref||ref.path!==row.project+'/deck.json'||ref.pptx_path!==row.project+'/deck.pptx'||!Array.isArray(row.dependencies?.files))return false;
  const document=JSON.parse(readFileSync(workspacePath(task.workspace,ref.path),'utf8'));
  return document.revision===row.revision&&document.artifacts?.pptx===ref.pptx_sha256&&
   sha(readFileSync(workspacePath(task.workspace,ref.path)))===ref.sha256&&
   sha(readFileSync(workspacePath(task.workspace,ref.pptx_path)))===ref.pptx_sha256&&
   row.dependencies.files.every((file:any)=>['deck.json','geneloop-deck.json'].includes(file.path)&&
    sha(readFileSync(workspacePath(task.workspace,row.project+'/'+file.path)))===file.sha256);
 }
 if(row.kind==='ppt_native_edit_v1'){
  const ref=row.native_source;
  if(!ref||typeof ref.path!=='string'||!ref.path.startsWith('/work/')||!/^[a-f0-9]{64}$/.test(ref.sha256))return false;
  return sha(readFileSync(workspacePath(task.workspace,ref.path)))===ref.sha256;
 }
 const project=row.project,files=row.dependencies?.files;
 if(typeof project!=='string'||!project.startsWith('/work/projects/')||!Array.isArray(files)||!files.length)return false;
 const manifest=row.manifest??project+'/delivery.json';
 const total=JSON.parse(readFileSync(workspacePath(task.workspace,manifest),'utf8')).notes_source==='total';
 const directory=workspacePath(task.workspace,project),inventory:string[]=[];
 const relevant=(path:string)=>path===manifest.slice(project.length+1)||
  ['spec_lock.md','design_spec.md','geneloop-project.json'].includes(path)||
  path.startsWith('svg_output/')&&path.endsWith('.svg')||
  path.startsWith('notes/')&&path.endsWith('.md')&&(!total||basename(path)==='total.md');
 for(const name of new Set([manifest.slice(project.length+1),'spec_lock.md','design_spec.md','geneloop-project.json'])){
  if(existsSync(join(directory,name)))inventory.push(name);
 }
 const visit=(folder:string)=>{
  const host=join(directory,folder);if(!existsSync(host))return;
  const stat=lstatSync(host);if(stat.isSymbolicLink()||!stat.isDirectory()||realpathSync(host)!==resolve(host))throw Error('delivery_source_changed');
  for(const leaf of readdirSync(host)){
   const key=folder+'/'+leaf,path=join(directory,key),s=lstatSync(path);
   if(s.isSymbolicLink()||inventory.length>=4096)throw Error('delivery_source_changed');
   if(s.isDirectory())visit(key);else if(relevant(key))inventory.push(key);
  }
 };
 visit('svg_output');visit('notes');
 if(digest(inventory.sort())!==digest(files.map((file:any)=>file.path).filter(relevant).sort()))return false;
 return files.filter((file:any)=>!file.path.startsWith('validation/')).every((file:any)=>{
  const logical=file.path.startsWith('@asset:')?file.path.slice(7):project+'/'+file.path;
  const path=workspacePath(task.workspace,logical),stat=lstatSync(path);
  return stat.isFile()&&stat.size<=30_000_000&&sha(readFileSync(path))===file.sha256;
 });
}

function currentPptReceipts(task:any,_resources:any={}){
 const folder=join(task.output,'ppt-delivery-receipts');
 if(!existsSync(folder))return [];
 if(lstatSync(folder).isSymbolicLink()||!lstatSync(folder).isDirectory()||realpathSync(folder)!==resolve(folder))return [];
 const names=readdirSync(folder),registered=new Set(names.filter(name=>/^current-[a-f0-9]{64}\.json$/.test(name)));
 return names.filter(name=>/^(?:current-)?[a-f0-9]{64}\.json$/.test(name)).flatMap(name=>{
  try{
   const path=join(folder,name),s=lstatSync(path);if(s.isSymbolicLink()||!s.isFile()||s.nlink!==1)return [];
   const row=JSON.parse(readFileSync(path,'utf8'));
   const registration='current-'+digest(row.project)+'.json';
   if(registered.has(registration)&&name!==registration||name.startsWith('current-')&&name!==registration)return [];
   return row.mechanical_status==='passed'&&currentManuscript(task,row)?[row]:[];
  }catch{return [];}
 });
}

/** A current complete host export can be returned without another model present. */
export function pptReadyDelivery(task:any,resources:any={}){
 const rows=currentPptReceipts(task,resources).filter(row=>verifiedArtifacts(task,row)&&Array.isArray(row.page_receipts)&&
  row.page_receipts.length>0&&['.pptx','.pdf'].every(ext=>row.artifacts.some((a:any)=>a.path.endsWith(ext)))&&
  row.artifacts.filter((a:any)=>a.path.endsWith('.png')).length>=row.page_receipts.length);
 const selected=task.stats?.ppt_last_delivered_project;
 if(typeof selected==='string')return rows.filter(row=>row.project===selected);
 const projects=new Set(rows.map(row=>row.project));
 return projects.size===1?rows:[];
}

function registerCurrentPptReceipt(task:any,receipt:any){
 if(receipt.mechanical_status!=='passed')return;
 const target=join(task.output,'ppt-delivery-receipts','current-'+digest(receipt.project)+'.json');
 const temp=target+'.'+randomUUID()+'.tmp';
 writeFileSync(temp,JSON.stringify(receipt),{mode:0o600,flag:'wx'});renameSync(temp,target);
}

/** Native JSON and SVG share the same current-artifact publication checks. */
export function acceptPptDeckReceipt(task:any,receipt:any){
 if(receipt.kind!=='ppt_native_json_v1'||receipt.mechanical_status!=='passed'||!currentManuscript(task,receipt)||!verifiedArtifacts(task,receipt))
  throw Error('ppt_deck_delivery_not_current');
 const folder=join(task.output,'ppt-delivery-receipts');mkdirSync(folder,{recursive:true,mode:0o700});
 const path=join(folder,receipt.key+'.json'),temp=path+'.'+randomUUID()+'.tmp';
 writeFileSync(temp,JSON.stringify(receipt),{mode:0o600,flag:'wx'});renameSync(temp,path);
 registerCurrentPptReceipt(task,receipt);(task.stats??={}).ppt_last_delivered_project=receipt.project;
}

/** Only host-produced crops of a still-current export can be published. */
function currentPptPreviewHashes(task:any,receipts:any[]){
 const folder=join(task.output,'ppt-preview-receipts'),hashes=new Set<string>();
 if(!existsSync(folder)||lstatSync(folder).isSymbolicLink()||!lstatSync(folder).isDirectory()||realpathSync(folder)!==resolve(folder))return hashes;
 for(const name of readdirSync(folder).filter(name=>/^[a-f0-9-]{36}\.json$/.test(name))){
  try{
   const path=join(folder,name),stat=lstatSync(path);
   if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>64000)continue;
   const row=JSON.parse(readFileSync(path,'utf8'));
   if(row.kind!=='ppt_preview_v1'||!task.request?.task_id||row.task_id!==task.request.task_id)continue;
   const source=receipts.find(receipt=>receipt.delivery_id===row.delivery_id&&digest(receipt.dependencies)===row.dependencies_sha256&&
    receipt.artifacts.some((artifact:any)=>artifact.path===row.source_path&&artifact.sha256===row.source_sha256&&artifact.path.endsWith('.png')));
   if(!source||!row.preview?.path?.endsWith('.png')||!verifiedArtifacts(task,{artifacts:[row.preview]}))continue;
   hashes.add(row.preview.sha256);
  }catch{/* Invalid or stale preview evidence grants no publication. */}
 }
 return hashes;
}

/** Starting a deck requires a current host export; pure discussion stays text-only. */
export function pptTaskAcceptance(task:any,resources:any={}){
 if(task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true)
  return {required:false,passed:true};
 try{
  const state=pptSourceState(task.workspace),before=task.ppt_initial_sources??{};
  const changed=Object.keys({...before,...state}).filter(project=>state[project]!==before[project]);
  const required=!!task.stats?.ppt_work_started||changed.length>0;
  if(!required)return {required:false,passed:true};
  const receipts=currentPptReceipts(task,resources).filter(row=>verifiedArtifacts(task,row)&&Array.isArray(row.page_receipts)&&row.page_receipts.length>0&&
   ['.pptx','.pdf'].every(ext=>row.artifacts.some((a:any)=>a.path.endsWith(ext)))&&
   row.artifacts.filter((a:any)=>a.path.endsWith('.png')).length>=row.page_receipts.length);
  if(receipts.length&&changed.every(project=>receipts.some(row=>row.project===project)))
   return {required:true,passed:true,delivery_ids:receipts.map(row=>row.delivery_id)};
  return {required:true,passed:false,reason:'ppt_delivery_not_delivered'};
 }catch{return {required:true,passed:false,reason:'ppt_delivery_unverifiable'};}
}

/** Return the host's current export even when the model omits its final present call. */
export function pptCurrentDeliveryFiles(task:any,resources:any={}):Map<string,string>{
 const accepted=pptTaskAcceptance(task,resources);
 if(!accepted.required||!accepted.passed)return new Map();
 const rows=currentPptReceipts(task,resources).filter(row=>accepted.delivery_ids?.includes(row.delivery_id));
 const priority=(path:string)=>path.endsWith('.pptx')?0:path.endsWith('.pdf')?1:2;
 return new Map(rows.flatMap(row=>row.artifacts).sort((a:any,b:any)=>priority(a.path)-priority(b.path))
  .map((a:any)=>[workspacePath(task.workspace,a.path),a.sha256]));
}

export function deliveryDependencies(workspace:string,project:string,manifest:string,resources:any={}){
 if(!project.startsWith('/work/projects/'))throw Error('delivery_project_required');
 const directory=workspacePath(workspace,project);
 if(!lstatSync(directory).isDirectory())throw Error('delivery_project_required');
 const manifestPath=workspacePath(workspace,manifest);
 if(!manifest.startsWith(project+'/')||!lstatSync(manifestPath).isFile())throw Error('delivery_manifest_outside_project');
 const files:any[]=[];
 const notesFromTotal=JSON.parse(readFileSync(manifestPath,'utf8')).notes_source==='total';
 const manifestRelative=relative(directory,manifestPath).split('\\').join('/');
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
   const relevant=logicalPath===manifestRelative||['spec_lock.md','design_spec.md','geneloop-project.json'].includes(logicalPath)||
    logicalPath.startsWith('svg_output/')&&logicalPath.endsWith('.svg')||
    logicalPath.startsWith('notes/')&&logicalPath.endsWith('.md')||
    logicalPath.startsWith('validation/')&&/\.(json|md)$/.test(logicalPath);
   if(!relevant)continue;
   if(!stat.isFile()||stat.nlink!==1||files.length>=4096||(bytes+=stat.size)>200_000_000)throw Error('delivery_dependency_protocol_bound');
   files.push({path:logicalPath,sha256:sha(readFileSync(file))});
  }
 };
 visit(directory);
 for(let index=0;index<files.length;index++){
  const row=files[index];
  if(!row.path.endsWith('.svg'))continue;
  const rowLogical=row.path.startsWith('@asset:')?row.path.slice(7):project+'/'+row.path;
  const text=readFileSync(workspacePath(workspace,rowLogical),'utf8');
  for(const match of text.matchAll(/(?:xlink:)?href\s*=\s*["']([^"']+)["']/g)){
   const reference=match[1];
   if(reference.startsWith('#')||reference.startsWith('data:'))continue;
   if(/^[a-z]+:/i.test(reference)||reference.includes('&'))throw Error('delivery_asset_reference_unsupported');
   const logical=posix.resolve(posix.dirname(rowLogical),reference);
   const key=logical.startsWith(project+'/')?logical.slice(project.length+1):'@asset:'+logical;
   if(files.some(file=>file.path===key))continue;
   if(!/\.(png|jpe?g|gif|webp|svg)$/i.test(logical))throw Error('delivery_external_asset_unsupported');
   const asset=workspacePath(workspace,logical),stat=lstatSync(asset);
   if(!stat.isFile()||stat.nlink!==1||stat.size>30_000_000)throw Error('delivery_asset_changed');
   if(files.length>=4096||(bytes+=stat.size)>200_000_000)throw Error('delivery_dependency_protocol_bound');
   files.push({path:key,sha256:sha(readFileSync(asset))});
  }
 }
 const profileBytes=readFileSync(new URL('../../../../scenarios/ppt_master/design-profiles.json',import.meta.url));
 return {files,environment:officeEvidenceVersion(resources),profile_sha256:sha(profileBytes),
  runner_sha256:sha(source('./ppt_delivery_runner.py')),preflight_sha256:sha(source('../authoring/ppt_design_preflight.py')),
  annotation_repair_sha256:sha(source('../learning/ppt_annotation_repair.py')),
  pipeline_sha256:sha(source('./ppt_delivery_pipeline.ts')),
  preparation_sha256:sha(source('./ppt_preparation_runner.py')),
  runtime_policy_sha256:sha(readFileSync(new URL('../../../../scenarios/ppt_master/runtime-policy.md',import.meta.url))),
  state_sha256:sha(source('./ppt_delivery_state.ts'))};
}

export function pptPreparationView(value:any){
 return {status:value.status,reused_calibration:value.reused_calibration,normal:value.normal,bold:value.bold,
  glyph_review:value.glyph_review,next_action:value.next_action,evidence_id:value.key};
}
export function pptDeliveryView(value:any){
 return {delivery_id:value.delivery_id,project:value.project,mechanical_status:value.mechanical_status,
  review_status:value.review_status,reused_checks:value.reused_checks,convergence_status:value.convergence_status,
  next_action:value.next_action,retryable:value.retryable,findings:value.findings,artifacts:value.artifacts,review_pages:value.review_pages,
  pages:(value.page_receipts??[]).map((row:any)=>({page:row.page,source:row.source,source_sha256:row.source_sha256})),
  stage_logs:(value.commands??[]).map((row:any)=>({stage:row.stage,exit_code:row.exit_code,log:row.log}))};
}

export function pptReviewPages(task:any,receipt:any){
 const seen=new Set<string>();
 for(const journal of visualObservationJournals(task))if(existsSync(journal))for(const line of readFileSync(journal,'utf8').split('\n')){
  try{
   const row=JSON.parse(line);
   if(row.scope==='tool_returned_bound_image_quality_unknown'&&/^[a-f0-9]{64}$/.test(row.sha256))seen.add(row.sha256);
  }catch{/* An interrupted journal append supplies no observation evidence. */}
 }
 return (receipt.artifacts??[]).flatMap((row:any)=>{
  if(!row.path.endsWith('.png')||seen.has(row.sha256))return [];
  seen.add(row.sha256);
  return [{path:row.path,sha256:row.sha256}];
 });
}

function visualObservationJournals(task:any){
 // The workspace is the same conversation's private workspace, never a global
 // user pool. Exact image bytes may survive a title/notes-only follow-up.
 return [join(task.output,'ppt-visual-observations.jsonl'),
  ...(basename(dirname(task.output))==='tasks'?[join(dirname(dirname(task.output)),'ppt-visual-observations',digest({workspace:task.workspace})+'.jsonl')]:[])];
}

export function pptImageInModel(task:any,artifact:any,images:Set<string>){
 if(images.has('sha256:'+artifact.sha256))return true;
 for(const journal of visualObservationJournals(task))if(existsSync(journal))for(const line of readFileSync(journal,'utf8').split('\n')){
  try{const row=JSON.parse(line);if(row.scope==='tool_returned_bound_image_quality_unknown'&&row.sha256===artifact.sha256&&images.has(row.attachment_id))return true;}catch{/* Interrupted append. */}
 }
 return false;
}

/** Reuse exposure, not a visual pass/fail verdict; never alter durable history. */
export function reusePptImages(content:any[],modelImages:Set<string>){
 const seen=new Set(modelImages);
 return content.map((part:any)=>{
  const id=part.type==='image'?part.attachment?.attachmentId:undefined;
  if(!id)return part;
  if(seen.has(id))return {type:'text',text:`[相同图片 ${id} 已在本次结果或当前模型上下文中提供，此回执不代表质量通过。]`};
  seen.add(id);
  return part;
 });
}

export async function recordPptVisualObservation(task:any,execution:any,result:any,attachments?:any){
 const image=result?.content?.find((row:any)=>row.type==='image');
 if(execution.name!=='read_image'||result?.isError||!image)return;
 const logical=execution.arguments?.file_path??execution.arguments?.path;
 try{
  if(typeof logical!=='string'||!logical.startsWith('/work/outputs/')||!logical.endsWith('.png'))return;
  const path=workspacePath(task.workspace,logical);
  const raw=readFileSync(path),version=sha(raw),reference=image.attachment??result.value?.image;
  if(!/^sha256:[a-f0-9]{64}$/.test(reference?.attachmentId??''))return;
  if(reference.attachmentId!=='sha256:'+version){
   if(!attachments?.saveImage)return;
   const normalized=await attachments.saveImage({data:raw,mediaType:'image/png',name:posix.basename(logical)});
   if(normalized.attachmentId!==reference.attachmentId)return;
  }
  const row=JSON.stringify({call_id:execution.callId,path:logical,
   sha256:version,attachment_id:reference.attachmentId,scope:'tool_returned_bound_image_quality_unknown'})+'\n';
  for(const journal of visualObservationJournals(task)){
   mkdirSync(dirname(journal),{recursive:true,mode:0o700});appendFileSync(journal,row,{mode:0o600});
  }
 }catch{/* An invalid image path supplies no observation evidence. */}
}

export async function runPptInSession(task:any,request:any,resources:any,signal?:AbortSignal){
 const code=['preview','asset','source_preview'].includes(request.operation)?source('../sources/ppt_preview_runner.py'):['native_inspect','native_edit','native_render'].includes(request.operation)?source('../authoring/ppt_native_edit.py'):source('../authoring/ppt_design_preflight.py')+'\n'+(request.operation==='prepare'?source('./ppt_preparation_runner.py'):
  request.operation==='compose'?source('../authoring/ppt_page_renderer.py'):
  source('../learning/ppt_annotation_repair.py')+'\n'+source('./ppt_delivery_runner.py'));
 const script=Buffer.from(code).toString('base64');
 const encoded=Buffer.from(JSON.stringify(request)).toString('base64');
 const python=process.env.SSS_PYTHON??'/usr/bin/python3';
 if(!/^\/[a-zA-Z0-9_./-]+$/.test(python))throw Error('delivery_python_invalid');
 const command=python+` -I -B -c "import base64;exec(base64.b64decode('${script}'))" '${encoded}'`;
 const session=task.request.session_id;
 const socket=process.env.GENELOOP_COMMAND_SOCKET;
 const runRoot=dirname(dirname(task.output));
 if(!socket&&task.workspace!==join(runRoot,'sessions',session,'work'))throw Error('ppt_delivery_workspace_mismatch');
 const argv=socket?[process.execPath,fileURLToPath(new URL('../../geneloop_command_client.mjs',import.meta.url)),socket,
  Buffer.from(JSON.stringify({session,command,cwd:'/work',readOnly:false,network:'none'})).toString('base64url')]:
  commandArgv(commandLayout(runRoot,session),command,'/work',python,process.execPath,false,{...resources,network:'none'});
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

export function cachedPptDelivery(task:any,receipt:any,key:string){
 if(receipt.key!==key)return null;
 if(receipt.mechanical_status==='failed'&&receipt.retryable!==true)
  return {...receipt,reused_checks:true,convergence_status:'unchanged',next_action:'repair_specific_findings_before_rechecking'};
 if(receipt.mechanical_status!=='passed'||!verifiedArtifacts(task,receipt))return null;
 const review_pages=pptReviewPages(task,receipt);
 return {...receipt,reused_checks:true,review_pages,next_action:review_pages.length?'read_image_for_review_pages':'present_current_delivery'};
}

export function registerPptDeliveryTool(ctx:any,current:(session:string)=>any,resources:any={},imageOptions?:()=>any){
 ctx.tools.register({...pptAssetTool,output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},async execute(args:any,execution:any){
  const task=current(execution?.agent?.session?.id)?.task;
  if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true)throw Error('asset_task_not_authorized');
  workspacePath(task.workspace,args.project+'/images');
  const value=await runPptInSession(task,{...args,operation:'asset',id:randomUUID()},resources,execution.signal);
  const target=workspacePath(task.workspace,value.path);
  if(sha(readFileSync(target))!==value.sha256)throw Error('asset_result_changed');
  return value;
 }});
 ctx.tools.register({...pptNativeEditTool,output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any,execution:any){
   const task=current(execution?.agent?.session?.id)?.task;
   if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true)
    throw Error('native_edit_task_not_authorized');
   if(!['inspect','apply'].includes(args.operation)||typeof args.source!=='string'||!args.source.startsWith('/work/')||!args.source.toLowerCase().endsWith('.pptx'))
    throw Error('native_edit_arguments_invalid');
   const original=workspacePath(task.workspace,args.source),version=sha(readFileSync(original));
   if(args.source_sha256!==undefined&&args.source_sha256!==version)throw Error('native_source_version_changed');
   if(args.operation==='apply'&&args.source_sha256!==version)throw Error('native_source_sha256_required_use_inspect');
   const output='/work/outputs/ppt-native-'+randomUUID();
   const intent=pptLiteralEdit(task);
   const literal=intent&&args.operation==='apply'&&verifiedLiteralPptEdits(intent,args.edits)&&
    args.source==='/work/inputs/'+task.scene_inputs[0].file&&version===task.scene_inputs[0].version_sha256;
   const value=await runPptInSession(task,{operation:args.operation==='inspect'?'native_inspect':'native_edit',
    source:args.source,source_sha256:version,edits:args.edits,output,
    ...(literal?{literal_targets:intent.replacements.map(({before})=>({page:intent.page,text:before}))}:{})},resources,execution.signal);
   if(args.operation==='inspect')return value;
   if(value.mechanical_status!=='passed')return {...value,next_action:'repair_reported_native_error_preserve_original'};
   execution.signal?.throwIfAborted();
   if(sha(readFileSync(original))!==version||!verifiedArtifacts(task,value))throw Error('native_delivery_changed');
   const close=literal&&value.unambiguous_text_targets===true&&value.unselected_parts_preserved===true&&
    value.rendered_replacements_verified===true;
   const receipt={...value,kind:'ppt_native_edit_v1',project:output,delivery_id:randomUUID(),
    native_source:{path:args.source,sha256:version},dependencies:{files:[],environment:officeEvidenceVersion(resources)},
    review_pages:close?[]:pptReviewPages(task,value)};
   receipt.key=digest({source:receipt.native_source,edits:args.edits,artifacts:receipt.artifacts});
   const folder=join(task.output,'ppt-delivery-receipts');mkdirSync(folder,{recursive:true,mode:0o700});
   writeFileSync(join(folder,receipt.key+'.json'),JSON.stringify(receipt),{mode:0o600,flag:'wx'});
   registerCurrentPptReceipt(task,receipt);task.stats.ppt_last_delivered_project=output;task.stats.ppt_work_started=true;
   if(close&&pptReadyDelivery(task,resources).some(row=>row.delivery_id===receipt.delivery_id)){
    execution.concludeTurn?.();
    return {...receipt,review_status:'rendered_literal_edits_verified',next_action:'current_delivery_ready'};
   }
   return {...receipt,next_action:'review_current_previews_then_deliver_no_svg_roundtrip'};
  }});
 const publicationNotes=new Map<symbol,string>();
 ctx.on?.('llm/stream',(request:any,next:any)=>{
  // Enter downstream authorization synchronously, as the native Runtime
  // requires. The returned stream remains lazy; pixels are prepared before
  // iteration reaches the provider. A denial must not become a delayed error.
  const downstream=next();
  return (async function*(){
  const value=current(request.sessionId);
  if(value?.task?.scene?.id==='ppt'){
   const images=new Set<string>(),references:any[]=[],loadedSkills:string[]=[];
   const walk=(blocks:any[])=>{for(const block of blocks??[]){
    if(block.type==='image'&&/^sha256:[a-f0-9]{64}$/.test(block.attachment?.attachmentId??''))references.push(block.attachment);
    if(block.type==='text'&&typeof block.text==='string'&&block.text.startsWith('<skill_content name="ppt-master">'))loadedSkills.push(block.text);
    if(block.type==='tool-result')walk(block.content);
   }};
   for(const message of request.messages??[])walk(message.content);
   // Public pricing covers first-stage offload only. Also resolve exact cached
   // request variants and both file/inline limits: Files API fallback must not
   // turn a nominal image occurrence into a fabricated observation.
   try{
    const options=imageOptions?.(),model=options?.models?.find((row:any)=>row.id===request.model);
    const pricing=ctx.get?.('llm')?.imageRequestPricing(request.provider,request.model);
    const prices=pricing?.priceImages(references);
    const store=ctx.get?.('attachments');
    const bounds=[options?.maxRequestFilesBytes,options?.maxInlineRequestImageBytes,options?.maxImagesPerRequest,
     options?.imageOffloadByteQuantum,options?.inlineImageOffloadByteQuantum,options?.imageOffloadCountQuantum];
    if(model&&store?.readImageRequest&&bounds.every(n=>Number.isSafeInteger(n)&&n>0)){
     const retained=references.filter((_ref,index)=>prices?.[index]?.visualTokens>0);
     const versions=new Map<string,any>();
     for(const ref of retained)if(!versions.has(ref.attachmentId))versions.set(ref.attachmentId,await store.readImageRequest(ref,resolveRequestImagePolicy(model),request.signal));
     const lengths=retained.map(ref=>versions.get(ref.attachmentId).bytes);
     const fileOffload=offloadedImagePrefixCount(lengths,{maxBytes:options.maxRequestFilesBytes,maxImages:options.maxImagesPerRequest,
      byteQuantum:options.imageOffloadByteQuantum,countQuantum:options.imageOffloadCountQuantum});
     const inlineOffload=offloadedImagePrefixCount(lengths.map(bytes=>4*Math.ceil(bytes/3)),{maxBytes:options.maxInlineRequestImageBytes,
      maxImages:options.maxImagesPerRequest,byteQuantum:options.inlineImageOffloadByteQuantum,countQuantum:options.imageOffloadCountQuantum});
     retained.slice(Math.max(fileOffload,inlineOffload)).forEach(ref=>images.add(ref.attachmentId));
    }
   }catch{/* Conservative fallback keeps all requested images. */}
   value.pptModelImages=images;
   value.pptLoadedSkillTexts=loadedSkills;
  }
  yield* downstream;
  })();
 },{global:true});
 ctx.on?.('tools/post-execute',async(execution:any,result:any,next:any)=>{
  let decision=await next();
  const note=publicationNotes.get(execution.token);publicationNotes.delete(execution.token);
  if(note&&decision.kind==='accept'&&!result.isError)
   decision={...decision,content:[...(decision.content??result.content??[]),{type:'text',text:note}]};
  const value=current(execution.agent?.session?.id);
  if(decision.kind!=='accept'||result.isError||!value?.pptModelImages||value.writeInternalCalls?.has(execution.callId))return decision;
  if(execution.name==='mcp__ppt_master__read_skill_entry'&&decision.content===undefined&&!Object.hasOwn(decision,'value')&&typeof result.value?.text==='string'&&
     result.value.text.length>0&&value.pptLoadedSkillTexts?.some((text:string)=>text.includes(result.value.text))){
   const {text,...entry}=result.value;
   return {...decision,content:[{type:'text',text:JSON.stringify({...entry,
    text_reused_from:'already_loaded_native_ppt_master_skill',text_sha256:sha(Buffer.from(text)),
    next_action:'use_already_loaded_identical_skill_and_current_source_catalog'})}]};
  }
  // Keep all original tool values and files. Only a later occurrence is a
  // reference; the original image-bearing message remains byte-for-byte intact.
  const content=decision.content??result.content;
  if(!content?.some((part:any)=>part.type==='image'))return decision;
  const projected=reusePptImages(content,value.pptModelImages);
  return projected.some((part,index)=>part!==content[index])?{...decision,content:projected}:decision;
 },{global:true});
 ctx.on?.('tools/execute',async(execution:any,next:any)=>{
  const project=execution.name==='bash'?directManagedProject(execution.arguments?.command):null;
  const task=current(execution.agent?.session?.id)?.task;
  if(execution.name==='present'&&task?.status==='running'&&task.scene?.id==='ppt'&&task.scene.ppt_execution_strategy==='ppt_master'){
   const plan=pptPublicationPlan(task,execution.arguments?.files??[],resources);
   if(plan.error)throw Error(plan.error);
   // Mark the owning native execution, not an authored result property: DSH
   // intentionally normalizes away wrapper-invented completion markers.
   if(['.pptx','.pdf'].every(ext=>plan.files.some((file:any)=>file.path.toLowerCase().endsWith(ext))))execution.concludeTurn?.();
   if(plan.omitted.length){
    if(typeof ctx.tools.execute!=='function')throw Error('ppt_delivery_dispatch_unavailable');
    appendFileSync(join(task.output,'ppt-delivery-audit.jsonl'),JSON.stringify({kind:'ppt_optional_preview_omitted',
     call_id:execution.callId,omitted:plan.omitted,model_requests_inside:0})+'\n',{mode:0o600});
    // Arguments are frozen by the native Runtime. Dispatch a real child call,
    // retaining cancellation/authorization and authoritative delivery events.
    const result=await ctx.tools.execute({name:'present',arguments:{...execution.arguments,files:plan.files},
     callId:execution.callId+':current-files',rootCallId:execution.rootCallId,parent:execution.token,
     agent:execution.agent,signal:execution.signal});
    if(result.isError)return result;
    publicationNotes.set(execution.token,'主稿已交付；以下附加预览未返回，不需要重做或重新导出PPT：'+plan.omitted.map((row:any)=>row.path).join('、'));
    return result;
   }
   const published=await next();
   return published;
  }
  if(!project||typeof ctx.tools.execute!=='function'||task?.status!=='running'||task.scene?.id!=='ppt'||
     task.scene?.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true)return next();
  workspacePath(task.workspace,project);
  const callId=execution.callId+':managed-delivery';
  appendFileSync(join(task.output,'ppt-delivery-audit.jsonl'),JSON.stringify({kind:'ppt_export_continued',
   call_id:execution.callId,arguments_sha256:digest(execution.arguments),child_call_id:callId,project})+'\n',{mode:0o600});
  const result=await ctx.tools.execute({name:'finalize_ppt',arguments:{project},callId,rootCallId:execution.rootCallId,
   parent:execution.token,agent:execution.agent,signal:execution.signal});
  if(result.isError)return result;
  if(result.concludesTurn)execution.concludeTurn?.();
  const view=pptDeliveryView(result.value);
  return {isError:false,...(result.concludesTurn?{concludesTurn:true}:{}),value:{kind:'foreground',exitCode:result.value.mechanical_status==='passed'?0:1,
   signal:null,timedOut:false,aborted:false,timeoutMs:900000,
   stdout:{text:JSON.stringify({continued_by:'finalize_ppt',...view}),truncated:false},stderr:{text:'',truncated:false}}};
 },{global:true});
 ctx.on?.('tools/result',async(execution:any,result:any)=>{
  publicationNotes.delete(execution.token);
  const task=current(execution.agent?.session?.id)?.task;
  if(task?.status==='running'&&task.scene?.id==='ppt')await recordPptVisualObservation(task,execution,result,ctx.get?.('attachments'));
 },{global:true});
 ctx.tools.guard?.((execution:any)=>{
  const session=execution.agent?.session?.id,task=current(session)?.task;
  if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene?.ppt_execution_strategy!=='ppt_master')return;
  const assetStop=pptAssetBudget(task,execution);
  if(assetStop)return assetStop;
  if(execution.name!=='bash')return;
  const command=execution.arguments?.command;
  if(typeof command==='string'&&command.includes('svg_output/')&&
     /(?:\bsvg2png\s*\(|\brsvg-convert\b|\binkscape\b[^\n]*--export|\b(?:magick|convert)\b[^\n]*\.svg)/.test(command)&&hasGenerateProject(task))
   return '项目页面的预览由finalize_ppt统一生成。请先完成页面与备注，再调用finalize_ppt并用read_image查看其Office渲染PNG；源码SVG的独立渲染和反复换DPI预览会引入字体与坐标差异。按具体finding或清楚可见的缺陷修订。';
  if(typeof command==='string'&&/python(?:3(?:\.\d+)?)?\s+[^;&|\n]*svg_quality_checker\.py/.test(command)&&
     !/\s--help\b/.test(command)&&hasGenerateProject(task))
   return 'Generate的官方检查由finalize_ppt统一执行。请先完成页面与讲者备注，然后调用finalize_ppt。宿主处理明确错误并保留原始报告，warning按当前画面与任务要求评估，避免逐条猜测式微调。';
  if(typeof command==='string'&&/(?:\bfc-(?:match|list|query)\b|\btext_measure\b|fontTools|pdffonts\b)/.test(command)&&!/(?:\s--help\b)/.test(command))
   return '字体解析与角色测量由prepare_ppt完成。使用该工具当前回执中的字体与normal/bold表制作；实际输出检查使用finalize_ppt。需要管理员处理的环境故障请保留具体错误。';
  if(typeof command==='string'&&command.includes('/work/outputs/')&&
     /(?:get_text\s*\(\s*["'](?:rawdict|dict|words)["']|get_bboxlog\s*\(|get_texttrace\s*\()/.test(command))
   return '成品的字符框、span和字体度量诊断由共同交付检查处理。使用finalize_ppt的具体finding与read_image画面定位问题；字符框相交不单独触发修订。原始资料的文字抽取仍可按来源路径进行。';
  if(!managedDefaultExport(command))return;
  if(directManagedProject(command)&&typeof ctx.tools.execute==='function'&&task.scene_options?.allow_output===true)return;
  const project=managedExportProject(command);
  appendFileSync(join(task.output,'ppt-delivery-audit.jsonl'),JSON.stringify({kind:'ppt_export_redirected',
   task_id:task.request?.task_id,command_sha256:sha(command)})+'\n',{mode:0o600});
  return '此Generate导出通过finalize_ppt执行。传入完整project路径'+(project?' '+project:'，将当前命令中的项目变量换成其真实/work/projects路径')+'。宿主生成清单并运行官方检查、PPTX导出及PDF/PNG渲染。';
 });
 ctx.tools.register({...pptPreviewTool,output:{schema:{type:'object'},render:(_args:any,value:any)=>{
  const {images,...receipt}=value;return [{type:'text',text:JSON.stringify(receipt)},...(images??[])];
 }},async execute(args:any,execution:any){
  const owner=current(execution.agent?.session?.id),task=owner?.task;
  if(!task||task.status!=='running'||task.scene.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options.allow_output!==true)
   throw Error('preview_task_not_authorized');
  if(args.source_page!==undefined){
   const source=task.scene_inputs?.find((row:any)=>args.path==='/work/inputs/'+row.file&&/\.pdf$/i.test(row.file));
   if(!source||args.source_page<1||args.crop!==undefined||args.scale!==undefined)throw Error('ppt_source_preview_requires_approved_pdf_page');
   const input=workspacePath(task.workspace,args.path);
   const output='/work/outputs/ppt-source-'+randomUUID()+'.jpg';
   const result=await runPptInSession(task,{operation:'source_preview',path:args.path,page:args.source_page,
    source_sha256:source.version_sha256,output},resources,execution.signal);
   execution.signal?.throwIfAborted();
   if(current(execution.agent.session.id)!==owner||task.status!=='running'||task.scene_options.allow_output!==true)
    throw Error('preview_authority_changed');
   const bytes=readFileSync(workspacePath(task.workspace,output));
   if(result.path!==output||result.page!==args.source_page||result.source_sha256!==source.version_sha256||
      sha(bytes)!==result.sha256||sha(readFileSync(input))!==source.version_sha256)throw Error('ppt_source_preview_changed');
   const attachment=await ctx.get('attachments').saveImage({data:bytes,mediaType:'image/jpeg',name:posix.basename(output)});
   return {...result,source:args.path,images:[{type:'image',attachment}]};
  }
  const receipt=currentPptReceipts(task,resources).find(row=>row.artifacts.some((a:any)=>a.path===args.path&&a.path.endsWith('.png')));
  const image=receipt?.artifacts.find((a:any)=>a.path===args.path);
  if(!image||!verifiedArtifacts(task,{artifacts:[image]}))throw Error('preview_requires_current_export_png');
  const output='/work/outputs/ppt-preview-'+randomUUID()+'.png';
  const result=await runPptInSession(task,{operation:'preview',path:args.path,source_sha256:image.sha256,output,crop:args.crop,scale:args.scale??2},resources,execution.signal);
  execution.signal?.throwIfAborted();
  if(current(execution.agent.session.id)!==owner||task.status!=='running'||task.scene_options.allow_output!==true)throw Error('preview_authority_changed');
  const actual=workspacePath(task.workspace,output);
  if(result.path!==output||result.sha256!==sha(readFileSync(actual))||result.source_sha256!==image.sha256||
     sha(readFileSync(workspacePath(task.workspace,args.path)))!==image.sha256)throw Error('preview_result_changed');
  const read=await ctx.tools.execute({name:'read_image',arguments:{file_path:output},callId:execution.callId+':preview',
   rootCallId:execution.rootCallId,parent:execution.token,agent:execution.agent,signal:execution.signal});
  const images=(read.content??[]).filter((part:any)=>part.type==='image');
  if(read.isError||!images.length)throw Error('preview_image_read_failed');
  const folder=join(task.output,'ppt-preview-receipts');mkdirSync(folder,{recursive:true,mode:0o700});
  writeFileSync(join(folder,randomUUID()+'.json'),JSON.stringify({kind:'ppt_preview_v1',task_id:task.request.task_id,
   delivery_id:receipt.delivery_id,dependencies_sha256:digest(receipt.dependencies),source_path:args.path,source_sha256:image.sha256,
   preview:{path:result.path,sha256:result.sha256,bytes:result.bytes}}),{mode:0o600,flag:'wx'});
  return {...result,images};
 }});
 ctx.tools.register({...pptPreparationTool,output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(pptPreparationView(value))}]},
  async execute(args:any,execution:any){
   const task=current(execution?.agent?.session?.id)?.task;
   if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master'||task.scene_options?.allow_output!==true)
    throw Error('preparation_task_not_authorized');
   workspacePath(task.workspace,args.project);
   if(locks.has(task.workspace))throw Error('delivery_already_running');
   locks.add(task.workspace);
   try{
    return await runPptInSession(task,{operation:'prepare',project:args.project,environment:officeEvidenceVersion(resources),
     implementation_sha256:sha(source('./ppt_preparation_runner.py')+source('../authoring/ppt_design_preflight.py'))},resources,execution.signal);
   }finally{locks.delete(task.workspace);}
  }});
 ctx.tools.register({...pptDeliveryTool,output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(pptDeliveryView(value))}]},
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
    const profile=args.profile??'general-readable-v1';
    const profiles=JSON.parse(readFileSync(new URL('../../../../scenarios/ppt_master/design-profiles.json',import.meta.url),'utf8'));
    if(!Object.hasOwn(profiles.profiles,profile))throw Error('delivery_profile_unknown');
    await runPptInSession(task,{operation:'prepare',project:args.project,environment:officeEvidenceVersion(resources),
     implementation_sha256:sha(source('./ppt_preparation_runner.py')+source('../authoring/ppt_design_preflight.py'))},resources,execution.signal);
    const dependencies=deliveryDependencies(task.workspace,args.project,args.manifest,resources);
    const fontRules=(context.fontRules??[]).filter((rule:any)=>rule.environment===dependencies.environment&&rule.training_task!==task.request.task_id);
    const ruleVersions=fontRules.map((rule:any)=>rule.id);
    const key=digest({project:args.project,manifest:args.manifest,profile,dependencies,ruleVersions});
    const folder=join(task.output,'ppt-delivery-receipts');mkdirSync(folder,{recursive:true,mode:0o700});
    const history=join(folder,'history-'+digest({project:args.project,profile})+'.json');
    const path=join(folder,key+'.json');
    if(existsSync(path)){
     const old=JSON.parse(readFileSync(path,'utf8'));
     const cached=cachedPptDelivery(task,old,key);
     if(cached){registerCurrentPptReceipt(task,cached);if(cached.mechanical_status==='passed'){
      task.stats.ppt_last_delivered_project=args.project;
      if(cached.review_pages?.length===0&&pptTaskAcceptance(task,resources).passed)execution.concludeTurn?.();
     }return cached;}
    }
    const output='/work/outputs/ppt-delivery-'+randomUUID();
    const integrated=existsSync(join(workspacePath(task.workspace,args.project),'geneloop-project.json'));
    const result=await runPptInSession(task,{...args,profile,output,font_rules:fontRules,integrated_generate:integrated},resources,execution.signal);
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
    if(result.mechanical_status==='passed'){
     receipt.review_pages=pptReviewPages(task,receipt);
     receipt.next_action=receipt.review_pages.length?'read_image_for_review_pages':'present_current_delivery';
    }
    if(result.mechanical_status==='passed'&&!verifiedArtifacts(task,receipt))throw Error('delivery_artifacts_changed');
    if(result.mechanical_status==='passed')capturePptLearningSources(task,receipt,execution,invocationArguments);
    const target=join(folder,afterKey+'.json'),temp=target+'.'+randomUUID()+'.tmp';
    writeFileSync(temp,JSON.stringify(receipt),{mode:0o600,flag:'wx'});renameSync(temp,target);
    const historyTemp=history+'.'+randomUUID()+'.tmp';writeFileSync(historyTemp,JSON.stringify(receipt),{mode:0o600,flag:'wx'});renameSync(historyTemp,history);
    registerCurrentPptReceipt(task,receipt);
    if(receipt.mechanical_status==='passed')task.stats.ppt_last_delivered_project=args.project;
    if(receipt.mechanical_status==='passed'&&receipt.review_pages?.length===0&&pptTaskAcceptance(task,resources).passed)execution.concludeTurn?.();
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
export function pptPublicationPlan(task:any,files:any[],resources:any={}){
 const generated=hasGenerateProject(task);
 const folder=join(task.output,'ppt-delivery-receipts');
 if(!generated&&!existsSync(folder))return {files,omitted:[]};
 const receipts=currentPptReceipts(task,resources),previews=currentPptPreviewHashes(task,receipts);
 const accepted:any[]=[],omitted:any[]=[];
 const error='此Generate交付缺少与当前源文件匹配的成功finalize_ppt回执。请仅在源文件变化或主稿损坏时重新调用finalize_ppt，直接返回其artifacts；附加预览无需触发整稿重做。';
 for(const file of files){
  if(!/\.(?:pptx|pdf|png)$/i.test(file.path??'')){accepted.push(file);continue;}
  try{
   const path=workspacePath(task.workspace,file.path),version=sha(readFileSync(path));
   if(receipts.some(row=>row.artifacts.some((artifact:any)=>artifact.sha256===version&&
      posix.extname(artifact.path).toLowerCase()===posix.extname(file.path).toLowerCase()))||
      file.path.toLowerCase().endsWith('.png')&&previews.has(version)){accepted.push(file);continue;}
  }catch{/* A native filesystem guard will also reject invalid paths. */}
  if(file.path?.toLowerCase().endsWith('.png'))omitted.push({path:file.path,reason:'preview_missing_or_not_current'});
  else return {files:[],omitted,error};
 }
 if(omitted.length&&!accepted.some(file=>/\.(?:pptx|pdf)$/i.test(file.path??'')))return {files:[],omitted,error};
 return {files:accepted,omitted};
}

/** Compatibility for callers that only need a rejection reason. */
export function validatePptPublication(task:any,files:any[],resources:any={}){
 return pptPublicationPlan(task,files,resources).error;
}
