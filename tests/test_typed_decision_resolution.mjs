import test from 'node:test';
import assert from 'node:assert/strict';
const options={skip:!process.features?.typescript};
const packet={request:{state:'current evidence',questions:{a:{type:'noul',instructions:'A?'},b:{type:'noul',instructions:'B?'}}},owner:'toy',task_id:'toy',parent_call_id:'original'};
const primary=(values,rejected)=>({call_id:'primary',decision:{accepted:!rejected.length,values,rejected_questions:rejected,threshold:.9}});
test('complete JEV and zero accepted answers never add a compact model call',options,async()=>{
 const {resolveTypedQuestions}=await import('../src/adapters/typed_decision_resolution.ts');
 for(const first of [primary({a:true,b:false},[]),primary({},['a','b'])]){
  let calls=0;const r=await resolveTypedQuestions(packet,{provider:'jev'},async()=>{calls++;return first;});
  assert.equal(calls,1);assert.deepEqual(r.decision,first.decision);
 }
});
test('only unresolved questions go to compact DeepSeek, preserving accepted answers and evidence',options,async()=>{
 const {resolveTypedQuestions}=await import('../src/adapters/typed_decision_resolution.ts');const seen=[];
 const first=primary({a:false},['b']);
 const r=await resolveTypedQuestions(packet,{provider:'jev'},async(p,o)=>{
  seen.push({p,o});return seen.length===1?first:{call_id:'completion',parent_call_id:'primary',decision:{accepted:true,values:{b:true},rejected_questions:[],threshold:.9}};
 });
 assert.equal(seen[1].o.provider,'deepseek');assert.deepEqual(Object.keys(seen[1].p.request.questions),['b']);
 assert.equal(seen[1].p.request.state,packet.request.state);assert.equal(seen[1].p.owner,packet.owner);
 assert.equal(seen[1].p.parent_call_id,'primary');assert.equal(r.provider,'jev+deepseek');
 assert.deepEqual(r.decision.values,{a:false,b:true});assert.equal(r.decision.accepted,true);
 assert.deepEqual(first.decision.values,{a:false});
});
test('completion cannot overwrite accepted results or escape its original pending keys',options,async()=>{
 const {mergeResolvedQuestions}=await import('../src/adapters/typed_decision_resolution.ts');
 const first=primary({a:true},['b']);
 assert.throws(()=>mergeResolvedQuestions(packet,first,{parent_call_id:'primary',decision:{values:{a:false,b:true}}}));
 assert.throws(()=>mergeResolvedQuestions(packet,first,{parent_call_id:'another',decision:{values:{b:true}}}));
 const r=mergeResolvedQuestions(packet,first,{parent_call_id:'primary',decision:{values:{},accepted:false,rejected_questions:['b']}});
 assert.equal(r.accepted,false);assert.deepEqual(r.values,{a:true});assert.deepEqual(r.rejected_questions,['b']);
});
test('direct DeepSeek mode stays one call with no JEV preparation',options,async()=>{
 const {resolveTypedQuestions}=await import('../src/adapters/typed_decision_resolution.ts');let calls=0;
 await resolveTypedQuestions(packet,{provider:'deepseek'},async(p,o)=>{calls++;assert.equal(o.provider,'deepseek');return primary({a:true,b:true},[]);});
 assert.equal(calls,1);
});
