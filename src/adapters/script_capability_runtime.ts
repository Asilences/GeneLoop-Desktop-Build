/** Native Script programs in the shared Capability runtime. No new evaluator. */
import {readFileSync,writeFileSync,mkdirSync,realpathSync} from 'node:fs';
import {join,resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {spawn} from 'node:child_process';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {loadScriptLibrary,programIdentity,scriptVirtualHost,fixedInput,compatibleInput,scriptCodeLocks} from './script_motif_runtime.ts';
import {capabilityDigest,capabilityRef,createCapability,createCapabilitySnapshot,validateCapabilitySnapshot,
 type CapabilitySnapshot,type CapabilityRef} from './capability_contract.ts';
import {createCapabilityRuntime,type CapabilityBackend} from './capability_runtime.ts';
import {bytesSha256,rsiRecord,type AdmissionHost} from './rsi_protocol.ts';
const root=fileURLToPath(new URL('../../',import.meta.url));
const assert=(value:unknown,reason:string)=>{if(!value)throw Error(reason);};
const same=(a:unknown,b:unknown)=>capabilityDigest(a)===capabilityDigest(b);
const read=(path:string)=>JSON.parse(readFileSync(path,'utf8'));
export const scriptCapabilityFiles=[...scriptCodeLocks,'src/adapters/script_runtime_compatibility.ts',
 'config/script-runtime-compatibility.json','src/adapters/script_capability_runtime.ts',
 'src/adapters/capability_runtime.ts','src/adapters/capability_contract.ts','src/adapters/rsi_protocol.ts',
 'scripts/script-capability-worker.mjs'];
export function scriptExecutorDigest(){return capabilityDigest(scriptCapabilityFiles.map(path=>({path,sha256:bytesSha256(readFileSync(join(root,path)))})));}

export function buildScriptCapabilities(path:string,owner:string,expectedSha256?:string){
 const bytes=readFileSync(path),library_sha256=bytesSha256(bytes);
 assert(!expectedSha256||expectedSha256===library_sha256,'script_material_library_changed');
 const library=loadScriptLibrary(path);
 assert(bytesSha256(readFileSync(path))===library_sha256,'script_material_library_changed');
 const capabilities=[],catalog=[],excluded=[];
 const seen=new Set();
 for(const program of library.programs){
  assert(!seen.has(program.id),'script_material_duplicate');seen.add(program.id);
  if(program.argv_contract||program.network_policy||!Array.isArray(program.inputs)||!program.inputs.length){
   excluded.push({program_id:program.id,reason:'script_capability_file_read_subset_only'});continue;
  }
  const output_schema={type:'object',properties:{stdout:{type:'string'},
   ...(program.certification.output_schema?{value:program.certification.output_schema}:{})},
   required:['stdout',...(program.certification.output_schema?['value']:[])],additionalProperties:false};
  const fileInput={type:'object',properties:{paths:{type:'array',
   items:{type:'string'},description:`Exactly ${program.inputs.length} granted input paths, in native slot order`}},required:['paths'],additionalProperties:false};
  const variants=[{input_schema:fileInput,value:false}];
  if(program.certification.value_binding)variants.push({input_schema:{type:'object',properties:{value:program.certification.value_binding.input_schema},
   required:['value'],additionalProperties:false},value:true});
  for(const variant of variants){
  const capability=createCapability({owner,contract:{input_schema:variant.input_schema,
   output_schema,effects:['read']},implementation:{kind:'legacy',legacy_ref:{backend:'script_motif',
   library_sha256,library_digest:library.digest,object_id:program.id,object_sha256:digest(programIdentity(program)),
   certificate_sha256:digest(program.certification)}},dependencies:[]},{lifecycle:'active',certification:'certified',migration:'legacy'});
  capabilities.push(capability);catalog.push({capability:capabilityRef(capability),description:program.description+(variant.value?' [Certified JSON value input; accepts previous capability results directly]':''),
   input_schema:capability.contract.input_schema,output_schema,input_contracts:program.inputs,
   certification_scope:program.certification.scope??'source_equivalence_not_semantic_quality'});
  }
 }
 const roots=capabilities.map(capabilityRef);
 // A supported native catalog must have at least one root; report unsupported
 // programs without pretending they have migrated.
 return {format:'script_capability_catalog_v1',owner,library_sha256,library_digest:library.digest,
  capabilities,roots,catalog,excluded,snapshot:capabilities.length?createCapabilitySnapshot(owner,roots,capabilities):null};
}

export type ScriptTaskManifest={format:'script_capability_task_v1';task_id:string;owner:string;workspace:string;
 libraries:{path:string;sha256:string}[];registry_path:string;inputs:{path:string;sha256:string}[];
 grant:{id:string;task_id:string;snapshot_sha256:string;root:CapabilityRef;arguments_sha256:string;
 mode:'execute'|'validate';effects:string[];revoked:boolean}};

async function invoke(job:unknown,signal?:AbortSignal):Promise<any>{
 assert(!signal?.aborted,'script_worker_cancelled');
 const env=Object.fromEntries(['PATH','HOME','TMPDIR','LD_LIBRARY_PATH','SSS_PYTHON'].filter(k=>process.env[k]).map(k=>[k,process.env[k]!])) as NodeJS.ProcessEnv;
 return new Promise((done,reject)=>{
  const child=spawn(process.execPath,['--experimental-strip-types',join(root,'scripts/script-capability-worker.mjs')],
   {cwd:root,env,detached:true,stdio:['pipe','pipe','pipe']});
  let output='',failure:string|null=null,escalation:ReturnType<typeof setTimeout>|undefined;
  const kill=(sig:NodeJS.Signals)=>{if(child.pid)try{process.kill(-child.pid,sig);}catch{}};
  const stop=(reason:string)=>{if(failure)return;failure=reason;kill('SIGTERM');escalation=setTimeout(()=>kill('SIGKILL'),1000);};
  const abort=()=>stop('script_worker_cancelled'),timer=setTimeout(()=>stop('script_worker_timeout'),45000);
  signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
  child.stdout.setEncoding('utf8');child.stderr.resume();child.stdin.on('error',()=>{});
  child.stdout.on('data',chunk=>{output+=chunk;if(Buffer.byteLength(output)>256000)stop('script_worker_output_exceeded');});
  child.on('error',()=>{failure??='script_worker_start_failed';});
  child.on('close',code=>{
   clearTimeout(timer);if(escalation){kill('SIGKILL');clearTimeout(escalation);}signal?.removeEventListener('abort',abort);
   try{assert(!failure,failure!);assert(code===0,'script_worker_failed');done(JSON.parse(output));}catch(error){reject(error);}
  });
  child.stdin.end(JSON.stringify(job));
 });
}

export async function runScriptCapability(manifestPath:string,snapshotValue:CapabilitySnapshot,args:unknown,
 options:{root?:CapabilityRef;signal?:AbortSignal}={}){
 assert(process.platform==='linux'||process.platform==='darwin','script_capability_platform_unsupported');
 const raw=readFileSync(manifestPath),manifest=JSON.parse(raw.toString('utf8')) as ScriptTaskManifest;
 assert(manifest.format==='script_capability_task_v1'&&manifest.owner&&manifest.task_id,'script_task_manifest_invalid');
 const snapshot=validateCapabilitySnapshot(snapshotValue,manifest.owner),grant=manifest.grant;
 const selected=options.root??grant?.root,argumentsSha=capabilityDigest(args);
 assert(grant&&grant.id&&grant.task_id===manifest.task_id&&grant.snapshot_sha256===snapshot.digest&&same(grant.root,selected)&&
  grant.arguments_sha256===argumentsSha&&['validate','execute'].includes(grant.mode)&&grant.revoked===false&&same(grant.effects,['read']),
  'script_task_grant_invalid');
 const workspace=realpathSync(manifest.workspace);
 const inputMap=new Map<string,{path:string;sha256:string}>();
 for(const input of manifest.inputs){
  assert(input.path==='/work/inputs/'+basename(input.path)&&!inputMap.has(input.path),'script_task_input_invalid');
  assert(bytesSha256(fixedInput(workspace,scriptVirtualHost(workspace,input.path)))===input.sha256,'script_task_input_changed');
  inputMap.set(input.path,input);
 }
 const native=new Map();
 function loadNative(){
  native.clear();
  for(const ref of manifest.libraries){
   const catalog=buildScriptCapabilities(ref.path,manifest.owner,ref.sha256),library=loadScriptLibrary(ref.path);
   for(const cap of catalog.capabilities)native.set(cap.id,{cap,program:library.programs.find((p:any)=>p.id===(cap.implementation as any).legacy_ref.object_id)});
  }
 }
 loadNative();const executor=scriptExecutorDigest();
 const identity=(m:ScriptTaskManifest)=>capabilityDigest({...m,grant:{...m.grant,revoked:false}}),frozenIdentity=identity(manifest);
 function current(){const m=read(manifestPath);assert(typeof m.grant?.revoked==='boolean'&&identity(m)===frozenIdentity,'script_task_manifest_changed');return m;}
 const versions={motif:{id:'capability-snapshot',sha256:snapshot.digest},matcher:{id:'native-script-runtime',sha256:executor}};
 const evidence=manifest.inputs.map((input,i)=>rsiRecord('evidence',{id:'input-'+i,sha256:input.sha256,version:input.sha256,
  task_id:manifest.task_id,subject:input.path,role:'current',status:'valid',observation_id:grant.id,origin:'tool'}));
 const dependencies=evidence.map(r=>({id:r.payload.id,sha256:r.payload.sha256,version:r.payload.version}));
 const host:AdmissionHost={taskId:manifest.task_id,stateVersion:snapshot.digest,versions,operators:new Map(),
  currentCodeSha256:new Map(),currentEvidence:new Map(),obligations:new Map(),
  grant:{id:grant.id,taskId:manifest.task_id,stateVersion:snapshot.digest,operations:[],effects:['read'],revoked:false}};
 for(const {cap} of native.values()){
  const operation='script.execute.'+cap.id;
  host.operators.set(cap.id,{certified:true,record:rsiRecord('operator',{id:cap.id,operation,description:'Certified native read-only Script program',
   source_kind:'tool',structure_signature:['run_certified_script'],input_schema:cap.contract.input_schema,
   output_schema:cap.contract.output_schema,parameter_sources:[],dependencies:[],effect:'read',
   code_sha256:executor,opaque:false,certificate_ref:'native-script-'+executor})});
  host.currentCodeSha256.set(cap.id,executor);host.grant.operations.push(operation);
 }
 function readHost(){
  host.grant.revoked=current().grant.revoked;
  const code=scriptExecutorDigest();for(const id of host.currentCodeSha256.keys())host.currentCodeSha256.set(id,code);
  host.currentEvidence=new Map(evidence.map(r=>[r.payload.id,structuredClone(r)]));
  manifest.inputs.forEach((input,i)=>{let valid=false;try{valid=bytesSha256(fixedInput(workspace,scriptVirtualHost(workspace,input.path)))===input.sha256;}catch{}
   if(!valid)host.currentEvidence.get('input-'+i)!.payload.status='invalidated';});return host;
 }
 const backend:CapabilityBackend={
  inspect(ref){loadNative();const item=[...native.values()].find(({cap})=>same(cap.implementation.legacy_ref,ref));
   assert(item,'script_capability_leaf_changed');return structuredClone(item.cap.implementation.legacy_ref);},
  request(call,args){
   const item=native.get(call.capability.id);assert(item&&same(capabilityRef(item.cap),capabilityRef(call.capability)),'script_capability_leaf_changed');
   const operation='script.execute.'+item.cap.id,obligation='obligation-'+call.callId,argumentsSha256=bytesSha256(JSON.stringify(args));
   host.obligations.set(obligation,{taskId:manifest.task_id,operation,argumentsSha256,stateVersion:snapshot.digest,dependencies});
   return rsiRecord('runtime_request',{id:call.callId,task_id:manifest.task_id,operator_id:item.cap.id,operation,
    arguments_sha256:argumentsSha256,dependencies,versions,obligation_ref:obligation,state_version:snapshot.digest});
  },
  async execute(call,operation,value){
   const item=native.get(call.capability.id),program=item.program;
   const valueMode=Object.hasOwn(item.cap.contract.input_schema.properties,'value');
   let paths:string[],files:{path:string;bytes:Buffer;sha256:string}[];
   if(valueMode){
    assert(program.certification.value_binding?.format==='script_json_value_binding_v1','script_value_binding_not_certified');
    const bytes=Buffer.from(JSON.stringify((value as any).value));assert(bytes.length>0&&bytes.length<=1000000,'script_value_input_bound');
    paths=['/work/inputs/value.json'];files=[{path:paths[0],bytes,sha256:bytesSha256(bytes)}];
   }else{
   paths=(value as any).paths as string[];
   assert(paths.length===program.inputs.length&&new Set(paths).size===paths.length,'script_capability_binding_invalid');
   files=paths.map((path,i)=>{const input=inputMap.get(path);assert(input,'script_capability_input_not_granted');
    const bytes=fixedInput(workspace,scriptVirtualHost(workspace,path));
    assert(bytesSha256(bytes)===input!.sha256,'script_capability_input_changed');
    assert(compatibleInput(program.inputs[i],path,bytes),'script_capability_input_contract_mismatch');
    return {path,bytes,sha256:input!.sha256};});
   }
   const work=join(workspace,'calls',call.callId);
   mkdirSync(join(workspace,'calls'),{recursive:true,mode:0o700});mkdirSync(work,{mode:0o700});
   for(const name of ['inputs','code','outputs/code','command-tmp'])mkdirSync(join(work,name),{recursive:true,mode:0o700});
   for(const file of files)writeFileSync(join(work,'inputs',basename(file.path)),file.bytes,{mode:0o400,flag:'wx'});
   const nonce=randomUUID(),inputVersions=files.map(f=>f.sha256);
   const receipt=await invoke({workspace:work,program,paths,versions:inputVersions,nonce},call.signal);
   assert(receipt.kind==='script_motif_receipt'&&receipt.nonce===nonce&&receipt.program_id===program.id&&same(receipt.versions,inputVersions)&&
    typeof receipt.output==='string'&&bytesSha256(receipt.output)===receipt.output_sha256&&receipt.network_evidence?.length===0,
    'script_capability_receipt_changed');
   const result={stdout:receipt.output,...(program.certification.output_schema?{value:JSON.parse(receipt.output)}:{})};
   return {value:result,receipt:{call_id:call.callId,parent_call_id:call.parentCallId,task_id:manifest.task_id,operation,status:'succeeded',
    native_receipt:{...receipt,script_version:(call.capability.implementation as any).legacy_ref}}};
  },
 };
 const runtime=createCapabilityRuntime({taskId:manifest.task_id,owner:manifest.owner,snapshot,readHost,
  readCapability:ref=>{const registry=validateCapabilitySnapshot(read(manifest.registry_path),manifest.owner);
   const cap=registry.capabilities.find(c=>c.id===ref.id);assert(cap,'script_capability_registry_missing');return cap;},
  backends:{script_motif:backend},...(grant.mode==='validate'?{readValidationGrant:()=>({id:grant.id,taskId:manifest.task_id,
   owner:manifest.owner,snapshotDigest:snapshot.digest,root:grant.root,revoked:current().grant.revoked})}:{})});
 const result=await runtime.execute(selected,args,{signal:options.signal});
 return {format:'script_capability_trace_v1',task_id:manifest.task_id,owner:manifest.owner,mode:grant.mode,grant_id:grant.id,
  validation_grant_id:grant.mode==='validate'?grant.id:null,manifest_sha256:bytesSha256(raw),executor_sha256:executor,
  snapshot_sha256:snapshot.digest,root:selected,arguments_sha256:argumentsSha,input_versions:manifest.inputs,...result};
}
