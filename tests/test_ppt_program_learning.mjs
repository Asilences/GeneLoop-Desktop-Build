/** Routing/ownership diagnostics; no model replies or measured cost claims. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,existsSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {installPptProgramLearning} from '../src/adapters/ppt_program_learning.ts';
import {artifactInvocation} from '../src/adapters/artifact_motif_runtime.ts';

test('Baseline records private program evidence but cannot resolve/execute a learned program',()=>{
 const output=mkdtempSync(join(tmpdir(),'ppt-program-route-')),workspace=join(output,'work');
 for(const path of ['inputs','code','outputs/code'])mkdirSync(join(workspace,path),{recursive:true});
 const handlers=new Map(),hooks=new Map(),variables=new Map();let guard,resolved=0;
 const task={request:{task_id:'a'.repeat(32),mode:'baseline'},selection:{rsi:true},status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},workspace,output,scene_options:{allow_output:true}};
 const agent={session:{id:'diag-ppt'},inject(){},ctx:{systemPrompt:{variable:(name,fn)=>variables.set(name,fn),section(){}},tools:{register(){},guard:fn=>{guard=fn;}},on:(name,fn)=>hooks.set(name,fn)}};
 installPptProgramLearning({tools:{register(){}},on:(name,fn)=>handlers.set(name,fn)},{current:()=>task,resolve:()=>{resolved++;throw Error('must not resolve');},resources:{},reused(){}});
 handlers.get('agent/created')({agent});
 assert.equal(variables.get('ppt_program_catalog')(),'');assert.equal(resolved,0);
 const execution={callId:'normal',name:'bash',arguments:{command:'python3 example.py'}};
 guard(execution);hooks.get('tools/result')(execution,{content:[],isError:false});
 assert.ok(existsSync(join(output,'reuse-boundaries.jsonl')));
 assert.equal(JSON.parse(readFileSync(join(output,'reuse-boundaries.jsonl'),'utf8')).call_id,'normal');
 assert.throws(()=>artifactInvocation('diag-ppt','geneloop-recipe {}'),/not_admitted/);
});

test('a cold execute task freezes its empty library; later pointers do not change it mid-task',()=>{
 const output=mkdtempSync(join(tmpdir(),'ppt-program-cold-')),workspace=join(output,'work');
 for(const path of ['inputs','code','outputs/code'])mkdirSync(join(workspace,path),{recursive:true});
 let calls=0;const handlers=new Map(),variables=new Map();
 const task={request:{task_id:'b'.repeat(32),mode:'execute'},selection:{rsi:true},status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},workspace,output,scene_options:{allow_output:true}};
 installPptProgramLearning({tools:{register(){}},on:(name,fn)=>handlers.set(name,fn)},{current:()=>task,resolve:()=>{calls++;return null;},resources:{},reused(){}});
 handlers.get('agent/created')({agent:{session:{id:'cold-ppt'},ctx:{systemPrompt:{variable:(n,f)=>variables.set(n,f),section(){}},tools:{register(){},guard(){}},on(){}},inject(){}}});
 assert.equal(variables.get('ppt_program_catalog')(),'');assert.equal(variables.get('ppt_program_catalog')(),'');assert.equal(calls,1);
 assert.equal(existsSync(join(output,'ppt-program-snapshot.json')),false);
});
