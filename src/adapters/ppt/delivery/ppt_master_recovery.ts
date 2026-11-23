/** Continue provider-truncated PPT work through the Harness steering hook.
 * The Harness retains max-tokens as a turn-end reason after steering, so its
 * later tool-calls also need a continuation until the provider actually stops.
 */
/** Keep editable drafts ahead of their previews when a follow-up adds files.
 * Callers still enforce the owning conversation/lane and read immutable bytes.
 * This is ordinary input recovery, shared by Baseline and Motif, not a bypass.
 */
export function prioritizePptDeliveries<T extends {row:{name:string}}>(rows:T[]):T[]{
  const priority=(name:string)=>/\.pptx$/i.test(name)?0:/\.pdf$/i.test(name)?1:2;
  return [...rows].reverse().sort((a,b)=>priority(a.row.name)-priority(b.row.name));
}

export function createPptMasterRecovery(){
  let finish:string|null=null, recovering=false, continuations=0, text='', nativeCall=false, formatRepairs=0;
  let toolResults=0, lastFormatToolResults=-1, deliveryRepairs=0;
  const completedCalls=new Set<string>();
  return {
    begin(){finish=null;text='';nativeCall=false;},
    observe(chunk:any){
      if(chunk?.type==='finish')finish=chunk.reason?.kind??null;
      if(chunk?.type==='text-delta'&&typeof chunk.text==='string')text=(text+chunk.text).slice(-32768);
      if(chunk?.type==='block-end'&&chunk.block?.type==='text'&&typeof chunk.block.text==='string')text=chunk.block.text.slice(-32768);
      if(chunk?.type==='tool-call-delta'||chunk?.type==='block-end'&&chunk.block?.type==='tool-call')nativeCall=true;
    },
    /** A real Harness tool result, including a correctable error, separates incidents. */
    observeResult(execution:any){
      if(typeof execution?.callId!=='string'||!execution.callId||completedCalls.has(execution.callId))return;
      completedCalls.add(execution.callId);toolResults++;
    },
    stop(aborted:boolean,context:{unfinished?:boolean}={}){
      if(aborted)return null;
      // Re-ask through native steering. Text is never parsed into executable calls.
      const malformed=/<\/?[｜|]DSML[｜|]\s*(?:invoke|function_calls)\b|<parameter\s+name=["'](?:edit|bash|write)["']/i.test(text);
      if(finish==='stop'&&context.unfinished===true&&malformed&&!nativeCall&&formatRepairs<3&&
        (formatRepairs===0||toolResults>lastFormatToolResults)){
        formatRepairs++;lastFormatToolResults=toolResults;continuations++;finish=null;text='';
        return {continuation:continuations,truncated:false,reason:'tool_call_as_text',instruction:
          '当前PPT尚未交付。刚才的编辑指令只是普通文本，没有成为实际工具调用，因而没有执行。下一次只发出一个已注册工具的原生调用，不输出DSML/XML标记、长篇文字或并行批次。沿用已有材料、页面和内容，只完成尚缺步骤。已有JSON稿件用patch_ppt修订或空edits恢复导出；SVG稿件沿prepare_ppt/finalize_ppt交付。不要重新测宽或重做成功页面。'};
      }
      // A normal provider stop can be only a promise to build the files. Allow
      // one same-task continuation after genuine tool progress; never interpret
      // prose as executable parameters or override refusal/user clarification.
      const refusal=/(?:cannot|can['’]t|not authorized|permission denied|无法|不能|请.{0,16}(?:提供|确认|授权|选择|补充)|please\s+(?:provide|confirm|choose)|(?:which|what)\s+(?:template|style|audience)|\?\s*$)/i.test(text);
      if(finish==='stop'&&context.unfinished===true&&!nativeCall&&!malformed&&text.trim()&&!refusal&&toolResults>0&&deliveryRepairs<1){
        deliveryRepairs++;continuations++;finish=null;text='';
        return {continuation:continuations,truncated:false,reason:'delivery_incomplete',instruction:
          '这份已授权PPT任务目前只有制作计划，没有当前PPTX/PDF交付。继续当前任务，复用已读材料，不重新搜索或重读论文。已有JSON稿件用patch_ppt完成修订/导出；尚未制作时直接提交完整内容给build_ppt，已选择SVG路线则完成现有项目的finalize_ppt。只完成尚缺的制作和当前预览检查，不再叙述将要制作；遇到真实权限或缺失事实问题则如实说明。'};
      }
      const truncated=finish==='max-tokens';
      if(!truncated && !(recovering && finish==='tool-calls'))return null;
      recovering=true;finish=null;continuations++;
      return {continuation:continuations,truncated,reason:'provider_length',instruction:truncated
        ? '服务商在单次输出长度处截断了当前回复，任务尚未完成。继续同一个已授权任务，沿用已读资料、已有项目与原始要求；执行余下制作和检查，不重述长篇计划。不得把截断内容当成完整工具调用，也不得声称尚未生成的文件已交付。'
        : '继续执行同一个尚未完成的任务，使用刚才实际工具结果推进；全部完成后正常给出交付答复。'};
    },
  };
}
