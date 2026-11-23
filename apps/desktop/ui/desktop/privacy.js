import {node,button} from './components.js';
/** Service information and actual local pipeline state; no learning/upload switches. */
export function privacyPanel(){
 const section=node('section',{class:'privacy-panel','data-privacy-panel':'true'});
 const status=node('p',{role:'status'},'正在读取本机处理状态…');
 section.append(node('h3',{},'数据与隐私'),
  node('p',{},'本机工作区的 Agent、工具和 RSI 在此电脑运行；模型请求仍发送至已连接的云端模型服务。'),
  node('p',{},'正常任务自动进入本机学习与脱敏处理。仅通过检查的工具流程结构经 HTTPS 自动收集；不上传原始轨迹、正文、参数、文件路径或原始工具名。'),
  node('p',{},'学习与收集是服务固定流程。没有独立验收证据时，候选不会自动成为已认证能力。'),status);
 let active=true;
 const labels={received:'服务器已回执',pending:'等待处理',unknown:'等待核对回执',waiting_server:'等待服务器接口',blocked:'脱敏未通过',blocked_transport:'等待 HTTPS 连接',no_tool_calls:'没有工具流程可收集'};
 async function refresh(){
  try{
   const value=await window.desktopWorkspaces.rsiStatus();if(!active)return;
   const counts=Object.entries(value.collection).map(([key,count])=>(labels[key]||key)+' '+count).join(' · ');
   status.textContent='接收端：'+value.target+'。'+(counts||'完成本机任务后会在此显示进度。');
   learning.textContent='本机学习：'+(value.learning.state==='processing_failed'?'处理暂未完成，将在后续任务重试':value.learning.certified?'已通过结构认证 '+value.learning.certified+' 项':'等待独立任务证据')+'。任务轨迹副本最多保留 '+value.raw_retention_days+' 天，派生学习副本最多保留 '+value.learning_retention_days+' 天。';
  }catch{if(active)status.textContent='请先连接并登录 GeneLoop，再查看本机处理状态。';}
 }
 const learning=node('p');section.append(learning,button('刷新状态',refresh,'secondary'));
 const timer=setInterval(refresh,15000);void refresh();
 return {section,dispose(){active=false;clearInterval(timer);}};
}
