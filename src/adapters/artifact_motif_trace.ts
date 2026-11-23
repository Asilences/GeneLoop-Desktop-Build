/** Exact private file evidence at native tool boundaries. */
import {appendFileSync,mkdirSync,writeFileSync,readFileSync,readdirSync,lstatSync,realpathSync,existsSync} from 'node:fs';
import {join,relative,resolve,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {digest} from '../motif_core/runtime/online_skill_runtime.mjs';
const sha=(b:any)=>createHash('sha256').update(b).digest('hex');
const textFiles=/[.](?:py|json|tex|bib|bbl|md|txt|csv|tsv)$/;
const artifactEvidence={depth:6,files:384,bytes:12_000_000,scope:'bounded_text_and_svg_files',
 extensions:/[.](?:py|json|tex|bib|bbl|md|txt|csv|tsv|svg)$/,skipUnreadableDirectories:false};
const reuseEvidence={depth:5,files:256,bytes:8_000_000,scope:'bounded_text_files_not_all_files',
 extensions:textFiles,skipUnreadableDirectories:true};
export const createArtifactTrace=(workspace:string,output:string)=>recordBoundaries(workspace,output,artifactEvidence);
export const createReuseTrace=(workspace:string,output:string)=>recordBoundaries(workspace,output,reuseEvidence);
function recordBoundaries(workspace:string,output:string,profile:typeof artifactEvidence){
 const directory=join(output,'reuse-evidence');mkdirSync(directory,{recursive:true,mode:0o700});
 const pending=new Map<string,any>();
 function snapshot(){
  const files:Record<string,any>={};let bytes=0,count=0,complete=true;
  function visit(path:string,depth=0){
   if(depth>profile.depth||count>=profile.files){complete=false;return;}
   if(!profile.skipUnreadableDirectories&&!existsSync(path))return;
   let rows;
   try{rows=readdirSync(path,{withFileTypes:true});}
   catch(error){if(profile.skipUnreadableDirectories)return;throw error;}
   for(const row of rows){
    if(row.name.startsWith('.')||row.isSymbolicLink())continue;
    const child=join(path,row.name);
    if(row.isDirectory()){visit(child,depth+1);continue;}
    if(!row.isFile()||!profile.extensions.test(row.name))continue;
    const size=lstatSync(child).size;if(size>1_000_000||bytes+size>profile.bytes||++count>profile.files||realpathSync(child)!==resolve(child)){complete=false;continue;}
    const data=readFileSync(child),hash=sha(data);bytes+=data.length;
    if(!existsSync(join(directory,hash)))writeFileSync(join(directory,hash),data,{mode:0o600,flag:'wx'});
    files[relative(workspace,child).split(sep).join('/')]={sha256:hash,bytes:data.length};
   }
  }
  visit(join(workspace,'inputs'));visit(join(workspace,'code'));visit(join(workspace,'outputs/code'));
  return {files,complete,scope:profile.scope,bytes};
 }
 return {
  before(execution:any){try{pending.set(execution.callId,{tool:execution.name,arguments_sha256:digest(execution.arguments),before:snapshot()});}catch{}},
  after(execution:any,result:any){const row=pending.get(execution.callId);pending.delete(execution.callId);if(!row)return;
   try{appendFileSync(join(output,'reuse-boundaries.jsonl'),JSON.stringify({...row,call_id:execution.callId,after:snapshot(),result_sha256:digest(result),is_error:result?.isError===true,at:new Date().toISOString()})+'\n',{mode:0o600});}catch{}
  }
 };
}
