import {request,post} from './api.js';
import {node,button} from './components.js';

const endpoint='/api/harless/rsi-sharing';

/** Preview and consent live only in this panel. Reopening starts without consent. */
export function privacyPanel(){
  const section=node('section',{class:'privacy-panel','data-privacy-panel':'true'});
  const status=node('p',{role:'status'},'正在检查当前部署的隐私设置…');
  const content=node('div');
  section.append(node('h3',{},'数据与隐私'),
    node('p',{},'正常任务会把你提交的内容发给当前服务器及任务所需的模型或工具。'),
    node('p',{},'轨迹共享、源码共享和可选遥测默认关闭。账号内学习可独立使用。'),status,content);
  let active=true,preview,configuration;
  const abort=new AbortController();
  const valid=()=>active&&!abort.signal.aborted;
  const fail=error=>{if(valid())status.textContent=error.message||'共享操作未完成。';};
  async function cancel(){
    const current=preview;
    preview=undefined;
    if(current)return post(endpoint,{action:'cancel',preview_id:current.preview_id},{keepalive:true}).catch(()=>undefined);
  }
  function showPreview(value){
    preview=value;
    const consent=node('input',{type:'checkbox','data-privacy-consent':'true'});
    const send=button('确认上传',async()=>{
      send.disabled=true;
      try{
        const result=await post(endpoint,{action:'send',preview_id:value.preview_id,sha256:value.sha256,consent:consent.checked},{signal:abort.signal});
        if(valid()){status.textContent=result.state==='sent'?'接收端已确认接收。':'接收状态尚未确认。';consent.disabled=true;}
      }catch(error){fail(error);}
    },'primary');
    send.dataset.privacySend='true';send.disabled=true;
    consent.onchange=()=>{send.disabled=!consent.checked||!configuration.enabled;};
    const download=button('保存本地副本',()=>{
      const url=URL.createObjectURL(new Blob([value.payload],{type:'application/json'}));
      const link=node('a',{href:url,download:'rsi-tool-flow.json'});link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    },'secondary');
    download.dataset.privacyDownload='true';
    const stop=button('取消本次共享',async()=>{
      const result=await cancel();
      if(valid()){
        status.textContent=result?.state==='cancelled'?'本次共享已取消。':
          result?.state==='sent'?'接收端已经确认接收本次对象。':'接收状态尚未确认，请核对接收端记录。';
        content.replaceChildren();
      }
    },'secondary');
    stop.dataset.privacyCancel='true';
    content.replaceChildren(node('p',{},'共享对象仅含工具流程结构。场景和工具使用本次对象内的编号，任务内容保留在账号内。以下 JSON 是将发送的完整内容。'),
      node('p',{},'接收端 '+(value.target||'尚未配置')),
      node('p',{},'本次共享编号 '+value.preview_id),
      node('p',{},value.bytes+' 字节 · SHA256 '+value.sha256),
      node('pre',{'data-privacy-payload':'true'},value.payload),
      node('label',{},consent,'我已核对以上内容和接收端，同意仅共享本次对象。'),send,download,stop);
  }
  async function load(){
    try{
      configuration=await request(endpoint,{signal:abort.signal});
      if(!valid())return;
      status.textContent=configuration.enabled?'共享需逐次预览并确认。':'当前部署未配置共享接收端，可生成预览或保存本地副本。';
      const value=await request('/api/harless/tasks',{signal:abort.signal});
      if(!valid())return;
      const tasks=(value.tasks||[]).filter(row=>row.status==='completed');
      if(!tasks.length){content.replaceChildren(node('p',{},'完成任务后，可在此选择工具流程结构。'));return;}
      const select=node('select',{'aria-label':'选择共享对象'},tasks.map((row,index)=>node('option',{value:row.task_id},(row.scene_label||row.scene||'通用场景')+' 已完成任务 '+(index+1))));
      const prepare=button('生成共享预览',async()=>{
        prepare.disabled=true;
        try{const value=await post(endpoint,{action:'preview',task_id:select.value},{signal:abort.signal});if(valid())showPreview(value);}
        catch(error){fail(error);prepare.disabled=false;}
      },'secondary');
      prepare.dataset.privacyPreview='true';content.append(select,prepare);
    }catch(error){
      if(valid()&&error.status===404)status.textContent='当前服务器尚未提供共享预览，可以继续使用当前账号内的学习。';
      else fail(error);
    }
  }
  void load();
  return {section,dispose(){active=false;abort.abort();void cancel();}};
}
