/** Local authority/catalog checks. Real render acceptance runs on Linux Docker. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {capabilityDigest} from '../src/adapters/capability_contract.ts';
import {buildSourceCapabilities,runSourceCapability,sourceCapabilityOutputSchema} from '../src/adapters/source_capability_runtime.ts';

function library(){
 const identity={format:'parameterized_source_program_v1',language:'tsx',template:'const p=__GENELOOP_PARAMETERS__;',
  parameters_schema:{type:'object',properties:{frames:{type:'integer'}},required:['frames'],additionalProperties:false}};
 const key=digest(identity),program={...identity,id:'source_'+key.slice(0,24),description:'Render the current bounded input',
  default_parameters:{frames:8},status:'certified',certification:{source_equivalent:true,program_identity:key}};
 const body={format:'source_program_library_v1',programs:[program]};
 return JSON.stringify({...body,digest:digest(body)});
}
function fixture(){
 const directory=realpathSync(mkdtempSync(join(tmpdir(),'source-capability-test-'))),raw=library();
 const catalog=buildSourceCapabilities(raw,'owner'),args={frames:8};
 const path=join(directory,'library.json'),registry=join(directory,'registry.json'),manifestPath=join(directory,'manifest.json');
 writeFileSync(path,raw);writeFileSync(registry,JSON.stringify(catalog.snapshot));
 const manifest={format:'source_capability_task_v1',task_id:'source-test',owner:'owner',workspace:directory,
  library_path:path,library_sha256:catalog.library_sha256,library_digest:catalog.library_digest,registry_path:registry,
  runtime_directory:directory,image:'not-started-diagnostic',inputs:[],grant:{id:'explicit-task-grant',task_id:'source-test',
   snapshot_sha256:catalog.snapshot.digest,root:catalog.roots[0],arguments_sha256:capabilityDigest(args),
   mode:'execute',effects:['workspace_write'],revoked:false}};
 writeFileSync(manifestPath,JSON.stringify(manifest));
 return {directory,catalog,args,manifest,manifestPath};
}

test('catalog exports exact native Source contracts and never grants an unverified library certification',()=>{
 const raw=library(),catalog=buildSourceCapabilities(raw,'owner');
 assert.equal(catalog.capabilities[0].certification,'certified');
 assert.deepEqual(catalog.capabilities[0].contract.output_schema,sourceCapabilityOutputSchema);
 assert.deepEqual(catalog.catalog[0].example_parameters,{frames:8});
 const changed=JSON.parse(raw);changed.programs[0].certification.source_equivalent=false;
 const {digest:_,...body}=changed;changed.digest=digest(body);
 assert.throws(()=>buildSourceCapabilities(JSON.stringify(changed),'owner'),/not_certified/);
});

test('offline catalog CLI exposes metadata without starting a worker',()=>{
 const f=fixture();try{
  const result=spawnSync(process.execPath,['scripts/run-source-capability.mjs','--catalog','--library',f.manifest.library_path,'--owner','owner'],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);assert.deepEqual(JSON.parse(result.stdout),f.catalog);
 }finally{rmSync(f.directory,{recursive:true,force:true});}
});

test('explicit task host builds real input evidence and cancellation rejects before a worker exists',async()=>{
 const f=fixture();try{
  const controller=new AbortController();controller.abort();
  const trace=await runSourceCapability(f.manifestPath,f.catalog.snapshot,f.args,{signal:controller.signal});
  assert.equal(trace.format,'source_capability_trace_v1');assert.equal(trace.status,'cancelled');
  assert.equal(trace.receipts.length,1);assert.equal(trace.receipts[0].dispatched,false);
  assert.equal(trace.arguments_sha256,capabilityDigest(f.args));assert.equal(trace.mode,'execute');
 }finally{rmSync(f.directory,{recursive:true,force:true});}
});

test('task authority binds snapshot, arguments, owner and granted effects before dispatch',async()=>{
 for(const change of [m=>m.grant.arguments_sha256='f'.repeat(64),m=>m.grant.snapshot_sha256='f'.repeat(64),
  m=>m.owner='foreign',m=>m.grant.effects.push('external_write'),m=>m.grant.revoked=true]){
  const f=fixture();try{
   change(f.manifest);writeFileSync(f.manifestPath,JSON.stringify(f.manifest));
   await assert.rejects(runSourceCapability(f.manifestPath,f.catalog.snapshot,f.args),/(grant_invalid|foreign_owner)/);
  }finally{rmSync(f.directory,{recursive:true,force:true});}
 }
});
