/** Cross-language contract diagnostics, never model effectiveness evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {capabilityDigest,validateCapability,validateCapabilitySnapshot,mapLegacyLibrary,capabilityRef,createCapabilitySnapshot} from '../src/adapters/capability_contract.ts';
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
