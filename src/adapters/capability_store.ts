/** Local experimental publication store. Trusted host callbacks run validation;
 * model proposals never supply certificates. This is not a production publisher.
 * The owner directory must remain writable only by the trusted host. Hashes bind
 * stored evidence; they do not authenticate a filesystem controlled by an attacker.
 */
import {createHash,randomUUID} from 'node:crypto';
import {mkdirSync,realpathSync,lstatSync,readFileSync,openSync,writeFileSync,fsyncSync,closeSync,renameSync,unlinkSync,rmSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {capabilityDigest,capabilityRef,createCapabilitySnapshot,validateCapabilitySnapshot,
 type CapabilityRef,type CapabilitySnapshot} from './capability_contract.ts';

export type CapabilityArtifact={name:string;bytes:Uint8Array};
export type CapabilityValidationCheck={id:string;status:'passed'|'failed'|'unknown';observation:string};
export type CapabilityValidationVerdict={passed:boolean;checks:CapabilityValidationCheck[];scope?:string;limitations?:string[]};
export type CapabilityValidationContext={candidateSnapshot:CapabilitySnapshot;root:CapabilityRef;input:unknown};
export type CapabilityValidationExecution={format:string;task_id:string;owner:string;mode:'validate'|'execute';grant_id:string;
 snapshot_sha256:string;root:CapabilityRef;arguments_sha256:string;status:string;result:unknown;receipts:any[];[key:string]:unknown};
export type CapabilityStoreOptions={directory:string;owner:string;
 runValidation:(context:CapabilityValidationContext)=>Promise<{execution:CapabilityValidationExecution;artifacts:CapabilityArtifact[]}>;
 validator:{id:string;sha256:string;check:(context:CapabilityValidationContext&{execution:CapabilityValidationExecution;artifacts:CapabilityArtifact[]})=>Promise<CapabilityValidationVerdict>}};
type FileRef={path:string;sha256:string};
export type CapabilityPublication={format:'capability_publication_v1';scope:'local_experiment';owner:string;root:CapabilityRef;
 previous_publication_sha256:string|null;candidate_snapshot_sha256:string;published_snapshot_sha256:string;
 task_id:string;validation_grant_id:string;input_sha256:string;result_sha256:string;validator:{id:string;sha256:string};
 files:{candidate:FileRef;snapshot:FileRef;input:FileRef;execution:FileRef;validation:FileRef;artifacts:(FileRef&{name:string})[]}};
export type LoadedCapabilityPublication={publication_sha256:string;publication:CapabilityPublication;snapshot:CapabilitySnapshot};
const sha=(bytes:Uint8Array|string)=>createHash('sha256').update(bytes).digest('hex');
const check=(condition:unknown,reason:string):asserts condition=>{if(!condition)throw Error('capability_store_'+reason);};
const isSha=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const same=(a:unknown,b:unknown)=>capabilityDigest(a)===capabilityDigest(b);
function jsonBytes(value:unknown){capabilityDigest(value);return Buffer.from(JSON.stringify(value));}
function id(value:unknown){check(typeof value==='string'&&Boolean(value.trim())&&value.length<=256,'identifier_invalid');}
function shape(value:any,keys:string[]){check(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(k=>Object.hasOwn(value,k)),'shape_invalid');}
function regular(path:string){const stat=lstatSync(path);check(stat.isFile()&&!stat.isSymbolicLink(),'file_not_regular');}
function directory(path:string){mkdirSync(path,{recursive:true,mode:0o700});const stat=lstatSync(path);check(stat.isDirectory()&&!stat.isSymbolicLink(),'directory_not_private');}
function writeNew(path:string,bytes:Uint8Array){const fd=openSync(path,'wx',0o600);try{writeFileSync(fd,bytes);fsyncSync(fd);}finally{closeSync(fd);}}
function syncDirectory(path:string){const fd=openSync(path,'r');try{fsyncSync(fd);}finally{closeSync(fd);}}
function successfulVerdict(value:any):asserts value is CapabilityValidationVerdict{
 check(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).every(k=>['passed','checks','scope','limitations'].includes(k)),'shape_invalid');
 check(value.passed===true&&Array.isArray(value.checks)&&value.checks.length>0,'validation_failed');
 if(Object.hasOwn(value,'scope'))check(typeof value.scope==='string'&&Boolean(value.scope.trim()),'validation_scope_invalid');
 if(Object.hasOwn(value,'limitations'))check(Array.isArray(value.limitations)&&value.limitations.every((item:any)=>typeof item==='string'),'validation_limitations_invalid');
 const ids=new Set();for(const item of value.checks){shape(item,['id','status','observation']);id(item.id);check(!ids.has(item.id),'duplicate_check');ids.add(item.id);
  check(item.status==='passed'&&typeof item.observation==='string'&&Boolean(item.observation.trim()),'validation_failed');}
}
function executionBinding(execution:CapabilityValidationExecution,snapshot:CapabilitySnapshot,root:CapabilityRef,input:unknown){
 capabilityDigest(execution);id(execution.format);id(execution.task_id);id(execution.grant_id);
 check(execution.mode==='validate'&&execution.owner===snapshot.owner,'validation_context_changed');
 check(execution.snapshot_sha256===snapshot.digest&&same(execution.root,root)&&execution.arguments_sha256===capabilityDigest(input),'validation_binding_changed');
 check(execution.status==='succeeded'&&Array.isArray(execution.receipts)&&execution.receipts.length>0,'execution_failed');
 const parents=execution.receipts.filter(r=>r.parent_call_id===null);
 check(parents.length===1&&same(parents[0].capability,root),'trace_root_changed');
 check(parents[0].arguments_sha256===sha(jsonBytes(input))&&parents[0].result_sha256===sha(jsonBytes(execution.result)),'trace_value_changed');
 const ids=new Set(execution.receipts.map(r=>r.call_id));check(ids.size===execution.receipts.length,'trace_duplicate_call');
 for(const receipt of execution.receipts){
  check(receipt.status==='succeeded'&&receipt.task_id===execution.task_id&&receipt.snapshot_sha256===snapshot.digest,'trace_execution_changed');
  check(Array.isArray(receipt.child_call_ids)&&receipt.child_call_ids.every((child:string)=>ids.has(child)),'trace_children_changed');
  check(receipt.parent_call_id===null||ids.has(receipt.parent_call_id),'trace_parent_changed');
 }
 check(execution.receipts.some(r=>r.kind==='legacy'&&r.dispatched===true&&r.backend_receipt?.status==='succeeded'),'trace_without_native_execution');
}

