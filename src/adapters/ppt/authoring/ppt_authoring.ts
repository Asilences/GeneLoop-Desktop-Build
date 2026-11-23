/** Shared authoring policy, not a learned workflow. Preserve adopted native pages. */
import {existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,realpathSync,renameSync,writeFileSync,unlinkSync} from 'node:fs';
import {dirname,isAbsolute,join,posix,resolve,relative,sep} from 'node:path';
import {randomUUID} from 'node:crypto';
import {pptOutputPackagingPlan} from '../delivery/ppt_output_packaging.ts';

const markerName='native-authoring.json';
function checked(path:string){
 const s=lstatSync(path);
 if(s.isSymbolicLink()||realpathSync(path)!==resolve(path)||s.isFile()&&s.nlink!==1)throw Error('ppt_authoring_path_changed');
 return path;
}
function markers(task:any){
 const parent=join(task.workspace,'code/projects');
 if(!existsSync(parent))return [];
 checked(parent);
 return readdirSync(parent,{withFileTypes:true}).filter(row=>row.isDirectory()&&!row.name.startsWith('.')).flatMap(row=>{
  const project='/work/projects/'+row.name,folder=checked(join(parent,row.name)),path=join(folder,'validation',markerName);
  if(!existsSync(path))return [];
  checked(dirname(path));const saved=JSON.parse(readFileSync(checked(path),'utf8'));
  if(saved.version!==1||saved.project!==project||!saved.pages||typeof saved.pages!=='object'||Array.isArray(saved.pages)||
    Object.entries(saved.pages).some(([name,sha])=>!(/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,127}\.svg$/u).test(name)||typeof sha!=='string'||!/^[a-f0-9]{64}$/.test(sha)))
   throw Error('ppt_authoring_marker_invalid');
  return [saved];
 });
}
export function recordPptNativeAuthoring(task:any,project:string,page:string,sha:string){
 if(!/^\/work\/projects\/[\p{L}\p{N}][\p{L}\p{N}_-]{0,79}$/u.test(project)||
  !/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,127}\.svg$/u.test(page)||!/^[a-f0-9]{64}$/.test(sha))throw Error('ppt_authoring_receipt_invalid');
 const folder=checked(join(task.workspace,'code',project.slice('/work/'.length))),validation=join(folder,'validation');
 mkdirSync(validation,{recursive:true});checked(validation);
 const previous=markers(task).find(row=>row.project===project);
 const target=join(validation,markerName),temp=target+'.'+randomUUID()+'.pending';
 writeFileSync(temp,JSON.stringify({version:1,project,pages:{...previous?.pages,[page]:sha}}),{mode:0o600,flag:'wx'});
 renameSync(temp,target);
}

/** Only the already-authorized learned-program release calls this boundary. */
export function releasePptNativeAuthoring(task:any,project:string){
 const saved=markers(task).find(row=>row.project===project);if(!saved)return;
 const target=join(task.workspace,'code',project.slice('/work/'.length),'validation',markerName);
 unlinkSync(checked(target)); // Policy only; keep every page, note and failure receipt.
}

