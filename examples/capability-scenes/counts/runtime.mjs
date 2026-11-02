/** Non-video adapter conformance example. Fixed native programs really execute;
 * admission/certification are diagnostic fixtures, not production credentials.
 */
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createCapability,capabilityRef,createCapabilitySnapshot,capabilityDigest} from '../../../src/adapters/capability_contract.ts';
import {createCapabilityRuntime} from '../../../src/adapters/capability_runtime.ts';
import {diagnosticHost} from '../../rsi-protocol-v1/host.mjs';

const hash=x=>createHash('sha256').update(x).digest('hex');
const code=fileURLToPath(new URL('../../rsi-protocol-v1/group_count.py',import.meta.url));
const checker=fileURLToPath(new URL('../../../tests/fixtures/capability_count_validator.py',import.meta.url));
export const contract={input_schema:{type:'object',properties:{rows:{type:'array',items:{type:'object',properties:{group:{type:'string'}},required:['group'],additionalProperties:false}}},required:['rows'],additionalProperties:false},output_schema:{type:'object'},effects:['read']};
export const validator={id:'diagnostic-count-checker',sha256:hash(readFileSync(checker))};
function reference(){return {backend:'artifact_motif',object_id:'diagnostic-group-count',
 library_sha256:hash(readFileSync(code)),library_digest:hash(readFileSync(code)),
 object_sha256:hash(readFileSync(code)),certificate_sha256:hash('diagnostic-only-admission')};}
export function seed(owner){
 const cap=createCapability({owner,contract,implementation:{kind:'legacy',legacy_ref:reference()},dependencies:[]},
  {certification:'certified',lifecycle:'active'});
 return createCapabilitySnapshot(owner,[capabilityRef(cap)],[cap]);
}
function child(path,input){
 return new Promise((resolve,reject)=>{
  const processChild=spawn(process.env.SSS_PYTHON??'python3',[path],{stdio:['pipe','pipe','pipe']});
  let output='',error='';processChild.stdout.on('data',b=>output+=b);processChild.stderr.on('data',b=>error+=b);
  processChild.on('error',reject);processChild.on('close',code=>{
   if(code!==0)reject(Error('count_native_failed'));else {try{resolve(JSON.parse(output));}catch(e){reject(e);}}
  });processChild.stdin.end(JSON.stringify(input));
 });
}
export async function execute(snapshot,root,input,{taskId,mode}){
 const owner=snapshot.owner,{host,request}=diagnosticHost(taskId);
 host.taskId=taskId;host.grant.taskId=taskId;request.payload.task_id=taskId;host.obligations.clear();
 for(const record of host.currentEvidence.values())record.payload.task_id=taskId;
 const registry=new Map(snapshot.capabilities.map(c=>[c.id,c]));
 const backend={inspect:()=>reference(),request(call,args){
  const record=structuredClone(request);Object.assign(record.payload,{id:call.callId,arguments_sha256:hash(JSON.stringify(args)),obligation_ref:'obligation-'+call.callId});
  host.obligations.set(record.payload.obligation_ref,{taskId:host.taskId,operation:record.payload.operation,argumentsSha256:record.payload.arguments_sha256,stateVersion:host.stateVersion,dependencies:record.payload.dependencies});return record;
 },async execute(call,operation,args){
  return {value:await child(code,args),receipt:{call_id:call.callId,operation,status:'succeeded'}};
 }};
 const grant={id:'diagnostic-validation-'+taskId,taskId:host.taskId,owner,snapshotDigest:snapshot.digest,root,revoked:false};
 const runtime=createCapabilityRuntime({taskId:host.taskId,owner,snapshot,readHost:()=>host,readCapability:ref=>registry.get(ref.id),
  backends:{artifact_motif:backend},...(mode==='validate'?{readValidationGrant:()=>grant}:{})});
 const result=await runtime.execute(root,input);
 const execution={format:'count_conformance_trace_v1',task_id:host.taskId,owner,mode,grant_id:grant.id,
  snapshot_sha256:snapshot.digest,root,arguments_sha256:capabilityDigest(input),...result};
 return {execution,artifacts:[{name:'counts.json',bytes:Buffer.from(JSON.stringify(result.result))}]};
}
export async function checkResult(input,run){
 const result=await child(checker,{input,artifact:Buffer.from(run.artifacts[0].bytes).toString('utf8')});
 return {...result,evidence_binding:{trace_sha256:hash(JSON.stringify(run.execution))}};
}