/** Instantiate only in trusted host code, never from model-controlled config.
 * runValidation must invoke the actual runtime validation-grant path and read its
 * artifacts. validator.check must run independent mechanical checks on those bytes.
 */
export function createCapabilityStore(options:CapabilityStoreOptions){
 id(options.owner);id(options.validator.id);check(isSha(options.validator.sha256),'validator_digest_invalid');
 check(typeof options.runValidation==='function'&&typeof options.validator.check==='function','trusted_callbacks_required');
 directory(options.directory);const base=realpathSync(options.directory),owner=options.owner;
 const ownerDirectory=join(base,sha(owner));directory(ownerDirectory);const versions=join(ownerDirectory,'versions');directory(versions);
 const runValidation=options.runValidation,validatorCheck=options.validator.check.bind(options.validator);
 const validator={id:options.validator.id,sha256:options.validator.sha256};
 function pointer():string|null{
  const file=join(ownerDirectory,'latest.json');if(!existsSync(file))return null;regular(file);
  const value=JSON.parse(readFileSync(file,'utf8'));shape(value,['format','owner','publication_sha256']);
  check(value.format==='capability_pointer_v1'&&value.owner===owner&&isSha(value.publication_sha256),'pointer_changed');return value.publication_sha256;
 }
 function loadVersion(publicationSha256:string):LoadedCapabilityPublication{
  check(isSha(publicationSha256),'publication_digest_invalid');
  const version=join(versions,publicationSha256),stat=lstatSync(version);check(stat.isDirectory()&&!stat.isSymbolicLink(),'version_not_directory');
  const manifest=join(version,'publication.json');regular(manifest);const bytes=readFileSync(manifest);check(sha(bytes)===publicationSha256,'publication_changed');
  const publication=JSON.parse(bytes.toString('utf8')) as CapabilityPublication;
  shape(publication,['format','scope','owner','root','previous_publication_sha256','candidate_snapshot_sha256','published_snapshot_sha256','task_id','validation_grant_id','input_sha256','result_sha256','validator','files']);
  check(publication.format==='capability_publication_v1'&&publication.scope==='local_experiment'&&publication.owner===owner,'publication_owner_changed');
  check(publication.previous_publication_sha256===null||isSha(publication.previous_publication_sha256),'previous_digest_invalid');
  shape(publication.files,['candidate','snapshot','input','execution','validation','artifacts']);
  function file(ref:FileRef,expectedPath:string){
   shape(ref,['path','sha256']);check(ref.path===expectedPath&&isSha(ref.sha256),'file_reference_changed');
   const path=join(version,expectedPath);regular(path);check(realpathSync(path)===path,'file_symlink');const data=readFileSync(path);check(sha(data)===ref.sha256,'evidence_changed');return data;
  }
  const candidate=validateCapabilitySnapshot(JSON.parse(file(publication.files.candidate,'candidate.json').toString('utf8')),owner);
  const snapshot=validateCapabilitySnapshot(JSON.parse(file(publication.files.snapshot,'snapshot.json').toString('utf8')),owner);
  const input=JSON.parse(file(publication.files.input,'input.json').toString('utf8'));
  const execution=JSON.parse(file(publication.files.execution,'execution.json').toString('utf8'));
  const verdict=JSON.parse(file(publication.files.validation,'validation.json').toString('utf8'));successfulVerdict(verdict);
  check(Array.isArray(publication.files.artifacts)&&publication.files.artifacts.length>0,'artifact_inventory_empty');const names=new Set();
  for(const [index,artifact] of publication.files.artifacts.entries()){
   shape(artifact,['name','path','sha256']);id(artifact.name);check(!names.has(artifact.name),'artifact_duplicate');names.add(artifact.name);
   file({path:artifact.path,sha256:artifact.sha256},'artifacts/'+String(index).padStart(4,'0')+'.bin');
  }
  check(candidate.digest===publication.candidate_snapshot_sha256&&snapshot.digest===publication.published_snapshot_sha256,'snapshot_changed');
  check(same(candidate.roots,[publication.root])&&same(snapshot.roots,[publication.root]),'published_roots_changed');
  executionBinding(execution,candidate,publication.root,input);
  check(execution.task_id===publication.task_id&&execution.grant_id===publication.validation_grant_id&&capabilityDigest(input)===publication.input_sha256&&capabilityDigest(execution.result)===publication.result_sha256,'publication_validation_changed');
  shape(publication.validator,['id','sha256']);id(publication.validator.id);check(isSha(publication.validator.sha256),'validator_digest_invalid');
  const promoted=candidate.capabilities.map(c=>c.id===publication.root.id?{...c,lifecycle:'active' as const,certification:'certified' as const,migration:'promoted' as const}:c);
  check(same(createCapabilitySnapshot(owner,[publication.root],promoted),snapshot),'promotion_changed');
  return {publication_sha256:publicationSha256,publication:structuredClone(publication),snapshot};
 }
 function loadLatest(){const current=pointer();return current===null?null:loadVersion(current);}
 async function publish(request:CapabilityValidationContext&{expectedLatest:string|null}){
  const expectedLatest=request.expectedLatest;
  check(expectedLatest===null||isSha(expectedLatest),'expected_latest_required');
  check(pointer()===expectedLatest,'cas_conflict');
  if(expectedLatest!==null)loadVersion(expectedLatest);
  const candidateSnapshot=validateCapabilitySnapshot(request.candidateSnapshot,owner),root=structuredClone(request.root),input=structuredClone(request.input);
  capabilityDigest(input);check(same(candidateSnapshot.roots,[root]),'single_root_required');
  const rootCapability=candidateSnapshot.capabilities.find(c=>same(capabilityRef(c),root));
  check(rootCapability?.certification==='candidate'&&rootCapability.lifecycle==='build_only','candidate_required');
  check(candidateSnapshot.capabilities.every(c=>c.id===root.id||c.certification==='certified'),'uncertified_dependency');
  const context={candidateSnapshot,root,input};
  const actual=await runValidation(structuredClone(context));
  const execution=structuredClone(actual.execution);executionBinding(execution,candidateSnapshot,root,input);
  check(Array.isArray(actual.artifacts)&&actual.artifacts.length>0,'artifact_inventory_empty');const names=new Set();
  const artifacts=actual.artifacts.map(a=>{id(a.name);check(!names.has(a.name),'artifact_duplicate');names.add(a.name);check(a.bytes instanceof Uint8Array,'artifact_bytes_required');return {name:a.name,bytes:Buffer.from(a.bytes)};});
  const verdict=structuredClone(await validatorCheck({...structuredClone(context),execution:structuredClone(execution),artifacts:artifacts.map(a=>({...a,bytes:Buffer.from(a.bytes)}))}));successfulVerdict(verdict);
  const promoted=candidateSnapshot.capabilities.map(c=>c.id===root.id?{...c,lifecycle:'active' as const,certification:'certified' as const,migration:'promoted' as const}:c);
  const snapshot=createCapabilitySnapshot(owner,[root],promoted);
  const payloads=[['candidate.json',jsonBytes(candidateSnapshot)],['snapshot.json',jsonBytes(snapshot)],['input.json',jsonBytes(input)],['execution.json',jsonBytes(execution)],['validation.json',jsonBytes(verdict)]] as const;
  const refs=Object.fromEntries(payloads.map(([path,bytes])=>[path,{path,sha256:sha(bytes)}]));
  const artifactRefs=artifacts.map((a,i)=>({name:a.name,path:'artifacts/'+String(i).padStart(4,'0')+'.bin',sha256:sha(a.bytes)}));
  const publication:CapabilityPublication={format:'capability_publication_v1',scope:'local_experiment',owner,root,previous_publication_sha256:expectedLatest,
   candidate_snapshot_sha256:candidateSnapshot.digest,published_snapshot_sha256:snapshot.digest,task_id:execution.task_id,validation_grant_id:execution.grant_id,
   input_sha256:capabilityDigest(input),result_sha256:capabilityDigest(execution.result),validator,
   files:{candidate:refs['candidate.json'],snapshot:refs['snapshot.json'],input:refs['input.json'],execution:refs['execution.json'],validation:refs['validation.json'],artifacts:artifactRefs}};
  const publicationBytes=jsonBytes(publication),publicationSha256=sha(publicationBytes);
  const lock=join(ownerDirectory,'.publish.lock'),staging=join(ownerDirectory,'.staging-'+randomUUID()),temporary=join(ownerDirectory,'.latest-'+randomUUID()+'.json');
  let locked=false;
  try{
   const fd=openSync(lock,'wx',0o600);locked=true;closeSync(fd);
   check(pointer()===expectedLatest,'cas_conflict');directory(staging);directory(join(staging,'artifacts'));
   for(const [path,bytes] of payloads)writeNew(join(staging,path),bytes);
   for(const [index,artifact] of artifacts.entries())writeNew(join(staging,artifactRefs[index].path),artifact.bytes);
   writeNew(join(staging,'publication.json'),publicationBytes);syncDirectory(join(staging,'artifacts'));syncDirectory(staging);
   const final=join(versions,publicationSha256);
   if(existsSync(final)){loadVersion(publicationSha256);rmSync(staging,{recursive:true});}else renameSync(staging,final);
   syncDirectory(versions);
   writeNew(temporary,jsonBytes({format:'capability_pointer_v1',owner,publication_sha256:publicationSha256}));renameSync(temporary,join(ownerDirectory,'latest.json'));syncDirectory(ownerDirectory);
  }finally{
   if(existsSync(staging))rmSync(staging,{recursive:true});if(existsSync(temporary))unlinkSync(temporary);if(locked)unlinkSync(lock);
  }
  return {status:'published' as const,...loadVersion(publicationSha256)};
 }
 return {publish,loadLatest,loadVersion};
}
