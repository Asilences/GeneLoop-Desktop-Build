/** Short-lived public HTTP retrieval and HTML conversion. No model credentials. */
import {pathToFileURL} from 'node:url';
import {HttpFetchProvider,DEFAULT_USER_AGENT} from '@deepseek-ai/dsh-web-fetch-http';
import {formatFetchOutput} from '@deepseek-ai/dsh-tool-web';
import {installProxyFromEnvironment} from '@deepseek-ai/dsh-http-proxy';

export function normalizePptFetchedValue(value){
 const cap=200000;
 if(value.body.kind!=='html')return value;
 const empty={...value,body:{kind:'text',content:''},truncated:false};
 const header=formatFetchOutput(empty,cap);
 const footer=formatFetchOutput({...empty,truncated:true},cap).slice(header.length);
 const rendered=formatFetchOutput(value,cap);
 if(!rendered.startsWith(header))throw Error('web_fetch_render_contract_changed');
 let content=rendered.slice(header.length),truncated=value.truncated;
 if(footer&&content.endsWith(footer)){content=content.slice(0,-footer.length);truncated=true;}
 return {...value,body:{kind:'text',content},truncated};
}

async function main(){
 let raw='';
 for await(const chunk of process.stdin){raw+=chunk;if(Buffer.byteLength(raw)>32768)throw Error('fetch_request_too_large');}
 const request=JSON.parse(raw);
 if(typeof request.url!=='string'||!request.url.trim())throw Error('fetch_url_required');
 const environment=new Map(Object.entries(process.env).map(([name,value])=>[name,{value}]));
 const dispose=await installProxyFromEnvironment(environment,()=>{});
 try{
  const provider=new HttpFetchProvider({maxResponseBytes:5e6,maxBodyChars:1e5,timeoutMs:30000,
   maxRedirects:5,userAgent:DEFAULT_USER_AGENT});
  const value=await provider.fetch({url:request.url},AbortSignal.timeout(30000));
  process.stdout.write(JSON.stringify({ok:true,value:normalizePptFetchedValue(value)}));
 }finally{await dispose();}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 main().catch(error=>{
  // Do not return proxy addresses, credentials, or raw native exception chains.
  process.stdout.write(JSON.stringify({ok:false,error:{code:/^[A-Z_]{1,80}$/.test(error.code??'')?error.code:'WEB_PROVIDER_ERROR'}}));
  process.exitCode=1;
 });
}
