/** Generic JSON decision contracts. Programs come from witnessed model decisions. */
import {runProgram,validateProgram,digest} from './paper_rsi_program.ts';
import {validateJevRequest} from './kouri_jev.ts';
import {withFileReadEvidence} from './file_read_evidence.ts';
export const FORMAT='geneloop-learned-decision-v1';
const fields=['format','description','scope_description','guard','request','bind','training_witnesses'];
const object=(v:any)=>v!==null&&typeof v==='object'&&!Array.isArray(v);
// File contexts already exist in memory; a second 192KB cutoff made long-file
// recipes unreachable. Keep expression/fuel/host-access checks in the kernel.
export const runLearnedProgram=(program:any,input:any)=>runProgram(program,withFileReadEvidence(input),{inputBytes:null,outputBytes:null});
export function validateLearnedDecision(value:any){
 if(!object(value)||value.format!==FORMAT||Object.keys(value).length!==fields.length||fields.some(k=>!Object.hasOwn(value,k))||
  typeof value.description!=='string'||!value.description||typeof value.scope_description!=='string'||!value.scope_description||
  !Array.isArray(value.training_witnesses)||!value.training_witnesses.length)throw Error('invalid learned decision');
 for(const key of ['guard','request','bind'])validateProgram(value[key]);
 for(const w of value.training_witnesses)if(!object(w)||typeof w.snapshot_id!=='string'||!object(w.values))throw Error('actual source witnesses required');
 return value;
}
export function prepareLearnedAction(value:any,context:any){
 validateLearnedDecision(value);
 if(runLearnedProgram(value.guard,context)!==true)return null;
 const request=runLearnedProgram(value.request,context);
 if(object(request)&&request.mode==='direct'){
  if(Object.keys(request).some(k=>!['mode','evidence'].includes(k)))throw Error('invalid direct program preparation');
  return {kind:'direct',request};
 }
 if(!object(request)||!Array.isArray(request.questions)||!request.questions.length||
   request.questions.some(q=>!object(q)||typeof q.id!=='string'||!q.id||!object(q.question))||
   new Set(request.questions.map(q=>q.id)).size!==request.questions.length)throw Error('invalid learned question builder');
 return {kind:'typed',request:validateJevRequest({state:JSON.stringify(request.state),questions:Object.fromEntries(request.questions.map(q=>[q.id,q.question]))})};
}
export function prepareLearnedDecision(value:any,context:any){
 const prepared=prepareLearnedAction(value,context);
 if(!prepared)return null;
 if(prepared.kind!=='typed')throw Error('direct program requires action execution port');
 return prepared.request;
}
export function bindLearnedDecision(value:any,context:any,values:any){
 validateLearnedDecision(value);
 const result=runLearnedProgram(value.bind,{...context,answers:values});
 if(result===null)return null;
 if(!object(result)||Object.keys(result).some(k=>!['tool','arguments','text'].includes(k))||typeof result.tool!=='string'||!object(result.arguments)||
  Object.hasOwn(result,'text')&&typeof result.text!=='string')throw Error('invalid learned tool binding');
 return result;
}
export const learnedDecisionDigest=digest;
