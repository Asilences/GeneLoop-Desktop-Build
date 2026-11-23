/** Trusted native task lifecycle; the Python modules own privacy and RSI semantics. */
import {validCollectedObject} from './rsi-object.ts';
import {spawn} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {appendFileSync,existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,realpathSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';

const sha=(value:string|Buffer)=>createHash('sha256').update(value).digest('hex');
const uuid=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const endpoint='/api/harless/rsi-collected-objects';
const terminal=(value:string)=>['completed','cancelled','failed','interrupted'].includes(value);
function read(path:string,limit=32*1024*1024):any{
 const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size>limit||realpathSync(path)!==path)throw Error('local_rsi_file_invalid');
 return JSON.parse(readFileSync(path,'utf8'));
}
function write(path:string,value:unknown){const temporary=path+'.'+randomUUID()+'.tmp';writeFileSync(temporary,JSON.stringify(value),{mode:0o600,flag:'wx',flush:true});renameSync(temporary,path);}
export type RsiBinding={root:string;attempt:string;logicalTask:string};
type Options={directory:string;server:string;identity:()=>Promise<string|undefined>;
 fetch:(url:string,init:RequestInit)=>Promise<Response>;notice?:()=>Promise<void>;allowLoopback?:boolean;
 tools:()=>{python:string;sourceRoot:string;gitleaks:string}|undefined};
