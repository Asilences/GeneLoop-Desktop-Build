import { app, WebContentsView, dialog, ipcMain, shell } from 'electron';
import type { BrowserWindow, IpcMainInvokeEvent, Session } from 'electron';
import { createHash, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { TITLE_BAR_HEIGHT } from './appearance.ts';
import { startLocalWorker } from './local-runtime.ts';
import type { LocalScene, LocalTaskUpdate } from './local-runtime.ts';
import { reopenDirectory } from './local-workspaces.ts';
import type { LocalWorkspace } from './local-workspaces.ts';

const here = dirname(fileURLToPath(import.meta.url));
const page = join(here, '../ui/local-workspace.html');
const channels = ['state', 'start', 'cancel', 'reveal', 'back'];
const leasePath = '/api/harless/desktop-model/lease';
type SavedTask = {
  prompt: string;
  at: number;
  scene?: LocalScene;
  sessionId?: string;
  updates: Extract<LocalTaskUpdate, { kind: 'answer' | 'report' | 'done' }>[];
};
const reportName = /^GeneLoop-[a-f0-9-]{36}\.md$/;
const sessionIdPattern = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;

function loadTasks(path: string): SavedTask[] {
  try {
    const rows: unknown = JSON.parse(readFileSync(path, 'utf8'));
    return Array.isArray(rows) ? rows.filter(row => typeof row?.prompt === 'string' && Number.isFinite(row.at) &&
      Array.isArray(row.updates)).slice(0, 30) : [];
  } catch { return []; }
}

export class LocalWorkspacePanel {
  private view?: WebContentsView;
  private workspaceId?: string;
  private busy = false;
  private closed = false;
  private controller?: ReturnType<typeof startLocalWorker>;
  private pending?: AbortController;
  private reports = new Set<string>();

  constructor(private options: { parent: BrowserWindow; server: string; session: Session; onClose: () => void }) {}

  get isOpen(): boolean { return !!this.view; }

  fit(): void {
    if (!this.view || this.options.parent.isDestroyed()) return;
    const [width, height] = this.options.parent.getContentSize();
    this.view.setBounds({ x: 0, y: TITLE_BAR_HEIGHT, width, height: Math.max(0, height - TITLE_BAR_HEIGHT) });
  }

  setVisible(visible: boolean): void { this.view?.setVisible(visible); }

  async open(workspace: LocalWorkspace): Promise<void> {
    if (!workspace.directory) throw Error('请先为工作区添加本机文件夹。');
    if (this.view) {
      if (this.workspaceId !== workspace.id) throw Error('请先返回另一个工作区。');
      this.view.webContents.focus();
      return;
    }
    if (this.busy || this.closed || this.pending) return;
    const runtime = app.isPackaged ? join(process.resourcesPath, 'geneloop-runtime.asar') : join(here, '../runtime-bundle');
    if (process.platform !== 'win32' || !existsSync(join(runtime, 'local-worker.mjs'))) {
      await dialog.showMessageBox(this.options.parent, { type: 'info', message: '本机工作区需要带运行时的 Windows 预览版。' });
      return;
    }
    this.busy = true;
    try {
      const directory = reopenDirectory(workspace.directory);
      const output = join(directory, 'GeneLoop 输出');
      const historyKey = createHash('sha256').update(workspace.id).update('\0').update(directory.toLowerCase()).digest('hex');
      const history = join(app.getPath('userData'), 'local-workspace', 'history', historyKey + '.json');
      const home = join(app.getPath('userData'), 'local-workspace', 'contexts', historyKey);
      const tasks = loadTasks(history);
      for (const task of tasks) {
        for (const update of task.updates) {
          if (update?.kind === 'report' && reportName.test(update.report?.name)) this.reports.add(update.report.name);
        }
      }
      const view = this.view = new WebContentsView({
        webPreferences: { preload: join(here, 'local-preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false },
      });
      view.setVisible(false);
      this.options.parent.contentView.addChildView(view);
      this.fit();
      this.workspaceId = workspace.id;
      const contents = view.webContents;
      contents.on('will-navigate', event => event.preventDefault());
      contents.setWindowOpenHandler(() => ({ action: 'deny' }));
      const handle = (channel: string, fn: (input: unknown) => unknown) => {
        ipcMain.handle('geneloop-local:' + channel, (event: IpcMainInvokeEvent, input: unknown) => {
          if (event.sender !== contents || event.senderFrame !== contents.mainFrame ||
              event.senderFrame.url !== pathToFileURL(page).href) throw Error('Invalid local workspace sender');
          return fn(input);
        });
      };
      const emit = (event: LocalTaskUpdate) => {
        if (!contents.isDestroyed()) contents.send('geneloop-local:update', event);
      };
      handle('state', () => ({ name: workspace.name, directory, output, tasks }));
      handle('back', () => {
        if (this.pending) throw Error('请先停止或等待当前本机任务。');
        this.closePanel();
      });
      handle('start', input => {
        if (this.pending) throw Error('已有本机任务正在运行。');
        const { prompt, scene, continuation } = (input ?? {}) as { prompt?: unknown; scene?: unknown; continuation?: unknown };
        if (typeof prompt !== 'string' || !prompt.trim()) throw Error('请输入任务内容。');
        if (scene !== 'files' && scene !== 'data' && scene !== 'paper') throw Error('本机场景无效。');
        const resume = continuation !== undefined;
        const previous = resume && typeof continuation === 'string' && sessionIdPattern.test(continuation) &&
          tasks.find(row => row.sessionId === continuation && row.scene === scene && row.updates.at(-1)?.kind === 'done' &&
            row.updates.some(event => event?.kind === 'done' && event.status === 'completed'));
        if (resume && !previous) throw Error('找不到该场景可继续的本机会话。');
        const sessionId = previous ? previous.sessionId! : randomUUID();
        const abort = this.pending = new AbortController();
        const task: SavedTask = { prompt, scene, at: Date.now(), updates: [] };
        return this.run({ runtime, directory, prompt, scene, home, sessionId, resume }, abort, update => {
          if (update.kind !== 'ready') task.updates.push(update);
          if (update.kind !== 'done') { emit(update); return; }
          if (update.status === 'completed') task.sessionId = sessionId;
          tasks.unshift(task);
          tasks.splice(30);
          try {
            mkdirSync(dirname(history), { recursive: true });
            writeFileSync(history + '.tmp', JSON.stringify(tasks) + '\n', { mode: 0o600 });
            renameSync(history + '.tmp', history);
          } catch {
            emit({ ...update, error: '本机任务历史未能保存。' });
            return;
          }
          emit(update);
        });
      });
      handle('cancel', () => { this.pending?.abort(); this.controller?.cancel(); });
      handle('reveal', name => {
        if (typeof name === 'string' && this.reports.has(name)) {
          shell.showItemInFolder(join(reopenDirectory(output), name));
        }
      });
      contents.once('render-process-gone', () => this.closePanel());
      try {
        await contents.loadFile(page);
        if (this.view !== view) return;
        view.setVisible(true);
        contents.focus();
      } catch (error) {
        if (this.view === view) this.closePanel();
        throw error;
      }
    } finally { this.busy = false; }
  }

  private async run(task: { runtime: string; directory: string; prompt: string; scene: LocalScene; home: string; sessionId: string; resume: boolean },
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
        ...task, executable: process.execPath, endpoint: new URL('/api/harless/desktop-model/v1', this.options.server).href,
        token: lease.token, model: lease.model,
        onUpdate: event => {
          if (event.kind === 'done') { outcome = event; return; }
          if (event.kind === 'report') {
            if (!reportName.test(event.report.name)) return;
            this.reports.add(event.report.name);
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
      this.controller = undefined;
      this.pending = undefined;
      emit(outcome ?? { kind: 'done', status: abort.signal.aborted ? 'canceled' : 'error' });
    }
  }

  private closePanel(notify = true): void {
    const view = this.view;
    if (!view) return;
    this.view = undefined;
    this.workspaceId = undefined;
    this.pending?.abort();
    this.controller?.cancel();
    for (const channel of channels) ipcMain.removeHandler('geneloop-local:' + channel);
    this.reports.clear();
    if (!this.options.parent.isDestroyed()) this.options.parent.contentView.removeChildView(view);
    if (!view.webContents.isDestroyed()) view.webContents.close();
    if (notify) this.options.onClose();
  }

  releaseWorkspace(id: string): void {
    if (id !== this.workspaceId) return;
    if (this.pending) throw Error('请先结束当前本机任务，再修改文件夹。');
    this.closePanel();
  }

  dispose(): void {
    this.closed = true;
    this.controller?.stop();
    this.closePanel(false);
  }
}
