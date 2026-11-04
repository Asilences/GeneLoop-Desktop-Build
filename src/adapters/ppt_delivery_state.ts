/** Identify repairs that changed a file without improving an observed defect. */
import {digest} from '../motif_core/online_skill_runtime.mjs';

export function deliveryProgress(previous:any,current:any){
 if(current.mechanical_status==='passed')return {status:'checked',next_action:'read_image'};
 if(current.retryable===true)return {status:'execution_failed',next_action:'inspect_stage_log'};
 const errors=(value:any)=>(value?.findings??[]).filter((row:any)=>row.severity==='error');
 const score=(rows:any[])=>rows.reduce((sum,row)=>sum+1+(typeof row.ratio==='number'?Math.max(0,4.5-row.ratio):0),0);
 const identity=(value:any)=>digest({content:(value?.page_receipts??[]).map((row:any)=>row.text_sha256),
  defects:errors(value).map((row:any)=>[row.rule,row.page,row.object,row.codepoints??null,row.detail??null]).sort()});
 const comparable=previous&&(current.page_receipts??[]).length>0&&current.page_receipts.every((row:any)=>typeof row.text_sha256==='string');
 if(comparable&&identity(previous)===identity(current)&&score(errors(current))>=score(errors(previous)))
  return {status:'stalled',next_action:'use_a_different_verified_repair_or_fallback'};
 return {status:'repair_needed',next_action:'repair_specific_findings'};
}
