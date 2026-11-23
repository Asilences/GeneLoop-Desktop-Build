/** Account-private desktop access to the existing File JEV and accounting CLI. */
import {mkdirSync,readFileSync,existsSync,writeFileSync,renameSync,lstatSync,readdirSync} from 'node:fs';
import {isAbsolute,join,dirname,relative,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {validateDecisionPacket} from '../src/adapters/typed_decisions.ts';

const digest=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const read=file=>JSON.parse(readFileSync(file,'utf8'));
const beneath=(root,path)=>{const rel=relative(root,path);return rel!==''&&rel!=='..'&&!rel.startsWith('..'+sep)&&!isAbsolute(rel);};
const unknown=()=>Object.assign(Error('Previous File judgement outcome is unknown'),{status:409});

export function createDesktopDecisions(settings) {
  const active=new Map();
  function account(userId) {
    const entry=settings?.accounts?.[userId];
    if(!entry)return;
    if(!['config','meterContext','python'].every(key=>typeof entry[key]==='string'&&isAbsolute(entry[key])))throw Error('Invalid desktop File decision configuration');
    const context=read(entry.meterContext);
    if(context.format!=='geneloop-decision-account-v1'||context.owner!==userId)throw Error('Desktop File decision account differs');
    return {...entry,directory:join(dirname(entry.meterContext),'desktop-decisions')};
  }
  async function meter(entry,event) {
    await new Promise((done,reject)=>{
      const child=spawn(entry.python,[join(import.meta.dirname,'decision-meter.py')],{
        stdio:['pipe','ignore','ignore'],windowsHide:true,
        env:{SystemRoot:process.env.SystemRoot,PATH:process.env.PATH,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
      child.once('error',reject);
      child.once('exit',code=>code===0?done():reject(Error('Original File account meter rejected the judgement')));
      child.stdin.on('error',reject);
      child.stdin.end(JSON.stringify({context_file:entry.meterContext,event}));
    });
  }
  async function invoke(entry,packet,runRoot,signal) {
    // Reuse #170's one-shot CLI and its original meter. The fresh process also
    // isolates TLS from native libraries loaded by the long-lived web host.
    await new Promise((done,reject)=>{
      const child=spawn(process.execPath,[join(import.meta.dirname,'run-typed-decision.mjs')],{
        stdio:['pipe','pipe','ignore'],windowsHide:true,...(signal?{signal}:{}),
        env:{SystemRoot:process.env.SystemRoot,PATH:process.env.PATH,NODE_OPTIONS:process.env.NODE_OPTIONS,
          SSS_PYTHON:entry.python,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
      let bytes=0,oversized=false;
      child.stdout.on('data',chunk=>{bytes+=chunk.length;if(bytes>2*1024*1024){oversized=true;child.kill();}});
      child.once('error',reject);
      child.once('exit',code=>code===0&&!oversized?done():reject(Error('Original File judgement CLI did not complete')));
      child.stdin.on('error',reject);
      child.stdin.end(JSON.stringify({packet,provider:'jev',record_root:runRoot,config:entry.config,meter_context:entry.meterContext}));
    });
  }
  return {
    available(userId){return Boolean(account(userId));},
    async judge(userId,input,signal) {
      const entry=account(userId);
      if(!entry)throw Error('File JEV is unavailable for this account');
      if(!input||!/^[a-f0-9]{64}$/.test(input.request_id??'')||Object.keys(input).sort().join(',')!=='packet,request_id')throw Error('Invalid File judgement identity');
      const packet=validateDecisionPacket({...input.packet,owner:userId});
      if(packet.scene!=='files'||!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(packet.task_id))throw Error('Invalid local File task');
      const scope=digest({owner:userId,task:packet.task_id,request:input.request_id});
      if(active.has(scope))throw Object.assign(Error('File judgement already running'),{status:409});
      active.set(scope,true);
      try{
        signal?.throwIfAborted();
        mkdirSync(entry.directory,{recursive:true,mode:0o700});
        const folder=join(entry.directory,scope);
        mkdirSync(folder,{mode:0o700,recursive:true});
        if(lstatSync(folder).isSymbolicLink())throw Error('Private File judgement path changed');
        const stateFile=join(folder,'state.json'),packetHash=digest(packet),runRoot=join(folder,'runs');
        let state=existsSync(stateFile)?read(stateFile):null;
        if(state&&state.packetHash!==packetHash)throw Error('Original File judgement changed');
        const output=result=>({result:result.result,decision:result.decision,accounting:{
          call_id:result.call_id,reported_usage:result.reported_usage,
          provider_reported_cost:result.provider_reported_cost,provider_cost_currency:result.provider_cost_currency,
          invoice_verified:result.invoice_verified,upstream_attempts:result.upstream_attempts}});
        const receipt=()=>{
          let directory=state?.recordDirectory;
          if(!directory&&state?.runRoot===runRoot&&existsSync(runRoot)){
            if(lstatSync(runRoot).isSymbolicLink())throw Error('Private File judgement path changed');
            const rows=readdirSync(runRoot,{withFileTypes:true});
            if(rows.length!==1||!rows[0].isDirectory()||!/^[a-f0-9-]{36}$/.test(rows[0].name))throw unknown();
            directory=join(runRoot,rows[0].name);
          }
          if(!directory||!beneath(folder,directory))throw unknown();
          if(lstatSync(directory).isSymbolicLink())throw Error('Private File receipt path changed');
          const resultFile=join(directory,'result.json');
          if(!existsSync(resultFile))throw unknown();
          if(lstatSync(resultFile).isSymbolicLink())throw Error('Private File receipt path changed');
          const result=read(resultFile);
          if(result.status!=='completed'||result.packet_sha256!==packetHash||result.owner!==userId||result.task_id!==packet.task_id)throw Error('Original paid File receipt differs');
          return {result,directory};
        };
        if(state){
          const {result}=receipt();
          await meter(entry,result);
          return {...output(result),reused:true};
        }
        // Claim before launching, including across gateway processes. An unknown
        // or interrupted launch never starts another potentially paid operation.
        state={packetHash,runRoot};
        try{writeFileSync(stateFile,JSON.stringify(state)+'\n',{mode:0o600,flag:'wx'});}
        catch(error){if(error.code==='EEXIST')throw unknown();throw error;}
        await invoke(entry,packet,runRoot,signal);
        const {result,directory}=receipt();
        writeFileSync(stateFile+'.tmp',JSON.stringify({packetHash,recordDirectory:directory})+'\n',{mode:0o600});
        renameSync(stateFile+'.tmp',stateFile);
        return {...output(result),reused:false};
      }finally{active.delete(scope);}
    },
  };
}
