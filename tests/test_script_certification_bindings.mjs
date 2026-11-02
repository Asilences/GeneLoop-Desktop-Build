/** Host binding diagnostics, not model quality or construction evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {heldoutBindings} from '../scripts/certify-script-motifs.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
function fixture(t){
 const work=realpathSync(mkdtempSync(join(tmpdir(),'explicit-heldout-')));mkdirSync(join(work,'inputs'));
 t.after(()=>rmSync(work,{recursive:true,force:true}));
 const rows=['before','after'].map((name,i)=>{
  const bytes=Buffer.from([80,75,3,4,i]);writeFileSync(join(work,'inputs',name+'.zip'),bytes);
  return {path:'/work/inputs/'+name+'.zip',sha256:sha(bytes),source:{path:'private-origin-'+i,sha256:sha(bytes)}};
 });
 const p={inputs:[{suffix:'.zip',format:'zip'},{suffix:'.zip',format:'zip'}],
  original_paths:['/work/inputs/after.zip','/work/inputs/before.zip'],witness:{files:{
   '/work/inputs/after.zip':{relative:'inputs/after.zip'},'/work/inputs/before.zip':{relative:'inputs/before.zip'}}}};
 return {work,rows,p};
}
test('explicit two-input certification follows witnessed slots rather than same-suffix guessing',t=>{
 const f=fixture(t);assert.throws(()=>heldoutBindings(f.p,{},f.work),/ambiguous_script_binding/);
 const bound=heldoutBindings(f.p,{explicit_inputs:f.rows},f.work);
 assert.deepEqual(bound.map(b=>b.path),['/work/inputs/after.zip','/work/inputs/before.zip']);
 assert.deepEqual(bound.map(b=>b.sha256),[f.rows[1].sha256,f.rows[0].sha256]);
});
test('changed hashes, duplicate roles, missing files and changed origin versions fail closed',t=>{
 for(const change of [f=>f.rows[0].sha256='0'.repeat(64),f=>f.rows[0].source.sha256='0'.repeat(64),
  f=>f.rows[1].path=f.rows[0].path,f=>f.rows.pop(),f=>f.rows[0].path='/work/inputs/other.zip',
  f=>writeFileSync(join(f.work,'inputs/before.zip'),'changed')]){
  const f=fixture(t);change(f);assert.throws(()=>heldoutBindings(f.p,{explicit_inputs:f.rows},f.work),/heldout_input_binding/);
 }
});
