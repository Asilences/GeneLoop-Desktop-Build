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
  let finish:string|null=null, recovering=false, continuations=0;
  return {
    begin(){finish=null;},
    observe(chunk:any){if(chunk?.type==='finish')finish=chunk.reason?.kind??null;},
    stop(aborted:boolean){
      if(aborted)return null;
      const truncated=finish==='max-tokens';
      if(!truncated && !(recovering && finish==='tool-calls'))return null;
      recovering=true;finish=null;continuations++;
      return {continuation:continuations,truncated,instruction:truncated
        ? '服务商在单次输出长度处截断了当前回复，任务尚未完成。继续同一个已授权任务，沿用已读资料、已有项目与原始要求；执行余下制作和检查，不重述长篇计划。不得把截断内容当成完整工具调用，也不得声称尚未生成的文件已交付。'
        : '继续执行同一个尚未完成的任务，使用刚才实际工具结果推进；全部完成后正常给出交付答复。'};
    },
  };
}
