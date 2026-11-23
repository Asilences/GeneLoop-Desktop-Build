import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
const options={skip:!process.features?.typescript};
const root=new URL('../',import.meta.url),library=new URL('motif-libraries/',root);
const release=new URL('file-management/',library);
const compatibility=JSON.parse(readFileSync(new URL('config/file-management-runtime-compatibility.json',root))).runtime_validators;
function currentRuntime(manifest){
 return Object.fromEntries(Object.keys(manifest.runtime_source).map(name=>{
  const current=compatibility[name]?.path??name;
  return [current,createHash('sha256').update(readFileSync(new URL(current,root))).digest('hex')];
 }));
}
test('current File seed rejects altered witnesses',options,async()=>{
 const {validatePublicManagementSeed}=await import('../src/adapters/management_seed.ts');
 // This verifies publication provenance. Admission and execution separately
 // compare the policy's tool contracts and execution version with the task.
 assert.ok(!readdirSync(library).some(name=>/^file-v[1-9][0-9]*$/.test(name)));
 const manifest=JSON.parse(readFileSync(new URL('entry.json',release)));
 const runtime=currentRuntime(manifest);
 assert.ok(manifest.entries.length > 0);
 for(const entry of manifest.entries){
  const bytes=readFileSync(new URL(entry.payload,release)),policy=JSON.parse(bytes),cert=JSON.parse(readFileSync(new URL(entry.certificate,release)));
  const sha=createHash('sha256').update(bytes).digest('hex');
  assert.doesNotThrow(()=>validatePublicManagementSeed(policy,cert,sha,runtime));
  assert.throws(()=>validatePublicManagementSeed(policy,{...cert,grants_execution:true},sha,runtime));
  assert.throws(()=>validatePublicManagementSeed(policy,{...cert,witnesses:cert.witnesses.map((row,index)=>index?row:{...row,accepted:false})},sha,runtime));
  assert.throws(()=>validatePublicManagementSeed(policy,cert,sha,{...runtime,'fake-source':'changed'}));
 }
});

test('current File seed cannot acquire execution authority with changed source bytes',options,async()=>{
 const {validatePublicManagementSeed}=await import('../src/adapters/management_seed.ts');
 const manifest=JSON.parse(readFileSync(new URL('entry.json',release)));
 const entry=manifest.entries[0],bytes=readFileSync(new URL(entry.payload,release));
 const runtime=currentRuntime(manifest);
 runtime[Object.keys(runtime)[0]]='0'.repeat(64);
 assert.throws(()=>validatePublicManagementSeed(JSON.parse(bytes),JSON.parse(readFileSync(new URL(entry.certificate,release))),createHash('sha256').update(bytes).digest('hex'),runtime),/seed source\/manifest changed/);
});
