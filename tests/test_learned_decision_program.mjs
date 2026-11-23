import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
const options={skip:!process.features?.typescript};
const lit=x=>['lit',x],get=(x,k)=>['get',x,Array.isArray(k)?k:lit(k)],input=['var','input'];
function fixture(){
 const items=get(input,'items'),item=['var','row'];
 const candidate={format:'geneloop-learned-decision-v1',description:'diagnostic toy decision, not a learned File workflow',scope_description:'toy list',
  guard:['eq',get(input,'goal'),lit('choose')],
  request:['object',{state:input,questions:['map',items,'row',['object',{id:get(item,'key'),question:['object',{type:lit('noul'),instructions:lit('Does this item satisfy the supplied goal?')}]}]]}],
  bind:['object',{tool:lit('demo_select'),arguments:['object',{keys:['map',['filter',items,'row',['eq',get(get(input,'answers'),get(item,'key')),lit(true)]],'row',get(item,'key')]}]}],
  training_witnesses:[{snapshot_id:'toy',values:{a:true}}]};
 return candidate;
}
test('pure generic contracts bind new identities and different member counts',options,async()=>{
 const api=await import('../src/adapters/learned_decision_program.ts');const c=fixture();
 for(const n of [2,5]){
  const items=Array.from({length:n},(_,i)=>({key:'new-'+i,body:'current input '+i})),context={goal:'choose',items};
  const r=api.prepareLearnedDecision(c,context);assert.equal(Object.keys(r.questions).length,n);
  assert.deepEqual(api.bindLearnedDecision(c,context,{'new-1':true}).arguments,{keys:['new-1']});
 }
 assert.equal(api.prepareLearnedDecision(c,{goal:'other',items:[]}),null);
});
test('File decisions keep complete large context while legacy kernel defaults stay unchanged',options,async()=>{
 const api=await import('../src/adapters/learned_decision_program.ts');
 const kernel=await import('../src/adapters/paper_rsi_program.ts');
 const context={goal:'choose',items:[{key:'fresh',body:'current'}],large:'x'.repeat(250000)};
 assert.throws(()=>kernel.runProgram(input,context),/input_too_large/);
 const request=api.prepareLearnedDecision(fixture(),context);
 assert.equal(JSON.parse(request.state).large.length,250000);
 assert.equal(api.bindLearnedDecision(fixture(),context,{fresh:true}).arguments.keys[0],'fresh');
 assert.throws(()=>api.runLearnedProgram(['get',input,lit('constructor')],context),/unsafe_get/);
});
test('contracts cannot invoke host code or access prototype state',options,async()=>{
 const api=await import('../src/adapters/learned_decision_program.ts');const c=fixture();
 assert.throws(()=>api.validateLearnedDecision({...c,guard:['eval',lit('process.env')]}));
 assert.throws(()=>api.prepareLearnedDecision({...c,guard:['get',input,lit('constructor')]},{goal:'choose'}));
 assert.throws(()=>api.validateLearnedDecision({...c,source:'host authored code'}));
});
test('invalid and duplicate question IDs fail before any model/API call',options,async()=>{
 const api=await import('../src/adapters/learned_decision_program.ts');
 assert.throws(()=>api.prepareLearnedDecision(fixture(),{goal:'choose',items:[{key:'same'},{key:'same'}]}));
 assert.throws(()=>api.prepareLearnedDecision(fixture(),{goal:'choose',items:[]}));
});
test('offline diagnostics retain useful evidence for missing and invalid components',options,()=>{
 for(const candidate of [{guard:lit(false)},{request:['unsupported']},{}]){
  const result=spawnSync(process.execPath,['scripts/diagnose-learned-decision.mjs'],{
   input:JSON.stringify({candidate,context:{goal:'diagnostic'},values:{}}),encoding:'utf8',
  });
  assert.equal(result.status,0,result.stderr);
  const diagnostic=JSON.parse(result.stdout);
  assert.equal(diagnostic.task_tools_executed,false);
  assert.equal(diagnostic.candidate_modified,false);
  assert.equal(diagnostic.binding_expression.ok,false);
  assert.deepEqual(diagnostic.binding_bindings,[]);
  if(candidate.guard)assert.deepEqual(diagnostic.guard,{ok:true,value:false});
  else assert.equal(diagnostic.guard_validation.ok,false);
 }
});
test('component admission rejects whole candidates, unknown operations and scope expansion before another paid step',options,()=>{
 const check=(patch,allowed_components)=>{
  const r=spawnSync(process.execPath,['scripts/validate-learned-components.mjs'],{
   input:JSON.stringify({patch,allowed_components}),encoding:'utf8',
  });
  const v=JSON.parse(r.stdout);assert.equal(v.task_tools_executed,false);assert.equal(v.candidate_modified,false);return v;
 };
 assert.equal(check({request:fixture()},['request']).ok,false);
 assert.equal(check({bind:['eval',lit('host code')]},['bind']).ok,false);
 assert.equal(check({guard:lit(true)},['request']).ok,false);
 assert.equal(check({training_witnesses:[{snapshot_id:'actual-source',values:{x:{free:'object'}}}]},['training_witnesses']).ok,false);
 assert.equal(check({request:fixture().request},['request']).ok,true);
});
test('offline request admission uses the actual provider choice contract',options,()=>{
 const check=question=>{
  const r=spawnSync(process.execPath,['scripts/validate-learned-components.mjs'],{
   input:JSON.stringify({kind:'typed_request',request:{state:'current evidence',questions:{current:question}}}),encoding:'utf8',
  });
  return JSON.parse(r.stdout);
 };
 assert.equal(check({type:'choice',instructions:'Choose an interpretation',criteria:'not an option map',options:['a','b']}).ok,false);
 assert.equal(check({type:'choice',instructions:'Choose an interpretation',criteria:{category_ids:['a','b']}}).ok,false);
 assert.equal(check({type:'choice',instructions:'Choose an interpretation',criteria:{a:'Meaning A',b:'Meaning B'}}).ok,true);
});
