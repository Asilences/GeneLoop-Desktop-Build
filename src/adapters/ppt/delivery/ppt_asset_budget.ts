/** Shared product limits for optional asset hunting; not an RSI policy. */
export function pptAssetBudget(task:any,call:any,now=Date.now()):string|undefined{
 if(task?.status!=='running'||task.scene?.id!=='ppt'||task.scene.ppt_execution_strategy!=='ppt_master')return;
 const command=call.name==='bash'?call.arguments?.command:'';
 const networkScript=typeof command==='string'&&/\bcurl\b|\bwget\b|urllib\.(?:request|urlopen)|requests\.(?:get|post)|https?:\/\//i.test(command);
 if(!networkScript&&!['web_search','web_fetch'].includes(call.name))return;
 // Reject open-ended crawlers, not source reading or local image preparation.
 if(networkScript&&/\bnohup\b|\bwhile\s|\bfor\s.+(?:\bin\b|range\s*\()|\bdef\s+(?:fetch|search|download|dl)\b|retries|tries\s*=/i.test(command))
  return 'PPT素材获取不运行批量爬虫、后台搜图或自写重试循环。使用已上传资料和本地素材先完成整份基础稿；单个必需来源用web_fetch/web_search。图片裁剪、缩放用prepare_ppt_asset。不得编造缺失的科研图或数据。';
 const stats=task.stats??(task.stats={});
 const seen=task.ppt_asset_calls??(task.ppt_asset_calls=new Map<string,string|undefined>());
 if(call.callId&&seen.has(call.callId))return seen.get(call.callId);
 const decided=(result?:string)=>{if(call.callId)seen.set(call.callId,result);return result;};
 stats.ppt_asset_started_at??=now;
 if(Number(stats.ppt_external_asset_attempts??0)>=8||now-stats.ppt_asset_started_at>90000){
  stats.ppt_asset_fallback=true;
  return decided('本轮外部素材获取已到收敛点，继续制作完整基础稿，不再重试外网搜图。优先使用原附件、已有本地图片或准确的文字/图表表达。用户必需但缺失的图件必须明确说明，不能伪造成已完成；已有当前成品直接交付，增强素材放后续用户修订。');
 }
 stats.ppt_external_asset_attempts=Number(stats.ppt_external_asset_attempts??0)+1;
 return decided();
}
