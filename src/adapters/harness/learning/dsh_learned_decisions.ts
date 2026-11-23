/** Capture-only is a transparent tap. Execution loads independently certified contracts. */
import {readFileSync,writeFileSync,appendFileSync,mkdirSync,existsSync,lstatSync,readdirSync,renameSync} from 'node:fs';
import {resolve,join,dirname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {observation,digest} from '../../../motif_core/runtime/online_skill_runtime.mjs';
import {prepareLearnedAction,bindLearnedDecision} from '../../learned_decision_program.ts';
import {DECISION_FORMAT} from '../../typed_decisions.ts';
import {resolveTypedQuestions} from '../../typed_decision_resolution.ts';
import {completedToolHistory} from '../../file_management/file_recovery_state.ts';
import {workspaceSnapshot,validatePendingDecision,originalInitialization} from '../../file_management/file_decision_checkpoint.ts';
export const name='geneloop-learned-decisions';export const inject=['agents','llm'];
const root=resolve(fileURLToPath(new URL('../../../../',import.meta.url))),read=(p:string)=>JSON.parse(readFileSync(p,'utf8'));
const sha=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
function privateFile(p:string){
 const file=resolve(p),base=join(root,'.local');if(!file.startsWith(base+sep))throw Error('private learned decision required');
 for(let q=file;q.startsWith(base+sep);q=dirname(q))if(existsSync(q)&&lstatSync(q).isSymbolicLink())throw Error('decision symlink refused');return file;
}
function toolStream(call:any,provider:string,proof:string){return(async function*(){
 const text='Actual '+provider+' decision executed a model-learned contract; proof '+proof+'. This is not a native DeepSeek-authored decision.';
 yield{type:'block-start',index:0,blockType:'reasoning'};yield{type:'reasoning-delta',index:0,text};yield{type:'block-end',index:0,block:{type:'reasoning',text}};
 let index=1;
 if(call.text){yield{type:'block-start',index,blockType:'text'};yield{type:'text-delta',index,text:call.text};yield{type:'block-end',index,block:{type:'text',text:call.text}};index++;}
 yield{type:'block-start',index,blockType:'tool-call'};yield{type:'tool-call-delta',index,id:call.callId,name:call.tool,argumentsDelta:JSON.stringify(call.arguments)};
 yield{type:'block-end',index,block:{type:'tool-call',id:call.callId,name:call.tool,arguments:JSON.stringify(call.arguments)}};
 yield{type:'finish',reason:{kind:'tool-calls'}};
})();}
export function apply(ctx:any,config:any){
 if(!['capture','execute'].includes(config.mode)||!['jev','deepseek'].includes(config.provider))throw Error('unknown learned decision mode');
 const binding=read(privateFile(process.env.SSS_EXPERIENCE_BINDING!)),operation=read(privateFile(process.env.SSS_OPERATION_BINDING!));
 if(sha(privateFile(binding.task_file))!==binding.task_sha256)throw Error('learning task changed');
 const spec=read(binding.task_file),home=join(dirname(binding.audit_file),'decision-captures'),auditFile=join(dirname(binding.audit_file),'learned-decision-audit.jsonl');
 mkdirSync(home,{recursive:true,mode:0o700});
 const save=(p:string,v:any)=>writeFileSync(p,JSON.stringify(v,null,2)+'\n',{mode:0o600,flag:'wx'});
 const audit=(v:any)=>appendFileSync(auditFile,JSON.stringify({...v,session_id:operation.session_id})+'\n',{mode:0o600});
 let live=false,sequence=0,lastTool:string|null=null,envelope:string|null=null;
 const receipts:any={},history:any[]=[];let recipes:any[]=[];
 const dependencies=()=>{for(const [name,h] of Object.entries(config.runtime_sources??{}))if(sha(resolve(root,name))!==h)throw Error('learned runtime changed');};
 dependencies();
 if(config.mode==='execute'){
  if(config.candidate_file){
   if(binding.role!=='certify')throw Error('candidate override is for independent certification only');
   const path=privateFile(config.candidate_file);if(sha(path)!==config.candidate_sha256)throw Error('candidate changed');recipes=[read(path)];
  }else{
   const catalogPath=privateFile(config.catalog_file);if(sha(catalogPath)!==config.catalog_sha256)throw Error('frozen experience catalogue changed');
   for(const job of read(catalogPath).jobs??[]){
    if(job.state!=='active')continue;
    const activationPath=privateFile(join(config.state_root,job.job,'activation.json'));
    const a=read(activationPath);if(a.kind!=='learned_decision_recipe')continue;
    if(a.owner!==spec.owner)continue;
    const suspension=join(dirname(activationPath),'suspension.json');
    if(existsSync(suspension)){
     const s=read(privateFile(suspension));
     if(s.format!=='geneloop-learned-decision-suspension-v1'||s.payload_sha256!==a.payload_sha256)throw Error('invalid learned decision suspension');
     audit({kind:'learned_decision_suspended',payload_sha256:a.payload_sha256,evidence_sha256:s.evidence_sha256});continue;
    }
    const payload=privateFile(a.payload_file),cert=privateFile(a.certificate_file);
    if(sha(payload)!==a.payload_sha256||sha(cert)!==a.certificate_sha256)throw Error('learned experience object changed');
    const proof=read(cert),value=read(payload);
    if(proof.status!=='certified'||proof.owner!==spec.owner||proof.payload_sha256!==a.payload_sha256||
      Object.entries(proof.runtime_sources).some(([n,h])=>sha(resolve(root,n))!==h)){audit({kind:'learned_decision_incompatible',payload_sha256:a.payload_sha256});continue;}
    recipes.push(value);
   }
  }
 }
 audit({kind:'learned_decision_ready',mode:config.mode,active_recipes:recipes.length,manual_workflow_plugins:false});
 const journal=join(home,'attempted.json'),attempted=new Set<string>(existsSync(journal)?read(journal):[]);
 const pendingByCall=new Map<string,string>(),primers=new Map<string,any>();let recoveryQueue:string[]=[];
 const statusFile=(file:string)=>file+'.status.json';
 const status=(file:string,value:any)=>{const tmp=statusFile(file)+'.'+randomUUID();save(tmp,value);renameSync(tmp,statusFile(file));};
 const checkpoint=(payload:any,proofFile:string,provider:string)=>{
  const proof=read(proofFile),effect=operation.catalog?.[proof.binding.tool]?.contract?.effect;
  if(!['read','stage'].includes(effect)||Object.keys(spec.external_roots??{}).length)return;
  const file=join(home,'pending-'+randomUUID()+'.json');
  save(file,{format:'file-paid-decision-checkpoint-v1',task_sha256:binding.task_sha256,task_id:spec.task_id,owner:spec.owner,
   payload_sha256:digest(payload),runtime_sha256:digest(config.runtime_sources),models_sha256:digest(config.expected_models),
   context:proof.context,request:proof.request,resolution:proof.resolution,binding:proof.binding,workspace:workspaceSnapshot(spec.workspace),
   tool_schema_sha256:payload.tool_schema_hashes[proof.binding.tool],provider,
   proof_file:proofFile,proof_sha256:sha(proofFile),
   paid_files:Object.fromEntries((proof.decision_result_files??[]).map((f:string)=>[f,sha(privateFile(f))]))});
  status(file,{state:'issued',call_ids:[proof.tool_call_id],proof_file:proofFile,proof_sha256:sha(proofFile)});
  pendingByCall.set(proof.tool_call_id,file);
  audit({kind:'learned_decision_checkpoint_saved',candidate:payload.candidate_sha256,pending_file:file,pending_sha256:sha(file),tool_call_id:proof.tool_call_id});
 };
 const meter=async(event:any)=>{const r=spawnSync(config.python,[join(root,'scripts/decision-meter.py')],{
  input:JSON.stringify({context_file:config.meter_context,event}),encoding:'utf8',env:process.env});if(r.status!==0)throw Error('original meter rejected learned decision');};
 ctx.on('agent/created',({agent}:any)=>{
  if(agent.session.id!==operation.session_id)return;
  if(live)throw Error('duplicate learning session');live=true;
  const restored=completedToolHistory(agent.session.snapshotEvents());
  for(const row of restored){receipts[row.tool]=row.out;history.push(row);lastTool=row.tool;}
  if(restored.length)audit({kind:'learned_decision_state_restored',completed_tool_results:restored.length,
   native_first_live_seq:agent.session.firstLiveSeq,no_new_reads_or_decisions:true});
  recoveryQueue=readdirSync(home).filter(n=>/^pending-[a-f0-9-]+\.json$/.test(n)).map(n=>join(home,n))
   .filter(f=>existsSync(statusFile(f))&&read(statusFile(f)).state==='issued');
  agent.ctx.on('tools/result',(exec:any,result:any)=>{
   const pending=pendingByCall.get(exec.callId);
   if(pending){const previous=read(statusFile(pending));status(pending,{...previous,state:result?.isError||result?.value?.isError?'failed':'completed'});}
   const out=observation(result,exec.name);if(!out||result?.isError||result?.value?.isError)return;
   lastTool=exec.name;const row={tool:exec.name,call_id:exec.callId,args:exec.arguments,out};receipts[exec.name]=out;history.push(row);
  });
 });
 ctx.on('agent/disposed',()=>{live=false;});
 ctx.on('llm/stream',async function*(options:any,next:any){
  if(!live||options.sessionId!==operation.session_id||!isAgentLoopRequest(options))return yield* next();
  const users=options.messages.filter(m=>m.role==='user'&&m.source?.kind==='user'),current=digest(users.map(m=>({id:m.id,content:m.content})));
  const matched=users.filter(m=>m.content?.length===1&&m.content[0].type==='text'&&createHash('sha256').update(m.content[0].text).digest('hex')===binding.prompt_sha256);
  if(matched.length!==1||envelope!==null&&envelope!==current)return yield* next();envelope=current;
  const context={goal:spec.objective,last_tool:lastTool,receipts:JSON.parse(JSON.stringify(receipts)),history:JSON.parse(JSON.stringify(history))};
  dependencies();
  if(config.mode==='execute'&&!options.messages.some(m=>m.source?.kind==='task-acceptance-repair')){
   while(recoveryQueue.length){
    const file=privateFile(recoveryQueue.shift()!),pending=read(file),previous=read(statusFile(file));
    const payload=recipes.find(p=>digest(p)===pending.payload_sha256);
    try{
     if(!payload)throw Error('original certified recipe not available');
     const oldProofFile=privateFile(previous.proof_file);
     if(sha(oldProofFile)!==previous.proof_sha256||sha(privateFile(pending.proof_file))!==pending.proof_sha256||
      Object.entries(pending.paid_files).some(([f,h])=>sha(privateFile(f))!==h))throw Error('original paid proof changed');
     const checked=validatePendingDecision(pending,{payload,task_sha256:binding.task_sha256,owner:spec.owner,task_id:spec.task_id,
      runtime_sha256:digest(config.runtime_sources),models_sha256:digest(config.expected_models),previous_call_ids:previous.call_ids,
      history,workspace:workspaceSnapshot(spec.workspace),schema:(options.tools??[]).find(t=>t.name===pending.binding.tool)?.parameters??null,
      primer:primers.get(file),scope:operation.scope,
      effect:operation.catalog?.[pending.binding.tool]?.contract?.effect,external_roots:Object.keys(spec.external_roots??{}).length>0});
     if(checked.kind==='completed'){status(file,{...previous,state:'completed'});continue;}
     if(checked.kind!=='replay')throw Error(checked.reason);
     if(!primers.has(file)){
      const tool=originalInitialization(operation,pending,options.tools??[]),callId='sss-recovery-initialize-'+randomUUID();
      primers.set(file,{call_id:callId,tool});recoveryQueue.unshift(file);
      audit({kind:'learned_decision_recovery_initialize',tool,tool_call_id:callId,pending_file:file,no_model_requests:true});
      return yield* toolStream({tool,arguments:{},callId},'original MCP initialization','same task permission handshake');
     }
     const callId='learned-recovered-'+randomUUID(),proofFile=join(home,'generated-'+callId+'.json'),oldProof=read(oldProofFile);
     save(proofFile,{...oldProof,tool_call_id:callId,recovered_from:{pending_file:file,pending_sha256:sha(file),
      previous_tool_call_id:oldProof.tool_call_id,proof_file:oldProofFile,proof_sha256:sha(oldProofFile),
      prerequisite_call_id:primers.get(file).call_id,
      workspace_sha256:digest(pending.workspace),current_workspace_sha256:digest(workspaceSnapshot(spec.workspace)),no_new_paid_calls:true}});
     status(file,{...previous,state:'issued',call_ids:[...previous.call_ids,callId],proof_file:proofFile,proof_sha256:sha(proofFile)});
     pendingByCall.set(callId,file);
     audit({kind:'learned_decision_recovered',candidate:payload.candidate_sha256,previous_tool_call_id:oldProof.tool_call_id,
      tool_call_id:callId,source_proof:oldProofFile,source_proof_sha256:sha(oldProofFile),execution_proof:proofFile,execution_proof_sha256:sha(proofFile),no_new_paid_calls:true});
     const primary=oldProof.decision_result_files?.[0];
     audit({kind:'learned_decision_tool_bound',candidate:payload.candidate_sha256,provider:pending.provider,
      ...(primary?{decision_call_id:read(primary).call_id}:{}),tool_call_id:callId,tool:checked.binding.tool,
      arguments_sha256:digest(checked.binding.arguments),complete_model_request_replaced:true,reused_paid_decision:true,
      execution_proof:proofFile,execution_proof_sha256:sha(proofFile)});
     return yield* toolStream({...checked.binding,callId},pending.provider,'recovered original paid decision');
    }catch(error){status(file,{...previous,state:'invalid',reason:String(error)});audit({kind:'learned_decision_recovery_invalidated',reason:String(error),ordinary_harness_same_checkpoint:true});}
   }
   const matches=[];
   for(const payload of recipes){
    const key=payload.candidate_sha256;
    if(attempted.has(key))continue;
    try{
     if(payload.owner!==spec.owner||payload.candidate_sha256!==digest(payload.candidate))throw Error('recipe ownership/digest changed');
     if(Object.entries(payload.tool_schema_hashes).some(([name,h])=>digest((options.tools??[]).find(t=>t.name===name)?.parameters??null)!==h))continue;
     const prepared=prepareLearnedAction(payload.candidate,context);
     if(prepared){
      const directBinding=prepared.kind==='direct'?bindLearnedDecision(payload.candidate,context,{}):null;
      if(prepared.kind!=='direct'||directBinding)matches.push({payload,...prepared,directBinding});
     }
    }catch(error){audit({kind:'learned_decision_guard_rejected',candidate:key,reason:String(error)});}
   }
   const direct=matches.filter(m=>m.kind==='direct'),eligible=direct.length?direct:matches;
   if(eligible.length===1){
    const {payload,request,kind,directBinding}=eligible[0],key=payload.candidate_sha256;
    attempted.add(key);writeFileSync(journal,JSON.stringify([...attempted]),{mode:0o600});
    audit({kind:'learned_decision_auto_match',candidate:key,context_sha256:digest(context),provider:kind==='direct'?'deterministic':config.provider});
    try{
     if(kind==='direct'){
      dependencies();const call=directBinding;
      if(!Object.hasOwn(payload.tool_schema_hashes,call.tool)||!(options.tools??[]).some(t=>t.name===call.tool))throw Error('direct binding not applicable');
      const callId='learned-direct-'+randomUUID(),executionProof=join(home,'generated-'+callId+'.json');
      save(executionProof,{format:'geneloop-learned-direct-execution-v1',candidate:key,owner:spec.owner,task_id:spec.task_id,
       tool_call_id:callId,context,request,resolution:{accepted:true,values:{},provider:'deterministic'},binding:call,upstream_attempts:0});
      checkpoint(payload,executionProof,'deterministic');
      audit({kind:'learned_decision_tool_bound',candidate:key,provider:'deterministic',tool_call_id:callId,tool:call.tool,
       arguments_sha256:digest(call.arguments),complete_model_request_replaced:true,upstream_attempts:0,
       execution_proof:executionProof,execution_proof_sha256:sha(executionProof)});
      return yield* toolStream({...call,callId},'deterministic program',callId);
     }
     const result=await resolveTypedQuestions({format:DECISION_FORMAT,scene:config.scene??'files',contract:key,owner:spec.owner,
      task_id:spec.task_id,parent_call_id:'learned-port-'+randomUUID(),evidence:[{id:'current-native-tool-receipts',sha256:digest(context),scope:'actual currently available tool receipts and user goal; no new reads'}],request},
      {provider:config.provider,recordRoot:config.record_root,config:config.provider_config,threshold:payload.threshold,meter,signal:options.signal,
       onResult:(r:any,stage:string)=>{
        audit({kind:'learned_decision_result',candidate:key,call_id:r.call_id,decision:r.decision,provider:r.provider,record_directory:r.record_directory,resolution_stage:stage});
        if(r.result.model!==config.expected_models[r.provider])throw Error('decision model-version change');
       }});
     if(!result.decision.accepted)throw Error('unresolved typed questions');
     dependencies();const call=bindLearnedDecision(payload.candidate,context,result.decision.values);
     if(!call||!Object.hasOwn(payload.tool_schema_hashes,call.tool)||!(options.tools??[]).some(t=>t.name===call.tool))throw Error('binding not applicable');
     const callId='learned-'+config.provider+'-'+randomUUID();
     const primary=result.calls[0],executionProof=join(home,'generated-'+primary.call_id+'.json');
     save(executionProof,{format:'geneloop-learned-decision-execution-v2',candidate:key,owner:spec.owner,task_id:spec.task_id,
      tool_call_id:callId,context,request,decision_result_files:result.calls.map((r:any)=>join(r.record_directory,'result.json')),resolution:result.decision,binding:call});
     checkpoint(payload,executionProof,result.provider);
     audit({kind:'learned_decision_tool_bound',candidate:key,decision_call_id:primary.call_id,provider:result.provider,
      tool_call_id:callId,tool:call.tool,arguments_sha256:digest(call.arguments),complete_model_request_replaced:true,
      execution_proof:executionProof,execution_proof_sha256:sha(executionProof)});
     return yield* toolStream({...call,callId},result.provider,primary.call_id);
    }catch(error){audit({kind:'learned_decision_fallback',candidate:key,reason:String(error),ordinary_harness_same_checkpoint:true});}
   }else if(eligible.length>1)audit({kind:'learned_decision_ambiguous',matches:eligible.length,ordinary_harness_same_checkpoint:true});
  }
  // A transparent tap, reached only when the original model stream is requested.
  const id=String(++sequence).padStart(4,'0')+'-'+randomUUID(),directory=join(home,id);mkdirSync(directory,{mode:0o700});
  const snapshot={format:'geneloop-native-decision-capture-v1',snapshot_id:id,session_id:operation.session_id,
   source_mode:config.source_mode??'harness_plus_motif',task_id:spec.task_id,owner:spec.owner,context,
   tools:options.tools??[],original_messages_sha256:digest(options.messages),original_system_sha256:digest(options.system??null),
   transparent_capture:true,manual_workflow_plugins:false};
  save(join(directory,'request.json'),snapshot);let finish:any=null;
  try{
   for await(const chunk of next()){
    appendFileSync(join(directory,'chunks.jsonl'),JSON.stringify(chunk)+'\n',{mode:0o600});if(chunk.type==='finish')finish=chunk;
    yield chunk;
   }
   save(join(directory,'completion.json'),{status:'completed',finish,request_sha256:sha(join(directory,'request.json'))});
  }catch(error){save(join(directory,'failure.json'),{status:'failed',reason:String(error),request_sha256:sha(join(directory,'request.json'))});throw error;}
 },{global:true});
}
