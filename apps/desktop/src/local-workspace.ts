import { app, shell } from 'electron';
import type { Session } from 'electron';
import { createHash, randomUUID } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, renameSync, writeFileSync } from 'node:fs';
import { basename, dirname, isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {LocalRsiHost,type RsiBinding} from './local-rsi.ts';
import { startLocalWorker } from './local-runtime.ts';
import { loadNativeToolProviders } from './native-tool-providers.ts';
import {localToolDirectory,localToolsPrepared} from './tool-location.ts';
import type { LocalMediaTools, LocalPptTools, LocalScene, LocalTaskUpdate, VideoApproval, FilePlanApproval } from './local-runtime.ts';
import { reopenDirectory } from './local-workspaces.ts';
import type { LocalWorkspace } from './local-workspaces.ts';

const here = dirname(fileURLToPath(import.meta.url));
const leasePath = '/api/harless/desktop-model/lease';
type SavedTask = {
  prompt: string;
  at: number;
  taskId?: string;
  started?: boolean;
  recoverable?: boolean;
  scene?: LocalScene;
  threadId?: string;
  sessionId?: string;
  updates: Extract<LocalTaskUpdate, { kind: 'answer' | 'report' | 'done' }>[];
};
const reportName = /^GeneLoop-[a-f0-9-]{36}\.(?:md|pptx|pdf|mp4|json|tsx|csv|zip|txt|docx|xlsx|png)$/;
const supportedScenes: readonly LocalScene[] = ['chat', 'files', 'data', 'paper', 'ppt', 'video'];
const localRuntime = () => app.isPackaged ? join(process.resourcesPath, 'geneloop-runtime.asar') : join(here, '../runtime-bundle');
const bundledTools = localToolDirectory;

function pptTools(): LocalPptTools | undefined {
  const bundle = bundledTools();
  const configured = !app.isPackaged && process.env.GENELOOP_PPT_PYTHON;
  const python = configured || join(bundle, process.platform === 'win32' ? 'python/python.exe' : 'python/bin/geneloop-python');
  const resources = join(bundle,'ppt-deck/scenarios/ppt_master/third_party/ppt-master');
  const deck = join(bundle,'local-ppt-deck.mjs');
  const soffice = configured ? process.env.GENELOOP_PPT_SOFFICE : join(bundle,
    process.platform === 'win32' ? 'libreoffice/program/soffice.com' : 'libreoffice/Contents/MacOS/soffice');
  const sourceRoot = configured ? process.env.GENELOOP_PPT_SOURCE_ROOT || join(here, '../../..') : join(bundle, 'source');
  const fixedFile = (path: string) => isAbsolute(path) && lstatSync(path).isFile() &&
    (process.platform === 'win32' ? realpathSync(path).toLowerCase() === path.toLowerCase() : realpathSync(path) === path);
  try {
    const hasBuiltInPpt = existsSync(deck);
    if (hasBuiltInPpt && (!fixedFile(deck) || !fixedFile(join(dirname(resources),'ppt-master-desktop-lock.json')))) return;
    const skill = hasBuiltInPpt ? resources : configured ? process.env.GENELOOP_PPT_MASTER_ROOT : join(bundle, 'ppt-master');
    if (!python || !skill || !soffice || !fixedFile(python) || !fixedFile(soffice) ||
        basename(soffice).toLowerCase() !== (process.platform === 'win32' ? 'soffice.com' : 'soffice') ||
        !existsSync(join(sourceRoot, 'scenarios/ppt_master/windows_delivery.py'))) return;
    return { python, skill: reopenDirectory(skill), soffice, sourceRoot, ...(hasBuiltInPpt ? {deck} : {}) };
  } catch { return undefined; }
}

function mediaTools(): LocalMediaTools | undefined {
  try {
    const configured = !app.isPackaged && process.env.GENELOOP_FFMPEG_DIRECTORY;
    const bundled = join(bundledTools(), 'ffmpeg');
    const directory = configured || (existsSync(bundled) ? bundled : join(app.getPath('userData'), 'local-tools', 'ffmpeg'));
    if (!isAbsolute(directory)) return;
    const root = reopenDirectory(directory);
    const executable = (name: string) => {
      const path = join(root, name);
      const stat = lstatSync(path);
      if (!stat.isFile() || stat.isSymbolicLink() ||
          (process.platform === 'win32' ? realpathSync(path).toLowerCase() !== path.toLowerCase() : realpathSync(path) !== path)) {
        throw Error('无效的本机媒体工具。');
      }
      return path;
    };
    const suffix = process.platform === 'win32' ? '.exe' : '';
    const result: LocalMediaTools = { ffmpeg: executable('ffmpeg' + suffix), ffprobe: executable('ffprobe' + suffix) };
    const manifestPath = join(bundledTools(),'manifest.json');
    if (!existsSync(manifestPath)) return result;
    const manifest = JSON.parse(readFileSync(manifestPath,'utf8'));
    if (manifest.platform !== process.platform || manifest.arch !== process.arch) return;
    if (typeof manifest.browser !== 'string' || !manifest.browser.startsWith('chromium/') || manifest.browser.includes('..')) return;
    const browser = realpathSync(join(bundledTools(),manifest.browser));
    const compositor = process.platform === 'win32' ? 'win32-x64-msvc' : 'darwin-'+process.arch;
    const binaries = localRuntime().replace(/\.asar$/,'.asar.unpacked')+'/node_modules/@remotion/compositor-'+compositor;
    if (existsSync(browser) && existsSync(binaries)) result.remotion = {browser,binaries};
    return result;
  } catch { return undefined; }
}

export function localSceneStatus(): Partial<Record<LocalScene, string>> {
  if(!localToolsPrepared())return Object.fromEntries(supportedScenes.map(scene=>[scene,'请先在「文件 → 本机工具」完成工具准备。']));
  const runtime = localRuntime();
  if (!['win32', 'darwin'].includes(process.platform) || !existsSync(join(runtime, 'local-worker.mjs'))) {
    return Object.fromEntries(supportedScenes.map(scene => [scene, '需要带本机运行时的 Windows 或 Mac 版本。']));
  }
  const status: Partial<Record<LocalScene, string>> = {};
  if (!existsSync(join(runtime, 'local-ppt-render.mjs'))) status.ppt = '本机演示文稿运行时尚未打包。';
  if (!mediaTools()) status.video = '本机视频需要在桌面数据目录安装 FFmpeg 和 FFprobe。';
  return status;
}
const sessionIdPattern = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;

function loadTasks(path: string): SavedTask[] {
  try {
    const rows: unknown = JSON.parse(readFileSync(path, 'utf8'));
    return Array.isArray(rows) ? rows.filter(row => typeof row?.prompt === 'string' && Number.isFinite(row.at) &&
      Array.isArray(row.updates)) : [];
  } catch { return []; }
}

function location(workspace: LocalWorkspace) {
  if (!workspace.directory) throw Error('请先为工作区添加本机文件夹。');
  const directory = workspace.directory;
  const key = createHash('sha256').update(workspace.id).update('\0')
    .update(process.platform === 'win32' ? directory.toLowerCase() : directory).digest('hex');
  const home = join(app.getPath('userData'), 'local-workspace', 'contexts', key);
  return { directory, home, history: join(app.getPath('userData'), 'local-workspace', 'history', key + '.json') };
}

export class LocalWorkspaceConversation {
  private controller?: ReturnType<typeof startLocalWorker>;
  private pending?: { workspaceId: string; threadId: string; abort: AbortController };
  private closed = false;
  private rsi:LocalRsiHost;
  private rsiBinding?:RsiBinding;

  constructor(private options: { server: string; session: Session; allowLoopback?:boolean; notice?:()=>Promise<void>; approveVideo?: (request: VideoApproval) => Promise<boolean>; approveFilePlan?: (request: FilePlanApproval) => Promise<boolean> }) {
    this.rsi=new LocalRsiHost({directory:join(app.getPath('userData'),'local-rsi'),server:options.server,
      identity:async()=>{const response=await options.session.fetch(new URL('/api/account/me',options.server).href,
        {credentials:'include',redirect:'error',bypassCustomProtocolHandlers:true,signal:AbortSignal.timeout(10000)});
        if(!response.ok)return;const value=await response.json();return typeof value.user?.id==='string'?value.user.id:undefined;},
      fetch:(url,init)=>options.session.fetch(url,{...init,bypassCustomProtocolHandlers:true}),notice:options.notice,allowLoopback:options.allowLoopback,
      tools:()=>{const tools=pptTools();if(!tools)return;return {...tools,gitleaks:join(bundledTools(),'privacy',process.platform==='win32'?'gitleaks.exe':'gitleaks')};}});
    this.rsi.schedule();
  }
  rsiStatus(){this.rsi.schedule();return this.rsi.status();}
  rsiCatalog(){return this.rsi.catalog();}

  history(workspace: LocalWorkspace): SavedTask[] {
    return loadTasks(location(workspace).history).map(task=>({...task,recoverable:
      task.scene==='files' && task.started===true && Boolean(task.sessionId) &&
      task.updates.filter(update=>update.kind==='done').at(-1)?.status!=='completed' &&
      !(this.pending?.workspaceId===workspace.id&&this.pending.threadId===task.threadId)}));
  }

  async start(workspace: LocalWorkspace, input: unknown, emit: (update: LocalTaskUpdate) => void) {
    if (this.closed || this.pending) throw Error('已有本机对话正在执行。');
    const request=(input??{}) as {prompt?:unknown;scene?:unknown;threadId?:unknown;recover?:unknown;taskId?:unknown};
    const {history,directory,home}=location(workspace);
    const tasks=loadTasks(history);
    const threadId=request.threadId;
    if(typeof threadId!=='string'||!sessionIdPattern.test(threadId))throw Error('无效的本机会话。');
    const original=tasks.find(task=>(task.threadId??task.sessionId)===threadId);
    const recovering=request.recover===true;
    if(recovering && (!original?.started || original.scene!=='files' || !original.sessionId ||
        !original.taskId || original.taskId!==request.taskId || original.updates.filter(update=>update.kind==='done').at(-1)?.status==='completed')){
      throw Error('原文件任务不可恢复，请核对当前对话。');
    }
    const prompt=recovering?original!.prompt:request.prompt;
    const scene=recovering?original!.scene:request.scene;
    if(typeof prompt!=='string'||!prompt.trim())throw Error('请输入消息。');
    if(!supportedScenes.includes(scene as LocalScene))throw Error('该场景暂不支持本机执行。');
    const localScene=scene as LocalScene,unavailable=localSceneStatus()[localScene];
    if(unavailable)throw Error(unavailable);
    const runtime=localRuntime(),media=mediaTools(),ppt=pptTools();
    if(localScene==='video'&&!media)throw Error('本机媒体工具不可用。');
    const approved=reopenDirectory(directory);
    const previous=tasks.find(row=>(row.threadId??row.sessionId)===threadId&&row.sessionId&&
      sessionIdPattern.test(row.sessionId)&&(row.updates.filter(update=>update.kind==='done').at(-1)?.status==='completed'||row.scene==='files'&&row.started));
    if(previous&&(previous.scene??'files')!==localScene)throw Error('切换场景请新建本机会话。');
    const sessionId=previous?.sessionId??randomUUID(),abort=new AbortController();
    this.pending={workspaceId:workspace.id,threadId,abort};
    const task:SavedTask=recovering?original!:{prompt,scene:localScene,threadId,sessionId,taskId:randomUUID(),at:Date.now(),updates:[]};
    if(recovering)task.updates=task.updates.filter(update=>update.kind!=='done');
    else tasks.unshift(task);
    const persist=()=>{
      mkdirSync(dirname(history),{recursive:true});
      const temporary=history+'.tmp';
      writeFileSync(temporary,JSON.stringify(tasks)+'\n',{mode:0o600});
      renameSync(temporary,history);
    };
    try{persist();}
    catch(error){this.pending=undefined;throw error;}
    try{this.rsiBinding=await this.rsi.begin({logicalTask:task.taskId!,sessionId,scene:localScene,workspaceId:workspace.id});}
    catch(error){this.pending=undefined;throw error;}
    await this.run({runtime,directory:approved,prompt,scene:localScene,media,ppt,home,sessionId,
      resume:Boolean(previous),recover:recovering},abort,update=>{
      if(update.kind==='session-opened')task.started=true;
      if(update.kind==='answer'||update.kind==='report'||update.kind==='done')task.updates.push(update);
      try{persist();}
      catch{
        this.controller?.cancel();
        if(update.kind==='done')emit({...update,error:'本机对话记录未能保存。'});
        return;
      }
      emit(update);
    });
  }

  cancel(workspaceId: string, threadId: string): void {
    if (this.pending?.workspaceId !== workspaceId || this.pending.threadId !== threadId) return;
    this.pending.abort.abort();
    this.controller?.cancel();
  }
  answer(workspaceId:string,threadId:string,id:unknown,answers:unknown):void {
    if(this.pending?.workspaceId!==workspaceId||this.pending.threadId!==threadId||typeof id!=='string'||!Array.isArray(answers))throw Error('本机问题已失效');
    this.controller?.answerQuestion(id,answers);
  }

  reveal(workspace: LocalWorkspace, name: unknown): void {
    if (typeof name !== 'string' || !reportName.test(name) || !this.history(workspace).some(task =>
      task.updates.some(update => update?.kind === 'report' && update.report?.name === name))) return;
    const { directory } = location(workspace);
    shell.showItemInFolder(join(reopenDirectory(join(directory, 'GeneLoop 输出')), name));
  }

  private async run(task: { runtime: string; directory: string; prompt: string; scene: LocalScene; media?: LocalMediaTools; ppt?: LocalPptTools; home: string; sessionId: string; resume: boolean; recover: boolean },
    abort: AbortController, emit: (event: LocalTaskUpdate) => void) {
    const endpoint = new URL(leasePath, this.options.server);
    let token: string | undefined;
    let outcome: Extract<LocalTaskUpdate, { kind: 'done' }> | undefined;
    try {
      const response = await this.options.session.fetch(endpoint.href, {
        method: 'POST', credentials: 'include', redirect: 'error', bypassCustomProtocolHandlers: true,
        headers: { origin: endpoint.origin, 'content-type': 'application/json' },
        body: task.scene === 'files' ? '{}' : JSON.stringify({ scene: task.scene }), signal: AbortSignal.timeout(22_000),
      });
      if (!response.ok) throw Error(response.status === 404 ? '当前服务器尚未开放本机模型试用。' :
        response.status === 403 ? '请在云端工作区登录已获授权的试用账号。' :
        response.status === 409 ? '已有本机任务，请等待授权结算。' : '无法获取本机模型授权。');
      const lease = await response.json();
      if (!/^[A-Za-z0-9_-]{43}$/.test(lease.token) || lease.model !== 'deepseek-flash') throw Error('本机模型授权响应无效。');
      token = lease.token;
      abort.signal.throwIfAborted();
      this.controller = startLocalWorker({
        rsiRoot:this.rsiBinding?.root,rsiReuse:lease.localRsiTools===true,
        fileHome:join(app.getPath('userData'),'file-runs',task.sessionId),
        nativeProviders:loadNativeToolProviders(join(app.getPath('userData'),'local-tools','providers.json')),
        ...task, legacyTools:![2,3,4].includes(lease.toolsetVersion),fullWorkflows:[3,4].includes(lease.toolsetVersion),commonCapabilities:lease.toolsetVersion===4,executable: process.execPath, endpoint: new URL('/api/harless/desktop-model/v1', this.options.server).href,
        nativePptDeck: lease.nativePptDeck === true, fileJev:lease.fileJev===true&&/^[a-f0-9]{64}$/.test(lease.fileJevAccount??''),fileJevAccount:lease.fileJevAccount,
        token: lease.token, model: lease.model,
        approveVideo: task.scene === 'video' && lease.videoRendering === true ? this.options.approveVideo : undefined,
        approveFilePlan:this.options.approveFilePlan,
        onUpdate: event => {
          if(event.kind==='rsi-event'){
            try{if(this.rsiBinding)this.rsi.record(this.rsiBinding,event.event);}
            catch{ /* Derived capture cannot cancel a normal Agent task. */ }return;
          }
          if (event.kind === 'done') { outcome = event; return; }
          if (event.kind === 'report') {
            if (!reportName.test(event.report.name)) return;
          }
          emit(event);
        },
      });
      await this.controller.closed;
    } catch (error) {
      if (!abort.signal.aborted) outcome = { kind: 'done', status: 'error', error: error instanceof Error ? error.message : '本机任务无法启动。' };
    } finally {
      if (token) {
        try {
          const response = await this.options.session.fetch(endpoint.href, {
            method: 'DELETE', redirect: 'error', credentials: 'omit', bypassCustomProtocolHandlers: true,
            headers: { authorization: 'Bearer ' + token }, signal: AbortSignal.timeout(7000),
          });
          await response.body?.cancel();
        } catch { /* 连接中断时由服务端短期授权超时结算。 */ }
      }
      try{if(this.rsiBinding)this.rsi.finish(this.rsiBinding,outcome?.status??(abort.signal.aborted?'canceled':'error'));}catch{ /* Keep normal task delivery independent of background storage. */ }
      this.rsiBinding=undefined;
      this.controller = undefined;
      this.pending = undefined;
      emit(outcome ?? { kind: 'done', status: abort.signal.aborted ? 'canceled' : 'error' });
    }
  }

  releaseWorkspace(id: string): void {
    if (this.pending?.workspaceId === id) throw Error('请先结束当前本机任务，再修改文件夹。');
  }

  dispose(): void {
    this.closed = true;
    this.rsi.dispose();
    this.pending?.abort.abort();
    this.controller?.stop();
  }
}