function pythonEnvironment():NodeJS.ProcessEnv{
 const env:NodeJS.ProcessEnv={PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
 for(const key of ['PATH','SYSTEMROOT','WINDIR','USERPROFILE','HOME','TEMP','TMP','TMPDIR']){
  if(process.env[key])env[key]=process.env[key];
 }
 return env;
}
export class LocalRsiHost{
 private running?:Promise<void>;private stopped=false;private timer?:ReturnType<typeof setTimeout>;
 private child?:ReturnType<typeof spawn>;private active=new Set<string>();private rejected=new Set<string>();private principal?:string;
 private recentCatalog?:{principal:string;expires:number;rows:unknown};
 private options:Options;
 constructor(options:Options){this.options=options;}
 private async store(){
  const principal=await this.options.identity();if(!principal)throw Error('请先登录 GeneLoop 账号。');
  const root=join(this.options.directory,sha(this.options.server+'\0'+principal));
  mkdirSync(join(root,'tasks'),{recursive:true,mode:0o700});mkdirSync(join(root,'motifs'),{recursive:true,mode:0o700});
  if(realpathSync(root)!==root)throw Error('本机学习目录无效。');
  const path=join(root,'owner.json');
  if(!existsSync(path))write(path,{version:1,principal,server:this.options.server});
  const owner=read(path,4096);if(owner.principal!==principal||owner.server!==this.options.server)throw Error('本机学习账号不匹配。');
  this.principal=principal;
  return {root,principal};
 }
 async begin(value:{logicalTask:string;sessionId:string;scene:string;workspaceId:string}):Promise<RsiBinding>{
  const {root,principal}=await this.store();
  const notice=join(root,'service-notice-v1.json');
  if(!existsSync(notice)){await this.options.notice?.();write(notice,{version:1,shown_at:Date.now()});}
  const attempt=randomUUID().replaceAll('-',''),path=join(root,'tasks',attempt);mkdirSync(path,{mode:0o700});
  write(join(path,'task.json'),{...value,logical_task_id:value.logicalTask,session_id:value.sessionId,
    principal,attempt_id:attempt,status:'running',at:Date.now(),schema_version:1});
  writeFileSync(join(path,'events.jsonl'),'',{flag:'wx',mode:0o600});this.active.add(attempt);
  return {root,attempt,logicalTask:value.logicalTask};
 }
 record(binding:RsiBinding,event:unknown){
  if(!this.active.has(binding.attempt)||this.rejected.has(binding.attempt))return;
  const path=join(binding.root,'tasks',binding.attempt);
  try{
  const meta=read(join(path,'task.json'),8192);
  if(meta.logical_task_id!==binding.logicalTask||meta.status!=='running')throw Error('本机轨迹来源变化。');
  const raw=JSON.stringify(event),file=join(path,'events.jsonl'),st=lstatSync(file);
  if(st.isSymbolicLink()||st.nlink!==1||st.size+Buffer.byteLength(raw)>32*1024*1024){
   write(join(path,'task.json'),{...meta,capture_error:true});
   write(join(path,'pipeline.json'),{privacy:'rejected',collection:'blocked',capture_error:true});
   throw Error('本机轨迹超出处理上限。');
  }
  appendFileSync(file,raw+'\n',{mode:0o600});
  }catch{
   this.rejected.add(binding.attempt);
   try{write(join(path,'pipeline.json'),{privacy:'rejected',collection:'blocked',capture_error:true});}catch{}
  }
 }
 finish(binding:RsiBinding,status:string){
  if(!this.active.delete(binding.attempt))return;
  const path=join(binding.root,'tasks',binding.attempt),meta=read(join(path,'task.json'),8192);
  write(join(path,'task.json'),{...meta,...(this.rejected.delete(binding.attempt)?{capture_error:true}:{}),status:status==='canceled'?'cancelled':status==='error'?'failed':status,finished_at:Date.now()});
  this.schedule();
 }
 schedule(){
  if(this.stopped)return;
  clearTimeout(this.timer);
  if(this.running)return;
  this.running=this.drain().catch(()=>{}).finally(()=>{this.running=undefined;if(!this.stopped){this.timer=setTimeout(()=>this.schedule(),60000);this.timer.unref();}});
 }
 async idle(){await this.running;}
 async catalog(){
  const {root,principal}=await this.store();
  if(this.recentCatalog?.principal===principal&&this.recentCatalog.expires>Date.now())return this.recentCatalog.rows;
  const tools=this.options.tools();
  if(!tools)throw Error('本机工具尚未就绪。');
  const rows=await new Promise<unknown>((resolve,reject)=>{
   const child=spawn(tools.python,['-B','-m','src.adapters.desktop.desktop_rsi_catalog',root],
    {cwd:tools.sourceRoot,env:pythonEnvironment(),windowsHide:true,stdio:['ignore','pipe','ignore']});
   child.stdout.setEncoding('utf8');
   let output='';
   const timeout=setTimeout(()=>child.kill(),10000);
   child.stdout.on('data',chunk=>{output+=chunk;if(output.length>256*1024)child.kill();});
   child.on('error',reject);
   child.on('close',code=>{
    clearTimeout(timeout);
    if(code!==0)return reject(Error('本机 Motif 库暂时无法读取。'));
    try{
     const rows=JSON.parse(output);
     if(!Array.isArray(rows))throw Error();
     resolve(rows);
    }catch{reject(Error('本机 Motif 库响应无效。'));}
   });
  });
  if(this.stopped||await this.options.identity()!==principal)throw Error('当前账号已变更。');
  this.recentCatalog={principal,expires:Date.now()+30000,rows};
  return rows;
 }
 private async process(root:string,id:string){
  const tools=this.options.tools();if(!tools)throw Error('本机脱敏组件尚未就绪。');
  return await new Promise<any>((resolve,reject)=>{
   const env:NodeJS.ProcessEnv={...pythonEnvironment(),SSS_RSI_GITLEAKS:tools.gitleaks,
    OMP_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1',MKL_NUM_THREADS:'1'};
   for(const key of ['PATH','SYSTEMROOT','WINDIR','USERPROFILE','HOME','TEMP','TMP','TMPDIR'])if(process.env[key])env[key]=process.env[key];
   const child=spawn(tools.python,['-B','-m','src.adapters.desktop.desktop_rsi','process',root,id],
    {cwd:tools.sourceRoot,env,windowsHide:true,stdio:['ignore','pipe','ignore']});this.child=child;
   child.stdout.setEncoding('utf8');
   let result='',over=false;
   child.stdout.on('data',chunk=>{result+=String(chunk);if(result.length>16384){over=true;child.kill();}});
   const timer=setTimeout(()=>child.kill(),120000);
   child.on('error',()=>{clearTimeout(timer);reject(Error('本机学习处理未完成。'));});
   child.on('close',code=>{clearTimeout(timer);this.child=undefined;if(code||over)return reject(Error('本机脱敏未通过。'));try{resolve(JSON.parse(result.trim().split('\n').at(-1)!));}catch{reject(Error('本机学习响应无效。'));}});
  });
 }
 private async drain(){
  const {root,principal}=await this.store();
  for(const id of readdirSync(join(root,'tasks')).filter(id=>/^[a-f0-9]{32}$/.test(id)).sort()){
   if(this.stopped||await this.options.identity()!==principal)return;
   const path=join(root,'tasks',id),meta=read(join(path,'task.json'),8192);
   if(meta.principal!==principal||meta.capture_error)continue;
   if(meta.status==='running'&&!this.active.has(id))write(join(path,'task.json'),{...meta,status:'interrupted',finished_at:Date.now()});
   if(!terminal(meta.status)&&meta.status!=='running')continue;
   if(this.active.has(id))continue;
   if(meta.at+90*86400000<Date.now()){
    for(const name of ['events.jsonl','privacy-learning.json','admission.json','collected-object.json'])rmSync(join(path,name),{force:true});
    continue;
   }
   if(meta.at+30*86400000<Date.now()){
    for(const name of ['privacy-learning.json','admission.json','collected-object.json'])rmSync(join(path,name),{force:true});
    continue;
   }
   const statePath=join(path,'pipeline.json');let state=existsSync(statePath)?read(statePath,8192):{privacy:'pending',collection:'pending'};
   if(state.privacy!=='admitted'){
    if(state.last_attempt_at&&state.last_attempt_at+15*60000>Date.now())continue;
    try{const result=await this.process(root,id);state={...state,...result,collection:result.has_object?'pending':'no_tool_calls'};this.recentCatalog=undefined;}
    catch{state={...state,privacy:'rejected',collection:'blocked',last_attempt_at:Date.now()};write(statePath,state);continue;}
    write(statePath,state);
   }
   if(!['pending','unknown','waiting_server','blocked'].includes(state.collection)||!state.has_object)continue;
   const objectPath=join(path,'collected-object.json');const object=read(objectPath,256*1024);
   if(!validCollectedObject(object)){write(statePath,{...state,collection:'blocked_object'});continue;}
   const body=JSON.stringify(object),hash=sha(body);
   if(state.sha256&&state.sha256!==hash){write(statePath,{...state,collection:'blocked_object'});continue;}
   state={...state,object_id:state.object_id??randomUUID(),sha256:hash,collection:'pending'};write(statePath,state);
   const target=new URL(endpoint,this.options.server);
   const loopback=this.options.allowLoopback&&['localhost','127.0.0.1','[::1]'].includes(target.hostname);
   if(target.protocol!=='https:'&&!(loopback&&target.protocol==='http:')){write(statePath,{...state,collection:'blocked_transport'});continue;}
   try{
    if(await this.options.identity()!==principal)return;
    // Reconcile every pending object before sending. A lost response never creates a new ID.
    const lookup=await this.options.fetch(target.href+'?object_id='+state.object_id,{method:'GET',credentials:'include',redirect:'error',signal:AbortSignal.timeout(10000)});
    let receipt:any;
    if(lookup.ok)receipt=await lookup.json();
    else if(lookup.status===404){
     const response=await this.options.fetch(target.href,{method:'POST',credentials:'include',redirect:'error',
      headers:{origin:target.origin,'content-type':'application/json','x-geneloop-object-id':state.object_id,'x-geneloop-object-sha256':hash},body,signal:AbortSignal.timeout(15000)});
     if(!response.ok){write(statePath,{...state,collection:'waiting_server',http_status:response.status});continue;}
     receipt=await response.json();
    }else{write(statePath,{...state,collection:'waiting_server',http_status:lookup.status});continue;}
    if(receipt?.accepted!==true||receipt.object_id!==state.object_id||receipt.sha256!==hash||!uuid.test(receipt.receipt_id))throw Error('invalid_receipt');
    write(statePath,{...state,collection:'received',receipt});
   }catch{write(statePath,{...state,collection:'unknown'});}
  }
 }
 async status(){
  const {root}=await this.store();const counts:Record<string,number>={};
  for(const id of readdirSync(join(root,'tasks')).filter(id=>/^[a-f0-9]{32}$/.test(id))){
   const path=join(root,'tasks',id,'pipeline.json');const state=existsSync(path)?read(path,8192):{collection:'pending'};
   counts[state.collection]=(counts[state.collection]??0)+1;
  }
  return {mandatory:true,learning:existsSync(join(root,'learning.json'))?read(join(root,'learning.json'),8192):{state:'waiting_for_independent_evidence'},
   collection:counts,target:new URL(this.options.server).origin,raw_retention_days:90,learning_retention_days:30};
 }
 dispose(){this.stopped=true;clearTimeout(this.timer);this.child?.kill();}
}
