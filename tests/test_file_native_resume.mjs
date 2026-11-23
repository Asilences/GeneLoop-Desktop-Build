import test from 'node:test';
import assert from 'node:assert/strict';
const options={skip:!process.features?.typescript};
test('File SDK adapter delegates upstream creation to native resume of the exact original session',options,async()=>{
 const {recoveryContext}=await import('../src/adapters/harness/learning/dsh_file_resume.ts');const seen=[];
 const original={agents:{async create(){throw Error('cold start');},async resume(v){seen.push(v);return {real:true};},get(id){return id;}},other(){return this===original;}};
 const ctx=recoveryContext(original,'same');
 assert.equal(ctx.other(),true);assert.equal(ctx.agents.get('same'),'same');
 await assert.rejects(()=>ctx.agents.create({sessionId:'other'}),/original session/);
 assert.deepEqual(await ctx.agents.create({sessionId:'same',agentOptions:{model:'exact'}}),{real:true});
 assert.deepEqual(seen,[{resumeSessionId:'same',agentOptions:{model:'exact'}}]);
 await assert.rejects(()=>ctx.agents.create({sessionId:'same'}),/exactly once/);
});
test('restored learned receipts come only from actual successful native call/result pairs',options,async()=>{
 const {completedToolHistory}=await import('../src/adapters/file_management/file_recovery_state.ts');
 const call=(id,name='read')=>({type:'tool/call',data:{callId:id,name,arguments:'{"file_id":"current"}'}});
 const result=(id,error=false)=>({type:'tool/result',data:{message:{content:[{type:'tool-result',toolCallId:id,isError:error,content:[{type:'text',text:'{"text":"actual receipt"}'}]}]}}});
 const events=[call('a'),result('a'),call('b'),result('b',true),result('unknown'),call('')];
 assert.deepEqual(completedToolHistory(events),[{tool:'read',call_id:'a',args:{file_id:'current'},out:{text:'actual receipt'}}]);
 assert.throws(()=>completedToolHistory([call('a'),call('a')]),/duplicate/);
});
