/** Opt-in native cancellation diagnostic. Runs no model and deploys no service.
 * Supply a NEW dedicated task workspace and a root with at least two leaf calls.
 * Only runSourceCapability may clean up its nonce-owned worker/container. This
 * script never removes containers, including when a diagnostic check fails.
 */
import {readFileSync,realpathSync,existsSync,lstatSync,readdirSync,readlinkSync,mkdirSync,writeFileSync,createReadStream} from 'node:fs';
import {join,relative,isAbsolute,dirname,basename,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {runSourceCapability} from '../src/adapters/source_capability_runtime.ts';
import {capabilityDigest,validateCapabilitySnapshot} from '../src/adapters/capability_contract.ts';

const exec=promisify(execFile),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const fail=reason=>{throw Error(reason);};
const flags=new Map();
for(let index=2;index<process.argv.length;index++){
 const key=process.argv[index];
 if(key==='--execute')flags.set(key,true);
 else if(key.startsWith('--')&&process.argv[index+1])flags.set(key,process.argv[++index]);
 else fail('cancel_check_arguments_invalid');
}
const bounded=(key,fallback,min,max)=>{
 const value=flags.has(key)?Number(flags.get(key)):fallback;
 if(!Number.isSafeInteger(value)||value<min||value>max)fail('cancel_check_duration_invalid');
 return value;
};
const contained=(base,path)=>{const value=relative(base,path);return value!==''&&value!=='..'&&!value.startsWith('../')&&!isAbsolute(value);};
const json=path=>JSON.parse(readFileSync(path,'utf8'));
async function inspect(identity){
 try{return JSON.parse((await exec('docker',['inspect',identity],{timeout:15000,maxBuffer:2_000_000})).stdout)[0];}
 catch(error){
  if(/No such (object|container)/.test(error.stderr??''))return null;
  throw Error('cancel_check_container_inspection_failed');
 }
}
async function findOwnedRunningContainer(calls){
 if(!existsSync(calls))return null;
 const candidates=(await exec('docker',['ps','-q','--filter','label=geneloop.experiment=source-capability-v1'],
  {timeout:15000,maxBuffer:100_000})).stdout.trim().split(/\s+/).filter(Boolean);
 if(candidates.length>256)fail('cancel_check_container_inventory_too_large');
 for(const identity of candidates){
  const container=await inspect(identity);
  if(!container?.State?.Running)continue;
  const nonce=container.Config?.Labels?.['geneloop.capability_nonce'];
  if(!/^[a-f0-9]{32}$/.test(nonce??''))continue;
  const name=container.Name?.replace(/^\//,'');
  if(name!=='geneloop-cap-'+nonce)continue;
  const mount=container.Mounts?.find(mount=>mount.Destination==='/work'&&mount.RW===true);
  if(!mount||!contained(calls,mount.Source))continue;
  const parts=relative(calls,mount.Source).split('/');
  if(parts.length!==2||parts[1]!=='work'||!/^[a-f0-9-]{36}$/.test(parts[0]))continue;
  if(!existsSync(mount.Source)||realpathSync(mount.Source)!==mount.Source)continue;
  // Record only this invocation's verified ownership, never unrelated metadata.
  return {container_id:container.Id,name,nonce,call_id:parts[0],work:mount.Source,
   verified_mount:{source:mount.Source,destination:mount.Destination,writable:mount.RW}};
 }
 return null;
}
async function fileSnapshot(directory){
 const rows=[];let entries=0,bytes=0;
 async function walk(path){
  if(++entries>10000)fail('cancel_check_artifact_inventory_too_large');
  const stat=lstatSync(path),name=relative(directory,path);
  if(stat.isSymbolicLink()){rows.push({path:name,type:'symlink',target:readlinkSync(path)});return;}
  if(stat.isDirectory()){
   rows.push({path:name,type:'directory'});
   for(const child of readdirSync(path).sort())await walk(join(path,child));
  }else if(stat.isFile()){
   bytes+=stat.size;if(bytes>2_000_000_000)fail('cancel_check_artifact_bytes_too_large');
   const hash=createHash('sha256');for await(const chunk of createReadStream(path))hash.update(chunk);
   rows.push({path:name,type:'file',bytes:stat.size,sha256:hash.digest('hex')});
  }else rows.push({path:name,type:'special'});
 }
 if(existsSync(directory))await walk(directory);
 return {digest:capabilityDigest(rows),entries:rows};
}

async function main(){
 if(process.platform!=='linux')fail('cancel_check_linux_required');
 for(const key of ['--manifest','--snapshot','--args','--output'])if(!flags.has(key))fail('cancel_check_required_argument_missing');
 const manifest=json(flags.get('--manifest')),snapshot=validateCapabilitySnapshot(json(flags.get('--snapshot')),manifest.owner);
 const args=json(flags.get('--args')),root=manifest.grant.root,workspace=realpathSync(manifest.workspace),calls=join(workspace,'calls');
 const requestedOutput=flags.get('--output');
 if(!isAbsolute(requestedOutput))fail('cancel_check_output_scope_invalid');
 const output=resolve(requestedOutput),outputParent=realpathSync(dirname(output));
 if(output!==join(outputParent,basename(output))||!contained(workspace,output)||contained(calls,output)||output===calls)fail('cancel_check_output_scope_invalid');
 if(existsSync(calls)||existsSync(output))fail('cancel_check_requires_unused_workspace');
 const capabilities=new Map(snapshot.capabilities.map(capability=>[capability.id,capability]));
 function leaves(ref){const capability=capabilities.get(ref.id);if(!capability)fail('cancel_check_root_missing');
  return capability.implementation.kind==='legacy'?1:capability.implementation.steps.reduce((sum,step)=>sum+leaves(step.capability),0);}
 const plannedLeafCalls=leaves(root);if(plannedLeafCalls<2)fail('cancel_check_requires_successor');
 const waitMs=bounded('--wait-ms',120000,1000,900000),stabilityMs=bounded('--stability-ms',2000,1000,10000);
 if(!flags.has('--execute'))return {format:'source_capability_cancel_check_v1',status:'preview',
  task_id:manifest.task_id,workspace,planned_leaf_calls:plannedLeafCalls,wait_ms:waitMs,stability_ms:stabilityMs,
  instruction:'Pass --execute to run the dedicated native cancellation diagnostic; no model is called.'};
 mkdirSync(output,{mode:0o700});
 const save=(name,value)=>writeFileSync(join(output,name),JSON.stringify(value,null,2)+'\n',{mode:0o600});
 const controller=new AbortController();let ended=false,trace,error,observed=null,inspectionError=null;
 const run=runSourceCapability(flags.get('--manifest'),snapshot,args,{signal:controller.signal})
  .then(value=>{trace=value;},failure=>{error=/^(source|capability|rsi)_[a-z_]+$/.test(failure.message)?failure.message:'cancel_check_runtime_failed';})
  .finally(()=>{ended=true;});
 const started=Date.now();
 try{
  while(!ended&&Date.now()-started<waitMs){
   observed=await findOwnedRunningContainer(calls);
   if(observed)break;
   await sleep(100);
  }
 }catch(error){inspectionError=error.message;}
 const abortAt=new Date().toISOString();
 // On timeout/error stop our own invocation too, but never call it a successful
 // cancellation validation unless the native owned container was observed first.
 controller.abort();await run;
 if(trace)save('trace.json',trace);
 if(!observed){
  const result={format:'source_capability_cancel_check_v1',status:'not_observed',task_id:manifest.task_id,
   workspace,planned_leaf_calls:plannedLeafCalls,trace_status:trace?.status??null,
   reason:inspectionError??error??'owned_running_container_not_observed',abort_at:abortAt};
  save('result.json',result);return result;
 }
 const matched=trace?.receipts?.findIndex(receipt=>receipt.call_id===observed.call_id)??-1;
 const checks={owned_running_container_observed:true,trace_interrupted:trace?.status==='interrupted',
  cancelled_leaf_dispatched:matched>=0&&trace.receipts[matched].kind==='legacy'&&trace.receipts[matched].dispatched===true,
  observed_leaf_has_planned_successor:matched>=0&&trace.receipts.slice(0,matched+1).filter(receipt=>receipt.kind==='legacy'&&receipt.dispatched).length<plannedLeafCalls,
  no_successor_leaf_dispatch:matched>=0&&!trace.receipts.slice(matched+1).some(receipt=>receipt.kind==='legacy'&&receipt.dispatched),
  container_absent:!(await inspect(observed.container_id))&&!(await inspect(observed.name)),
  artifact_directory_stable:false};
 const samples=[];
 for(let index=0;index<3;index++){
  if(index)await sleep(Math.ceil(stabilityMs/2));
  samples.push(await fileSnapshot(calls));
  checks.container_absent&&=!(await inspect(observed.container_id))&&!(await inspect(observed.name));
 }
 checks.artifact_directory_stable=samples.every(sample=>sample.digest===samples[0].digest);
 save('artifact-samples.json',samples);
 const result={format:'source_capability_cancel_check_v1',status:Object.values(checks).every(Boolean)?'passed':'failed',
  task_id:manifest.task_id,workspace,planned_leaf_calls:plannedLeafCalls,observed,abort_at:abortAt,
  trace_status:trace?.status??null,runtime_error:error??null,checks,stability_ms:stabilityMs,
  limitation:'A bounded post-cancel observation window, not rollback of earlier artifacts or arbitrary external effects.'};
 save('result.json',result);return result;
}
try{
 const result=await main();process.stdout.write(JSON.stringify(result)+'\n');
 if(!['passed','preview'].includes(result.status))process.exitCode=1;
}catch(error){
 const reason=/^(cancel_check|source|capability|rsi)_[a-z_]+$/.test(error.message??'')?error.message:'cancel_check_failed';
 process.stdout.write(JSON.stringify({format:'source_capability_cancel_check_v1',status:'failed',reason})+'\n');process.exitCode=1;
}
