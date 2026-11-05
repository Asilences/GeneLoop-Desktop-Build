import assert from 'node:assert/strict';
import { mkdtempSync, realpathSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Context } from '@deepseek-ai/cordis';
import { LocalSubprocessRuntime } from '@deepseek-ai/dsh-subprocess-local';
const runtime=resolve(process.env.GENELOOP_NATIVE_RUNTIME || 'runtime-bundle');
const {runNativeProcess}=await import(pathToFileURL(join(runtime,'native-process.mjs')).href);
const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-cancel-')));
const ctx=new Context();new LocalSubprocessRuntime(ctx);
const abort=new AbortController();
process.env.GENELOOP_CREDENTIAL_PROBE_TOKEN='synthetic-probe-only';
const grandchild="const fs=require('node:fs');setInterval(()=>fs.appendFileSync('heartbeat','.'),50)";
const program=`if(process.env.GENELOOP_CREDENTIAL_PROBE_TOKEN)throw Error('credential inherited');
const{spawn}=require('node:child_process');const fs=require('node:fs');
const child=spawn(process.execPath,['-e',${JSON.stringify(grandchild)}],{stdio:'ignore',windowsHide:true});
fs.writeFileSync('ready',String(child.pid));setInterval(()=>{},1000);`;
try {
  const running=runNativeProcess(ctx,[process.execPath,'-e',program],root,abort.signal);
  const outcome=running.then(()=>({resolved:true}),error=>({error}));
  const deadline=Date.now()+15_000;
  while(!existsSync(join(root,'heartbeat'))) {
    assert.ok(Date.now()<deadline,'孙进程未启动');
    await new Promise(done=>setTimeout(done,50));
  }
  abort.abort();
  assert.ok((await outcome).error,'取消必须使正在执行的工具失败');
  const before=readFileSync(join(root,'heartbeat')).length;
  await new Promise(done=>setTimeout(done,500));
  assert.equal(readFileSync(join(root,'heartbeat')).length,before,'取消后仍有孙进程运行');
  console.log(JSON.stringify({diagnostic:true,platform:process.platform,arch:process.arch,
    credentialScrubbed:true,cancelled:true,grandchildStopped:true}));
} finally {
  delete process.env.GENELOOP_CREDENTIAL_PROBE_TOKEN;
  abort.abort();await ctx.fiber.dispose();
  assert.ok(root.startsWith(realpathSync(tmpdir())));rmSync(root,{recursive:true,force:true});
}
