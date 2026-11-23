/** File-only SDK composition: reuse the upstream server and public native resume. */
import {apply as serve} from '@deepseek-ai/dsh-sdk-jsonrpc-server';
export const name='geneloop-file-resume';
export const inject=['agents','sdkAppStartup','loader'];

export function recoveryContext(ctx:any,sessionId:string){
 let resumed=false;
 const agents=new Proxy(ctx.agents,{get(target,key){
  if(key==='create')return async(options:any)=>{
   if(options.sessionId!==sessionId||resumed)throw Error('File recovery must open its original session exactly once');
   resumed=true;
   return target.resume({resumeSessionId:sessionId,agentOptions:options.agentOptions});
  };
  const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
 }});
 return new Proxy(ctx,{get(target,key){
  if(key==='agents')return agents;
  const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
 }});
}

export function apply(ctx:any,config:any){
 if(typeof config.session_id!=='string'||!config.session_id)throw Error('original File session required');
 return serve(recoveryContext(ctx,config.session_id),{maxTokensAsSuccess:true});
}
