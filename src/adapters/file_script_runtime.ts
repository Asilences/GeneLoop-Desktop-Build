/** File programs use the existing no-network worker; all effects cross host MCP guards. */
import {createInterface} from 'node:readline';
import {runContainer} from './harness/dsh_code_container.ts';
const lines=createInterface({input:process.stdin});
const pending=new Map<number,{resolve:(v:any)=>void,reject:(e:any)=>void}>();
let started=false,sequence=0;
const abort=new AbortController();process.on('SIGTERM',()=>abort.abort());
const send=(v:any)=>new Promise<void>((resolve,reject)=>process.stdout.write(JSON.stringify(v)+'\n',error=>error?reject(error):resolve()));
lines.on('line',async line=>{
 try{
  const q=JSON.parse(line);
  if(q.type==='response'){
   const p=pending.get(q.id);if(!p)throw Error('unexpected host response');pending.delete(q.id);
   q.error?p.reject(Error(q.error)):p.resolve(q.value);return;
  }
  if(started||q.type!=='run')throw Error('one script per worker');started=true;
  const result=await runContainer({program:q.program,signal:abort.signal,bindings:[{global:'files',functions:{
   call:async(args:any)=>await new Promise((resolve,reject)=>{
    const id=++sequence;pending.set(id,{resolve,reject});send({...args,type:'call',id}).catch(reject);
   })
  }}]},'node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e');
  await send({type:'done',result});lines.close();process.exit(0);
 }catch(error){await send({type:'done',result:{error:{kind:'protocol',message:String(error)},logs:[]}});lines.close();process.exit(1);}
});
