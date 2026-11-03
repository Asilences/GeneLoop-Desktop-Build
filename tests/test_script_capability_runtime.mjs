/** Diagnostic certificates/inputs. Actual sandbox execution is Linux opt-in. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {scriptCodeLocks,programIdentity,loadScriptLibrary} from '../src/adapters/script_motif_runtime.ts';
import {scriptProvenanceLocks} from '../src/adapters/script_runtime_compatibility.ts';
import {buildScriptCapabilities,runScriptCapability} from '../src/adapters/script_capability_runtime.ts';
import {capabilityDigest,capabilityRef,createCapability,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {bytesSha256 as sha} from '../src/adapters/rsi_protocol.ts';
import {extendCapabilitySeed} from '../src/adapters/capability_materials.ts';

function fixture(t){
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'script-capability-')));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const work=join(dir,'work');mkdirSync(join(work,'inputs'),{recursive:true});
 writeFileSync(join(work,'inputs','test.txt'),'alpha\nbeta\n');
 const identity={version:1,language:'python',template:"import json\nprint(json.dumps({'lines': len(open('__MOTIF_INPUT_0__').read().splitlines())}))",inputs:[{suffix:'.txt',format:'text'}]};
 const p={...identity,id:'script_'+digest(identity).slice(0,24),description:'Count input lines',certification:{passed:true,cases:2,
  source_equivalent:true,program_sha256:digest(identity),output_schema:{type:'object',properties:{lines:{type:'number'}},required:['lines'],additionalProperties:false}}};
 const body={kind:'sandboxed_script_motif_library',version:1,programs:[p],code_locks:Object.fromEntries(scriptCodeLocks.map(path=>[path,sha(readFileSync(path))]))};
 const library=join(dir,'library.json');
 const saveLibrary=()=>{writeFileSync(library,JSON.stringify({...body,digest:digest(body)}));return buildScriptCapabilities(library,'owner');};
 const catalog=saveLibrary(),args={paths:['/work/inputs/test.txt']},registry=join(dir,'registry.json'),manifestPath=join(dir,'manifest.json');
 writeFileSync(registry,JSON.stringify(catalog.snapshot));
 const manifest={format:'script_capability_task_v1',task_id:'task',owner:'owner',workspace:work,registry_path:registry,
  libraries:[{path:library,sha256:sha(readFileSync(library))}],inputs:[{path:args.paths[0],sha256:sha('alpha\nbeta\n')}],
  grant:{id:'grant',task_id:'task',snapshot_sha256:catalog.snapshot.digest,root:catalog.roots[0],arguments_sha256:capabilityDigest(args),
   effects:['read'],revoked:false,mode:'execute'}};
 const save=()=>writeFileSync(manifestPath,JSON.stringify(manifest));save();
 return {dir,work,body,library,saveLibrary,catalog,args,manifestPath,manifest,save};
}

test('old exact runtime hash is whitelisted; compiler provenance does not revoke executable certificates',t=>{
 const f=fixture(t),transition=JSON.parse(readFileSync('config/script-runtime-compatibility.json')).transitions[0];
 assert.equal(sha(readFileSync(transition.path)),transition.to_sha256);
 f.body.code_locks[transition.path]=transition.from_sha256;
 for(const path of scriptProvenanceLocks)f.body.code_locks[path]='a'.repeat(64);
 assert.equal(f.saveLibrary().capabilities.length,1);
 f.body.code_locks[transition.path]='b'.repeat(64);
 assert.throws(f.saveLibrary,/script_runtime_changed/);
});
test('unknown sandbox versions, changed program identity and invalid certificates remain rejected',t=>{
 for(const mutate of [f=>f.body.code_locks['src/adapters/script_motif_shell.ts']='c'.repeat(64),
  f=>f.body.programs[0].template+='\nprint(99)',f=>f.body.programs[0].certification.source_equivalent=false]){
  const f=fixture(t);mutate(f);assert.throws(f.saveLibrary,/(script_runtime_changed|uncertified_script)/);
 }
});
test('reviewed upload-limit transition preserves old Script material without admitting other versions',t=>{
 const f=fixture(t),transition=JSON.parse(readFileSync('config/script-runtime-compatibility.json')).transitions.find(r=>r.path==='src/adapters/reuse_mediation.ts');
 assert.ok(transition);assert.equal(sha(readFileSync(transition.path)),transition.to_sha256);
 const certificate=JSON.stringify(f.body.programs[0].certification);
 f.body.code_locks[transition.path]=transition.from_sha256;
 assert.equal(f.saveLibrary().capabilities.length,1);
 assert.equal(JSON.stringify(f.body.programs[0].certification),certificate);
 f.body.code_locks[transition.path]='f'.repeat(64);assert.throws(f.saveLibrary,/script_runtime_changed/);
});
test('catalog preserves native certificate and material registration makes Script available to Builder',t=>{
 const f=fixture(t),cap=f.catalog.capabilities[0];
 assert.equal(cap.implementation.legacy_ref.certificate_sha256,digest(f.body.programs[0].certification));
 assert.deepEqual(cap.contract.effects,['read']);assert.ok(cap.contract.output_schema.properties.value);
 const other=join(f.dir,'other.json');writeFileSync(other,readFileSync(f.library)+'\n');
 const ref={path:other,sha256:sha(readFileSync(other))};
 const merged=extendCapabilitySeed(f.catalog.snapshot,{owner:'owner',materials:[{owner:'owner',format:'capability_material_v1',backend:'script_motif',library:ref,evidence:[ref]}]});
 assert.equal(merged.snapshot.capabilities.length,2);assert.equal(merged.catalog.length,1);
});
test('unsupported argv or network programs are explicitly excluded from the new catalog',t=>{
 const f=fixture(t),p=f.body.programs[0];p.network_policy='fixed_metadata_get_v1';
 p.certification.program_sha256=digest(programIdentity(p));p.id='script_'+p.certification.program_sha256.slice(0,24);
 const catalog=f.saveLibrary();assert.equal(catalog.snapshot,null);assert.equal(catalog.excluded.length,1);
});
test('pre-cancelled execution dispatches no native worker',{skip:process.platform==='win32'},async t=>{
 const f=fixture(t),controller=new AbortController();controller.abort();
 const trace=await runScriptCapability(f.manifestPath,f.catalog.snapshot,f.args,{signal:controller.signal});
 assert.equal(trace.status,'cancelled');assert.equal(trace.receipts[0].dispatched,false);
});
test('host authority and input/library versions are checked before native dispatch',{skip:process.platform==='win32'},async t=>{
 for(const change of [f=>f.manifest.grant.revoked=true,f=>f.manifest.grant.effects=['external_write'],
  f=>f.manifest.grant.arguments_sha256='f'.repeat(64),f=>writeFileSync(join(f.work,'inputs/test.txt'),'changed'),
  f=>writeFileSync(f.library,readFileSync(f.library)+' ')]){
  const f=fixture(t);change(f);f.save();await assert.rejects(runScriptCapability(f.manifestPath,f.catalog.snapshot,f.args),/(grant_invalid|input_changed|library_changed)/);
 }
});
test('Windows catalog remains readable but native sandbox execution is explicitly unsupported',{skip:process.platform!=='win32'},async t=>{
 const f=fixture(t);assert.equal(f.catalog.capabilities.length,1);
 await assert.rejects(runScriptCapability(f.manifestPath,f.catalog.snapshot,f.args),/platform_unsupported/);
});
const sandbox=process.platform==='linux'&&existsSync('/usr/bin/bwrap')&&process.env.RUN_SCRIPT_CAPABILITY_SANDBOX==='1';
function valueFixture(t,items=[]){
 const f=fixture(t),p=f.body.programs[0];
 p.inputs=[{suffix:'.json',format:'json',shape:{object:{items:'array'}}}];
 p.template="import json\nx=json.load(open('__MOTIF_INPUT_0__'))\nprint(json.dumps({'items':x['items'],'count':len(x['items'])}))";
 p.certification.output_schema={type:'object',properties:{items:{type:'array'},count:{type:'number'}},required:['items','count'],additionalProperties:false};
 p.certification.value_binding={format:'script_json_value_binding_v1',input_schema:{type:'object',properties:{items:{type:'array'}},required:['items'],additionalProperties:false}};
 p.certification.program_sha256=digest(programIdentity(p));p.id='script_'+p.certification.program_sha256.slice(0,24);
 const catalog=f.saveLibrary(),leaf=catalog.capabilities.find(c=>c.contract.input_schema.properties.value);
 const args={value:{items}};
 f.manifest.libraries[0].sha256=catalog.library_sha256;
 f.manifest.grant.root=capabilityRef(leaf);f.manifest.grant.snapshot_sha256=catalog.snapshot.digest;f.manifest.grant.arguments_sha256=capabilityDigest(args);
 f.save();writeFileSync(f.manifest.registry_path,JSON.stringify(catalog.snapshot));
 return {...f,catalog,leaf,args};
}
test('JSON values require certified opt-in; old path catalog stays intact and malformed metadata is rejected',t=>{
 const f=valueFixture(t);assert.equal(f.catalog.capabilities.length,2);
 assert.ok(f.catalog.capabilities.some(c=>c.contract.input_schema.properties.paths));
 f.body.programs[0].certification.value_binding.format='unreviewed';assert.throws(f.saveLibrary,/invalid_script_value_binding/);
});
test('a fixed file with the wrong format reports a contract mismatch rather than a changed version',{skip:process.platform==='win32'},async t=>{
 const f=valueFixture(t),leaf=f.catalog.capabilities.find(c=>c.contract.input_schema.properties.paths),args={paths:['/work/inputs/test.txt']};
 f.manifest.grant.root=capabilityRef(leaf);f.manifest.grant.arguments_sha256=capabilityDigest(args);f.save();
 const trace=await runScriptCapability(f.manifestPath,f.catalog.snapshot,args);
 assert.equal(trace.status,'failed');assert.ok(trace.receipts.some(r=>r.reason==='script_capability_input_contract_mismatch'));
});
test('JSON result flow accepts new array contents, composes, and retains original file guards',{skip:!sandbox},async t=>{
 for(const items of [[],['new','values']]){
  const f=valueFixture(t,items),ref=capabilityRef(f.leaf);
  const cap=createCapability({owner:'owner',contract:f.leaf.contract,implementation:{kind:'composition',steps:[
   {id:'first',capability:ref,arguments:{kind:'input',path:[]}},
   {id:'second',capability:ref,arguments:{kind:'object',fields:{value:{kind:'object',fields:{items:{kind:'step',step_id:'first',path:['value','items']}}}}}}
  ],output:{kind:'step',step_id:'second',path:[]}},dependencies:[ref]},
  {certification:'certified',lifecycle:'active',migration:'promoted'});
  const snapshot=createCapabilitySnapshot('owner',[capabilityRef(cap)],[f.leaf,cap]);
  f.manifest.grant.root=capabilityRef(cap);f.manifest.grant.snapshot_sha256=snapshot.digest;f.save();
  writeFileSync(f.manifest.registry_path,JSON.stringify(snapshot));
  const trace=await runScriptCapability(f.manifestPath,snapshot,f.args);
  assert.equal(trace.status,'succeeded',JSON.stringify(trace));assert.equal(trace.result.value.count,items.length);
  const receipts=trace.receipts.filter(r=>r.kind==='legacy');assert.equal(receipts.length,2);
  for(const r of receipts)assert.deepEqual(r.backend_receipt.native_receipt.versions,[sha(JSON.stringify({items}))]);
  writeFileSync(join(f.work,'inputs/test.txt'),'changed');
  await assert.rejects(runScriptCapability(f.manifestPath,snapshot,f.args),/input_changed/);
 }
});
test('native sandbox executes composition, preserves input, and binds exact leaf receipts',{skip:!sandbox},async t=>{
 const f=fixture(t),leaf=f.catalog.capabilities[0];
 const cap=createCapability({owner:'owner',contract:leaf.contract,implementation:{kind:'composition',steps:[{id:'read',capability:capabilityRef(leaf),
  arguments:{kind:'input',path:[]}}],output:{kind:'step',step_id:'read',path:[]}},dependencies:[capabilityRef(leaf)]},{certification:'certified',lifecycle:'active',migration:'promoted'});
 const snapshot=createCapabilitySnapshot('owner',[capabilityRef(cap)],[leaf,cap]);
 f.manifest.grant.root=capabilityRef(cap);f.manifest.grant.snapshot_sha256=snapshot.digest;f.save();
 writeFileSync(f.manifest.registry_path,JSON.stringify(snapshot));
 const trace=await runScriptCapability(f.manifestPath,snapshot,f.args);
 assert.equal(trace.status,'succeeded',JSON.stringify(trace));assert.equal(trace.result.value.lines,2);
 const native=trace.receipts.find(r=>r.kind==='legacy').backend_receipt.native_receipt;
 assert.equal(native.script_version.library_sha256,f.catalog.library_sha256);assert.equal(native.output_sha256,sha(trace.result.stdout));
 assert.equal(readFileSync(join(f.work,'inputs/test.txt'),'utf8'),'alpha\nbeta\n');
});
