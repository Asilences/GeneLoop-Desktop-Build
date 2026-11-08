/** Bounded local child transport. Rules remain in the common Python kernel. */
import {spawn,type ChildProcessWithoutNullStreams} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import {performance} from 'node:perf_hooks';

const root=fileURLToPath(new URL('../../',import.meta.url));
const MAX_BYTES=32*1024*1024,MAX_FRAME=MAX_BYTES+4096,MAX_POOLS=4,MAX_QUEUED=32;
const DEADLINE=120000,IDLE=60000;
const allowed:string[]=JSON.parse(readFileSync(new URL('../../config/rsi-privacy-tools.json',import.meta.url),'utf8')).worker_environment;
export const privacyWorkerEnvironment=()=>Object.fromEntries(allowed.filter(key=>process.env[key]!==undefined)
 .map(key=>[key,process.env[key]!]));
type Job={id:string;body:string;bytes:number;deadline:number;resolve:(value:any)=>void;reject:(error:Error)=>void;
 timer:ReturnType<typeof setTimeout>;signal?:AbortSignal;abort?:()=>void;settled:boolean};
type Pool={key:string;python:string;env:Record<string,string>;queue:Job[];bytes:number;child?:ChildProcessWithoutNullStreams;
 current?:Job;buffer:Buffer;idle?:ReturnType<typeof setTimeout>};
const pools=new Map<string,Pool>();
const rejected=()=>Error('geneloop_privacy_rejected');

function settle(pool:Pool,job:Job,error?:Error,value?:any){
 if(job.settled)return;
 job.settled=true;clearTimeout(job.timer);job.signal?.removeEventListener('abort',job.abort!);
 pool.bytes-=job.bytes;job.body='';
 if(error)job.reject(error);else job.resolve(value);
}
function stop(pool:Pool){
 clearTimeout(pool.idle);const child=pool.child;pool.child=undefined;pool.buffer=Buffer.alloc(0);
 child?.stdin.destroy();child?.stdout.destroy();child?.stderr.destroy();child?.kill();
}
function failed(pool:Pool,child:ChildProcessWithoutNullStreams){
 if(pool.child!==child)return;
 const current=pool.current;pool.current=undefined;stop(pool);
 if(current)settle(pool,current,rejected());
 dispatch(pool);
}
function dispatch(pool:Pool){
 if(pool.current)return;
 const next=pool.queue.shift();
 if(!next){
  pool.idle=setTimeout(()=>{if(!pool.current&&!pool.queue.length){stop(pool);pools.delete(pool.key);}},IDLE);
  pool.idle.unref?.();return;
 }
 if(next.settled){dispatch(pool);return;}
 clearTimeout(pool.idle);pool.current=next;
 if(performance.now()>=next.deadline){pool.current=undefined;settle(pool,next,rejected());dispatch(pool);return;}
 if(!pool.child){
  let child:ChildProcessWithoutNullStreams;
  try{
   child=spawn(pool.python,['-B','-m','src.adapters.geneloop_privacy_worker','--authorized'],
    {cwd:root,env:{...pool.env,PYTHONUTF8:'1'},windowsHide:true,stdio:['pipe','pipe','pipe']});
  }catch{pool.current=undefined;settle(pool,next,rejected());dispatch(pool);return;}
  pool.child=child;child.unref();
  (child.stdin as any).unref?.();(child.stdout as any).unref?.();(child.stderr as any).unref?.();
  child.stderr.resume(); // Never persist findings, paths or upstream exception text.
  child.on('error',()=>failed(pool,child));child.on('exit',()=>failed(pool,child));
  child.stdin.on('error',()=>failed(pool,child));
  child.stdout.on('data',(chunk:Buffer)=>{
   if(pool.child!==child)return;
   pool.buffer=Buffer.concat([pool.buffer,chunk]);
   if(pool.buffer.length>MAX_FRAME){failed(pool,child);return;}
   const end=pool.buffer.indexOf(10);if(end<0)return;
   const current=pool.current;
   try{
    if(!current||end!==pool.buffer.length-1||performance.now()>=current.deadline)throw rejected();
    const result=JSON.parse(pool.buffer.subarray(0,end).toString('utf8'));pool.buffer=Buffer.alloc(0);
    if(result.id!==current.id||typeof result.ok!=='boolean'||
      Object.keys(result).some(key=>!['id','ok','value','reason'].includes(key)))throw rejected();
    if(result.ok&&(!('value'in result)||Buffer.byteLength(JSON.stringify(result.value))>MAX_BYTES))throw rejected();
    if(performance.now()>=current.deadline)throw rejected();
    pool.current=undefined;
    settle(pool,current,result.ok?undefined:rejected(),result.value);dispatch(pool);
   }catch{failed(pool,child);}
  });
 }
 try{pool.child.stdin.write(next.body+'\n');next.body='';}catch{failed(pool,pool.child);}
}

export function runPrivacyWorker(python:string,operation:string,value:unknown,signal?:AbortSignal):Promise<any>{
 if(signal?.aborted)return Promise.reject(rejected());
 let body:string;
 try{body=JSON.stringify({id:randomUUID(),operation,value});}catch{return Promise.reject(rejected());}
 if(typeof body!=='string'||Buffer.byteLength(body)>MAX_FRAME)return Promise.reject(rejected());
 const env=privacyWorkerEnvironment(),key=JSON.stringify([python,env]);
 let pool=pools.get(key);
 if(!pool){
  if(pools.size>=MAX_POOLS){
   const idle=[...pools.values()].find(row=>!row.current&&!row.queue.length);
   if(!idle)return Promise.reject(rejected());stop(idle);pools.delete(idle.key);
  }
  pool={key,python,env,queue:[],bytes:0,buffer:Buffer.alloc(0)};pools.set(key,pool);
 }
 const selected=pool,bytes=Buffer.byteLength(body);
 if(selected.queue.length>=MAX_QUEUED||selected.bytes+bytes>MAX_FRAME)return Promise.reject(rejected());
 return new Promise((resolve,reject)=>{
  const job:Job={id:JSON.parse(body).id,body,bytes,deadline:performance.now()+DEADLINE,resolve,reject,settled:false,
   timer:undefined as any,signal};
  const cancel=()=>{
   if(job.settled)return;
   if(selected.current===job){selected.current=undefined;stop(selected);}
   else selected.queue=selected.queue.filter(row=>row!==job);
   settle(selected,job,rejected());dispatch(selected);
  };
  job.abort=cancel;job.timer=setTimeout(cancel,DEADLINE);signal?.addEventListener('abort',cancel,{once:true});
  selected.bytes+=bytes;selected.queue.push(job);dispatch(selected);
 });
}

/** Test/application teardown only; callers never receive a raw queued payload. */
export function closePrivacyWorkers(){
 for(const pool of pools.values()){
  const jobs=[...(pool.current?[pool.current]:[]),...pool.queue];pool.current=undefined;pool.queue=[];stop(pool);
  for(const job of jobs)settle(pool,job,rejected());
 }
 pools.clear();
}