/** A small literal shell subset shared with learned-program leases. */
export function pptManagedShellReadOrPublish(command:unknown,allowedOutput:(path:string)=>boolean=()=>true){
 if(typeof command!=='string'||/[\n\r`$<>|;\\]/.test(command)||command.replaceAll('&&','').includes('&'))return false;
 let cwd='/work';
 const literal=(s:string)=>s.startsWith('/work/')&&posix.normalize(s.replace(/\/$/,''))===s.replace(/\/$/,'');
 const output=(s:string)=>literal(s)&&s.startsWith('/work/outputs/')&&!/[*?\[\]{}]/.test(s)&&allowedOutput(s);
 const scratch=(s:string)=>(s==='/tmp'||s.startsWith('/tmp/'))&&posix.normalize(s)===s&&!/[*?\[\]{}]/.test(s)&&allowedOutput(s);
 return command.split('&&').every(part=>{
  const words=part.trim().match(/"[^"\n]*"|'[^'\n]*'|[^\s"']+/g);
  if(!words||words.join(' ').replaceAll(/\s+/g,' ')!==part.trim().replaceAll(/\s+/g,' '))return false;
  const [name,...args]=words.map(s=>/^['"]/.test(s)?s.slice(1,-1):s);
  if(name==='echo')return args.every(s=>!s.startsWith('-')&&!/[;&`$<>|\\]/.test(s));
  const outputPath=(s:string)=>output(s)||scratch(s);
  if(name==='cd'&&args.length===1&&(args[0]==='/work'||literal(args[0])||scratch(args[0]))){cwd=args[0];return true;}
  const paths=(items:string[])=>items.length>0&&items.every(s=>!s.startsWith('-')&&!s.includes('..')&&!/[?{}!]/.test(s)&&
   (s.startsWith('/')?literal(s)||scratch(s):!s.includes('/')&&(cwd==='/work'||literal(cwd)||scratch(cwd))));
  if(['sha256sum','ls','pwd'].includes(name))return name==='pwd'?args.length===0:paths(args.filter(s=>name==='ls'&&['-l','-la','-al'].includes(s)?false:true));
  if(name==='shasum')return args[0]==='-a'&&args[1]==='256'&&paths(args.slice(2));
  if(name==='cat')return paths(args);
  if(['head','tail'].includes(name))return args[0]==='-n'&&/^\d{1,4}$/.test(args[1]??'')&&Number(args[1])<=1000?paths(args.slice(2)):paths(args);
  if(name==='mkdir')return args[0]==='-p'&&args.length>1&&args.slice(1).every(outputPath);
  if(name==='cp')return args.length===2&&!args.some(s=>s.includes('*'))&&
   (args.every(output)||output(args[0])&&scratch(args[1])&&/\.(png|jpe?g|webp)$/i.test(args[0])&&/\.(png|jpe?g|webp)$/i.test(args[1]));
  return false;
 });
}
function safeOutput(workspace:string,logical:string){
 const root=resolve(workspace),physical=logical==='/tmp'||logical.startsWith('/tmp/')?join(root,'command-tmp',logical.slice(5)):
  join(root,'outputs/code',logical.slice('/work/outputs/'.length));
 for(let probe=physical;probe!==root;probe=dirname(probe)){
  if(dirname(probe)===probe)return false;
  try{checked(probe);}catch(error:any){if(error.code!=='ENOENT')return false;}
 }
 return true;
}
const instruction='已有内置页由PPT执行层维护。继续compose_ppt_page（修订传当前SHA），或按程序卡使用execute_ppt_program；不要改写成功页、另写批量重建/测宽脚本或重读旧executor规范。新页可以使用相同页型；确有特殊绘图需求可直接write新的独立SVG并用已有字号，保留成功页。素材裁剪、缩放、复制用prepare_ppt_asset；字体/容量检查和导出交给prepare_ppt/finalize_ppt，最后present成品；读取内容用read/grep和来源工具。';
export function pptNativeAuthoringGuard(task:any,call:any){
 if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master')return;
 const saved=markers(task);if(!saved.length)return;
 const path=call.arguments?.file_path??call.arguments?.path;
 if(['write','edit'].includes(call.name)&&typeof path==='string'){
  const local=relative(join(task.workspace,'code'),resolve(path));
  const logical=isAbsolute(path)&&!path.startsWith('/work/')&&!local.startsWith('..')&&!isAbsolute(local)
    ?'/work/'+local.split(sep).join('/'):posix.resolve('/work',path.replaceAll('\\','/'));
  if(saved.some(row=>logical===row.project+'/validation/'+markerName||
    Object.keys(row.pages).some(page=>logical===row.project+'/svg_output/'+page)))return instruction;
 }
 if(call.name==='bash'&&!pptManagedShellReadOrPublish(call.arguments?.command,p=>safeOutput(task.workspace,p))&&
   !pptOutputPackagingPlan(call.arguments?.command))return instruction;
}
