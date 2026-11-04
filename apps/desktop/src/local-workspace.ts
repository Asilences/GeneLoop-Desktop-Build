import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import type { IpcMainInvokeEvent, Session } from 'electron';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { startLocalWorker } from './local-runtime.ts';
import type { LocalTaskUpdate } from './local-runtime.ts';
import { reopenDirectory } from './local-workspaces.ts';
import type { LocalWorkspace } from './local-workspaces.ts';

const here = dirname(fileURLToPath(import.meta.url));
const page = join(here, '../ui/local-workspace.html');
const channels = ['state', 'start', 'cancel', 'reveal'];
const leasePath = '/api/harless/desktop-model/lease';
type SavedTask = {
  prompt: string;
  at: number;
  updates: Extract<LocalTaskUpdate, { kind: 'answer' | 'report' | 'done' }>[];
};
const reportName = /^GeneLoop-[a-f0-9-]{36}\.md$/;

function loadTasks(path: string): SavedTask[] {
  try {
    const rows: unknown = JSON.parse(readFileSync(path, 'utf8'));
    return Array.isArray(rows) ? rows.filter(row => typeof row?.prompt === 'string' && Number.isFinite(row.at) &&
      Array.isArray(row.updates)).slice(0, 30) : [];
  } catch { return []; }
}

export class LocalWorkspaceWindow {
  private child?: BrowserWindow;
  private workspaceId?: string;
  private busy = false;
  private closed = false;
  private controller?: ReturnType<typeof startLocalWorker>;
  private pending?: AbortController;
  private reports = new Set<string>();

  constructor(private options: { parent: BrowserWindow; server: string; session: Session }) {}

  async open(workspace: LocalWorkspace): Promise<void> {
    if (!workspace.directory) throw Error('请先为工作区添加本机文件夹。');
    if (this.child && !this.child.isDestroyed()) {
      if (this.workspaceId !== workspace.id) throw Error('请先关闭另一个工作区的任务窗口。');
      this.child.focus();
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
      const tasks = loadTasks(history);
      for (const task of tasks) {
        for (const update of task.updates) {
          if (update?.kind === 'report' && reportName.test(update.report?.name)) this.reports.add(update.report.name);
        }
      }
      const child = this.child = new BrowserWindow({
        parent: this.options.parent, width: 760, height: 680, minWidth: 500, minHeight: 480, show: false,
        title: workspace.name + ' · GeneLoop Desktop', autoHideMenuBar: true,
        webPreferences: { preload: join(here, 'local-preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false },
      });
      this.workspaceId = workspace.id;
      child.setMenu(null);
      child.webContents.on('will-navigate', event => event.preventDefault());
      child.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
      const handle = (channel: string, fn: (input: unknown) => unknown) => {
        ipcMain.handle('geneloop-local:' + channel, (event: IpcMainInvokeEvent, input: unknown) => {
          if (event.sender !== child.webContents || event.senderFrame !== child.webContents.mainFrame ||
              event.senderFrame.url !== pathToFileURL(page).href) throw Error('Invalid local workspace sender');
          return fn(input);
        });
      };
      const emit = (event: LocalTaskUpdate) => {
        if (!child.isDestroyed()) child.webContents.send('geneloop-local:update', event);
      };
      handle('state', () => ({ directory, output, tasks }));
      handle('start', input => {
        if (this.pending) throw Error('已有本机任务正在运行。');
        if (typeof input !== 'string' || !input.trim()) throw Error('请输入任务内容。');
        const abort = this.pending = new AbortController();
        const task: SavedTask = { prompt: input, at: Date.now(), updates: [] };
        return this.run(runtime, directory, input, abort, update => {
          if (update.kind !== 'ready') task.updates.push(update);
          if (update.kind !== 'done') { emit(update); return; }
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
      child.once('closed', () => {
        this.pending?.abort();
        this.controller?.cancel();
        for (const channel of channels) ipcMain.removeHandler('geneloop-local:' + channel);
        this.child = undefined;
        this.workspaceId = undefined;
        this.reports.clear();
      });
      try { await child.loadFile(page); child.show(); }
      catch (error) { child.destroy(); throw error; }
    } finally { this.busy = false; }
  }

  private async run(runtime: string, directory: string, prompt: string, abort: AbortController, emit: (event: LocalTaskUpdate) => void) {
    const endpoint = new URL(leasePath, this.options.server);
    let token: string | undefined;
    let outcome: Extract<LocalTaskUpdate, { kind: 'done' }> | undefined;
    try {
      const response = await this.options.session.fetch(endpoint.href, {
        method: 'POST', credentials: 'include', redirect: 'error', bypassCustomProtocolHandlers: true,
        headers: { origin: endpoint.origin, 'content-type': 'application/json' },
        body: '{}', signal: AbortSignal.timeout(22_000),
      });
      if (!response.ok) throw Error(response.status === 404 ? '当前服务器尚未开放本机模型试用。' :
        response.status === 403 ? '请在云端工作区登录已获授权的试用账号。' :
        response.status === 409 ? '已有本机任务，请等待授权结算。' : '无法获取本机模型授权。');
      const lease = await response.json();
      if (!/^[A-Za-z0-9_-]{43}$/.test(lease.token) || lease.model !== 'deepseek-flash') throw Error('本机模型授权响应无效。');
      token = lease.token;
      abort.signal.throwIfAborted();
      this.controller = startLocalWorker({
        executable: process.execPath, runtime, home: join(app.getPath('userData'), 'local-workspace'),
        directory, endpoint: new URL('/api/harless/desktop-model/v1', this.options.server).href,
        token: lease.token, model: lease.model, prompt,
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

  releaseWorkspace(id: string): void {
    if (id !== this.workspaceId) return;
    if (this.pending) throw Error('请先结束当前本机任务，再修改文件夹。');
    this.child?.destroy();
  }

  dispose(): void {
    this.closed = true;
    this.pending?.abort();
    this.controller?.stop();
    this.child?.destroy();
  }
}
