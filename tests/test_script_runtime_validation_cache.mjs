/** Request-cache/mutation diagnostics. Worker replies are deterministic stubs;
 * actual sandbox replay remains a separate Linux verification. No models. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,cpSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {scriptCodeLocks} from '../src/adapters/script_motif_runtime.ts';
import * as runtime from '../src/adapters/script_capability_runtime.ts';
import {capabilityDigest,capabilityRef,createCapability,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
import {bytesSha256 as sha} from '../src/adapters/rsi_protocol.ts';
import {SCRIPT_FAILURE_FRAME,scriptWorkerFailure} from '../src/adapters/script_worker_failure.mjs';

const unsupported=process.platform==='win32',sourceRoot=resolve('.');

function fixture(t,api=runtime,codeRoot=sourceRoot){
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'script-validation-cache-')));
 t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const work=join(dir,'work');mkdirSync(join(work,'inputs'),{recursive:true});
 const input=join(work,'inputs/test.txt');writeFileSync(input,'alpha\nbeta\n');
 const identity={version:1,language:'python',template:"import json\nprint(json.dumps({'lines':len(open('__MOTIF_INPUT_0__').read().splitlines())}))",
  inputs:[{suffix:'.txt',format:'text'}]};
 const program={...identity,id:'script_'+digest(identity).slice(0,24),description:'Diagnostic line count',
  certification:{passed:true,cases:2,source_equivalent:true,program_sha256:digest(identity),
   output_schema:{type:'object',properties:{lines:{type:'number'}},required:['lines'],additionalProperties:false}}};
 const body={kind:'sandboxed_script_motif_library',version:1,programs:[program],
  code_locks:Object.fromEntries(scriptCodeLocks.map(path=>[path,sha(readFileSync(join(codeRoot,path)))]))};
 const library=join(dir,'library.json');writeFileSync(library,JSON.stringify({...body,digest:digest(body)}));
 const catalog=api.buildScriptCapabilities(library,'owner'),leaf=catalog.capabilities[0],ref=capabilityRef(leaf);
 const composed=createCapability({owner:'owner',contract:leaf.contract,
  implementation:{kind:'composition',steps:[{id:'first',capability:ref,arguments:{kind:'input',path:[]}},
   {id:'second',capability:ref,arguments:{kind:'input',path:[]}}],output:{kind:'step',step_id:'second',path:[]}},dependencies:[ref]},
  {lifecycle:'active',certification:'certified',migration:'promoted'});
 const snapshot=createCapabilitySnapshot('owner',[capabilityRef(composed)],[leaf,composed]);
 const registry=join(dir,'registry.json');writeFileSync(registry,JSON.stringify(snapshot));
 const args={paths:['/work/inputs/test.txt']},manifestPath=join(dir,'manifest.json');
 const manifest={format:'script_capability_task_v1',task_id:'task',owner:'owner',workspace:work,registry_path:registry,
  libraries:[{path:library,sha256:sha(readFileSync(library))}],inputs:[{path:args.paths[0],sha256:sha(readFileSync(input))}],
  grant:{id:'grant',task_id:'task',snapshot_sha256:snapshot.digest,root:capabilityRef(composed),
   arguments_sha256:capabilityDigest(args),effects:['read'],revoked:false,mode:'execute'}};
 const save=()=>writeFileSync(manifestPath,JSON.stringify(manifest));save();
 return {dir,work,input,library,registry,catalog,body,leaf,composed,snapshot,args,manifest,manifestPath,save,api,codeRoot};
}

function stubWorker(t,hook=()=>{}){
 let calls=0;
 const mock=t.mock.method(childProcess,'spawn',()=>{
  const child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();child.stdin=new EventEmitter();
  child.stdin.end=raw=>setImmediate(()=>{
   const job=JSON.parse(raw),action=hook(job,++calls);
   if(action?.failed){
    if(action.preexistingDiagnostic)writeFileSync(join(job.workspace,'failure.json'),'existing diagnostic');
    const diagnostic=scriptWorkerFailure(Error('script_sandbox_failed: Traceback\n  File "<stdin>", line 12\nTypeError: diagnostic'));
    child.stderr.write(SCRIPT_FAILURE_FRAME+JSON.stringify(diagnostic)+'\n');child.emit('close',1);return;
   }
   const output=JSON.stringify({lines:2});
   child.stdout.write(JSON.stringify({kind:'script_motif_receipt',nonce:job.nonce,program_id:job.program.id,
    versions:job.versions,output,output_sha256:sha(output),network_evidence:[],elapsed_ms:0}));
   child.emit('close',0);
  });
  return child;
 });
 syncBuiltinESMExports();t.after(()=>{mock.mock.restore();syncBuiltinESMExports();});
 return ()=>calls;
}

test('request-local cache parses stable material and registry once while preserving native catalog shape',{skip:unsupported},async t=>{
 const f=fixture(t),libraryText=readFileSync(f.library,'utf8'),registryText=readFileSync(f.registry,'utf8');
 assert.equal(Object.hasOwn(f.catalog,'library'),false);assert.equal(Object.hasOwn(f.catalog,'programs'),false);
 const parse=JSON.parse;let libraryParses=0,registryParses=0;
 t.mock.method(JSON,'parse',function(text,...args){if(text===libraryText)libraryParses++;if(text===registryText)registryParses++;return parse.call(this,text,...args);});
 const calls=stubWorker(t);
 const first=await f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args);
 assert.equal(first.status,'succeeded',JSON.stringify(first));assert.equal(calls(),2);
 assert.deepEqual(first.result.value,{lines:2});assert.equal(libraryParses,1);assert.equal(registryParses,1);
 // No process/global cache may confer the first request's validation on a
 // second task invocation or another owner.
 const second=await f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args);
 assert.equal(second.status,'succeeded');assert.equal(libraryParses,2);assert.equal(registryParses,2);
});

test('changed valid registry bytes are revalidated rather than using a stale parsed entry',{skip:unsupported},async t=>{
 const f=fixture(t);let parses=0;const parse=JSON.parse;
 t.mock.method(JSON,'parse',function(text,...args){if(typeof text==='string'&&text.startsWith('{"format":"capability_snapshot_v1"'))parses++;return parse.call(this,text,...args);});
 stubWorker(t,(_job,call)=>{if(call===1)writeFileSync(f.registry,readFileSync(f.registry)+'\n');});
 const trace=await f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args);
 assert.equal(trace.status,'succeeded');assert.equal(parses,2);
});

test('the same exact library remains independently mapped for another owner',{skip:unsupported},async t=>{
 const f=fixture(t);stubWorker(t);
 assert.equal((await f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args)).status,'succeeded');
 const other=f.api.buildScriptCapabilities(f.library,'another-owner');
 const registry=join(f.dir,'other-registry.json');writeFileSync(registry,JSON.stringify(other.snapshot));
 f.manifest.owner='another-owner';f.manifest.registry_path=registry;
 f.manifest.grant.root=other.roots[0];f.manifest.grant.snapshot_sha256=other.snapshot.digest;f.save();
 const trace=await f.api.runScriptCapability(f.manifestPath,other.snapshot,f.args);
 assert.equal(trace.status,'succeeded');assert.equal(trace.owner,'another-owner');
 assert.equal(trace.receipts[0].capability.id,other.roots[0].id);
 assert.notEqual(other.roots[0].id,f.catalog.roots[0].id);
});

for(const mutation of ['library','registry','input','grant']){
 test('live '+mutation+' mutation after a worker cannot be hidden by cached validation',{skip:unsupported},async t=>{
  const f=fixture(t);
  const calls=stubWorker(t,(_job,call)=>{
   if(call!==1)return;
   if(mutation==='library')writeFileSync(f.library,readFileSync(f.library)+' ');
   if(mutation==='registry'){
    const changed=f.snapshot.capabilities.map(c=>c.id===f.leaf.id?{...c,certification:'rejected'}:c);
    writeFileSync(f.registry,JSON.stringify(createCapabilitySnapshot('owner',f.snapshot.roots,changed)));
   }
   if(mutation==='input')writeFileSync(f.input,'changed\n');
   if(mutation==='grant'){f.manifest.grant.revoked=true;f.save();}
  });
  const trace=await f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args);
  assert.notEqual(trace.status,'succeeded',JSON.stringify(trace));assert.equal(calls(),1);
  assert.ok(trace.receipts.some(r=>r.reason&&/library_changed|not_certified|evidence|input_changed|permission_denied/.test(r.reason)),JSON.stringify(trace));
 });
}

test('an invalid expected material hash on a new invocation cannot reuse the old request cache',{skip:unsupported},async t=>{
 const f=fixture(t);stubWorker(t);
 assert.equal((await f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args)).status,'succeeded');
 f.manifest.libraries[0].sha256='0'.repeat(64);f.save();
 await assert.rejects(f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args),/script_material_library_changed/);
});

test('failure sidecar IO is optional and must not replace the original worker error',{skip:unsupported},async t=>{
 const f=fixture(t);stubWorker(t,()=>({failed:true,preexistingDiagnostic:true}));
 const trace=await f.api.runScriptCapability(f.manifestPath,f.snapshot,f.args);
 assert.equal(trace.status,'failed');assert.ok(trace.receipts.some(r=>r.reason==='script_worker_failed'),JSON.stringify(trace));
});

test('actual executor or compatibility policy changes invalidate cached validation in an isolated source copy',{skip:unsupported},async t=>{
 const isolated=realpathSync(mkdtempSync(join(tmpdir(),'script-cache-code-')));t.after(()=>rmSync(isolated,{recursive:true,force:true}));
 for(const name of ['src','scripts','config','schemas'])cpSync(join(sourceRoot,name),join(isolated,name),{recursive:true});
 symlinkSync(realpathSync(join(sourceRoot,'node_modules')),join(isolated,'node_modules'),'dir');
 const api=await import(pathToFileURL(join(isolated,'src/adapters/script_capability_runtime.ts')).href);
 for(const file of ['src/adapters/capability_runtime.ts','config/script-runtime-compatibility.json'])await t.test(file,async child=>{
  const f=fixture(child,api,isolated),path=join(isolated,file),original=readFileSync(path);
  // Only this private copy is touched. The real shared checkout/locks never
  // change while the suite or other agents are running.
  const worker=stubWorker(child,(_job,call)=>{if(call===1)writeFileSync(path,Buffer.concat([original,Buffer.from('\n')]));});
  try{
   const trace=await api.runScriptCapability(f.manifestPath,f.snapshot,f.args);
   assert.notEqual(trace.status,'succeeded');assert.equal(worker(),1);
   assert.ok(trace.receipts.some(r=>r.reason==='script_capability_executor_changed'),JSON.stringify(trace));
  }finally{writeFileSync(path,original);}
 });
});
