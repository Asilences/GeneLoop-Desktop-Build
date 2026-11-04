/** Synthetic certificate/permission diagnostics, with native sandbox execution on Linux. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {artifactLocks,identity,hash} from '../src/adapters/artifact_motif_runtime.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {buildArtifactCapabilities,runArtifactCapability} from '../src/adapters/artifact_capability_runtime.ts';
import {capabilityDigest,capabilityRef} from '../src/adapters/capability_contract.ts';
import {pptPublicCapabilities,pptPublicCatalog} from '../src/adapters/ppt_capability_online.ts';
const root=resolve(import.meta.dirname,'..');
const save=(path,value)=>writeFileSync(path,JSON.stringify(value));
function fixture(){
 const directory=mkdtempSync(join(tmpdir(),'artifact-capability-')),workspace=join(directory,'workspace');
 for(const name of ['inputs','code','outputs/code','command-tmp'])mkdirSync(join(workspace,name),{recursive:true});
 const source='import json,sys\nfrom pathlib import Path\nd=json.load(open(sys.argv[1]))\no=Path(sys.argv[2]);o.mkdir()\n(o/"title.txt").write_text(d["title"],encoding="utf-8")\n';
 const program={version:1,source,source_sha256:hash(source),inputs:[{suffix:'.json',format:'json',shape:{object:{title:'string'}}}],
  dependencies:{},input_argument_indices:[0],output_argument_index:1,argument_count:2,language:'python',execution_policy:'fresh_output_network_disabled_v1'};
 const version=digest(identity(program));program.id='artifact_'+version.slice(0,24);
 program.certification={passed:true,distinct_inputs:2,source_equivalent:true,program_sha256:version};
 const body={kind:'witnessed_artifact_program_library',version:1,scene:'ppt',programs:[program],
  code_locks:Object.fromEntries(artifactLocks.map(path=>[path,hash(readFileSync(join(root,path)))]))};
 const library=join(directory,'library.json');save(library,{...body,digest:digest(body)});
 const catalog=buildArtifactCapabilities(library,'owner'),snapshot=catalog.snapshot;
 const registry=join(directory,'registry.json');save(registry,snapshot);
 const input=join(workspace,'inputs/current.json');writeFileSync(input,'{"title":"Independent current title"}');
 const args={inputs:['/work/inputs/current.json'],output:'/work/outputs/current'};
 const manifest={format:'artifact_capability_task_v1',task_id:'current-task',owner:'owner',workspace,libraries:[{path:library,sha256:hash(readFileSync(library))}],
  registry_path:registry,inputs:[{path:'/work/inputs/current.json',sha256:hash(readFileSync(input))}],resources:{},
  grant:{id:'own-grant',task_id:'current-task',root:snapshot.roots[0],snapshot_sha256:snapshot.digest,
   arguments_sha256:capabilityDigest(args),effects:['workspace_write'],mode:'execute',revoked:false}};
 const path=join(directory,'manifest.json');save(path,manifest);
 return {directory,workspace,library,catalog,snapshot,args,manifest,path,registry,input};
}
test('native catalog checks original code locks, exact bytes and owner identity',()=>{
 const f=fixture(),before=readFileSync(f.library);
 assert.equal(f.catalog.capabilities[0].certification,'certified');
 assert.notDeepEqual(buildArtifactCapabilities(f.library,'other').roots,f.snapshot.roots);
 assert.throws(()=>buildArtifactCapabilities(f.library,'owner','0'.repeat(64)),/library_changed/);
 const changed=JSON.parse(before);changed.code_locks[artifactLocks[0]]='0'.repeat(64);
 const {digest:old,...body}=changed;save(f.library,{...body,digest:digest(body)});
 assert.throws(()=>buildArtifactCapabilities(f.library,'owner'),/artifact_code_changed/);
});
test('revoked permission, changed input and foreign registry fail before native dispatch',async()=>{
 for(const mutation of ['revoked','input','registry']){
  const f=fixture();
  if(mutation==='revoked'){f.manifest.grant.revoked=true;save(f.path,f.manifest);}
  if(mutation==='input')writeFileSync(f.input,'{"title":"changed"}');
  if(mutation==='registry')save(f.registry,buildArtifactCapabilities(f.library,'other').snapshot);
  if(mutation==='registry'){
   const result=await runArtifactCapability(f.path,f.snapshot,f.args);
   assert.notEqual(result.status,'succeeded');assert.equal(result.receipts[0].dispatched,false);
  }else await assert.rejects(()=>runArtifactCapability(f.path,f.snapshot,f.args),/grant_invalid|input_changed/);
 }
});
const namespace=process.platform==='linux'&&spawnSync('bwrap',['--unshare-user','--ro-bind','/','/','--unshare-net','/usr/bin/true']).status===0;
test('public Runtime executes the certified native program on current bytes',{skip:!namespace},async()=>{
 const f=fixture(),result=await runArtifactCapability(f.path,f.snapshot,f.args);
 assert.equal(result.status,'succeeded',JSON.stringify(result));
 assert.equal(readFileSync(join(f.workspace,'outputs/code/current/title.txt'),'utf8'),'Independent current title');
 assert.equal(result.receipts[0].backend_receipt.native_receipt.program_id,result.result.program_id);
 assert.equal(result.owner,'owner');
});
test('online catalog denies a changed snapshot and never exposes unregistered roots',()=>{
 const f=fixture(),path=join(f.directory,'public.json');save(path,f.snapshot);
 const selection={user:'owner',public_capabilities:{snapshot:{path,sha256:hash(readFileSync(path))},roots:[f.snapshot.roots[0]]}};
 assert.throws(()=>pptPublicCapabilities(selection),/not_published/);
 writeFileSync(path,'{}');assert.throws(()=>pptPublicCapabilities(selection),/snapshot_changed/);
});
test('current parameter grant is evidence even without uploaded files, while file bindings still require versions',async()=>{
 const f=fixture();f.manifest.inputs=[];save(f.path,f.manifest);
 const result=await runArtifactCapability(f.path,f.snapshot,f.args);
 assert.equal(result.receipts[0].dispatched,true);
 assert.match(result.receipts[0].reason,/input_not_granted/);
 assert.ok(result.receipts[0].events.length>0);
});
test('public wrapper catalog references the existing native schema instead of duplicating it',()=>{
 const schema={type:'object',properties:{title:{type:'string'}},required:['title']};
 const native={id:'native-cap',implementation:{kind:'legacy',legacy_ref:{backend:'artifact_motif',object_id:'page-program'}}};
 const cap={id:'public-cap',dependencies:[{id:native.id}],contract:{input_schema:{properties:{parameters:schema}}}};
 const state={roots:[cap],snapshot:{capabilities:[native,cap]}},library={programs:[{id:'page-program',component:{parameters_schema:schema}}]};
 assert.deepEqual(pptPublicCatalog(state,library),[{id:'public-cap',parameters_from_program:'page-program'}]);
 cap.contract.input_schema.properties.parameters={type:'object'};
 assert.deepEqual(pptPublicCatalog(state,library),[{id:'public-cap',parameters_schema:{type:'object'}}]);
});
