// Official DSH tool execution without model calls. No quality/cost claim.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const app=resolve('.'),runtime=resolve(process.env.GENELOOP_NATIVE_RUNTIME||join(app,'runtime-bundle')),bundle=resolve(process.env.GENELOOP_NATIVE_TOOLS||join(app,'desktop-tools-bundle'));
const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-common-'))),workspace=join(root,'原始材料');mkdirSync(workspace);
writeFileSync(join(workspace,'sample.txt'),'unchanged');
const config={root,workspace,network:process.argv.includes('--network'),tools:{sourceRoot:join(bundle,'source'),skill:join(bundle,'ppt-master'),
  python:join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python'),
  soffice:join(bundle,process.platform==='win32'?'libreoffice/program/soffice.com':'libreoffice/Contents/MacOS/soffice')}};
writeFileSync(join(root,'config.json'),JSON.stringify(config));
const plugin=join(root,'diagnostic.mjs');
writeFileSync(plugin,`
import assert from 'node:assert/strict';import {readFileSync,writeFileSync} from 'node:fs';import {join} from 'node:path';import {randomUUID,createHash} from 'node:crypto';
import {openCommonCapabilities} from ${JSON.stringify(pathToFileURL(join(runtime,'local-common.mjs')).href)};
import {openWorkspaceReader,openReportWriter} from ${JSON.stringify(pathToFileURL(join(runtime,'local-files.mjs')).href)};
import {LocalAttachmentStore} from ${JSON.stringify(pathToFileURL(join(runtime,'node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js')).href)};
export const inject=['agents','tools','subprocess','sandboxPolicy'];
export function apply(ctx){void (async()=>{
let common,handle;const config=JSON.parse(readFileSync(${JSON.stringify(join(root,'config.json'))},'utf8'));const signal=AbortSignal.timeout(90000);
const reader=openWorkspaceReader(config.workspace),writer=openReportWriter(config.workspace);
try{
 new LocalAttachmentStore(ctx,{dshHome:join(config.root,'dsh')});
 common=await openCommonCapabilities(ctx,{reader,writer,tools:config.tools,sessionId:randomUUID(),signal,sourceDirectory:config.workspace,askUser:async request=>({answers:request.questions.map(q=>({id:q.id,selected:[],custom:'人工诊断回答'}))})});
 handle=await ctx.agents.create({sessionId:randomUUID(),meta:{cwd:config.workspace},agentOptions:{provider:'deepseek-official',model:'deepseek-flash'}});
 const agent=handle.agent;const call=async(name,args)=>{const r=await ctx.tools.execute({callId:randomUUID(),name,arguments:args,agent,signal});assert.equal(r.isError,false,JSON.stringify(r));return r;};
 common.importFiles([{path:'sample.txt',sha256:createHash('sha256').update('unchanged').digest('hex')}]);
 await call('read',{file_path:'inputs/sample.txt'});
 await call('write',{file_path:'outputs/result.txt',content:'first'});
 await call('read',{file_path:'outputs/result.txt'});
 await call('edit',{file_path:'outputs/result.txt',old_string:'first',new_string:'second'});
 await call('glob',{pattern:'**/*.txt'});await call('grep',{pattern:'second',path:'outputs'});
 const shell=process.platform==='win32'?'pwsh':'bash';
 await call(shell,{command:'python -c "print(6*7)"',description:'诊断随包Python'});
 const job=await call(shell,{command:'python -c "import time;print(42,flush=True);time.sleep(30)"',description:'检查本机后台任务取消',run_in_background:true});
 assert.equal(job.value.kind,'background');const jobId=job.value.jobId;
 await call('job_list',{});await call('job_output',{job_id:jobId});await call('job_kill',{job_id:jobId});
 const stopped=await call('job_output',{job_id:jobId,wait:true,timeout_ms:10000});assert.equal(stopped.value.job.status,'killed');
 let network;
 if(config.network){await call('web_fetch',{url:'https://example.com/'});const search=await call('web_search',{queries:['GeneLoop GitHub']});assert.ok(search.value.sources.length);network=true;}
 await call('ask_user_question',{questions:[{id:'check',question:'补充诊断资料'}]});
 const denied=await ctx.tools.execute({callId:randomUUID(),name:'read',arguments:{file_path:'../outside.txt'},agent,signal});assert.equal(denied.isError,true);
 assert.equal(readFileSync(join(config.workspace,'sample.txt'),'utf8'),'unchanged');
 const delivery=common.publish(['outputs/result.txt']);assert.equal(delivery.length,1);
 const missing=common.names.filter(name=>!ctx.tools.get(name,agent));assert.deepEqual(missing,[]);
 writeFileSync(join(config.root,'result.json'),JSON.stringify({diagnostic:true,model_requests:0,platform:process.platform,tools:common.names,read_write_edit:true,search:true,python:true,jobs_cancel:true,network:network??'not-run',old_session_cwd_mapped:true,questions:true,delivery:true,original_unchanged:true,traversal_denied:true}));
}catch(error){writeFileSync(join(config.root,'result.json'),JSON.stringify({error:error.message,stack:error.stack}));}
finally{await handle?.dispose();await common?.close();reader.close();writer.close();process.exit(0);}
})();}
`);
const patch=join(root,'patch.json');writeFileSync(patch,JSON.stringify([{id:'persistent-pwsh',disabled:true},{id:'persistent-bash',disabled:true},{id:'plugin-package-inventory-deepseek',disabled:true},{insert:[{name:pathToFileURL(plugin).href}]}]));
const child=spawn(process.execPath,[join(runtime,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'--profile','sdk-minimal','--patch',patch],{
 cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{SystemRoot:process.env.SystemRoot,HOME:root,USERPROFILE:root,APPDATA:root,LOCALAPPDATA:root,TEMP:root,TMP:root,DSH_HOME:join(root,'dsh'),ELECTRON_RUN_AS_NODE:'1'}});
let stderr='';child.stderr.on('data',b=>stderr=(stderr+b.toString()).slice(-5000));child.stdout.resume();
const timer=setTimeout(()=>child.kill(),100000);await new Promise(done=>child.once('close',done));clearTimeout(timer);
let result;try{result=JSON.parse(readFileSync(join(root,'result.json'),'utf8'));}catch{throw Error('公共工具未完成启动：'+stderr);}
console.log(JSON.stringify({root,...result}));assert.equal(result.error,undefined,result.error);
