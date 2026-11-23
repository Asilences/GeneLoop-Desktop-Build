// Supplemental wiring test. Real privacy tools, synthetic events, no model/HTTP UAT.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [codeArg,outArg,mode]=process.argv.slice(2),code=resolve(codeArg),out=resolve(outArg);
assert(['default','candidate'].includes(mode));
assert.equal(!!process.env.SSS_RSI_PRIVACY_CANDIDATE_CONFIG,mode==='candidate');
const {capturePlatformLearningTrace}=await import(pathToFileURL(join(code,'src/adapters/web/learning/harless_learning_trace.ts')));
const {runPrivacyWorker,closePrivacyWorkers}=await import(pathToFileURL(join(code,'src/adapters/privacy_worker_pool.ts')));
const {projectPlatformLearningTrace}=await import(pathToFileURL(join(code,'src/adapters/geneloop_privacy.ts')));
const configured=JSON.parse(readFileSync(join(code,'config/harless-scenes.json'),'utf8')).scenes.map(row=>row.id);
const scenes=[...new Set([...configured,'chat','coding','future-custom-mcp'])];assert.equal(scenes.length,9);
mkdirSync(out,{recursive:false,mode:0o700});
const rows=[],tool='mcp__diagnostic__analyze',hash=raw=>createHash('sha256').update(raw).digest('hex');
try{
 for(const scene of scenes){
  const directory=join(out,scene);mkdirSync(directory,{mode:0o700});
  const input=join(directory,'events.jsonl'),catalog=join(directory,'effective-config.json');
  const events=[
   {type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'保留 RMSE 与 24 fps; email owner@example.com.'}]}},
   {type:'tool/call',data:{callId:'private-call-owner@example.com',name:tool,
    arguments:JSON.stringify({nested:[{email:'owner@example.com',phone:13800138000}],threshold:0.05})}},
   {type:'tool/result',data:{message:{source:{kind:'tool',callId:'private-call-owner@example.com'},content:[
    {type:'tool-result',toolCallId:'private-call-owner@example.com',isError:false,
     content:[{type:'text',text:JSON.stringify({text:'Keep RMSE; owner@example.com',path:'/home/private-owner/report.pdf'})}]}]}}},
   {type:'assistant/message',data:{message:{source:{kind:'model'},content:[{type:'text',text:'Keep 24 fps; owner@example.com.'}]}}},
  ];
  writeFileSync(input,events.map(row=>JSON.stringify(row)).join('\n')+'\n',{mode:0o600});
  writeFileSync(catalog,JSON.stringify({allowed_tools:[tool]}),{mode:0o600});
  const original=hash(readFileSync(input)),started=performance.now();
  const row={scene,mode,passed:false};
  try{
   await capturePlatformLearningTrace({provider_mode:'real'},directory,scene,'completed',0);
   assert(existsSync(join(directory,'privacy-learning.json')),'web_admission_missing');
   const web=JSON.parse(readFileSync(join(directory,'privacy-learning.json'),'utf8'));
   const imported=await runPrivacyWorker(process.env.SSS_PYTHON,'import',
    {input,scene,status:'completed',start:0,allowed_tools:[tool]});
   row.web_import_equal=JSON.stringify(web)===JSON.stringify(imported);
   row.projector_structure_retained=web.scene===(configured.includes(scene)||['chat','coding','sdk'].includes(scene)?scene:'generic')&&web.status==='completed'&&web.format==='geneloop.rsi-learning-trace/v4'
    &&JSON.stringify(web.nodes)===JSON.stringify([{tool:'tool-0',outcome:'observed_success'}]);
   const material=JSON.stringify(web.content);
   row.task_invariants_retained=material.includes('RMSE')&&material.includes('24 fps')&&material.includes('0.05');
   row.four_material_sources_present=web.content.length===4&&web.content.some(value=>value.type==='tool/result')
    &&web.content.some(value=>value.type==='tool/call')&&web.content.some(value=>value.role==='user')
    &&web.content.some(value=>value.role==='model');
   row.forbidden_literals_removed=['owner@example.com','13800138000','private-call-owner','/home/private-owner/report.pdf']
    .every(value=>!JSON.stringify(web).includes(value));
   const shared=JSON.parse(await projectPlatformLearningTrace(process.env.SSS_PYTHON,input,scene,'completed',0,catalog,true));
   row.sharing_is_minimal_topology=shared.format==='geneloop.rsi-shared-object/v1'&&shared.trace.scene==='generic'
    &&!('content' in shared.trace)&&shared.trace.nodes[0].tool==='tool-0'&&!JSON.stringify(shared).includes(tool);
   row.original_unchanged=original===hash(readFileSync(input));
   row.passed=Object.entries(row).filter(([key])=>!['scene','mode','passed'].includes(key)).every(([,value])=>value===true);
  }catch(error){row.error_type=error?.name??'Error';row.original_unchanged=original===hash(readFileSync(input));}
  row.seconds=(performance.now()-started)/1000;rows.push(row);console.log(JSON.stringify(row));
 }
}finally{closePrivacyWorkers();}
const receipt={mode,registered_scene_count:configured.length,scene_groups:scenes.length,total:rows.length,
 passed:rows.filter(row=>row.passed).length,rows,
 scope:'all registered scenes plus chat/coding/future MCP; real Web settlement, SDK/offline import operation and sharing projection in the common worker; synthetic inputs; CLI cold parity separately tested',
 http_or_desktop_uat:false,cloud_requests:0,production_service_touched:false,
 source_sha256:hash(readFileSync(new URL(import.meta.url))),
 timing_scope:'sequential supplemental checks after heavy benchmarks, pooled worker including first cold initialization; not a benchmark latency comparison'};
writeFileSync(join(out,'summary.json'),JSON.stringify(receipt,null,2)+'\n',{mode:0o600});
if(receipt.total!==9||receipt.passed!==9)process.exitCode=1;
