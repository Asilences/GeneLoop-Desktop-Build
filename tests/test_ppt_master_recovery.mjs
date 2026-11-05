import test from 'node:test';
import assert from 'node:assert/strict';

test('PPT follow-up reserves editable drafts before optional page previews',{skip:!process.features?.typescript},async()=>{
 const {prioritizePptDeliveries}=await import('../src/adapters/ppt_master_recovery.ts');
 const rows=[{row:{name:'older.pptx'}},{row:{name:'newer.pptx'}},{row:{name:'newer.pdf'}},
  ...Array.from({length:15},(_,i)=>({row:{name:`page-${i+1}.png`}}))];
 const before=JSON.stringify(rows),ordered=prioritizePptDeliveries(rows);
 assert.deepEqual(ordered.slice(0,3).map(r=>r.row.name),['newer.pptx','older.pptx','newer.pdf']);
 assert.equal(JSON.stringify(rows),before);
 // Two originals and one newly uploaded image leave five of the eight slots.
 assert.ok(ordered.slice(0,5).some(r=>r.row.name==='newer.pptx'));
 assert.equal(ordered.length,rows.length,'ordering does not silently delete a source');
});
test('provider length recovery keeps native tool continuation, stops on final/error/cancel', {skip:!process.features?.typescript}, async()=>{
 const {createPptMasterRecovery}=await import('../src/adapters/ppt_master_recovery.ts');
 const r=createPptMasterRecovery();r.begin();r.observe({type:'finish',reason:{kind:'tool-calls'}});assert.equal(r.stop(false),null);
 r.begin();r.observe({type:'finish',reason:{kind:'max-tokens'}});assert.equal(r.stop(false).truncated,true);assert.equal(r.stop(false),null);
 r.begin();r.observe({type:'finish',reason:{kind:'tool-calls'}});assert.equal(r.stop(false).continuation,2);
 for(const kind of ['stop','error','aborted']){r.begin();r.observe({type:'finish',reason:{kind}});assert.equal(r.stop(false),null);}
 r.begin();r.observe({type:'finish',reason:{kind:'max-tokens'}});assert.equal(r.stop(true),null);
});
