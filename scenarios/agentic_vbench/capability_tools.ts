/** Native transport for the original benchmark Capability dispatcher.
 * The Python Harness observer owns dispatch; this module only returns its reply.
 */
import {readFileSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {isDeepStrictEqual} from 'node:util';
import {setTimeout as pause} from 'node:timers/promises';
export const name='agentic-vbench-capability-tools';
export const inject=['tools'];
export function apply(ctx:any){
 const spec=JSON.parse(readFileSync(process.env.GENELOOP_VIDEO_CAPABILITY_TOOLS!,'utf8'));
 const directory=process.env.GENELOOP_VIDEO_CAPABILITY_REPLIES!;
 for(const tool of spec){
  if(!['capability_list','capability_call'].includes(tool.name))throw Error('video_capability_transport_tool_invalid');
  ctx.tools.register({...tool,output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
   async execute(args:any,execution:any){
    if(!/^[A-Za-z0-9_-]{1,200}$/.test(execution.callId))throw Error('video_capability_transport_call_invalid');
    const path=join(directory,execution.callId+'.json');
    while(!existsSync(path))await pause(20,undefined,{signal:execution.signal});
    const reply=JSON.parse(readFileSync(path,'utf8'));
    if(reply.call_id!==execution.callId||reply.name!==tool.name||!isDeepStrictEqual(reply.arguments,args))
     throw Error('video_capability_transport_reply_mismatch');
    if(reply.error)throw Error(reply.error);
    return reply.value;
   }});
 }
}
