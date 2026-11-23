/** Rehydrate only genuine completed tool receipts from the native persisted log. */
import {observation} from '../../motif_core/runtime/online_skill_runtime.mjs';
export function completedToolHistory(events:any[]){
 const calls=new Map<string,any>(),history:any[]=[];
 for(const event of events){
  if(event.type==='tool/call'){
   const e=event.data;
   if(!e?.callId||!e.name)continue;
   if(calls.has(e.callId))throw Error('duplicate native recovery call identity');
   const args=typeof e.arguments==='string'?JSON.parse(e.arguments):e.arguments;
   calls.set(e.callId,{tool:e.name,call_id:e.callId,args});
  }
  if(event.type!=='tool/result')continue;
  for(const block of event.data?.message?.content??[]){
   if(block.type!=='tool-result'||block.isError)continue;
   const call=calls.get(block.toolCallId);if(!call)continue;
   const out=observation({content:block.content},call.tool);
   if(!out||out.error||out.isError)continue;
   history.push({...call,out});
  }
 }
 return history;
}
