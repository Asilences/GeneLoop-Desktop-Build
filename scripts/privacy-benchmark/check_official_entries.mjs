// Real common Web settlement and offline import; synthetic content, no model API.
// This checks host configuration propagation and cold/warm admission separately
// from the benchmark observer. Original events are never replaced or edited.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const [codeArg,outArg]=process.argv.slice(2),code=resolve(codeArg),out=resolve(outArg);
assert(process.env.SSS_RSI_PRIVACY_CANDIDATE_CONFIG&&process.env.SSS_RSI_PRIVACY_CANDIDATE_SHA256);
mkdirSync(out,{recursive:false,mode:0o700});
const {capturePlatformLearningTrace}=await import(pathToFileURL(join(code,'src/adapters/web/learning/harless_learning_trace.ts')).href);
const {privacyWorkerEnvironment,closePrivacyWorkers}=await import(pathToFileURL(join(code,'src/adapters/privacy_worker_pool.ts')).href);
const cases=[
 {id:'zh-mixed',accepted:true,text:'请比较两种回归方法，保留 RMSE、JSON、MCP、HTTPS 与 n=128；联系邮箱 owner@example.com。',keep:['RMSE','JSON','MCP','HTTPS','n=128'],remove:['owner@example.com']},
 {id:'en-semantic',accepted:true,text:'Compare linear regression and random forests; retain RMSE, JSON, MCP, HTTPS and n=128. Email owner@example.com.',keep:['RMSE','JSON','MCP','HTTPS','n=128'],remove:['owner@example.com']},
 {id:'explicit-secret',accepted:false,text:JSON.stringify({password:'diagnostic-only-not-a-real-credential'}),keep:[],remove:[]},
];
const rows=[];
const hash=(data)=>createHash('sha256').update(data).digest('hex');
try{
 for(const scene of ['paper-proofreading','ppt','coding'])for(const fixture of cases){
  const directory=join(out,`${scene}-${fixture.id}`);mkdirSync(directory,{mode:0o700});
  const input=join(directory,'events.jsonl'),catalog=join(directory,'effective-config.json');
  writeFileSync(input,JSON.stringify({type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:fixture.text}]}})+'\n',{mode:0o600});
  writeFileSync(catalog,JSON.stringify({allowed_tools:[]}),{mode:0o600});
  const original=hash(readFileSync(input));
  const started=performance.now();
  await capturePlatformLearningTrace({provider_mode:'real'},directory,scene,'completed',0);
  const webMs=performance.now()-started;
  const web=existsSync(join(directory,'privacy-learning.json'))?JSON.parse(readFileSync(join(directory,'privacy-learning.json'),'utf8')):null;
  const offStarted=performance.now();
  const offlineProcess=spawnSync(process.env.SSS_PYTHON,['-B','-m','src.adapters.geneloop_learning_trace','--authorized','--input',input,
   '--scene',scene,'--status','completed','--start','0','--catalog',catalog,'--diagnostic-reason'],{
    cwd:code,env:{...privacyWorkerEnvironment(),PYTHONUTF8:'1'},timeout:125000,encoding:'utf8',stdio:['ignore','pipe','pipe']});
  const offlineMs=performance.now()-offStarted;
  const offline=offlineProcess.status===0?JSON.parse(offlineProcess.stdout):null;
  const serialized=web===null?'':JSON.stringify(web);
  const row={scene,case_id:fixture.id,expected_accepted:fixture.accepted,
    web_accepted:web!==null,offline_accepted:offline!==null,
    equal:JSON.stringify(web)===JSON.stringify(offline),
    offline_exit_code:offlineProcess.status,offline_transport_error:offlineProcess.error?.code??null,
    offline_rejection_reason:offlineProcess.stderr?.match(/^geneloop_privacy_rejected:([a-z_]+)\s*$/m)?.[1]??null,
    original_unchanged:original===hash(readFileSync(input)),web_ms:webMs,offline_ms:offlineMs,
    required_task_fragments:fixture.keep.length,retained_task_fragments:fixture.keep.filter(value=>serialized.includes(value)).length,
    forbidden_literal_residuals:fixture.remove.filter(value=>serialized.includes(value)).length};
  row.passed=row.equal&&row.original_unchanged&&row.web_accepted===row.expected_accepted&&row.offline_accepted===row.expected_accepted
   &&(fixture.accepted?(row.retained_task_fragments===row.required_task_fragments&&row.forbidden_literal_residuals===0):offlineProcess.status===1);
  rows.push(row);
  console.log(JSON.stringify(row));
 }
}finally{closePrivacyWorkers();}
const receipt={total:rows.length,passed:rows.filter(row=>row.passed).length,rows,
 source_sha256:hash(readFileSync(new URL(import.meta.url))),cloud_requests:0,production_touched:false,
 scope:'real projectors and candidate detectors; synthetic text; no HTTP server, desktop, model provider or receiver UAT',
 timing:'Web first request includes cold initialization, later requests reuse public worker; offline CLI cold on every invocation; no benchmark prediction memo'};
writeFileSync(join(out,'summary.json'),JSON.stringify(receipt,null,2),{mode:0o600});
if(rows.length!==9||receipt.passed!==rows.length)process.exitCode=1;
