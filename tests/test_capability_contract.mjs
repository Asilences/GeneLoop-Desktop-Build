/** Cross-language contract diagnostics, never model effectiveness evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {createCapability,capabilityIdentity,capabilityDigest,validateCapability,validateCapabilitySnapshot,mapLegacyLibrary,capabilityRef,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
const python=process.env.SSS_PYTHON??(process.platform==='win32'?'python':'python3');
function fixture(){
 const run=spawnSync(python,['-c',`import json,base64
from tests.test_capability_contract import leaf,compose,legacy_fixture
from src.adapters.capability_contract import create_capability_snapshot,capability_ref,map_legacy_library,capability_digest
a,b=leaf(),leaf('b');c=compose([a,b]);d=compose([c])
legacy=[]
for backend in ['source_program','artifact_motif']:
 raw,sha=legacy_fixture(backend);legacy.append({'backend':backend,'raw':raw.decode(),'sha':sha,'mapped':map_legacy_library(raw,'owner',backend,sha)})
vectors=[{'𐀀':1e-7,'':1e-6,'中文':1.25},[1,0,1.0,-0.0,True,None],{'a':'\\n\\t\\u0000','é':9.75}]
print(json.dumps({'snapshot':create_capability_snapshot('owner',[capability_ref(d)],[a,b,c,d]),'legacy':legacy,'vectors':[{'value':x,'digest':capability_digest(x)} for x in vectors]},ensure_ascii=False))`],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);return JSON.parse(run.stdout);
}
const data=fixture();
test('empty initial library is valid without admitting unreferenced capabilities',()=>{
 const empty=createCapabilitySnapshot('owner',[],[]);
 assert.deepEqual(validateCapabilitySnapshot(empty),empty);
 assert.throws(()=>createCapabilitySnapshot('owner',[],[data.snapshot.capabilities[0]]),/snapshot_extra_capability/);
});
test('Python/TS agree on Unicode scalar order, decimal float64 values and legacy mapping',()=>{
 for(const v of data.vectors)assert.equal(capabilityDigest(v.value),v.digest);
 for(const v of data.legacy)assert.deepEqual(mapLegacyLibrary(v.raw,'owner',v.backend,v.sha),v.mapped);
 for(const v of [Infinity,NaN,Number.MAX_SAFE_INTEGER+1,'\ud800',undefined])assert.throws(()=>capabilityDigest(v));
 assert.equal(capabilityDigest([1,-0]),capabilityDigest([1.0,0]));
});
test('Python recursive snapshot validates and is reproducible in TS',()=>{
 const s=data.snapshot;assert.deepEqual(validateCapabilitySnapshot(s,'owner'),s);
 assert.deepEqual(createCapabilitySnapshot(s.owner,[...s.roots].reverse(),[...s.capabilities].reverse()),s);
 const clone=validateCapabilitySnapshot(s);clone.capabilities[0].owner='other';assert.equal(s.capabilities[0].owner,'owner');
});
test('tampered ownership, references, closure, dataflow and metadata digest fail closed',()=>{
 const s=data.snapshot,root=s.capabilities.find(c=>c.id===s.roots[0].id);
 for(const mutate of [x=>x.owner='foreign',x=>x.digest='0'.repeat(64),x=>x.roots.push(x.roots[0]),x=>x.capabilities.pop(),x=>x.capabilities.push(x.capabilities[0])]){
  const x=structuredClone(s);mutate(x);assert.throws(()=>validateCapabilitySnapshot(x,'owner'));
 }
 const changed=structuredClone(root);changed.implementation.steps[0].arguments={kind:'step',step_id:'absent',path:[]};assert.throws(()=>validateCapability(changed),/unavailable/);
 const states=structuredClone(root);states.certification='rejected';states.lifecycle='archived';assert.deepEqual(capabilityRef(states),capabilityRef(root));
 for(const legacy of data.legacy)assert.throws(()=>mapLegacyLibrary(legacy.raw+' ','owner',legacy.backend,legacy.sha),/bytes_changed/);
});

test('native legacy decimals and non-BMP metadata keys share the authoritative mapping path',()=>{
 const result=spawnSync(process.execPath,['--experimental-strip-types','tests/fixtures/capability_legacy_native.mjs'],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);const fixture=JSON.parse(result.stdout);
 assert.match(fixture.raw,/1\.0/);assert.match(fixture.raw,/0\.1/);
 assert.deepEqual(mapLegacyLibrary(fixture.raw,'owner','source_program',fixture.sha),fixture.mapped);
 const bridge=spawnSync(python,['-c',`import json,sys
from src.adapters.capability_contract import map_legacy_library
f=json.load(sys.stdin)
print(json.dumps(map_legacy_library(f['raw'],'owner','source_program',f['sha']),ensure_ascii=False))`],{input:result.stdout,encoding:'utf8'});
 assert.equal(bridge.status,0,bridge.stderr);assert.deepEqual(JSON.parse(bridge.stdout),fixture.mapped);
});

test("Python and TS have the same schema dialect and accept each other's wire output",()=>{
 const cases=JSON.parse(readFileSync(new URL('./fixtures/capability_dialect_cases.json',import.meta.url),'utf8'));
 const run=spawnSync(python,['-c',`import copy,json
from tests.test_capability_contract import leaf
from src.adapters.capability_contract import create_capability,capability_identity
cases=json.load(open('tests/fixtures/capability_dialect_cases.json'))
results=[]
for case in cases:
 definition=capability_identity(leaf());definition['contract']['input_schema']=case['schema']
 try:
  capability=create_capability(definition);results.append({'accepted':True,'capability':capability})
 except ValueError:results.append({'accepted':False})
print(json.dumps(results,ensure_ascii=False,allow_nan=False))`],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);const py=JSON.parse(run.stdout),ts=[];
 const leaf=data.snapshot.capabilities.find(c=>c.implementation.kind==='legacy');
 for(const [i,item] of cases.entries()){
  const definition=structuredClone(capabilityIdentity(leaf));definition.contract.input_schema=item.schema;
  let cap;try{cap=createCapability(definition);}catch{}
  assert.equal(Boolean(cap),item.accepted,item.name);assert.equal(py[i].accepted,item.accepted,item.name);
  if(cap){assert.deepEqual(validateCapability(py[i].capability),py[i].capability);ts.push(cap);}
 }
 const reverse=spawnSync(python,['-c',`import json,sys
from src.adapters.capability_contract import validate_capability
for capability in json.load(sys.stdin):validate_capability(capability,'owner')
print('accepted')`],{input:JSON.stringify(ts),encoding:'utf8'});
 assert.equal(reverse.status,0,reverse.stderr);assert.equal(reverse.stdout.trim(),'accepted');
});

test('new composition wire rejects negative zero even though canonical hashes equate zeros',()=>{
 const root=structuredClone(data.snapshot.capabilities.find(c=>c.implementation.kind==='composition'));
 root.implementation.steps[0].arguments={kind:'literal',value:-0};
 assert.throws(()=>validateCapability(root),/negative_zero/);
 const snapshot=structuredClone(data.snapshot);snapshot.capabilities[0].contract.output_schema.default=-0;
 assert.throws(()=>validateCapabilitySnapshot(snapshot),/negative_zero/);
});

test('Source sidecar mapping uses original native admission rules without certificate upgrades',()=>{
 const generated=spawnSync(process.execPath,['--experimental-strip-types','tests/fixtures/capability_native_validation.mjs'],{encoding:'utf8'});
 assert.equal(generated.status,0,generated.stderr);
 for(const item of JSON.parse(generated.stdout)){
  if(item.native_accepted){
   const cap=mapLegacyLibrary(item.raw,'owner','source_program',item.sha)[0];
   assert.equal(cap.certification,'candidate');assert.equal(cap.lifecycle,'build_only');
   assert.deepEqual(cap.contract.input_schema.required,['x','x']);
   assert.equal(cap.implementation.legacy_ref.library_sha256,item.sha);
  }else assert.throws(()=>mapLegacyLibrary(item.raw,'owner','source_program',item.sha),/source_program_changed/,item.name);
 }
});
