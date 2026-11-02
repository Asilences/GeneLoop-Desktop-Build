/** Trusted Source adapter: pinned bytes -> native scene render -> actual artifact.
 * Candidate code never supplies the task manifest, registry or validation grant.
 */
import {readFileSync,writeFileSync,realpathSync,statSync,mkdirSync} from 'node:fs';
import {resolve,relative,isAbsolute,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {spawn,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {capabilityDigest,capabilityIdentity,capabilityRef,createCapability,createCapabilitySnapshot,
 mapLegacyLibrary,validateCapabilitySnapshot,type CapabilityRef,type CapabilitySnapshot} from './capability_contract.ts';
import {decodeSourceLibrary} from './source_program_runtime.ts';
import {createCapabilityRuntime,type CapabilityBackend,type CapabilityCall} from './capability_runtime.ts';
import {bytesSha256,rsiRecord,type AdmissionHost} from './rsi_protocol.ts';

const root=fileURLToPath(new URL('../..',import.meta.url));
const worker=join(root,'scenarios/remotion_edit/structured/capability_worker.py');
const exec=promisify(execFile);
export const sourceCapabilityOutputSchema={type:'object',properties:{
 source_version:{type:'string'},video_sha256:{type:'string'},video_path:{type:'string'},
 duration_seconds:{type:'number'},call_id:{type:'string'},
},required:['source_version','video_sha256','video_path','duration_seconds','call_id'],additionalProperties:false};
const assert=(ok:unknown,reason:string)=>{if(!ok)throw Error(reason);};
const same=(a:unknown,b:unknown)=>capabilityDigest(a)===capabilityDigest(b);
const sha=(value:unknown)=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const read=(path:string)=>JSON.parse(readFileSync(path,'utf8'));
function inside(base:string,path:string){const part=relative(base,path);return part!==''&&!part.startsWith('..'+(process.platform==='win32'?'\\':'/'))&&part!=='..'&&!isAbsolute(part);}

/** Certification is inherited only from a checked native source-equivalence
 * certificate. It is not semantic task quality and never certifies compositions.
 */
export function buildSourceCapabilities(raw:string|Buffer,owner:string){
 const bytes=Buffer.isBuffer(raw)?raw:Buffer.from(raw,'utf8');
 const {library,library_sha256}=decodeSourceLibrary(bytes);
 const capabilities=mapLegacyLibrary(bytes,owner,'source_program',library_sha256).map(mapped=>createCapability({
  ...capabilityIdentity(mapped),contract:{...mapped.contract,output_schema:sourceCapabilityOutputSchema},
 },{lifecycle:'active',certification:'certified',migration:'legacy'}));
 const roots=capabilities.map(capabilityRef);
 const snapshot=createCapabilitySnapshot(owner,roots,capabilities);
 const catalog=capabilities.map(capability=>{
  const implementation=capability.implementation;
  assert(implementation.kind==='legacy','source_capability_legacy_required');
  const program=library.programs.find((p:any)=>p.id===(implementation as any).legacy_ref.object_id);
  return {capability:capabilityRef(capability),description:program.description,
   input_schema:capability.contract.input_schema,output_schema:capability.contract.output_schema,
   example_parameters:program.default_parameters};
 });
 return {format:'source_capability_catalog_v1',owner,library_sha256,library_digest:library.digest,
  capabilities,roots,catalog,snapshot};
}

export type SourceTaskManifest={
 format:'source_capability_task_v1';task_id:string;owner:string;workspace:string;
 library_path:string;library_sha256:string;library_digest:string;registry_path:string;
 additional_libraries?:{path:string;sha256:string}[];
 runtime_directory:string;media_tools_directory?:string;image:string;python?:string;
 inputs:{name:string;path:string;sha256:string}[];
 grant:{id:string;task_id:string;snapshot_sha256:string;root:CapabilityRef;arguments_sha256:string;
  mode:'execute'|'validate';effects:string[];revoked:boolean};
};

function executorDigest(){
 return capabilityDigest(['src/adapters/source_capability_runtime.ts','src/adapters/capability_runtime.ts',
  'src/adapters/rsi_protocol.ts','src/adapters/source_program_runtime.ts','src/adapters/source_program_bridge.py',
  'scripts/materialize-source-program.mjs','scenarios/remotion_edit/server.py',
  'scenarios/remotion_edit/structured/server.py','scenarios/remotion_edit/structured/program_server.py',
  'scenarios/remotion_edit/structured/capability_worker.py'].map(path=>({path,sha256:bytesSha256(readFileSync(join(root,path)))})));
}

async function cleanupContainer(name:string,nonce:string){
 let raw:string;
 try{raw=(await exec('docker',['inspect',name],{timeout:15000,maxBuffer:1_000_000})).stdout;}
 catch(error:any){
  if(/No such (object|container)/.test(error.stderr??''))return {status:'absent',name};
  throw Error('source_container_inspection_failed');
 }
 const rows=JSON.parse(raw);
 assert(rows.length===1&&rows[0].Config?.Labels?.['geneloop.capability_nonce']===nonce,'source_container_owner_mismatch');
 const id=rows[0].Id;
 await exec('docker',['rm','-f',id],{timeout:30000,maxBuffer:100_000});
 return {status:'removed',name,container_id:id};
}

async function invokeWorker(request:any,python:string,signal?:AbortSignal):Promise<any>{
 assert(process.platform==='linux','source_capability_linux_required');
 assert(!signal?.aborted,'source_worker_cancelled');
 const env=Object.fromEntries(['PATH','LD_LIBRARY_PATH','HOME','TMPDIR'].filter(key=>process.env[key]).map(key=>[key,process.env[key]!])) as NodeJS.ProcessEnv;
 Object.assign(env,{PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',SSS_PYTHON:python});
 return new Promise((resolveWorker,reject)=>{
  const child=spawn(python,[worker],{cwd:root,env,detached:true,stdio:['pipe','pipe','pipe']});
  let stdout='',failure:string|null=null,killTimer:ReturnType<typeof setTimeout>|undefined;
  const kill=(sig:NodeJS.Signals)=>{if(child.pid)try{process.kill(-child.pid,sig);}catch(error:any){if(error.code!=='ESRCH')failure='source_worker_termination_failed';}};
  const stop=(reason:string)=>{if(failure)return;failure=reason;kill('SIGTERM');killTimer=setTimeout(()=>kill('SIGKILL'),5000);};
  const abort=()=>stop('source_worker_cancelled');
  const deadline=setTimeout(()=>stop('source_worker_timeout'),900000);
  signal?.addEventListener('abort',abort,{once:true});
  if(signal?.aborted)abort();
  child.stdout.setEncoding('utf8');child.stderr.resume();
  child.stdout.on('data',chunk=>{stdout+=chunk;if(stdout.length>2_000_000)stop('source_worker_output_exceeded');});
  child.stdin.on('error',()=>{});
  child.on('error',()=>{failure??='source_worker_start_failed';});
  child.on('close',async code=>{
   clearTimeout(deadline);if(killTimer)clearTimeout(killTimer);signal?.removeEventListener('abort',abort);
   try{
    writeFileSync(join(resolve(request.work,'..'),'worker-output.json'),stdout||JSON.stringify({status:'failed',reason:failure??'source_worker_no_output'}),{mode:0o600});
    // On cancellation/escalation the fixed worker may not reach its finally.
    // Stop only the container bearing this call's unique nonce and immutable ID.
    if(failure)await cleanupContainer('geneloop-cap-'+request.nonce,request.nonce);
    if(failure)throw Error(failure);
    const result=JSON.parse(stdout);
    assert(code===0&&result.status==='succeeded'&&['removed','absent'].includes(result.cleanup?.status),
     /^source_[a-z_]+$/.test(result.reason??'')?result.reason:'source_worker_failed');
    resolveWorker(result);
   }catch(error){reject(error);}
  });
  child.stdin.end(JSON.stringify(request));
 });
}

/** Invoke from a trusted runner/validator. manifestPath and registry_path must be
 * outside model-writable workspaces; all candidate outputs get per-call mounts.
 */
export async function runSourceCapability(manifestPath:string,snapshotValue:CapabilitySnapshot,args:unknown,
 options:{root?:CapabilityRef;signal?:AbortSignal}={}){
 const manifestBytes=readFileSync(manifestPath),manifest=JSON.parse(manifestBytes.toString('utf8')) as SourceTaskManifest;
 capabilityDigest(manifest);
 assert(manifest.format==='source_capability_task_v1'&&manifest.task_id&&manifest.owner,'source_task_manifest_invalid');
 assert(sha(manifest.library_sha256)&&sha(manifest.library_digest)&&typeof manifest.image==='string'&&manifest.image.length>0,
  'source_task_manifest_invalid');
 const snapshot=validateCapabilitySnapshot(snapshotValue,manifest.owner);
 const selected=options.root??manifest.grant?.root,argumentsSha=capabilityDigest(args),grant=manifest.grant;
 assert(grant&&grant.task_id===manifest.task_id&&grant.snapshot_sha256===snapshot.digest&&same(grant.root,selected)&&
  grant.arguments_sha256===argumentsSha&&['execute','validate'].includes(grant.mode)&&grant.revoked===false&&
  same(grant.effects,['workspace_write']),'source_task_grant_invalid');
 const workspace=realpathSync(manifest.workspace);
 assert(statSync(workspace).isDirectory()&&Array.isArray(manifest.inputs),'source_task_workspace_invalid');
 const names=new Set<string>();
 const inputs=manifest.inputs.map(item=>{
  const path=realpathSync(item.path);
  assert(item.name&&!/[\\/\x00]/.test(item.name)&&item.name!=='.'&&item.name!=='..'&&!names.has(item.name)&&
   inside(workspace,path)&&statSync(path).isFile()&&sha(item.sha256),'source_task_input_invalid');
  names.add(item.name);assert(bytesSha256(readFileSync(path))===item.sha256,'source_task_input_changed');
  return {...item,path};
 });
 const libraryBytes=readFileSync(manifest.library_path);
 decodeSourceLibrary(libraryBytes,{library_sha256:manifest.library_sha256,library_digest:manifest.library_digest});
 const libraries=new Map([[manifest.library_sha256,libraryBytes]]);
 for(const ref of manifest.additional_libraries??[]){
  const raw=readFileSync(ref.path);
  assert(bytesSha256(raw)===ref.sha256,'source_material_library_changed');
  decodeSourceLibrary(raw,{library_sha256:ref.sha256});libraries.set(ref.sha256,raw);
 }
 const nativeCatalog={capabilities:[...libraries.values()].flatMap(raw=>buildSourceCapabilities(raw,manifest.owner).capabilities)};
 const nativeLeaves=new Map(nativeCatalog.capabilities.map(capability=>[capability.id,capability]));
 const executionSha=executorDigest();
 const versions={motif:{id:'capability-snapshot',sha256:snapshot.digest},matcher:{id:'source-native-renderer',sha256:executionSha}};
 const manifestIdentity=(value:SourceTaskManifest)=>capabilityDigest({...value,grant:{...value.grant,revoked:false}});
 const frozenManifestIdentity=manifestIdentity(manifest);
 function currentManifest(){
  const current=read(manifestPath) as SourceTaskManifest;
  assert(typeof current.grant?.revoked==='boolean','source_task_manifest_invalid');
  assert(manifestIdentity(current)===frozenManifestIdentity,'source_task_manifest_changed');
  return current;
 }
 const evidence=[rsiRecord('evidence',{id:'task-arguments',sha256:argumentsSha,version:argumentsSha,task_id:manifest.task_id,
  subject:'Granted root arguments',role:'current',status:'valid',observation_id:grant.id,origin:'tool'}),
  ...inputs.map((item,index)=>rsiRecord('evidence',{id:'asset-'+index,sha256:item.sha256,version:item.sha256,
   task_id:manifest.task_id,subject:item.name,role:'current',status:'valid',observation_id:grant.id,origin:'tool'}))];
 const dependencies=evidence.map(record=>({id:record.payload.id,sha256:record.payload.sha256,version:record.payload.version}));
 const host:AdmissionHost={taskId:manifest.task_id,stateVersion:snapshot.digest,versions,
  operators:new Map(),currentCodeSha256:new Map(),currentEvidence:new Map(),obligations:new Map(),
  grant:{id:grant.id,taskId:manifest.task_id,stateVersion:snapshot.digest,operations:[],effects:grant.effects,revoked:false}};
 for(const capability of nativeCatalog.capabilities){
  const operation='source.render.'+capability.id;
  const record=rsiRecord('operator',{id:capability.id,operation,description:'Trusted native Source renderer in an isolated task workspace',
   source_kind:'tool',structure_signature:['render_program'],input_schema:capability.contract.input_schema,
   output_schema:sourceCapabilityOutputSchema,parameter_sources:[],dependencies:[],effect:'workspace_write',
   code_sha256:executionSha,opaque:false,certificate_ref:'trusted-native-renderer-'+executionSha});
  // This certifies the fixed native renderer, not a proposed composite program.
  host.operators.set(capability.id,{record,certified:true});host.currentCodeSha256.set(capability.id,executionSha);
  host.grant.operations.push(operation);
 }
 function readHost(){
  host.grant.revoked=currentManifest().grant.revoked;
  const currentCode=executorDigest();
  for(const id of host.currentCodeSha256.keys())host.currentCodeSha256.set(id,currentCode);
  host.currentEvidence=new Map(evidence.map(record=>[record.payload.id,structuredClone(record)]));
  inputs.forEach((item,index)=>{
   let valid=false;try{valid=bytesSha256(readFileSync(item.path))===item.sha256;}catch{}
   if(!valid)host.currentEvidence.get('asset-'+index)!.payload.status='invalidated';
  });
  return host;
 }
 let imageId:string|null=null;
 const backend:CapabilityBackend={
  inspect(reference){
   const leaf=nativeCatalog.capabilities.find(capability=>capability.implementation.kind==='legacy'&&
    same(capability.implementation.legacy_ref,reference));
   assert(leaf&&leaf.implementation.kind==='legacy','source_capability_leaf_unknown');
   return structuredClone((leaf!.implementation as any).legacy_ref);
  },
  request(call,args){
   const leaf=nativeLeaves.get(call.capability.id);
   assert(leaf&&same(capabilityRef(leaf),capabilityRef(call.capability)),'source_capability_leaf_changed');
   const operation='source.render.'+leaf!.id,argumentsSha256=bytesSha256(JSON.stringify(args)),obligation='obligation-'+call.callId;
   host.obligations.set(obligation,{taskId:manifest.task_id,operation,argumentsSha256,stateVersion:snapshot.digest,dependencies});
   return rsiRecord('runtime_request',{id:call.callId,task_id:manifest.task_id,operator_id:leaf!.id,operation,
    arguments_sha256:argumentsSha256,dependencies,versions,obligation_ref:obligation,state_version:snapshot.digest});
  },
  async execute(call:CapabilityCall,operation,args){
   if(imageId===null){
    const image=(await exec('docker',['image','inspect',manifest.image,'--format','{{.Id}}'],{timeout:15000,maxBuffer:100_000})).stdout.trim();
    assert(/^sha256:[a-f0-9]{64}$/.test(image),'source_container_image_invalid');imageId=image;
   }
   assert(!call.signal?.aborted,'source_worker_cancelled');
   const selectedLibrary=(call.capability.implementation as any).legacy_ref;
   const selectedBytes=libraries.get(selectedLibrary.library_sha256);
   assert(selectedBytes,'source_material_library_missing');
   const nonce=randomUUID().replaceAll('-',''),directory=join(workspace,'calls',call.callId);
   mkdirSync(join(workspace,'calls'),{recursive:true,mode:0o700});mkdirSync(directory,{mode:0o700});
   const native=await invokeWorker({call_id:call.callId,parent_call_id:call.parentCallId,task_id:manifest.task_id,parent_pid:process.pid,nonce,
    work:join(directory,'work'),runtime_directory:realpathSync(manifest.runtime_directory),
    media_tools_directory:manifest.media_tools_directory?realpathSync(manifest.media_tools_directory):undefined,
    image:imageId,inputs,library_base64:selectedBytes!.toString('base64'),
    library_sha256:selectedLibrary.library_sha256,library_digest:selectedLibrary.library_digest,
    program_id:(call.capability.implementation as any).legacy_ref.object_id,arguments:args},
    manifest.python??process.env.SSS_PYTHON??'python3',call.signal);
   const value=native.value,receipt=native.native_receipt;
   const expected=(call.capability.implementation as any).legacy_ref,actual=receipt.source_program_version;
   assert(receipt.call_id===call.callId&&receipt.parent_call_id===call.parentCallId&&receipt.task_id===manifest.task_id&&
    receipt.source_sha256===value.source_version&&receipt.video_sha256===value.video_sha256&&
    receipt.video_path===value.video_path&&actual?.library_sha256===expected.library_sha256&&actual.library_digest===expected.library_digest&&
    actual.program_id===expected.object_id&&actual.program_sha256===expected.object_sha256&&actual.certificate_sha256===expected.certificate_sha256&&
    inside(directory,realpathSync(value.video_path))&&bytesSha256(readFileSync(value.video_path))===value.video_sha256,
    'source_capability_artifact_receipt_changed');
   return {value,receipt:{call_id:call.callId,parent_call_id:call.parentCallId,task_id:manifest.task_id,
    operation,status:'succeeded',native_receipt:{...receipt,cleanup:native.cleanup}}};
  },
 };
 const runtime=createCapabilityRuntime({taskId:manifest.task_id,owner:manifest.owner,snapshot,readHost,
  readCapability:ref=>{
   const registry=validateCapabilitySnapshot(read(manifest.registry_path),manifest.owner);
   const capability=registry.capabilities.find(capability=>capability.id===ref.id);
   assert(capability,'source_capability_registry_missing');return capability;
  },backends:{source_program:backend},
  ...(grant.mode==='validate'?{readValidationGrant:()=>({id:grant.id,taskId:manifest.task_id,owner:manifest.owner,
   snapshotDigest:snapshot.digest,root:grant.root,revoked:currentManifest().grant.revoked})}:{})});
 const outcome=await runtime.execute(selected,args,{signal:options.signal});
 return {format:'source_capability_trace_v1',task_id:manifest.task_id,owner:manifest.owner,mode:grant.mode,
  grant_id:grant.id,validation_grant_id:grant.mode==='validate'?grant.id:null,
  manifest_sha256:bytesSha256(manifestBytes),executor_sha256:executionSha,image_id:imageId,snapshot_sha256:snapshot.digest,
  root:selected,arguments_sha256:argumentsSha,input_versions:inputs.map(({name,sha256})=>({name,sha256})),...outcome};
}
