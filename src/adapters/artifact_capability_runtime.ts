/** Public Capability execution through the existing certified Artifact sandbox. */
import {appendFileSync,readFileSync,realpathSync,statSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {artifactLocks,artifactInvocation,loadArtifactLibrary,registerArtifactContext} from './artifact_motif_runtime.ts';
import {executeArtifactJob,executePublicArtifactTask} from './artifact_motif_transport.ts';
import {componentContractSchema} from './ppt_component_schema.ts';
import {capabilityDigest,capabilityIdentity,capabilityRef,createCapability,createCapabilitySnapshot,
 mapLegacyLibrary,validateCapabilitySnapshot,type CapabilitySnapshot} from './capability_contract.ts';
import {createCapabilityRuntime,type CapabilityBackend} from './capability_runtime.ts';
import {bytesSha256,rsiRecord,type AdmissionHost} from './rsi_protocol.ts';

const root=fileURLToPath(new URL('../../',import.meta.url));
const read=(path:string)=>JSON.parse(readFileSync(path,'utf8'));
const same=(a:unknown,b:unknown)=>capabilityDigest(a)===capabilityDigest(b);
function check(value:unknown,reason:string):asserts value {if(!value)throw Error(reason);}

export function buildArtifactCapabilities(path:string,owner:string,expectedSha256?:string){
 const bytes=readFileSync(path),sha256=bytesSha256(bytes);
 check(!expectedSha256||sha256===expectedSha256,'artifact_capability_library_changed');
 const library=loadArtifactLibrary(path);
 const capabilities=mapLegacyLibrary(bytes,owner,'artifact_motif',sha256).map(mapped=>{
  const native=(mapped.implementation as any).legacy_ref;
  const program=library.programs.find((p:any)=>p.id===native.object_id);
  const inputSchema=program.component?{type:'object',properties:{parameters:componentContractSchema(program.component.parameters_schema)},
   required:['parameters'],additionalProperties:false}:mapped.contract.input_schema;
  return createCapability({...capabilityIdentity(mapped),contract:{...mapped.contract,input_schema:inputSchema}},
   {lifecycle:'active',certification:'certified',migration:'legacy'});
 });
 const roots=capabilities.map(capabilityRef);
 return {format:'artifact_capability_catalog_v1',owner,library_sha256:sha256,library_digest:library.digest,
  capabilities,roots,snapshot:createCapabilitySnapshot(owner,roots,capabilities),
  catalog:capabilities.map(capability=>{
   const program=library.programs.find((p:any)=>p.id===(capability.implementation as any).legacy_ref.object_id);
   return {capability:capabilityRef(capability),description:program.component?.summary??program.interface?.summary??program.id,
    input_schema:capability.contract.input_schema,output_schema:capability.contract.output_schema};
  })};
}

function executorDigest(){
 return capabilityDigest([...artifactLocks,'src/adapters/artifact_capability_runtime.ts','src/adapters/capability_runtime.ts',
  'src/adapters/capability_contract.ts','src/adapters/rsi_protocol.ts'].map(path=>({path,sha256:bytesSha256(readFileSync(join(root,path)))})));
}

/** manifest/registry are host-owned files outside the model-writable workspace.
 * Every dispatch rechecks native code, library bytes, permissions and evidence.
 */
export async function runArtifactCapability(manifestPath:string,snapshotValue:CapabilitySnapshot,args:unknown,
 options:{signal?:AbortSignal;resolvePath?:(path:string)=>string;resources?:any;assertAuthority?:()=>void}={}){
 const readManifest=()=>{
  const value=read(manifestPath);
  if(options.resolvePath){
   value.workspace=options.resolvePath(value.workspace);
   value.registry_path=options.resolvePath(value.registry_path);
   value.libraries=value.libraries.map((ref:any)=>({...ref,path:options.resolvePath!(ref.path)}));
   value.evidence=(value.evidence??[]).map((ref:any)=>({...ref,path:options.resolvePath!(ref.path)}));
   value.resources=options.resources??{};
  }
  return value;
 };
 const manifest=readManifest(),snapshot=validateCapabilitySnapshot(snapshotValue,manifest.owner),grant=manifest.grant;
 check(manifest.format==='artifact_capability_task_v1'&&typeof manifest.task_id==='string'&&manifest.task_id.length>0,
  'artifact_capability_manifest_invalid');
 const argumentsSha256=capabilityDigest(args),selected=grant?.root;
 check(grant&&grant.task_id===manifest.task_id&&grant.snapshot_sha256===snapshot.digest&&grant.arguments_sha256===argumentsSha256&&
  ['validate','execute'].includes(grant.mode)&&same(grant.effects,['workspace_write'])&&grant.revoked===false,
  'artifact_capability_grant_invalid');
 if(process.env.GENELOOP_COMMAND_SOCKET&&!manifest.session_id&&!options.resolvePath){
  const result=await executePublicArtifactTask(manifestPath,options.signal);
  check(result.owner===manifest.owner&&result.task_id===manifest.task_id&&result.snapshot_sha256===snapshot.digest&&
   result.arguments_sha256===argumentsSha256&&same(result.root,selected),'artifact_capability_transport_changed');
  return result;
 }
 const workspace=realpathSync(manifest.workspace);
 check(statSync(workspace).isDirectory()&&Array.isArray(manifest.libraries)&&manifest.libraries.length>0,'artifact_capability_workspace_invalid');
 const inputs=manifest.inputs??[];
 check(Array.isArray(inputs),'artifact_capability_inputs_invalid');
 function inputValid(input:any){
  check(typeof input.path==='string'&&/^\/work\/inputs\/[^/\\]+$/.test(input.path),'artifact_capability_input_invalid');
  const path=join(workspace,'inputs',input.path.slice('/work/inputs/'.length));
  return realpathSync(path)===resolve(path)&&bytesSha256(readFileSync(path))===input.sha256;
 }
 for(const input of inputs)check(inputValid(input),'artifact_capability_input_changed');
 const native=new Map<string,any>();
 function loadNative(){
  native.clear();
  for(const ref of manifest.libraries){
   const catalog=buildArtifactCapabilities(ref.path,manifest.owner,ref.sha256),library=loadArtifactLibrary(ref.path);
   for(const capability of catalog.capabilities)native.set(capability.id,{capability,library,
    program:library.programs.find((p:any)=>p.id===(capability.implementation as any).legacy_ref.object_id)});
  }
 }
 loadNative();
 const executor=executorDigest(),versions={motif:{id:'capability-snapshot',sha256:snapshot.digest},
  matcher:{id:'artifact-native-runtime',sha256:executor}};
 const original=capabilityDigest({...manifest,grant:{...grant,revoked:false}});
 function current(){
  const value=readManifest();
  check(typeof value.grant?.revoked==='boolean'&&capabilityDigest({...value,grant:{...value.grant,revoked:false}})===original,
   'artifact_capability_manifest_changed');
  return value;
 }
 const inputEvidence=[rsiRecord('evidence',{id:'task-arguments',sha256:argumentsSha256,version:argumentsSha256,
  task_id:manifest.task_id,subject:'Granted current task parameters',role:'current',status:'valid',observation_id:grant.id,origin:'tool'}),
  ...inputs.map((input:any,index:number)=>rsiRecord('evidence',{id:'input-'+index,sha256:input.sha256,
   version:input.sha256,task_id:manifest.task_id,subject:input.path,role:'current',status:'valid',observation_id:grant.id,origin:'tool'}))];
 const dependencies=inputEvidence.map((row:any)=>({id:row.payload.id,sha256:row.payload.sha256,version:row.payload.version}));
 const host:AdmissionHost={taskId:manifest.task_id,stateVersion:snapshot.digest,versions,operators:new Map(),
  currentCodeSha256:new Map(),currentEvidence:new Map(),obligations:new Map(),
  grant:{id:grant.id,taskId:manifest.task_id,stateVersion:snapshot.digest,operations:[],effects:['workspace_write'],revoked:false}};
 for(const {capability} of native.values()){
  const operation='artifact.execute.'+capability.id;
  host.operators.set(capability.id,{certified:true,record:rsiRecord('operator',{id:capability.id,operation,
   description:'Certified Artifact program in its original isolated sandbox',source_kind:'tool',structure_signature:['artifact_program'],
   input_schema:capability.contract.input_schema,output_schema:capability.contract.output_schema,parameter_sources:[],dependencies:[],
   effect:'workspace_write',code_sha256:executor,opaque:false,certificate_ref:'native-artifact-'+executor})});
  host.currentCodeSha256.set(capability.id,executor);host.grant.operations.push(operation);
 }
 function readHost(){
  options.assertAuthority?.();
  host.grant.revoked=current().grant.revoked;
  for(const ref of manifest.evidence??[])check(bytesSha256(readFileSync(ref.path))===ref.sha256,'artifact_capability_evidence_changed');
  check(executorDigest()===executor,'artifact_capability_executor_changed');
  host.currentEvidence=new Map(inputEvidence.map((row:any)=>[row.payload.id,structuredClone(row)]));
  inputs.forEach((input:any,index:number)=>{
   let valid=false;try{valid=inputValid(input);}catch{}
   if(!valid)host.currentEvidence.get('input-'+index)!.payload.status='invalidated';
  });
  return host;
 }
 const auditPath=join(dirname(manifestPath),'artifact-capability-native.jsonl');
 const backend:CapabilityBackend={
  inspect(ref){
   loadNative();const item=[...native.values()].find(item=>same(item.capability.implementation.legacy_ref,ref));
   check(item,'artifact_capability_leaf_changed');return structuredClone(item.capability.implementation.legacy_ref);
  },
  request(call,value){
   const item=native.get(call.capability.id);
   check(item&&same(capabilityRef(item.capability),capabilityRef(call.capability)),'artifact_capability_leaf_changed');
   const operation='artifact.execute.'+call.capability.id,obligation='obligation-'+call.callId;
   const argumentsHash=bytesSha256(JSON.stringify(value));
   host.obligations.set(obligation,{taskId:manifest.task_id,operation,argumentsSha256:argumentsHash,stateVersion:snapshot.digest,dependencies});
   return rsiRecord('runtime_request',{id:call.callId,task_id:manifest.task_id,operator_id:call.capability.id,operation,
    arguments_sha256:argumentsHash,dependencies,versions,obligation_ref:obligation,state_version:snapshot.digest});
  },
  async execute(call,operation,value){
   const item=native.get(call.capability.id),session='public-artifact-'+randomUUID();
   const audit=(row:any)=>appendFileSync(auditPath,JSON.stringify({...row,task_id:manifest.task_id,call_id:call.callId})+'\n',{mode:0o600});
   registerArtifactContext(session,{library:item.library,workspace,taskId:manifest.task_id,allowOutput:true,
    resources:manifest.resources??{},audit,auditPath});
   try{
    const parameters=value as any;
    const command=item.program.component?'geneloop-component '+JSON.stringify({id:item.program.id,parameters:parameters.parameters,
     output:'/work/outputs/capability-'+call.callId}):'geneloop-recipe '+JSON.stringify({id:item.program.id,...parameters});
    const job=artifactInvocation(session,command);
    if(!item.program.component){
     for(const bound of job.bound)check(inputs.some((input:any)=>input.path===bound.path&&input.sha256===bound.sha256),
      'artifact_capability_input_not_granted');
    }
    const result=await executeArtifactJob(job,manifest.session_id??session,call.signal);
    const receipt=result.receipt??result;
    check(receipt.kind==='artifact_program_receipt'&&receipt.program_id===item.program.id,'artifact_capability_native_receipt_invalid');
    return {value:receipt,receipt:{call_id:call.callId,parent_call_id:call.parentCallId,task_id:manifest.task_id,
     operation,status:'succeeded',native_receipt:receipt}};
   }finally{registerArtifactContext(session,null);}
  }
 };
 const runtime=createCapabilityRuntime({taskId:manifest.task_id,owner:manifest.owner,snapshot,readHost,
  readCapability(ref){return validateCapabilitySnapshot(read(manifest.registry_path),manifest.owner).capabilities.find(c=>c.id===ref.id);},
  backends:{artifact_motif:backend},...(grant.mode==='validate'?{readValidationGrant:()=>({id:grant.id,taskId:manifest.task_id,
   owner:manifest.owner,snapshotDigest:snapshot.digest,root:selected,revoked:current().grant.revoked})}:{})});
 const started=performance.now(),result=await runtime.execute(selected,args,options);
 return {...result,format:'artifact_capability_trace_v1',owner:manifest.owner,task_id:manifest.task_id,mode:grant.mode,grant_id:grant.id,root:selected,
  snapshot_sha256:snapshot.digest,arguments_sha256:argumentsSha256,input_versions:inputs,duration_ms:performance.now()-started};
}
