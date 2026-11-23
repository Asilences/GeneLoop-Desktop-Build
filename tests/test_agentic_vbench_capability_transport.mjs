import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {apply} from '../scenarios/agentic_vbench/capability_tools.ts';

function fixture(){
 const directory=mkdtempSync(join(tmpdir(),'video-cap-native-')),file=join(directory,'tools.json'),saved={...process.env};
 writeFileSync(file,JSON.stringify([{name:'capability_call',description:'transport fixture',parameters:{type:'object'}}]));
 process.env.GENELOOP_VIDEO_CAPABILITY_TOOLS=file;process.env.GENELOOP_VIDEO_CAPABILITY_REPLIES=directory;
 let tool;apply({tools:{register:value=>tool=value}});
 return {directory,tool,close(){process.env=saved;rmSync(directory,{recursive:true,force:true});}};
}

test('native tool returns the original host reply only for matching name, call and arguments',async()=>{
 const f=fixture();
 try{
  const args={capability_id:'fixture',input_files:['/workspace/current.json']};
  const reply={call_id:'call-1',name:'capability_call',arguments:args,value:{status:'succeeded',receipt:{path:'original-runtime-trace',sha256:'fixture'}}};
  writeFileSync(join(f.directory,'call-1.json'),JSON.stringify(reply));
  assert.deepEqual(await f.tool.execute(args,{callId:'call-1'}),reply.value);
  await assert.rejects(f.tool.execute({...args,capability_id:'other'},{callId:'call-1'}),/reply_mismatch/);
  await assert.rejects(f.tool.execute(args,{callId:'../outside'}),/call_invalid/);
 }finally{f.close();}
});

test('pending native transport respects cancellation without inventing a Runtime result',async()=>{
 const f=fixture();
 try{
  const cancel=new AbortController();cancel.abort();
  await assert.rejects(f.tool.execute({capability_id:'fixture'},{callId:'call-absent',signal:cancel.signal}),{name:'AbortError'});
 }finally{f.close();}
});
