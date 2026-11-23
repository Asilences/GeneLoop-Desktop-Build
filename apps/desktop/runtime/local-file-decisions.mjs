import {createHash} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,renameSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {validateJevRequest,validateJevResponse} from '../../../src/adapters/kouri_jev.ts';
import {acceptDecision,DECISION_FORMAT} from '../../../src/adapters/typed_decisions.ts';

const digest=value=>createHash('sha256').update(typeof value==='string'?value:JSON.stringify(value)).digest('hex');
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?
  Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;

/** Bind paid judgements to the original local session and actual source bytes. */
export function openFileDecisions({reader,home,sessionId,prompt,signal,enabled,endpoint,token,account}) {
  const directory=join(home,'file-decisions',sessionId);
  mkdirSync(directory,{recursive:true,mode:0o700});
  let pending=false;
  return async function judge({sources,questions}) {
    if(!enabled||!/^[a-f0-9]{64}$/.test(account??''))throw Error('当前服务器尚未启用文件 JEV 判断，请继续使用当前主模型判断。');
    if(pending)throw Error('请等待当前 JEV 判断完成。');
    if(!Array.isArray(sources)||!sources.length||sources.length>16)throw Error('请选择实际读取的来源文件。');
    let total=0;
    const materials=sources.map(source=>{
      if(!source||typeof source.path!=='string'||!/^[a-f0-9]{64}$/.test(source.sha256))throw Error('来源需要相对路径和 SHA256。');
      const bytes=reader.readBytes(source.path,256*1024);total+=bytes.length;
      if(total>256*1024||createHash('sha256').update(bytes).digest('hex')!==source.sha256)throw Error('来源内容已变化，请重新核对。');
      return {path:source.path,sha256:source.sha256,text:bytes.toString('utf8')};
    });
    const request=validateJevRequest({state:JSON.stringify({goal:prompt,materials}),questions:JSON.parse(questions)});
    const evidence=materials.map(({path,sha256})=>({id:path,sha256,scope:'current authorized local file contents'}));
    const packet={format:DECISION_FORMAT,scene:'files',owner:'gateway-account',task_id:sessionId,
      parent_call_id:'local-file-judgement',contract:digest(canonical(request.questions)),evidence,request};
    const key=digest(canonical({packet,account,origin:new URL(endpoint).origin})),file=join(directory,key+'.json');
    const save=value=>{
      const temporary=file+'.tmp';
      writeFileSync(temporary,JSON.stringify(value)+'\n',{mode:0o600});
      renameSync(temporary,file);
    };
    signal.throwIfAborted();
    if(existsSync(file)){
      const saved=JSON.parse(readFileSync(file,'utf8'));
      if(saved.key!==key||saved.sessionId!==sessionId)throw Error('原判断记录不匹配。');
      if(saved.status==='completed'){
        validateJevResponse(saved.result,request);
        return {...saved,reused:true};
      }
      // The server uses the same request identity to recover a completed response.
      // A started/unknown provider call is never automatically submitted twice.
    }
    pending=true;
    save({key,sessionId,status:'started',request_id:key});
    try{
      const url=new URL(endpoint);
      url.pathname=url.pathname.replace(/\/v1\/?$/,'/v1/systemone');
      const response=await fetch(url,{method:'POST',redirect:'error',signal,
        headers:{authorization:'Bearer '+token,'content-type':'application/json'},
        body:JSON.stringify({request_id:key,packet})});
      if(!response.ok)throw Error(response.status===409?'上次 JEV 调用结果待核对，未重复付费。':
        response.status===403?'当前任务未获文件判断授权。':'JEV 暂不可用，请继续用主模型核对。');
      const value=await response.json();
      validateJevResponse(value.result,request);
      const decision=acceptDecision(packet,value.result,value.decision?.threshold??0.9);
      const result={key,sessionId,status:'completed',request_id:key,result:value.result,decision,
        accounting:value.accounting,reused:value.reused===true};
      save(result);
      return result;
    }finally{pending=false;}
  };
}
