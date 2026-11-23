import test from 'node:test';
import assert from 'node:assert/strict';

test('PPT follow-up reserves editable drafts before optional page previews',{skip:!process.features?.typescript},async()=>{
 const {prioritizePptDeliveries}=await import('../src/adapters/ppt/delivery/ppt_master_recovery.ts');
 const rows=[{row:{name:'older.pptx'}},{row:{name:'newer.pptx'}},{row:{name:'newer.pdf'}},
  ...Array.from({length:15},(_,i)=>({row:{name:`page-${i+1}.png`}}))];
 const before=JSON.stringify(rows),ordered=prioritizePptDeliveries(rows);
 assert.deepEqual(ordered.slice(0,3).map(r=>r.row.name),['newer.pptx','older.pptx','newer.pdf']);
 assert.equal(JSON.stringify(rows),before);
 // Two originals and one newly uploaded image leave five of the eight slots.
 assert.ok(ordered.slice(0,5).some(r=>r.row.name==='newer.pptx'));
 assert.equal(ordered.length,rows.length,'ordering does not silently delete a source');
});

test('textual DSML recovers only after real tool results, with a hard task limit', {skip:!process.features?.typescript},async()=>{
 const {createPptMasterRecovery}=await import('../src/adapters/ppt/delivery/ppt_master_recovery.ts');
 const r=createPptMasterRecovery();
 const malformed=()=>{r.begin();for(const text of ['<parameter name="edit">','x','</｜DS','ML｜ invoke>'])r.observe({type:'text-delta',text,index:0});r.observe({type:'finish',reason:{kind:'stop'}});};
 malformed();assert.equal(r.stop(false,{unfinished:false}),null);
 const result=r.stop(false,{unfinished:true});assert.equal(result.reason,'tool_call_as_text');
 assert.equal(result.truncated,false);assert.match(result.instruction,/原生调用/);
 assert.equal(Object.hasOwn(result,'arguments'),false,'text must not become executable arguments');
 malformed();assert.equal(r.stop(false,{unfinished:true}),null,'no repeated repair without an actual tool result');
 r.observeResult({callId:'first-real-call'});malformed();assert.equal(r.stop(false,{unfinished:true}).reason,'tool_call_as_text');
 r.observeResult({callId:'first-real-call'});malformed();assert.equal(r.stop(false,{unfinished:true}),null,'duplicate result is not progress');
 r.observeResult({callId:'second-real-call'});malformed();assert.equal(r.stop(false,{unfinished:true}).reason,'tool_call_as_text');
 r.observeResult({callId:'third-real-call'});malformed();assert.equal(r.stop(false,{unfinished:true}),null,'at most three format repairs in a task');
 const cancelled=createPptMasterRecovery();cancelled.begin();cancelled.observe({type:'block-end',block:{type:'text',text:'</｜DSML｜ invoke>'}});
 cancelled.observe({type:'finish',reason:{kind:'stop'}});assert.equal(cancelled.stop(true,{unfinished:true}),null);
});

test('ordinary prose and actual tool calls do not trigger format recovery', {skip:!process.features?.typescript},async()=>{
 const {createPptMasterRecovery}=await import('../src/adapters/ppt/delivery/ppt_master_recovery.ts');
 for(const native of [true,false]){
  const r=createPptMasterRecovery();r.begin();r.observe({type:'text-delta',text:native?'</｜DSML｜ invoke>':'The DSML format is discussed on page 3.',index:0});
  if(native)r.observe({type:'tool-call-delta',name:'edit'});
  r.observe({type:'finish',reason:{kind:'stop'}});assert.equal(r.stop(false,{unfinished:true}),null);
 }
});

test('a real preparation followed only by a promise gets one bounded same-task delivery continuation', {skip:!process.features?.typescript},async()=>{
 const {createPptMasterRecovery}=await import('../src/adapters/ppt/delivery/ppt_master_recovery.ts');
 for(const text of ["Now I'll build the complete deck. I've planned 19 slides.",
  'I need to stage the figures into the project and add the target slide count.','接下来制作完整的PPT。']){
  const r=createPptMasterRecovery();r.observeResult({callId:'real-material-read'});
  const stop=()=>{r.begin();r.observe({type:'block-end',block:{type:'text',text}});r.observe({type:'finish',reason:{kind:'stop'}});};
  stop();const result=r.stop(false,{unfinished:true});assert.equal(result.reason,'delivery_incomplete');
  assert.match(result.instruction,/复用已读材料/);assert.match(result.instruction,/patch_ppt/);assert.equal(Object.hasOwn(result,'arguments'),false);
  r.observeResult({callId:'more-real-progress'});stop();assert.equal(r.stop(false,{unfinished:true}),null,'one completion repair per task');
 }
});

test('delivery repair respects successful delivery, cancellation, missing progress, actual calls and refusals', {skip:!process.features?.typescript},async()=>{
 const {createPptMasterRecovery}=await import('../src/adapters/ppt/delivery/ppt_master_recovery.ts');
 for(const mode of ['complete','cancel','no-progress','native-call','refusal','clarification']){
  const r=createPptMasterRecovery();if(mode!=='no-progress')r.observeResult({callId:'read'});r.begin();
  r.observe({type:'text-delta',text:mode==='refusal'?"I cannot access this source. I'll build it after permission.":mode==='clarification'?'请提供关键数据，接下来制作PPT。':"Now I'll build the complete deck."});
  if(mode==='native-call')r.observe({type:'tool-call-delta'});
  r.observe({type:'finish',reason:{kind:'stop'}});
  assert.equal(r.stop(mode==='cancel',{unfinished:mode!=='complete'}),null,mode);
 }
});
test('provider length recovery keeps native tool continuation, stops on final/error/cancel', {skip:!process.features?.typescript}, async()=>{
 const {createPptMasterRecovery}=await import('../src/adapters/ppt/delivery/ppt_master_recovery.ts');
 const r=createPptMasterRecovery();r.begin();r.observe({type:'finish',reason:{kind:'tool-calls'}});assert.equal(r.stop(false),null);
 r.begin();r.observe({type:'finish',reason:{kind:'max-tokens'}});assert.equal(r.stop(false).truncated,true);assert.equal(r.stop(false),null);
 r.begin();r.observe({type:'finish',reason:{kind:'tool-calls'}});assert.equal(r.stop(false).continuation,2);
 for(const kind of ['stop','error','aborted']){r.begin();r.observe({type:'finish',reason:{kind}});assert.equal(r.stop(false),null);}
 r.begin();r.observe({type:'finish',reason:{kind:'max-tokens'}});assert.equal(r.stop(true),null);
});
