/** Diagnostic execution only: real fixed subprocesses, synthetic authority.
 * These checks establish dispatch/dataflow/guards, not learned or model gains.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createCapability,capabilityRef,capabilityIdentity,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {createCapabilityRuntime} from '../src/adapters/capability_runtime.ts';
import {bytesSha256} from '../src/adapters/rsi_protocol.ts';
import {diagnosticHost} from '../examples/rsi-protocol-v1/host.mjs';

const owner='diagnostic-owner',active={lifecycle:'active',certification:'certified',migration:'testing'};
const rows={type:'array',items:{type:'object',properties:{group:{type:'string'}},required:['group'],additionalProperties:false}};
const counts={type:'object',properties:Object.fromEntries(['A','B','C'].map(key=>[key,{type:'integer'}])),additionalProperties:false};
const output={type:'object',properties:{counts},required:['counts'],additionalProperties:false};
const obj=fields=>({kind:'object',fields}),input=(...path)=>({kind:'input',path});
const step=(step_id,...path)=>({kind:'step',step_id,path});
const argumentsValue={first:[{group:'A'},{group:'A'}],second:[{group:'A'},{group:'B'}]};
function setup(){
 const programs=new Map([
  ['count',fileURLToPath(new URL('../examples/rsi-protocol-v1/group_count.py',import.meta.url))],
  ['sum',fileURLToPath(new URL('./fixtures/capability_sum_counts.py',import.meta.url))],
 ]);
 const refs=new Map([...programs].map(([name,path])=>[name,{backend:'artifact_motif',
  library_sha256:bytesSha256('diagnostic-registry-v1'),library_digest:bytesSha256('diagnostic-library-v1'),
  object_id:name,object_sha256:bytesSha256(readFileSync(path)),certificate_sha256:bytesSha256('diagnostic-certificate-v1')} ]));
 const count=createCapability({owner,contract:{input_schema:{type:'object',properties:{rows},required:['rows'],additionalProperties:false},output_schema:output,effects:['read']},implementation:{kind:'legacy',legacy_ref:refs.get('count')},dependencies:[]},active);
 const sum=createCapability({owner,contract:{input_schema:{type:'object',properties:{left:counts,right:counts},required:['left','right'],additionalProperties:false},output_schema:output,effects:['read']},implementation:{kind:'legacy',legacy_ref:refs.get('sum')},dependencies:[]},active);
 const root=createCapability({owner,contract:{input_schema:{type:'object',properties:{first:rows,second:rows},required:['first','second'],additionalProperties:false},output_schema:output,effects:['read']},implementation:{kind:'composition',steps:[
  {id:'left',capability:capabilityRef(count),arguments:obj({rows:input('first')})},
  {id:'right',capability:capabilityRef(count),arguments:obj({rows:input('second')})},
  {id:'combined',capability:capabilityRef(sum),arguments:obj({left:step('left','counts'),right:step('right','counts')})},
 ],output:step('combined',)},dependencies:[capabilityRef(count),capabilityRef(sum)]},active);
 const capabilities=[root,count,sum],registry=new Map(capabilities.map(c=>[c.id,structuredClone(c)]));
 const snapshot=createCapabilitySnapshot(owner,[capabilityRef(root)],capabilities);
 const {host,request:template}=diagnosticHost();
 const operatorTemplate=structuredClone(host.operators.get('group-count').record);
 host.operators.clear();host.currentCodeSha256.clear();
 for(const [name,path] of programs){
  const operator=structuredClone(operatorTemplate);
  Object.assign(operator.payload,{id:name,operation:name,code_sha256:bytesSha256(readFileSync(path)),input_schema:{type:'object'},output_schema:{type:'object'}});
  host.operators.set(name,{record:operator,certified:true});
  host.currentCodeSha256.set(name,operator.payload.code_sha256);
 }
 host.grant.operations=['count','sum'];
 const executed=[];
 const backend={
  inspect(reference){
   const actual=structuredClone(refs.get(reference.object_id));
   actual.object_sha256=bytesSha256(readFileSync(programs.get(reference.object_id)));
   return actual;
  },
  request(call,args){
   const operation=call.capability.implementation.legacy_ref.object_id;
   const request=structuredClone(template);
   Object.assign(request.payload,{id:call.callId,operation,operator_id:operation,arguments_sha256:bytesSha256(JSON.stringify(args)),obligation_ref:'diagnostic-obligation-'+call.callId});
   // Synthetic independent host chooses each operation; runtime never creates authority.
   host.obligations.set(request.payload.obligation_ref,{taskId:host.taskId,operation,argumentsSha256:request.payload.arguments_sha256,stateVersion:host.stateVersion,dependencies:structuredClone(request.payload.dependencies)});
   return request;
  },
  async execute(call,operation,args){
   const result=spawnSync(process.env.SSS_PYTHON??'python3',[programs.get(operation)],{input:JSON.stringify(args),encoding:'utf8'});
   assert.equal(result.status,0,result.stderr);
   const value=JSON.parse(result.stdout);
   executed.push({operation,args:structuredClone(args),value});
   return {value,receipt:{call_id:call.callId,operation,status:'succeeded'}};
  },
 };
 const options={taskId:host.taskId,owner,snapshot,readHost:()=>host,readCapability:ref=>registry.get(ref.id),backends:{artifact_motif:backend}};
 return {root,count,sum,registry,snapshot,host,refs,backend,options,executed};
}

test('actual three-call execution consumes two predecessor results and emits linked receipts',async()=>{
 const s=setup(),runtime=createCapabilityRuntime(s.options);
 const result=await runtime.execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'succeeded');assert.deepEqual(result.result,{counts:{A:3,B:1}});
 assert.deepEqual(s.executed.map(x=>x.operation),['count','count','sum']);
 assert.deepEqual(s.executed[2].args,{left:{A:2},right:{A:1,B:1}});
 assert.equal(result.receipts.length,4);
 const [root,...children]=result.receipts;
 assert.deepEqual(root.child_call_ids,children.map(x=>x.call_id));
 for(const child of children){
  assert.equal(child.parent_call_id,root.call_id);assert.equal(child.dispatched,true);
  assert.equal(child.backend_receipt.call_id,child.call_id);
  assert.deepEqual(child.events.map(x=>x.payload.phase),['started','succeeded']);
  assert.equal(child.events[1].payload.result_sha256,child.result_sha256);
  assert.equal(child.snapshot_sha256,s.snapshot.digest);
  assert.ok(Number.isFinite(child.duration_ms)&&child.duration_ms>=0);
 }
 const changed=await runtime.execute(capabilityRef(s.root),{...argumentsValue,second:[{group:'C'}]});
 assert.deepEqual(changed.result,{counts:{A:2,C:1}});
});

test('task snapshot is private and registry revisions cannot silently drift',async()=>{
 const s=setup(),runtime=createCapabilityRuntime(s.options);
 s.snapshot.capabilities.length=0;runtime.snapshot().capabilities.length=0;
 assert.equal((await runtime.execute(capabilityRef(s.root),argumentsValue)).status,'succeeded');
 const changed=createCapability({...capabilityIdentity(s.count),contract:{...s.count.contract,effects:['read','workspace_write']}},active);
 s.registry.set(s.count.id,changed);
 const rejected=await runtime.execute(capabilityRef(s.root),argumentsValue);
 assert.equal(rejected.receipts[0].reason,'capability_revision_changed');assert.equal(s.executed.length,3);
});

for(const [name,mutate,reason] of [
 ['revocation',s=>{s.host.grant.revoked=true;},'capability_permission_denied'],
 ['effect removal',s=>{s.host.grant.effects=[];},'capability_permission_denied'],
 ['state change',s=>{s.host.stateVersion='new-state';},'capability_state_changed'],
 ['component drift',s=>{s.host.versions.motif.sha256='f'.repeat(64);},'capability_component_version_changed'],
 ['certificate revocation',s=>{s.registry.get(s.count.id).certification='rejected';},'capability_not_certified'],
 ['build only root',s=>{s.registry.get(s.root.id).lifecycle='build_only';},'capability_not_executable'],
 ['native certificate drift',s=>{s.refs.get('sum').certificate_sha256='f'.repeat(64);},'capability_legacy_changed'],
])test(name+' rejects before any backend dispatch',async()=>{
 const s=setup(),runtime=createCapabilityRuntime(s.options);mutate(s);
 const result=await runtime.execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'rejected');assert.equal(result.receipts[0].reason,reason);assert.equal(s.executed.length,0);
});

for(const lifecycle of ['build_only','archived'])test(lifecycle+' dependency stays executable through its certified root',async()=>{
 const s=setup();
 s.registry.get(s.count.id).lifecycle=lifecycle;
 s.options.snapshot=createCapabilitySnapshot(owner,[capabilityRef(s.root)],[...s.registry.values()]);
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'succeeded');assert.deepEqual(result.result,{counts:{A:3,B:1}});
});

for(const lifecycle of ['build_only','archived'])test('an admitted root finishes after '+lifecycle+' and cannot be selected by the next call',async()=>{
 const s=setup(),execute=s.backend.execute;
 s.backend.execute=async(...args)=>{
  const native=await execute(...args);
  if(s.executed.length===1)s.registry.get(s.root.id).lifecycle=lifecycle;
  return native;
 };
 const runtime=createCapabilityRuntime(s.options);
 const admitted=await runtime.execute(capabilityRef(s.root),argumentsValue);
 assert.equal(admitted.status,'succeeded');assert.deepEqual(admitted.result,{counts:{A:3,B:1}});
 assert.equal(s.executed.length,3);assert.ok(admitted.receipts.every(receipt=>receipt.status==='succeeded'));
 const next=await runtime.execute(capabilityRef(s.root),argumentsValue);
 assert.equal(next.status,'rejected');assert.equal(next.receipts[0].reason,'capability_not_executable');
 assert.equal(s.executed.length,3);
});

test('promotion of the same revisions does not interrupt actual multi-step execution or rewrite its snapshot',async()=>{
 const s=setup(),execute=s.backend.execute;
 s.backend.execute=async(...args)=>{
  const native=await execute(...args);
  if(s.executed.length===1)for(const capability of s.registry.values())capability.migration='promoted';
  return native;
 };
 const runtime=createCapabilityRuntime(s.options);
 const result=await runtime.execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'succeeded');assert.deepEqual(result.result,{counts:{A:3,B:1}});
 assert.equal(s.executed.length,3);
 assert.ok(runtime.snapshot().capabilities.every(capability=>capability.migration==='testing'));
 assert.ok(result.receipts.every(receipt=>receipt.snapshot_sha256===s.snapshot.digest));
});

test('live guards and native inspection cover only the selected root dependency closure',async()=>{
 const s=setup(),reads=[],inspections=[];
 const unused=createCapability({...capabilityIdentity(s.count),
  contract:{...s.count.contract,effects:['workspace_write']},
  implementation:{kind:'legacy',legacy_ref:{...s.count.implementation.legacy_ref,object_id:'unused'}}},active);
 s.registry.set(unused.id,{...unused,certification:'rejected'});
 s.options.snapshot=createCapabilitySnapshot(owner,[capabilityRef(s.root),capabilityRef(unused)],
  [s.root,s.count,s.sum,unused]);
 s.options.readCapability=ref=>{reads.push(ref.id);return s.registry.get(ref.id);};
 const inspect=s.backend.inspect;
 s.backend.inspect=ref=>{inspections.push(ref.object_id);return inspect(ref);};
 const runtime=createCapabilityRuntime(s.options);
 const result=await runtime.execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'succeeded');assert.equal(s.executed.length,3);
 assert.equal(reads.includes(unused.id),false);assert.equal(inspections.includes('unused'),false);
 assert.ok(reads.includes(s.count.id)&&reads.includes(s.sum.id));
 const rejected=await runtime.execute(capabilityRef(unused),{rows:[]});
 assert.equal(rejected.status,'rejected');assert.equal(rejected.receipts[0].reason,'capability_not_certified');
 assert.equal(s.executed.length,3);
});

for(const [name,mutate,reason] of [
 ['dependency certificate',s=>{s.registry.get(s.sum.id).certification='rejected';},'capability_not_certified'],
 ['permission',s=>{s.host.grant.revoked=true;},'capability_permission_denied'],
 ['immutable revision',s=>{s.registry.set(s.sum.id,createCapability({...capabilityIdentity(s.sum),
   contract:{...s.sum.contract,output_schema:{type:'object'}}},active));},'capability_revision_changed'],
 ['current evidence',s=>{for(const record of s.host.currentEvidence.values())record.payload.status='invalidated';},'evidence_invalidated'],
])test('admission never freezes away a later '+name+' invalidation',async()=>{
 const s=setup(),execute=s.backend.execute;
 s.backend.execute=async(...args)=>{
  const native=await execute(...args);if(s.executed.length===1)mutate(s);return native;
 };
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'failed');assert.equal(result.receipts[0].reason,reason);
 assert.equal(s.executed.length,1);assert.equal(result.receipts[1].events.at(-1).payload.phase,'succeeded');
 assert.equal(result.result,null);
});

test('invalid typed inputs reject and never dispatch',async()=>{
 const s=setup(),runtime=createCapabilityRuntime(s.options);
 const result=await runtime.execute(capabilityRef(s.root),{first:[{group:1}],second:[]});
 assert.equal(result.receipts[0].reason,'capability_input_schema_invalid');assert.equal(s.executed.length,0);
});

test('non-JSON arguments remain visible as rejected attempts with unknown argument digest',async()=>{
 for(const input of [undefined,{...argumentsValue,bad:NaN},{...argumentsValue,bad:()=>{}}]){
  const s=setup(),runtime=createCapabilityRuntime(s.options);
  const result=await runtime.execute(capabilityRef(s.root),input);
  assert.equal(result.status,'rejected');assert.equal(result.receipts.length,1);
  assert.equal(result.receipts[0].arguments_sha256,null);assert.ok(result.receipts[0].reason);
  assert.equal(result.receipts[0].dispatched,false);assert.equal(s.executed.length,0);
 }
});

test('permission revoked during request preparation is rechecked at dispatch boundary',async()=>{
 const s=setup(),request=s.backend.request;
 s.backend.request=(...args)=>{const value=request(...args);s.host.grant.revoked=true;return value;};
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'rejected');assert.equal(s.executed.length,0);
});

test('cancellation before dispatch differs from interruption after actual work; no successors replay',async()=>{
 const s=setup(),controller=new AbortController();controller.abort();
 let result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue,{signal:controller.signal});
 assert.equal(result.status,'cancelled');assert.equal(s.executed.length,0);
 const t=setup(),during=new AbortController(),execute=t.backend.execute;
 t.backend.execute=async(...args)=>{const value=await execute(...args);during.abort();return value;};
 result=await createCapabilityRuntime(t.options).execute(capabilityRef(t.root),argumentsValue,{signal:during.signal});
 assert.equal(result.status,'interrupted');assert.equal(t.executed.length,1);
 assert.equal(result.receipts[1].events.at(-1).payload.phase,'succeeded');
 assert.ok(result.receipts[1].result_sha256);assert.equal(result.result,null);
});

test('a materialization result without a native execution receipt cannot count as execution success',async()=>{
 const s=setup();s.backend.execute=async()=>({value:{source:'not executed'}});
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'failed');assert.equal(result.receipts[1].reason,'capability_backend_receipt_invalid');
 assert.equal(result.receipts[1].backend_receipt,null);assert.equal(result.result,null);
});

test('failed native call preserves execution failure evidence and stops dependent work',async()=>{
 const s=setup();s.backend.execute=async()=>{throw Error('diagnostic-native-failure');};
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'failed');assert.equal(result.receipts.length,2);
 assert.deepEqual(result.receipts[1].events.map(x=>x.payload.phase),['started','failed']);
 assert.equal(result.receipts[1].reason,'diagnostic-native-failure');
});

test('invalid native output is retained as failure evidence and never becomes successor input',async()=>{
 const s=setup(),execute=s.backend.execute;
 s.backend.execute=async(...args)=>{
  const native=await execute(...args);native.value={counts:{A:'wrong-type'}};return native;
 };
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'failed');assert.equal(s.executed.length,1);
 assert.equal(result.receipts[1].reason,'capability_output_schema_invalid');
 assert.ok(result.receipts[1].result_sha256);assert.equal(result.result,null);
});

test('late library drift stops successors after retaining already completed work',async()=>{
 const s=setup(),execute=s.backend.execute;
 s.backend.execute=async(...args)=>{
  const native=await execute(...args);s.refs.get('sum').library_sha256='f'.repeat(64);return native;
 };
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(s.root),argumentsValue);
 assert.equal(result.status,'failed');assert.equal(s.executed.length,1);
 assert.equal(result.receipts[1].reason,'capability_legacy_changed');
 assert.equal(result.receipts[1].events.at(-1).payload.phase,'succeeded');
 assert.equal(result.receipts[0].dispatched,true);
});

test('external writes remain disabled even when a capability and host declare permission',async()=>{
 const s=setup();
 const external=createCapability({...capabilityIdentity(s.count),contract:{...s.count.contract,effects:['read','external_write']}},active);
 s.registry.set(external.id,external);s.host.grant.effects.push('external_write');
 s.options.snapshot=createCapabilitySnapshot(owner,[capabilityRef(external)],[external]);
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(external),{rows:[]});
 assert.equal(result.receipts[0].reason,'capability_external_write_not_enabled');assert.equal(s.executed.length,0);
});

test('Python compiler output requires independent diagnostic certification before TypeScript execution',async()=>{
 const s=setup(),directory=mkdtempSync(join(tmpdir(),'capability-runtime-'));
 try{
  const proposal={format:'capability_compose_proposal_v1',owner,contract:s.root.contract,
   steps:s.root.implementation.steps,output:s.root.implementation.output};
  const construction=createCapabilitySnapshot(owner,[capabilityRef(s.count),capabilityRef(s.sum)],[s.count,s.sum]);
  const proposalPath=join(directory,'proposal.json'),constructionPath=join(directory,'construction.json'),outputPath=join(directory,'candidate.json');
  writeFileSync(proposalPath,JSON.stringify(proposal));writeFileSync(constructionPath,JSON.stringify(construction));
  const compiled=spawnSync(process.execPath,['scripts/project.mjs','python','scripts/build-capability.py',
   '--proposal',proposalPath,'--construction-snapshot',constructionPath,'--owner',owner,'--output',outputPath],
  {cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8'});
  assert.equal(compiled.status,0,compiled.stderr);
  const built=JSON.parse(readFileSync(outputPath,'utf8'));
  assert.equal(built.capability.certification,'candidate');assert.equal(built.capability.lifecycle,'build_only');
  s.registry.set(built.capability.id,built.capability);s.options.snapshot=built.snapshot;
  const rejected=await createCapabilityRuntime(s.options).execute(capabilityRef(built.capability),argumentsValue);
  assert.equal(rejected.receipts[0].reason,'capability_not_certified');assert.equal(s.executed.length,0);
  // Explicit synthetic host decision. Neither compiler nor runtime self-certifies.
  const certified={...built.capability,...active};s.registry.set(certified.id,certified);
  s.options.snapshot=createCapabilitySnapshot(owner,[capabilityRef(certified)],[certified,s.count,s.sum]);
  const result=await createCapabilityRuntime(s.options).execute(capabilityRef(certified),argumentsValue);
  assert.equal(result.status,'succeeded');assert.deepEqual(result.result,{counts:{A:3,B:1}});
  assert.equal(result.receipts.length,4);
 }finally{rmSync(directory,{recursive:true,force:true});}
});

test('independent validation grant executes the bound candidate without upgrading certification',async()=>{
 const s=setup(),candidate={...s.root,certification:'candidate',lifecycle:'build_only'};
 s.registry.set(candidate.id,candidate);
 s.options.snapshot=createCapabilitySnapshot(owner,[capabilityRef(candidate)],[candidate,s.count,s.sum]);
 const grant={id:'trusted-validation',taskId:s.host.taskId,owner,snapshotDigest:s.options.snapshot.digest,
  root:capabilityRef(candidate),revoked:false};
 s.options.readValidationGrant=()=>grant;
 const result=await createCapabilityRuntime(s.options).execute(capabilityRef(candidate),argumentsValue);
 assert.equal(result.status,'succeeded');assert.equal(s.executed.length,3);
 assert.equal(s.registry.get(candidate.id).certification,'candidate');
 const ordinary={...s.options};delete ordinary.readValidationGrant;
 const rejected=await createCapabilityRuntime(ordinary).execute(capabilityRef(candidate),argumentsValue);
 assert.equal(rejected.status,'rejected');assert.equal(rejected.receipts[0].reason,'capability_not_certified');
});

test('validation authorization cannot cover another snapshot or candidate dependency and is revocable',async()=>{
 for(const variant of ['snapshot','dependency','revoked-during']){
  const s=setup(),candidate={...s.root,certification:'candidate',lifecycle:'build_only'};
  s.registry.set(candidate.id,candidate);
  if(variant==='dependency')s.registry.get(s.count.id).certification='candidate';
  s.options.snapshot=createCapabilitySnapshot(owner,[capabilityRef(candidate)],[...s.registry.values()]);
  const grant={id:'trusted-validation',taskId:s.host.taskId,owner,snapshotDigest:variant==='snapshot'?'f'.repeat(64):s.options.snapshot.digest,
   root:capabilityRef(candidate),revoked:false};
  s.options.readValidationGrant=()=>grant;
  if(variant==='revoked-during'){
   const execute=s.backend.execute;s.backend.execute=async(...args)=>{const result=await execute(...args);grant.revoked=true;return result;};
  }
  const result=await createCapabilityRuntime(s.options).execute(capabilityRef(candidate),argumentsValue);
  assert.notEqual(result.status,'succeeded');assert.equal(s.executed.length,variant==='revoked-during'?1:0);
  assert.equal(result.receipts[0].reason,variant==='dependency'?'capability_not_certified':'capability_validation_grant_invalid');
 }
});
