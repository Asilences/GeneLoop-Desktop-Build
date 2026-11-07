// Compose official DSH capabilities; keep its Agent loop, tools and jobs intact.
import {mkdirSync,writeFileSync,readFileSync,lstatSync,realpathSync,existsSync,chmodSync} from 'node:fs';
import {join,resolve,relative,isAbsolute,dirname,sep} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {LocalFileSystem} from '@deepseek-ai/dsh-fs-local';
import {publishArtifacts} from './local-artifacts.mjs';
import {commonToolNames} from './common-tool-catalog.mjs';
import {runNativeProcess} from './native-process.mjs';
import {fileURLToPath} from 'node:url';
const sha=b=>createHash('sha256').update(b).digest('hex');
const under=(root,path)=>{const rel=relative(root,path);return rel===''||rel!=='..'&&!rel.startsWith('..'+sep)&&!isAbsolute(rel);};

export async function openCommonCapabilities(ctx,{reader,writer,tools,media,sessionId,signal,onReport,askUser,sourceDirectory}) {
  if(!/^[a-f0-9-]{36}$/.test(sessionId))throw Error('本机会话标识无效');
  const root=join(process.env.DSH_HOME??process.cwd(),'task-workspaces',sessionId);
  mkdirSync(root,{recursive:true});const work=realpathSync(root);
  for(const name of ['inputs','outputs','projects','bin'])mkdirSync(join(work,name),{recursive:true});
  const sourceManifest=join(work,'approved-inputs.json');if(!existsSync(sourceManifest))writeFileSync(sourceManifest,'{"files":{}}');
  const pptProfile=join(dirname(tools.sourceRoot),'skills','geneloop-ppt');
  if(!existsSync(join(pptProfile,'SKILL.md')))throw Error('PPT 制作材料包需要更新，未加载上游的配音或视频扩展。');
  const allowedRead=[work,realpathSync(tools.skill),realpathSync(dirname(pptProfile))];
  // Older persisted sessions keep their original cwd. Preserve the official
  // session/history and map only that exact default cwd to the task copy.
  const taskCwd=cwd=>!cwd||sourceDirectory&&resolve(cwd)===resolve(sourceDirectory)?work:cwd;
  const subprocess=ctx.get('subprocess'),spawn=subprocess.spawn;
  // Ripgrep uses the official subprocess service directly instead of fs.resolve.
  // Keep the same cwd migration at that public seam; execution stays upstream.
  subprocess.spawn=function(spec){
    let argv=spec.argv;
    // Native executables cannot be spawned from a virtual ASAR path. Keep the
    // official ripgrep argv/parser and use its app-owned unpacked binary.
    const command=argv?.[0];
    if(typeof command==='string'&&/\.asar[\\/]node_modules[\\/]@vscode[\\/]ripgrep(?:-[^\\/]+)?[\\/]/.test(command)){
      const native=command.replace(/\.asar([\\/])/ ,'.asar.unpacked$1');
      if(!existsSync(native))throw Error('包内搜索工具缺失');
      argv=[native,...argv.slice(1)];
    }
    return spawn.call(this,{...spec,argv,cwd:taskCwd(spec.cwd)});
  };
  function checked(path){
    const full=resolve(path);if(!allowedRead.some(base=>under(base,full)))throw Error('路径不在本轮工作目录或已发布技能内');
    for(let at=full;;at=dirname(at)){
      if(existsSync(at)&&lstatSync(at).isSymbolicLink())throw Error('本机工具拒绝通过链接访问');
      if(allowedRead.includes(at)||dirname(at)===at)break;
    }
    return full;
  }
  class TaskFileSystem extends LocalFileSystem {
    async resolve(path,opts){const cwd=taskCwd(opts?.cwd);checked(resolve(cwd,path));const target=await super.resolve(path,{...opts,cwd});checked(target.targetKey);return target;}
    async lstat(path,opts,abort){const cwd=taskCwd(opts?.cwd);checked(resolve(cwd,path));return super.lstat(path,{...opts,cwd},abort);}
    async writeText(target,...args){const path=checked(target.targetKey);if(!under(work,path)||under(join(work,'inputs'),path))throw Error('输入资料与技能只读');return super.writeText(target,...args);}
    async editText(target,...args){const path=checked(target.targetKey);if(!under(work,path)||under(join(work,'inputs'),path))throw Error('输入资料与技能只读');return super.editText(target,...args);}
  }
  const fibers=[];
  const load=async(name,config={})=>{const m=await import('@deepseek-ai/'+name);const f=ctx.plugin(m.default??m,config);fibers.push(f);await f;};
  const fsFiber=ctx.plugin(TaskFileSystem,{cwd:work});fibers.push(fsFiber);await fsFiber;
  // The upstream default SDK uses danger-full-access. Native task commands never do.
  const policy=ctx.get('sandboxPolicy');policy.defaultMode='workspace-write';policy.workspaceRoot=work;
  await load('dsh-fs-observation-policy');await load('dsh-tool-fs');
  await load('dsh-tool-fs-search',{sampleOverCapGlobResults:false});
  const windows=process.platform==='win32';
  await load(windows?'dsh-pwsh-sandbox':'dsh-bash-sandbox',{cwd:work,timeoutMs:60000,maxTimeoutMs:450000,
    ...(windows?{pwshPath:join(process.env.SystemRoot,'System32/WindowsPowerShell/v1.0/powershell.exe')}:{})});
  // Electron supplies Node in installed apps. Launch wrappers contain only host
  // paths; task-authored code still runs under the official shell sandbox.
  if(windows){
    const quote=p=>'"'+p.replaceAll('"','""')+'"';
    writeFileSync(join(work,'bin/node.cmd'),'@echo off\r\n'+quote(process.execPath)+' %*\r\n');
    for(const name of ['python','python3'])writeFileSync(join(work,'bin',name+'.cmd'),'@echo off\r\n'+quote(tools.python)+' '+quote(join(tools.sourceRoot,'src/adapters/desktop_python_entry.py'))+' %*\r\n');
  }else{
    const quote=p=>"'"+p.replaceAll("'","'\\''")+"'";
    for(const [name,exe] of [['node',process.execPath],['python',tools.python],['python3',tools.python]]){
      const path=join(work,'bin',name);writeFileSync(path,'#!/bin/sh\nexec '+quote(exe)+(name==='node'?'':' '+quote(join(tools.sourceRoot,'src/adapters/desktop_python_entry.py')))+' "$@"\n');chmodSync(path,0o700);
    }
  }
  const shell=ctx.get('shell'),resolveShell=shell.resolve.bind(shell);
  shell.resolve=request=>{
    const spec=resolveShell(request);spec.workdir=taskCwd(spec.workdir);if(!under(work,resolve(spec.workdir)))throw Error('命令目录必须在本轮工作目录');
    const toolRoot=dirname(tools.sourceRoot);
    const paths=[join(work,'bin'),dirname(tools.python),dirname(tools.soffice),join(toolRoot,'extras','pandoc'),...(media?[dirname(media.ffmpeg)]:[]),process.env.SystemRoot?join(process.env.SystemRoot,'System32'):'/usr/bin','/bin'];
    spec.env={HOME:work,USERPROFILE:work,APPDATA:work,LOCALAPPDATA:work,TEMP:work,TMP:work,TMPDIR:work,
      PATH:paths.join(windows?';':':'),...(windows?{SystemRoot:process.env.SystemRoot,ComSpec:join(process.env.SystemRoot,'System32/cmd.exe'),PATHEXT:'.COM;.EXE;.BAT;.CMD'}:{}),
      ELECTRON_RUN_AS_NODE:'1',GENELOOP_OFFICE_NODE:process.execPath,GENELOOP_PPT_MASTER_ROOT:tools.skill,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',
      NODE_PATH:join(dirname(fileURLToPath(import.meta.url)),'node_modules'),PYTHONPATH:tools.sourceRoot,
      PLAYWRIGHT_BROWSERS_PATH:join(toolRoot,'chromium'),TIKTOKEN_CACHE_DIR:join(toolRoot,'python-data','tiktoken'),RL_renderPMBackend:'_renderPM',
      GENELOOP_NATIVE_SKILL_RUNTIME:'1',GENELOOP_NATIVE_WORKSPACE:work,GENELOOP_NATIVE_SOFFICE:tools.soffice};
    spec.sandboxPolicy={mode:'workspace-write',workspaceRoot:work};return spec;
  };
  await load('dsh-shell-env');await load(process.platform==='win32'?'dsh-tool-pwsh':'dsh-tool-bash',{enableRunInBackground:true});await load('dsh-tool-jobs');
  await load('dsh-user-questions');await load('dsh-tool-ask-user');
  const stopQuestions=ctx.on('user-questions/request',async(request,next)=>{
    if(!askUser)return next();return askUser(request);
  });
  await load('dsh-tool-todo',{allowParallelInProgress:true});await load('dsh-skill');
  await load('dsh-skill-filesystem',{includeDefaultRoots:false,customSkillDirs:[dirname(pptProfile)],watch:false});await load('dsh-tool-skill');
  await load('dsh-web',{searchProvider:'bing-rss',fetchProvider:'http'});await load('dsh-web-fetch-http');
  const web=ctx.get('web');
  // Public search uses no account model credential. Retrieval is the upstream
  // SSRF-checked, IP-pinned HTTP provider, including the RSS feed request.
  const stopSearch=web.registerSearchProvider({id:'bing-rss',available:()=>true,async search(request,abort){
    const {DOMParser}=await import('@xmldom/xmldom');let lastError;
    // These are two explicit public endpoints, not an automatic redirect grant.
    for(const endpoint of ['https://www.bing.com/search?format=rss&cc=us&mkt=en-US&q=','https://cn.bing.com/search?format=rss&q=']){
      abort?.throwIfAborted();
      try{
        const response=await web.fetch({url:endpoint+encodeURIComponent(request.query)},abort);
        if(response.statusCode!==200||response.truncated)throw Error('公开搜索服务未返回完整结果');
        const raw=response.body.content;if(/<!DOCTYPE|<!ENTITY/i.test(raw))throw Error('搜索结果XML不被接受');
        const parsed=new DOMParser({onError:(level,message)=>{if(level!=='warning')throw Error('搜索XML无效：'+message);}}).parseFromString(raw,'text/xml');
        if(parsed.documentElement?.tagName!=='rss'||!parsed.getElementsByTagName('channel').length)throw Error('搜索服务未返回RSS结果，不能作为搜索成功');
        const text=(item,name)=>item.getElementsByTagName(name)[0]?.textContent??'';
        const sources=Array.from(parsed.getElementsByTagName('item')).map(item=>({url:text(item,'link'),title:text(item,'title'),snippet:text(item,'description')}))
          .filter(row=>{try{return ['http:','https:'].includes(new URL(row.url).protocol);}catch{return false;}});
        return {sources,truncated:false};
      }catch(error){abort?.throwIfAborted();lastError=error;}
    }
    throw lastError??Error('公开搜索服务不可用');
  }});
  await load('dsh-tool-web');await load('dsh-goal');await load('dsh-tool-goal');await load('dsh-plan-mode',{section:'Plan mode is read-only. Inspect the approved sources and prepare a complete plan. Do not mutate files or start background work. Submit the complete Markdown plan through exit_plan_mode and wait for the human decision before implementation.'});
  await load('dsh-subagent');await load('dsh-subagent-spawn-in-process',{providerName:'spawn'});
  await load('dsh-tool-subagent',{provider:'spawn',toolName:'subagent',backgroundMode:'one-shot'});await load('dsh-tool-present');
  const stopGuard=ctx.tools.guard(call=>{
    if(!commonToolNames.includes(call.name))return;
    const args=call.arguments??{};
    if(args.sandbox_permissions||args.sandbox_mode==='danger-full-access')return '本机任务不允许提权或解除目录限制';
    if(['glob','grep'].includes(call.name))try{checked(resolve(work,args.path??'.'));}catch(error){return error.message;}
    if(call.name==='present')try{for(const row of args.files??[])if(!under(join(work,'outputs'),checked(resolve(work,row.path))))return '请将交付文件放在outputs目录';}catch(error){return error.message;}
  });
  const api={directory:work,names:commonToolNames.filter(name=>name!==(windows?'bash':'pwsh')),
    resolvePath:path=>checked(resolve(work,path)),
    async command(command,timeoutSeconds=180){
      if(typeof command!=='string'||!command.trim()||!Number.isInteger(timeoutSeconds)||timeoutSeconds<1||timeoutSeconds>240)throw Error('命令需要正文和1至240秒超时');
      const result=await shell.run(shell.resolve({command,workdir:work,timeoutMs:timeoutSeconds*1000,signal}));
      return {exit_code:result.exitCode??1,stdout:result.stdout.text,stderr:result.stderr.text,timed_out:result.timedOut,aborted:result.aborted,sandbox:result.sandbox,
        dialect:windows?'powershell':'bash'};
    },
    importFiles(sources){
      if(!Array.isArray(sources)||sources.length>64)throw Error('最多选择64份来源');
      const approved=JSON.parse(readFileSync(sourceManifest,'utf8'));
      for(const row of sources){const bytes=reader.readBytes(row.path,32*1024*1024);if(sha(bytes)!==row.sha256)throw Error('来源版本已变化');
        const target=checked(resolve(work,'inputs',row.path));if(!under(join(work,'inputs'),target))throw Error('来源路径越界');
        mkdirSync(dirname(target),{recursive:true});writeFileSync(target,bytes);approved.files[row.path]=row.sha256;
      }writeFileSync(sourceManifest,JSON.stringify(approved));return {directory:work,inputs:approved.files,originals_modified:false};
    },
    publish(paths){
      if(!Array.isArray(paths)||!paths.length||paths.length>32)throw Error('请选择1至32份实际产物');
      return publishArtifacts(writer,onReport,signal,paths.map(name=>{
        const path=checked(resolve(work,name));if(!under(join(work,'outputs'),path))throw Error('只能交付outputs目录内产物');
        const st=lstatSync(path);if(!st.isFile()||st.nlink!==1)throw Error('产物必须是独立普通文件');
        return {extension:path.split('.').at(-1).toLowerCase(),bytes:readFileSync(path)};
      }));
    },
    guard(call){if(commonToolNames.includes(call.name)&&['bash','pwsh'].includes(call.name)&&call.arguments?.workdir&&!under(work,resolve(work,call.arguments.workdir)))return '命令目录越界';},
    async ppt(operation,args){
      const project=checked(resolve(work,args.project));
      if(!under(join(work,'projects'),project))throw Error('PPT工程必须位于本轮projects目录');
      const output=join(work,'outputs','ppt-'+randomUUID()),request=join(work,'ppt-request-'+randomUUID()+'.json');
      const manifest=args.manifest?checked(resolve(work,args.manifest)):undefined;
      if(manifest&&!under(project,manifest))throw Error('页面清单必须在当前PPT工程中');
      writeFileSync(request,JSON.stringify({operation,work,project,output,skill:tools.skill,soffice:tools.soffice,manifest,profile:args.profile}));
      const script=join(tools.sourceRoot,'src/adapters/desktop_ppt_pipeline.py');
      const command=await runNativeProcess(ctx,[tools.python,'-B','-X','utf8',script,request],work,signal,{timeoutMs:450000});
      const result=JSON.parse(command.stdout.trim().split('\n').at(-1));
      if(operation==='finalize'){
        if(result.mechanical_status!=='passed')throw Error(JSON.stringify(result));
        result.published=api.publish([...result.artifacts.map(row=>relative(work,join(output,row.path))),relative(work,join(output,'delivery-receipt.json'))]);
      }
      return result;
    },
    async close(){stopQuestions();stopSearch();stopGuard();stopPresent();await Promise.allSettled(fibers.reverse().map(f=>f.dispose()));subprocess.spawn=spawn;},
  };
  const stopPresent=ctx.on('tools/post-execute',async(exec,result,next)=>{
    if(exec.name==='present'&&!result.isError)api.publish(result.value.files.map(row=>row.path));
    return next();
  });
  return api;
}
