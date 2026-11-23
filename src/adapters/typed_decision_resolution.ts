/** Scene-neutral completion of unresolved questions; no task tools or routing. */
import {runTypedDecision} from './typed_decisions.ts';

export function mergeResolvedQuestions(packet:any,primary:any,completion:any){
 const keys=Object.keys(packet.request.questions),pending=primary.decision.rejected_questions;
 if(!Array.isArray(pending)||new Set(pending).size!==pending.length||pending.some((k:string)=>!keys.includes(k)))throw Error('invalid pending questions');
 const values={...primary.decision.values};
 if(Object.keys(values).some(k=>!keys.includes(k)||pending.includes(k)))throw Error('invalid accepted question ownership');
 if(completion){
  if(completion.parent_call_id!==primary.call_id||Object.keys(completion.decision.values).some(k=>!pending.includes(k)))throw Error('completion changed an accepted question');
  Object.assign(values,completion.decision.values);
 }
 const rejected=keys.filter(k=>!Object.hasOwn(values,k));
 return {accepted:rejected.length===0,values,rejected_questions:rejected,status:rejected.length?'fallback_required':'accepted',threshold:primary.decision.threshold};
}

export async function resolveTypedQuestions(packet:any,options:any,runner:any=runTypedDecision){
 const calls:any[]=[];
 const invoke=async(p:any,provider:string,stage:string)=>{
  const r=await runner(p,{...options,provider});calls.push(r);
  if(options.onResult)await options.onResult(r,stage);
  return r;
 };
 const primary=await invoke(packet,options.provider,'primary');
 // Zero useful answers returns to the ordinary Harness without another typed call.
 if(options.provider!=='jev'||primary.decision.accepted||!Object.keys(primary.decision.values).length)
  return {calls,decision:primary.decision,provider:options.provider};
 options.signal?.throwIfAborted();
 const pending=primary.decision.rejected_questions;
 const questions=Object.fromEntries(pending.map((k:string)=>[k,packet.request.questions[k]]));
 const completionPacket={...packet,parent_call_id:primary.call_id,request:{...packet.request,questions}};
 const completion=await invoke(completionPacket,'deepseek','compact_completion');
 return {calls,decision:mergeResolvedQuestions(packet,primary,completion),provider:'jev+deepseek'};
}
