import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';

// Runs the real Web settlement projector and real offline CLI, without a server
// or model Provider. This is entry-point equivalence, not model/desktop UAT.
const root=process.argv[2],code=join(root,'code'),output=join(root,'results','entries-r1');
const {capturePlatformLearningTrace}=await import(pathToFileURL(join(code,'src/adapters/web/learning/harless_learning_trace.ts')).href);
mkdirSync(output,{recursive:true});
const cases=JSON.parse(readFileSync(join(root,'entry-cases-private.json'),'utf8'));
const rows=[];
for(const scene of ['paper-proofreading','ppt'])for(const fixture of cases){
  const directory=join(output,`${scene}-${fixture.id}`);mkdirSync(directory,{recursive:true});
  const input=join(directory,'events.jsonl'),catalog=join(directory,'effective-config.json');
  const events=[{type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:fixture.text}]}}];
  writeFileSync(input,events.map(row=>JSON.stringify(row)).join('\n'),{mode:0o600});
  writeFileSync(catalog,JSON.stringify({allowed_tools:[]}),{mode:0o600});
  const original=createHash('sha256').update(readFileSync(input)).digest('hex');
  const started=performance.now();
  await capturePlatformLearningTrace({provider_mode:'real'},directory,scene,'completed',0);
  const webMs=performance.now()-started;
  const web=existsSync(join(directory,'privacy-learning.json'))?JSON.parse(readFileSync(join(directory,'privacy-learning.json'),'utf8')):null;
  const offlineStarted=performance.now();
  let offline=null;
  try{
    offline=JSON.parse(execFileSync(process.env.SSS_PYTHON,['-m','src.adapters.geneloop_learning_trace','--authorized','--input',input,
      '--scene',scene,'--status','completed','--start','0','--catalog',catalog],{
      cwd:code,env:Object.fromEntries(['PATH','HOME','SSS_RSI_GITLEAKS','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']
        .filter(k=>process.env[k]).map(k=>[k,process.env[k]])),
      timeout:120000,encoding:'utf8',stdio:['ignore','pipe','pipe']}));
  }catch(error){if(error.status!==1)throw error;}
  const offlineMs=performance.now()-offlineStarted;
  rows.push({scene,case_id:fixture.id,expected_accepted:fixture.id!=='secret-field-control',
    source_sha256:createHash('sha256').update(fixture.text).digest('hex'),
    web_accepted:web!==null,offline_accepted:offline!==null,equal:JSON.stringify(web)===JSON.stringify(offline),web_ms:webMs,offline_ms:offlineMs,
    original_unchanged:original===createHash('sha256').update(readFileSync(input)).digest('hex')});
  console.log(JSON.stringify({entry_case:fixture.id,scene,equal:rows.at(-1).equal,accepted:web!==null}));
}
writeFileSync(join(output,'entry-summary.json'),JSON.stringify({rows,total:rows.length,equal:rows.filter(r=>r.equal).length,
  accepted:rows.filter(r=>r.web_accepted&&r.offline_accepted).length,cloud_requests:0,cloud_api_cost:0},null,2),{mode:0o600});
// Persist every observed mismatch before reporting failure to orchestration.
// A successful child exit does not establish Web/offline equivalence.
if(rows.some(row=>!row.equal||!row.original_unchanged||row.web_accepted!==row.expected_accepted||row.offline_accepted!==row.expected_accepted))process.exitCode=1;
