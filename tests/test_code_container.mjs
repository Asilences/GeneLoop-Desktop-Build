/** Optional actual Docker/upstream execution checks, never call a paid model. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {runContainer} from '../src/adapters/harness/dsh_code_container.ts';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
const options={skip:process.env.SSS_TEST_CONTAINER!=='1'};
const image='node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e';

test('Actual upstream TypeScript backend preserves nested callback results and parallel completion',options,async()=>{
  const calls=[];
  const result=await runContainer({program:'const r=await Promise.all([tools.read({n:1}),tools.read({n:2})]); return r.map(x=>x.n);',
    bindings:[{global:'tools',functions:{read:async arg=>{calls.push(arg.n);return arg;}}}]},image);
  assert.deepEqual(result.value,[1,2]);assert.equal(result.error,undefined);assert.deepEqual(calls,[1,2]);
});

test('Host private files/environment are not mounted, network is disabled, and program cannot write the mounted runtime',options,async()=>{
  const directory=mkdtempSync(join(tmpdir(),'sss-private-probe-')),secret=join(directory,'key.txt');writeFileSync(secret,'fixture-never-exported');
  const previous=process.env.DEEPSEEK_API_KEY;process.env.DEEPSEEK_API_KEY='fixture-host-env';
  try {
    const result=await runContainer({program:`const fs=await import('node:fs'); let read=false,write=false,network=false;
      try{fs.readFileSync(${JSON.stringify(secret)});read=true;}catch{}
      try{fs.writeFileSync('/app/runner.mjs','changed');write=true;}catch{}
      try{await fetch('http://1.1.1.1',{signal:AbortSignal.timeout(300)});network=true;}catch{}
      return {read,write,network,key:Boolean(process.env.DEEPSEEK_API_KEY)};`,bindings:[]},image);
    assert.deepEqual(result.value,{read:false,write:false,network:false,key:false});
  } finally {if(previous===undefined)delete process.env.DEEPSEEK_API_KEY;else process.env.DEEPSEEK_API_KEY=previous;rmSync(directory,{recursive:true});}
});

test('Abort terminates the native worker/container and invalid images are rejected',options,async()=>{
  const controller=new AbortController();setTimeout(()=>controller.abort(),500);
  const result=await runContainer({program:'while(true){}',bindings:[],signal:controller.signal},image);
  assert.equal(result.error.kind,'abort');
  assert.throws(()=>runContainer({program:'return 1;',bindings:[]},'untrusted:latest'),/unapproved/);
});

test('Large UTF-8 tool bodies and File receipt logs survive both process exits intact',options,async()=>{
  const text='完整正文-'.repeat(24000);
  const child=spawn(process.execPath,['--experimental-strip-types',fileURLToPath(new URL('../src/adapters/file_script_runtime.ts',import.meta.url))],{stdio:['pipe','pipe','pipe']});
  let stderr='';child.stderr.on('data',b=>stderr+=b.toString());
  const lines=createInterface({input:child.stdout});
  const result=new Promise((resolve,reject)=>{
    let done=false;
    lines.on('line',line=>{
      try{
        const frame=JSON.parse(line);
        if(frame.type==='call')child.stdin.write(JSON.stringify({type:'response',id:frame.id,value:{text}})+'\n');
        else if(frame.type==='done'){done=true;resolve(frame.result);}
      }catch(e){reject(e);}
    });
    child.on('error',reject);
    child.on('close',code=>{if(!done)reject(Error(`missing complete receipt: ${code} ${stderr}`));});
  });
  child.stdin.write(JSON.stringify({type:'run',program:'const r=await files.call({name:"read_file",arguments:{}});console.log(JSON.stringify({text:r.text,length:r.text.length}));'})+'\n');
  try{
    const output=await result;assert.equal(output.error,undefined);
    const actual=JSON.parse(output.logs[0]);assert.equal(actual.text,text);assert.equal(actual.length,text.length);
  }finally{lines.close();child.stdin.end();if(child.exitCode===null)child.kill();}
});
