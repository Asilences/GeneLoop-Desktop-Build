/** Account-private output reuse for certified, self-contained page programs. */
import {copyFileSync,existsSync,lstatSync,mkdirSync,mkdtempSync,readFileSync,realpathSync,renameSync,writeFileSync} from 'node:fs';
import {join,relative,resolve,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
import {officeEvidenceVersion} from './geneloop_presentation.ts';
import {digest} from '../motif_core/online_skill_runtime.mjs';

const sha=(data:any)=>createHash('sha256').update(data).digest('hex');
function fixed(directory:string){
 const stat=lstatSync(directory);
 if(!stat.isDirectory()||stat.isSymbolicLink()||realpathSync(directory)!==resolve(directory))throw Error('component_cache_directory_changed');
}
function child(directory:string,name:string){
 const path=join(directory,name),rel=relative(directory,path);
 if(!rel||rel.startsWith('..')||isAbsolute(rel)||realpathSync(path)!==path)throw Error('component_cache_file_outside');
 const stat=lstatSync(path);
 if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>50_000_000)throw Error('component_cache_file_changed');
 return path;
}
export function componentCacheKey(job:any){
 if(job.certification||!job.cacheRoot||job.program.component?.cache_policy!=='bound_page_output_v1')return null;
 return digest({program:job.program.id,source:job.program.source_sha256,library:job.library.digest,
  inputs:job.bound.map((b:any)=>b.sha256),resources:officeEvidenceVersion(job.resources??{}),
  node:process.version,python:process.env.SSS_PYTHON??'python3',renderer:sha(readFileSync(new URL('./ppt_component_render.py',import.meta.url)))});
}
export function readComponentCache(root:string,key:string,destination:string){
 if(!existsSync(root))return null;
 fixed(root);const directory=join(root,key);if(!existsSync(directory))return null;
 fixed(directory);const record=JSON.parse(readFileSync(child(directory,'manifest.json'),'utf8'));
 if(record.version!==1||record.key!==key||!Array.isArray(record.files)||!record.files.length||record.files.length>128)throw Error('component_cache_manifest_changed');
 let bytes=0;
 const verified=record.files.map((row:any)=>{
  if(typeof row.path!=='string'||!Number.isSafeInteger(row.bytes)||row.bytes<0||(bytes+=row.bytes)>100_000_000)throw Error('component_cache_manifest_changed');
  const path=child(directory,row.path),data=readFileSync(path);
  if(data.length!==row.bytes||sha(data)!==row.sha256)throw Error('component_cache_bytes_changed');
  return {...row,data};
 });
 mkdirSync(destination,{mode:0o700});
 for(const row of verified){const target=join(destination,row.path);mkdirSync(join(target,'..'),{recursive:true,mode:0o700});writeFileSync(target,row.data,{mode:0o600,flag:'wx'});}
 return record;
}
export function saveComponentCache(root:string,key:string,output:string,receipt:any){
 mkdirSync(root,{recursive:true,mode:0o700});fixed(root);
 if(existsSync(join(root,key)))return false;
 const directory=mkdtempSync(join(root,'pending-'));
 for(const row of receipt.files){
  const source=child(output,row.path),target=join(directory,row.path);
  if(sha(readFileSync(source))!==row.sha256)throw Error('component_cache_source_changed');
  mkdirSync(join(target,'..'),{recursive:true,mode:0o700});copyFileSync(source,target);
 }
 writeFileSync(join(directory,'manifest.json'),JSON.stringify({version:1,key,files:receipt.files,stdout:receipt.stdout,stderr:receipt.stderr}),{mode:0o600,flag:'wx'});
 try{renameSync(directory,join(root,key));return true;}catch(error){if(!existsSync(join(root,key)))throw error;return false;}
}
