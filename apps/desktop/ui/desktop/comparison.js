import {request,post} from './api.js';
import {node,button,markdown,dialog,icon} from './components.js';
import {deliveryPath,deliveryFiles,presentation,presentationCard} from './deliveries.js';

function iconAction(label,symbol,action){
  const control=button(icon(symbol),action,'result-icon');
  control.setAttribute('aria-label',label);
  control.title=label;
  return control;
}

export function comparisonCard(view,{trace,onUpdate,fail}){
  const section=node('section',{class:'comparison-result','data-comparison':view.id},node('h3',{},view.presentation==='single'?'任务结果':'执行对照'));
  const terminal=new Set(['completed','failed','cancelled']);
  async function update(body,control){control.disabled=true;try{const next=await post('/api/harless/comparisons',{session_id:view.session_id,id:view.id,...body});onUpdate(next);}catch(error){fail(error);}finally{control.disabled=false;}}
  for(const [lane,result]of Object.entries(view.lanes||{})){
    const content=node('div',{class:'comparison-lane'},node('h4',{},view.presentation==='single'?'GeneLoop':lane==='motif'?'Motif执行':'标准执行'),node('small',{},({completed:'已完成',failed:'执行失败',cancelled:'已停止',running:'正在执行',queued:'等待执行',preparing:'正在准备'})[result.status]||'正在处理'));
    content.append(trace?node('pre',{},JSON.stringify(result.stats||{},null,2)):markdown(result.answer_display||result.answer||result.failure||'等待服务器返回结果…'));
    const deck=!trace&&presentation(deliveryFiles(deliveryPath(view.session_id,view.id),lane,result));
    if(deck)content.append(presentationCard(deck));
    const actions=node('div',{class:'result-tools',role:'group','aria-label':'结果操作'});
    const footer=node('div',{class:'result-footer'},actions);
    if(result.answer)actions.append(iconAction('复制结果','copy',async()=>{
      try{await navigator.clipboard.writeText(result.answer);}catch(error){fail(error);}
    }));
    const stats=result.stats||{},metrics=[];
    if(Number.isFinite(stats.model_requests))metrics.push(stats.model_requests+' 次模型请求');
    if(Number.isFinite(stats.input_tokens)&&Number.isFinite(stats.output_tokens))metrics.push((stats.input_tokens+stats.output_tokens).toLocaleString()+' tok');
    if(Number.isFinite(stats.cost_usd))metrics.push('代理估费 $'+stats.cost_usd.toFixed(4));
    if(metrics.length)footer.append(node('div',{class:'result-metrics'},metrics.join(' · ')));
    if(terminal.has(result.status)&&result.output_sha256){
      for(const [vote,label,symbol]of [['up','赞','like'],['down','踩','dislike']]){
        const selected=result.feedback===vote;
        const control=iconAction(label,symbol,()=>update({action:'feedback',lane,vote:selected?null:vote,output_sha256:result.output_sha256},control));
        control.setAttribute('aria-pressed',String(selected));actions.append(control);
      }
      if(view.scoring_available){
        const ratings=node('div',{class:'result-score-scale',role:'group','aria-label':'结果评分'});
        for(let score=1;score<=5;score++){
          const selected=view.scores?.[lane]===score;
          const control=button(String(score),()=>update({action:'rate',lane,score,revision:view.score_revision,output_sha256:result.output_sha256},control));
          control.setAttribute('aria-pressed',String(selected));control.setAttribute('aria-label',score+' 分');ratings.append(control);
        }
        footer.append(node('div',{class:'result-ratings'},node('span',{},'评分'),ratings));
      }
    }
    const history=iconAction('查看轨迹','trace',async()=>{history.disabled=true;try{const value=await request('/api/harless/comparisons?'+new URLSearchParams({session_id:view.session_id,id:view.id,trace:'1',lane,after:'-1',limit:'100'}));dialog('执行轨迹',node('pre',{},JSON.stringify(value,null,2)));}catch(error){fail(error);}finally{history.disabled=false;}});actions.append(history);
    content.append(footer);section.append(content);
  }
  if(!terminal.has(view.status)){const stop=button('停止任务',()=>update({action:'cancel'},stop),'secondary');section.append(stop);}
  return section;
}
