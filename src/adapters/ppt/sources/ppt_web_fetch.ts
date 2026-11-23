/** PPT-only execution containment; this is shared engineering, not an RSI Motif. */
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {scopeOf} from '@deepseek-ai/dsh-scope';
import {proxyEnvironmentForChild} from '@deepseek-ai/dsh-http-proxy';

const worker=fileURLToPath(new URL('./ppt_web_fetch_worker.mjs',import.meta.url));
export function pptFetchEnvironment(source:NodeJS.ProcessEnv=process.env){
 const names=['PATH','HOME','USERPROFILE','SYSTEMROOT','SystemRoot','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL','NODE_OPTIONS'];
 return {...Object.fromEntries(names.filter(name=>source[name]!==undefined).map(name=>[name,source[name]])),
  ...proxyEnvironmentForChild(),ELECTRON_RUN_AS_NODE:'1'};
}
export function isolatedPptFetch(url:string,signal?:AbortSignal,options:{workerPath?:string;timeoutMs?:number;env?:NodeJS.ProcessEnv}={}):Promise<any>{
 if(typeof url!=='string'||!url.trim()||url.length>16384)return Promise.reject(Error('WEB_INVALID_URL'));
 if(signal?.aborted)return Promise.reject(Error('WEB_ABORTED'));
 return new Promise((resolve,reject)=>{
  const child=spawn(process.execPath,['--max-old-space-size=256',options.workerPath??worker],{
   env:pptFetchEnvironment(options.env??process.env),stdio:['pipe','pipe','pipe'],windowsHide:true});
  const chunks:Buffer[]=[];let bytes=0,settled=false;
  const finish=(error?:Error,value?:any)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);error?reject(error):resolve(value);};
  const abort=()=>{child.kill();finish(Error('WEB_ABORTED'));};
  const timer=setTimeout(()=>{child.kill();finish(Error('WEB_FETCH_TIMEOUT'));},options.timeoutMs??31000);timer.unref();
  signal?.addEventListener('abort',abort,{once:true});
  child.on('error',()=>finish(Error('WEB_WORKER_START_FAILED')));
  child.stdin.on('error',()=>{});
  child.stdout.on('data',(chunk:Buffer)=>{
   bytes+=chunk.length;if(bytes>2*1024*1024){child.kill();finish(Error('WEB_RESPONSE_TOO_LARGE'));}else chunks.push(chunk);
  });
  child.stderr.on('data',()=>{}); // Native diagnostics stay out of model context.
  child.on('close',(code,termination)=>{
   if(settled)return;
   let result:any;try{result=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{}
   if(!result?.ok){
    const reason=/^[A-Z_]{1,80}$/.test(result?.error?.code??'')?result.error.code:
     termination?'WEB_WORKER_TERMINATED':code!==0?'WEB_WORKER_FAILED':'WEB_WORKER_INVALID_RESPONSE';
    finish(Error(reason));return;
   }
   const value=result.value;
   if(code!==0||termination||typeof value?.url!=='string'||!Number.isInteger(value.statusCode)||
    !['html','text'].includes(value.body?.kind)||typeof value.body?.content!=='string'||
    typeof value.truncated!=='boolean'||value.body.kind==='html'){
    finish(Error('WEB_WORKER_INVALID_RESPONSE'));return;
   }
   finish(undefined,value);
  });
  child.stdin.end(JSON.stringify({url}));
 });
}

export function bindPptWebFetch(agent:any,fetcher=isolatedPptFetch){
 const original=agent.ctx.tools.get('web_fetch',scopeOf(agent.ctx));
 if(!original)return ()=>{};
 // Keep model-facing name, order, schemas, metadata and presentation unchanged.
 return agent.ctx.tools.register({...original,async execute(args:any,execution:any){
  return fetcher(args.url,execution.signal);
 }});
}
