import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtempSync,realpathSync,mkdirSync,writeFileSync,readFileSync,appendFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {once} from 'node:events';
import {randomUUID,createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url),app=fileURLToPath(new URL('../',import.meta.url));
const output=realpathSync(mkdtempSync(join(process.env.GENELOOP_DESKTOP_VALIDATION_ROOT||tmpdir(),'gl-file-recover-')));
const source=join(output,'source'),profile=join(output,'profile');
mkdirSync(source);writeFileSync(join(source,'invoice.txt'),'Invoice: microscope reagents. Total: 125 CNY.');
const hash=createHash('sha256').update(readFileSync(join(source,'invoice.txt'))).digest('hex');
const sources=[{path:'invoice.txt',sha256:hash}];
const questions=JSON.stringify({category:{type:'choice',instructions:'Classify the actual document',
  criteria:{invoice:'Invoice',paper:'Scientific paper',unknown:'Insufficient information'}}});
const token='a'.repeat(43);
let modelCalls=0,jevCalls=0,workflowId,failure;
const requests=[];
const server=createServer(async(req,res)=>{
 try{
  const parts=[];for await(const part of req)parts.push(part);
  const body=parts.length?JSON.parse(Buffer.concat(parts)):{};requests.push(req.url);
  const json=value=>{res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify(value));};
  if(req.url==='/api/account/me')return json({user:{id:'file-recovery-fixture'}});
  if(req.url==='/api/harless/desktop-model/lease')return json(req.method==='DELETE'?{ok:true}:{token,model:'deepseek-flash',fileJev:true,fileJevAccount:'a'.repeat(64),toolsetVersion:4});
  if(req.url==='/api/harless/desktop-model/v1/systemone'){
    jevCalls++;
    assert.equal(body.packet.request.state.includes('microscope reagents'),true);
    return json({result:{model:'jev-fixture',answers:{category:{type:'choice',choice:'invoice',
      probabilities:{invoice:0.99,paper:0.005,unknown:0.005}}}},decision:{threshold:0.9},accounting:{invoice_verified:false}});
  }
  assert.equal(req.url,'/api/harless/desktop-model/v1/chat/completions');
  modelCalls++;
  appendFileSync(join(output,'model-inputs.jsonl'),JSON.stringify({step:modelCalls,body})+'\n');
  if(modelCalls===4){res.writeHead(200,{'content-type':'text/event-stream'});res.write(': waiting for cancellation\n\n');writeFileSync(join(output,'waiting'),'1');return;}
  const tasks={
    1:['local_workflow_open',{sources:JSON.stringify(sources),request:'Inspect the invoice copy',settings:'{"workflow":"management"}'}],
    2:['mcp__native_management__read_task',{}],
    3:['local_file_judge',{sources,questions}],
    5:['mcp__native_management__list_files',{}],
    6:['local_file_judge',{sources,questions}],
    7:['local_save_report',{markdown:'# Recovery\nThe original invoice and paid judgement were preserved.'}],
  };
  const tools=body.messages.filter(message=>message.role==='tool');
  if(modelCalls===2){
    const result=JSON.parse(tools.at(-1).content);workflowId=result.workflow_id;assert.ok(workflowId);
  }
  if(modelCalls===5){
    assert.ok(tools.some(message=>message.content.includes('jev-fixture')));
    assert.ok(body.tools.some(tool=>tool.function?.name==='mcp__native_management__list_files'),'original MCP tools restored before model resume');
  }
  if(modelCalls===6){
    const result=JSON.parse(tools.at(-1).content);
    assert.equal(result.result?.isError,undefined);
    assert.ok(!JSON.stringify(result).includes('Unknown workflow'));
  }
  const call=tasks[modelCalls];
  const delta=call?{tool_calls:[{index:0,id:'test-'+modelCalls,type:'function',function:{name:call[0],arguments:JSON.stringify(call[1])}}]}:{content:'Original File task recovered and delivered.'};
  const base={id:randomUUID(),object:'chat.completion.chunk',created:1,model:body.model};
  res.writeHead(200,{'content-type':'text/event-stream'});
  for(const choices of [[{index:0,delta:{role:'assistant',...delta},finish_reason:null}],
    [{index:0,delta:{},finish_reason:call?'tool_calls':'stop'}],[]]){
    res.write('data: '+JSON.stringify({...base,choices,...(!choices.length?{usage:{prompt_tokens:50,completion_tokens:10,total_tokens:60}}:{})})+'\n\n');
  }
  res.end('data: [DONE]\n\n');
 }catch(error){failure??=error;console.error(error.stack);res.writeHead(500);res.end('{}');}
});
server.listen(0,'127.0.0.1');await once(server,'listening');
const origin='http://127.0.0.1:'+server.address().port;
const env={...process.env,GENELOOP_FILE_RECOVERY_FIXTURE:JSON.stringify({output,source,profile,origin})};
delete env.ELECTRON_RUN_AS_NODE;
const child=spawn(require('electron'),['test/file-recovery.cjs'],{cwd:app,env,stdio:'inherit',windowsHide:true});
const timeout=setTimeout(()=>child.kill(),150000);
try{
 const [code]=await once(child,'exit');
 assert.equal(code,0);
 if(failure)throw failure;
 assert.equal(jevCalls,1,'recovery must not repeat the paid JEV call');
 assert.equal(modelCalls,8);
 const result={passed:true,modelCalls,jevCalls,originalWorkflow:workflowId,output,provider:'protocol fixture, no paid calls',packaged:process.env.GENELOOP_FILE_RECOVERY_PACKAGE||null};
 writeFileSync(join(output,'summary.json'),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result));
}finally{clearTimeout(timeout);server.closeAllConnections();server.close();}
