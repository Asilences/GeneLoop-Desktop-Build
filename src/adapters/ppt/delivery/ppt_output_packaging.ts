/** Fixed output-only file operations. Parsed commands are never sent to a shell. */
import {copyFileSync,existsSync,lstatSync,mkdirSync,readdirSync} from 'node:fs';
import {basename,join,posix} from 'node:path';
import {pptWorkspacePath} from './ppt_delivery_pipeline.ts';

type Operation={kind:'copy'|'list'|'mkdir'|'echo';paths:string[];quiet?:boolean};
const outputPath=(path:string)=>(path==='/work/outputs'||path.startsWith('/work/outputs/'))&&posix.normalize(path)===path&&!/[\x00-\x1f:]/.test(path)&&
 !path.split('/').some(part=>part.startsWith('.'));

export function pptOutputPackagingPlan(command:unknown):Operation[]|null {
 if(typeof command!=='string'||command.length>8192||/[\r\n`$|<\\()]/.test(command))return null;
 const token=/\s*("[^"\r\n]*"|'[^'\r\n]*'|&&|;|[^\s;&"']+)/gy;
 const segments:string[][]=[[]];let offset=0;
 while(offset<command.trimEnd().length){
  token.lastIndex=offset;const match=token.exec(command);if(!match)return null;offset=token.lastIndex;
  const word=match[1];
  if(word==='&&'||word===';'){if(!segments.at(-1)!.length)return null;segments.push([]);}
  else segments.at(-1)!.push(/^['"]/.test(word)?word.slice(1,-1):word);
 }
 if(!segments.at(-1)!.length||segments.length>16)return null;
 const operations:Operation[]=[];
 for(const words of segments){
  const [name,...args]=words;
  const literal=(path:string)=>outputPath(path)&&!/[>*?\[\]{}&]/.test(path);
  if(name==='cp'&&args.length===2&&args.every(literal))operations.push({kind:'copy',paths:args});
  else if(name==='mkdir'&&args[0]==='-p'&&args.length>1&&args.slice(1).every(literal))operations.push({kind:'mkdir',paths:args.slice(1)});
  else if(name==='echo'&&args.length===1&&args[0]==='---')operations.push({kind:'echo',paths:args});
  else if(name==='ls'){
   const quiet=args.at(-1)==='2>/dev/null',paths=args.filter((arg,index)=>
    !['-l','-la','-al','-a'].includes(arg)&&!(quiet&&index===args.length-1));
   if(!paths.length||!paths.every(path=>literal(path)||outputPath(path)&&
    !/[*>?\[\]{}&]/.test(posix.dirname(path))&&/^\*\.(png|jpe?g|webp|pdf|pptx)$/i.test(posix.basename(path))))return null;
   operations.push({kind:'list',paths,quiet});
  }else return null;
 }
 return operations;
}

export function executePptOutputPackaging(task:any,operations:Operation[],signal:AbortSignal){
 signal.throwIfAborted();
 if(!lstatSync(pptWorkspacePath(task.workspace,'/work/outputs/')).isDirectory())throw Error('ppt_output_parent_invalid');
 const lines:string[]=[];
 const target=(logical:string)=>{
  if(!outputPath(logical)||/[>*?\[\]{}&]/.test(logical))throw Error('ppt_output_path_invalid');
  const physical=join(task.workspace,'outputs/code',logical.slice('/work/outputs/'.length));
  // New destinations inherit the same fixed-parent checks as existing files.
  let ancestor=logical;
  while(!lstatSync(join(task.workspace,'outputs/code',ancestor.slice('/work/outputs/'.length)),{throwIfNoEntry:false})){
   ancestor=posix.dirname(ancestor);
   if(ancestor==='/work/outputs'){
    break;
   }
  }
  // The trailing slash maps the logical output mount itself correctly.
  if(ancestor==='/work/outputs'){
   const parent=pptWorkspacePath(task.workspace,'/work/outputs/');
   if(!lstatSync(parent).isDirectory())throw Error('ppt_output_parent_invalid');
  }else pptWorkspacePath(task.workspace,ancestor);
  if(existsSync(physical)&&lstatSync(physical).isFile()&&lstatSync(physical).nlink!==1)throw Error('ppt_output_file_linked');
  return physical;
 };
 for(const operation of operations){
  signal.throwIfAborted();
  if(operation.kind==='echo'){lines.push('---');continue;}
  if(operation.kind==='mkdir'){
   for(const path of operation.paths)mkdirSync(target(path),{recursive:true,mode:0o700});
  }else if(operation.kind==='copy'){
   const [from,to]=operation.paths,source=pptWorkspacePath(task.workspace,from);
   if(!lstatSync(source).isFile())throw Error('ppt_output_source_not_file');
   let destination=target(to);
   if(existsSync(destination)&&lstatSync(destination).isDirectory())destination=target(to+'/'+basename(source));
   if(source!==destination)copyFileSync(source,destination);
   lines.push('Copied '+from+' to '+to);
  }else{
   for(const path of operation.paths){
    if(path.includes('*')){
     const folder=posix.dirname(path),physical=target(folder);
     if(!existsSync(physical)&&operation.quiet)continue;
     const ext=posix.extname(path).toLowerCase();
     for(const name of readdirSync(physical).sort())if(name.toLowerCase().endsWith(ext)){
      pptWorkspacePath(task.workspace,folder+'/'+name);lines.push(folder+'/'+name);
     }
    }else{
     const physical=target(path);
     if(!existsSync(physical)&&operation.quiet)continue;
     if(lstatSync(physical).isDirectory())for(const name of readdirSync(physical).sort())lines.push(path+'/'+name);
     else lines.push(path);
    }
   }
  }
 }
 return lines.join('\n');
}
