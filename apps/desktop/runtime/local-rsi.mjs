import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {readFileSync,readdirSync,lstatSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {defineTool} from '@deepseek-ai/dsh-tools';
/** Scene-independent private motifs reuse the existing Python verified read executor. */
export function registerLocalRsi(scope,{root,tools,scene,readTools,signal}){
 if(!root||!tools)return;
 const folder=join(root,'motifs');
 const motifs=()=>readdirSync(folder).filter(name=>/^motif-[a-f0-9]{24}\.json$/.test(name)&&!existsSync(join(folder,name.replace('.json','.suspended')))).map(name=>{
  const path=join(folder,name),st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.size>256*1024)return;
  try{const row=JSON.parse(readFileSync(path,'utf8'));return row.scene===scene&&row.artifact.tools.every(n=>readTools.has(n))?row:undefined;}catch{return;}
 }).filter(Boolean);
 const list=motifs();if(!list.length)return;
 scope.tools.register(defineTool({name:'local_motif_list',description:'列出当前账号在本机正常任务中学得、经独立轨迹结构验收的只读流程；尚未证明质量或费用收益。',parameters:{},
  output:{schema:{type:'json'},render:(_,v)=>[{type:'text',text:JSON.stringify(v)}]},
  execute(){return motifs().map(row=>({id:row.id,tools:row.artifact.tools,entry_parameters:Object.fromEntries(Object.entries(row.artifact.dependencies.operators).map(([n,v])=>[n,v.required_params.filter(param=>!v.bindings.some(binding=>binding.to_param===param))])),certification_scope:row.certification_scope}));}}));
 scope.tools.register(defineTool({name:'local_motif_run',description:'在当前授权目录使用账号私有、已通过独立结构验收的只读 Motif。bindings 为按工具名分组的当前参数 JSON。不会执行历史命令或修改用户原件；仍需检查结果。',
  parameters:{motif_id:{type:'string',required:true},bindings:{type:'string',required:true}},
  output:{schema:{type:'json'},render:(_,v)=>[{type:'text',text:JSON.stringify(v)}]},
  async execute({motif_id,bindings}){
   signal?.throwIfAborted();
   if(!motifs().some(row=>row.id===motif_id))throw Error('本机能力不可用。');
   const env={PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
   for(const key of ['PATH','SYSTEMROOT','WINDIR','USERPROFILE','HOME','TEMP','TMP','TMPDIR'])if(process.env[key])env[key]=process.env[key];
   return await new Promise((resolve,reject)=>{
    const child=spawn(tools.python,['-B','-m','src.adapters.desktop.desktop_rsi','execute',root],{cwd:tools.sourceRoot,env,windowsHide:true,stdio:['pipe','pipe','ignore']});
    child.stdout.setEncoding('utf8');
    let buffer='',settled=false,busy=false;
    const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);child.kill();error?reject(error):resolve(value);};
    const abort=()=>finish(Error('本机复用已取消。'));const timer=setTimeout(abort,120000);signal?.addEventListener('abort',abort,{once:true});
    child.on('error',()=>finish(Error('本机复用进程未就绪。')));child.on('close',()=>finish(Error('本机复用未完成。')));
    child.stdin.on('error',()=>finish(Error('本机复用连接中断。')));
    child.stdout.on('data',chunk=>{
     buffer+=String(chunk);if(buffer.length>1024*1024)return finish(Error('本机复用响应超限。'));
     const index=buffer.indexOf('\n');if(index<0)return;
     if(busy)return finish(Error('本机复用协议无效。'));
     let row;try{row=JSON.parse(buffer.slice(0,index));buffer=buffer.slice(index+1);}catch{return finish(Error('本机复用响应无效。'));}
     if(row.kind==='result')return finish(null,row);
     if(row.kind!=='tool'||!readTools.has(row.name))return finish(Error('本机复用工具未经授权。'));
     busy=true;
     Promise.resolve().then(()=>{signal?.throwIfAborted();return readTools.get(row.name).execute(row.arguments);}).then(value=>{
      if(!settled){busy=false;child.stdin.write(JSON.stringify({ok:true,value})+'\n');}
     },()=>finish(Error('本机复用读取失败。')));
    });
    try{child.stdin.write(JSON.stringify({motif_id,bindings:JSON.parse(bindings),scene,invocation_id:randomUUID()})+'\n');}catch{finish(Error('本机复用参数无效。'));}
   });
  }}));
 scope.systemPrompt.section({name:'geneloop:private-rsi',order:10216,text:'本机账号库中有 '+list.length+' 个已通过独立结构验收的只读 Motif。任务合适时可用 local_motif_list 查看，给 local_motif_run 提供本轮实际参数，自然复用。没有适用能力时照常使用原工具；结构认证不代表任务质量或降费已证明。'});
}
