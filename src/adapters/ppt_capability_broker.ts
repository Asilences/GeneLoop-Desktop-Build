/** Host authority for a frozen account-local public validation/followup task. */
import {readFileSync,realpathSync,lstatSync} from 'node:fs';
import {join,dirname,relative,resolve,isAbsolute,basename} from 'node:path';
import {createHash} from 'node:crypto';
import {createPptLearning} from './harless_ppt_learning.ts';
import {capabilityDigest,validateCapabilitySnapshot} from './capability_contract.ts';

const hash=(raw:any)=>createHash('sha256').update(raw).digest('hex');
const check=(value:unknown,reason:string)=>{if(!value)throw Error(reason);};

export function publicPptValidationTask(accountOutput:string,file:string,python:string){
 const output=realpathSync(accountOutput);
 const map=(name:string)=>{
  check(typeof name==='string','public_validation_path_missing');
  const path=resolve(name.startsWith('/app/.local/web/')?join(output,name.slice('/app/.local/web/'.length)):name);
  const rel=relative(output,path);
  check(rel&&!rel.startsWith('..')&&!isAbsolute(rel)&&realpathSync(path)===path,'public_validation_foreign_path');
  const stat=lstatSync(path);
  check(!stat.isSymbolicLink()&&(!stat.isFile()||stat.nlink===1),'public_validation_redirected_path');
  return path;
 };
 const json=(path:string)=>{
  const fixed=map(path),stat=lstatSync(fixed);
  check(stat.isFile()&&stat.size<=4_000_000,'public_validation_fixed_json_required');
  return JSON.parse(readFileSync(fixed,'utf8'));
 };
 const manifestPath=map(file),rel=relative(output,manifestPath).split('\\').join('/');
 const match=/^learning\/(ppt-[a-f0-9]{64})\/capability\/improvements\/[a-f0-9]{64}\/[^/]+\/attempt-[0-9]+\/publication\/(validation|followup)\/manifest\.json$/.exec(rel);
 check(match,'public_validation_outside_owned_learner');
 const directory=dirname(manifestPath),attempt=dirname(dirname(directory)),label=match![2];
 const learning=join(output,'learning',match![1]);
 const manifest=json(manifestPath),registry=map(join(directory,'registry.json')),argsPath=map(join(directory,'args.json'));
 check(manifest.format==='artifact_capability_task_v1'&&typeof manifest.owner==='string'&&manifest.owner.length>0,
  'public_validation_manifest_invalid');
 check(map(manifest.workspace)===join(attempt,label+'-workspace')&&map(manifest.registry_path)===registry,
  'public_validation_workspace_changed');
 const snapshot=validateCapabilitySnapshot(json(registry),manifest.owner),args=json(argsPath),grant=manifest.grant;
 check(grant&&grant.task_id===manifest.task_id&&grant.snapshot_sha256===snapshot.digest&&
  grant.arguments_sha256===capabilityDigest(args)&&grant.mode===(label==='validation'?'validate':'execute')&&grant.revoked===false,
  'public_validation_grant_invalid');
 check(Array.isArray(manifest.libraries)&&manifest.libraries.length>0,'public_validation_libraries_missing');
 for(const ref of manifest.libraries){
  const path=map(ref.path),rel=relative(learning,path);
  check(rel&&!rel.startsWith('..')&&!isAbsolute(rel)&&hash(readFileSync(path))===ref.sha256,'public_validation_library_changed');
 }
 function assertAuthority(){
  const pointer=json(join(learning,'program-selected.json'));
  check(pointer.user===manifest.owner&&typeof pointer.scope==='string'&&
   basename(learning)==='ppt-'+hash(pointer.user+'\0'+pointer.scope),'public_validation_owner_scope_changed');
  const selection=createPptLearning({output,user:pointer.user,scope:pointer.scope,python,taskIds:()=>[]}).program();
  check(selection&&manifest.libraries.some((ref:any)=>map(ref.path)===selection.library&&ref.sha256===selection.library_sha256),
   'public_validation_native_authority_changed');
 }
 assertAuthority();
 return {manifestPath,registry,argsPath,resolvePath:map,assertAuthority};
}
