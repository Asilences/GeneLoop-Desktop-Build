/** Real loopback account gateway; provider replies are explicit diagnostics. */
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {spawn} from 'node:child_process';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {createHash,createHmac} from 'node:crypto';
import {createGateway} from '../scripts/harless_gateway.mjs';

const root=resolve(import.meta.dirname,'..'),python=process.env.SSS_PURE_CODE_PYTHON??process.env.SSS_PYTHON;
for(const failing of [false,true])test('member page learning binds, meters and releases its Session: '+(failing?'provider failure':'success'),
 {skip:!python||!existsSync(python),timeout:30000},async t=>{
 const directory=mkdtempSync(join(tmpdir(),'ppt-member-budget-')),data=join(directory,'db');mkdirSync(data);
 t.after(()=>rmSync(directory,{recursive:true,force:true}));
 const user={id:'diagnostic-member',role:'member'},admin='diagnostic-only-admin',seen=[];
 writeFileSync(join(data,'accounts.json'),JSON.stringify({version:1,users:[user],invites:[],sessions:[],ownerClaim:null}));
 const proposal={description:'Diagnostic title',source:'import json,sys\nprint(json.load(open(sys.argv[1])))',
  parameters_schema:{type:'object',properties:{title:{type:'string'}},required:['title']},default_parameters:{title:'Diagnostic'}};
 const upstream=http.createServer(async(req,res)=>{
  let raw='';for await(const part of req)raw+=part;
  const body=JSON.parse(raw);seen.push({path:req.url,body,session:req.headers['x-deepseek-harness-session-id']});
  const model=req.url==='/v1/chat/completions';
  res.writeHead(model&&failing?500:200,{'content-type':'application/json'});
  res.end(JSON.stringify(model?(failing?{error:'diagnostic failure'}:{choices:[{finish_reason:'tool_calls',message:{tool_calls:[
   {function:{name:'propose_ppt_component',arguments:JSON.stringify(proposal)}}]}}]}):
   {usage_complete:!failing,upstream_requests:1,observed_peak_cost_usd:failing?null:.002}));
 });
 upstream.listen(0,'127.0.0.1');await once(upstream,'listening');const port=upstream.address().port;
 t.after(()=>{upstream.closeAllConnections();upstream.close();});
 const gateway=createGateway({dataDir:data,publicOrigin:'https://diagnostic.invalid',adminToken:admin,scopedBudgetPort:1,
  memberPolicy:{budget_usd:null,control_token:'diagnostic-control'},upstreamBrokerPort:port,upstreamControlPort:port,apiKey:'diagnostic'});
 gateway.scopedBudget.listen(0,'127.0.0.1');await once(gateway.scopedBudget,'listening');t.after(()=>gateway.close());
 const endpoint='http://127.0.0.1:'+gateway.scopedBudget.address().port;
 const delegated=purpose=>createHmac('sha256',admin).update(purpose+':'+user.id).digest('base64url');
 const policy=join(directory,'policy.json');writeFileSync(policy,JSON.stringify({endpoint:endpoint+'/v1',control_endpoint:endpoint,
  control_token:delegated('control'),budget_task_prefix:createHash('sha256').update(user.id).digest('hex').slice(0,8),budget_usd:null}));
 const code=`import sys,urllib.error\nfrom pathlib import Path\nfrom src.adapters.ppt_component_learning import propose_component\ntry:\n propose_component({'source_sha256':'diagnostic'},sys.argv[1],Path(sys.argv[2]))\nexcept urllib.error.HTTPError as error:\n if error.code != 500: raise\n`;
 const child=spawn(python,['-c',code,policy,join(directory,'proposal')],{cwd:root,
  env:{...process.env,PYTHONUTF8:'1',DEEPSEEK_API_KEY:delegated('model')},stdio:['ignore','pipe','pipe']});
 let stderr='';child.stderr.on('data',part=>stderr+=part);const [status]=await once(child,'close');assert.equal(status,0,stderr);
 assert.deepEqual(seen.map(row=>row.path),['/tasks/register','/tasks/activate','/bind','/v1/chat/completions','/tasks/cancel','/unbind']);
 const registration=seen[0].body,binding=seen[2].body;
 assert.equal(registration.budget_usd,null);assert.equal(binding.budget_session_id,registration.session_id);
 assert.match(binding.session_id,/^session-/);assert.equal(seen[3].session,binding.session_id);
 assert.deepEqual(seen[5].body,binding);
 const costs=JSON.parse(readFileSync(join(directory,'proposal/model-costs.json'),'utf8'));
 assert.equal(costs.observed_model_usd,failing?null:.002);
 assert.equal(JSON.parse(readFileSync(join(directory,'proposal/budget-attribution.json'),'utf8')).phase,'component_source_learning');
 const revoked=await fetch(endpoint+'/v1/chat/completions',{method:'POST',headers:{authorization:'Bearer '+delegated('model'),
  'x-deepseek-harness-session-id':binding.session_id,'content-type':'application/json'},body:'{}'});
 assert.equal(revoked.status,403,'Finished learning Session must lose its model route');
 });
