import { BrowserWindow, WebContentsView, dialog, ipcMain, session, shell, Menu, nativeTheme } from 'electron';
import type { IpcMainInvokeEvent, Session, Event, DownloadItem, WebContents } from 'electron';
import { createHash, randomUUID } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { downloadName, externalWebUrl, ownedDownload, sameServer, serverOrigin } from './policy.ts';
import { saveSettings } from './settings.ts';
import type { Settings } from './settings.ts';
import { authorizedDirectory, LocalWorkspaceStore, reopenDirectory } from './local-workspaces.ts';
import { LocalWorkspacePanel } from './local-workspace.ts';
import { LocalFrontendHost } from './frontend.ts';
import { TITLE_BAR_HEIGHT, LIGHT_APPEARANCE, DARK_APPEARANCE, readAppearance } from './appearance.ts';
import type { Appearance } from './appearance.ts';

const directory = dirname(fileURLToPath(import.meta.url));
type DownloadListener = (event: Event, item: DownloadItem, contents: WebContents) => void;
export type DesktopState = { phase: 'connecting' | 'connected' | 'error' | 'settings'; server: string; message: string; version: string; appearance: Appearance; workspaceVisible: boolean; modalOpen: boolean };

export class DesktopWorkspace {
  readonly window: BrowserWindow;
  workspace: WebContentsView | undefined;
  frontend: LocalFrontendHost | undefined;
  readonly ready: Promise<void>;
  private currentSession?: Session;
  private localWorkspace?: LocalWorkspacePanel;
  private readonly localWorkspaces: LocalWorkspaceStore;
  private readonly folderTickets = new Map<string, string>();
  private downloadListener?: DownloadListener;
  private pageReady = false;
  private stateValue: DesktopState;
  private generation = 0;
  private lastDownloaded?: string;
  private allowClose = false;
  private disposed = false;
  private readonly page = join(directory, '../ui/index.html');

  constructor(private options: { settings: Settings; settingsFile: string; version: string; downloadsDirectory: string; allowLoopback?: boolean; closeToTray?: boolean }) {
    const { settings } = options;
    this.localWorkspaces = new LocalWorkspaceStore(join(dirname(options.settingsFile), 'local-workspaces.json'));
    const appearance = nativeTheme.shouldUseDarkColors ? DARK_APPEARANCE : LIGHT_APPEARANCE;
    this.stateValue = { phase: 'connecting', server: settings.server, message: '', version: options.version, appearance, workspaceVisible: false, modalOpen: false };
    this.window = new BrowserWindow({
      ...settings.window, minWidth: 800, minHeight: 600, show: false,
      title: 'GeneLoop Desktop', backgroundColor: appearance.background, autoHideMenuBar: true,
      titleBarStyle: process.platform === 'win32' ? 'hidden' : 'default',
      ...(process.platform === 'win32' ? { titleBarOverlay: { color: appearance.background, symbolColor: appearance.foreground, height: TITLE_BAR_HEIGHT } } : {}),
      icon: join(directory, '../assets/icon.png'),
      webPreferences: { preload: join(directory, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true },
    });
    this.window.webContents.on('will-navigate', event => event.preventDefault());
    this.window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    this.window.webContents.on('page-title-updated', event => event.preventDefault());
    this.window.on('resize', () => this.fit());
    this.window.on('close', event => {
      const { width, height } = this.window.getNormalBounds();
      options.settings.window = { width, height, maximized: this.window.isMaximized() };
      try { saveSettings(options.settingsFile, options.settings); } catch { /* 退出不因偏好保存失败而挂住。 */ }
      if (options.closeToTray && !this.allowClose) { event.preventDefault(); this.window.hide(); }
      else this.dispose();
    });
    this.window.on('closed', () => this.dispose());
    ipcMain.handle('geneloop:local-workspaces', (event, command: unknown, value: unknown) => {
      const view = this.workspace?.webContents;
      if (!view || event.sender !== view || event.senderFrame !== view.mainFrame ||
          !sameServer(event.senderFrame.url, this.stateValue.server) ||
          !['/', '/login', '/register', '/account', '/starting'].includes(new URL(event.senderFrame.url).pathname)) {
        throw Error('Invalid workspace sender');
      }
      return this.localWorkspaceAction(command, value);
    });
    ipcMain.handle('geneloop:state', event => { this.requireShell(event); return this.state(); });
    ipcMain.handle('geneloop:menu', (event, name: unknown) => {
      this.requireShell(event);
      if (name !== 'file' && name !== 'edit' && name !== 'view' && name !== 'help') return;
      if (this.stateValue.phase === 'connected' && this.stateValue.modalOpen) return;
      if (this.pageReady && this.stateValue.phase === 'connected' && !this.localWorkspace?.isOpen) this.workspace?.webContents.focus();
      Menu.getApplicationMenu()?.getMenuItemById('desktop-' + name)?.submenu?.popup({ window: this.window, x: { file: 8, edit: 58, view: 108, help: 158 }[name], y: TITLE_BAR_HEIGHT });
    });
    ipcMain.handle('geneloop:settings', event => { this.requireShell(event); this.showSettings(); });
    ipcMain.handle('geneloop:retry', event => { this.requireShell(event); void this.connect(this.stateValue.server); });
    ipcMain.handle('geneloop:connect', async (event, input: unknown) => {
      this.requireShell(event);
      try {
        const server = serverOrigin(input, options.allowLoopback);
        const settings = { ...options.settings, server };
        saveSettings(options.settingsFile, settings);
        options.settings = settings;
        void this.connect(server);
        return { ok: true };
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : '未能保存连接设置。' };
      }
    });
    this.ready = this.window.loadFile(this.page).then(async () => {
      if (settings.window.maximized) this.window.maximize();
      this.window.show();
      await this.connect(settings.server);
    });
  }

  state(): DesktopState { return { ...this.stateValue }; }
  permitClose(): void { this.allowClose = true; }

  runWorkspaceCommand(command: 'new-session' | 'new-workspace' | 'attach' | 'account-nav'): void {
    const view = this.workspace?.webContents;
    if (!view || view.isDestroyed() || !this.stateValue.workspaceVisible ||
        this.stateValue.phase !== 'connected' || this.stateValue.modalOpen || this.localWorkspace?.isOpen ||
        !sameServer(view.getURL(), this.stateValue.server)) return;
    // 附件按钮需要桌面菜单点击提供的用户手势来打开系统文件选择器。
    void view.executeJavaScript(`document.getElementById(${JSON.stringify(command)})?.click(); void 0`, true).catch(() => {});
  }

  async openLocalWorkspace(): Promise<void> {
    if (this.stateValue.phase !== 'connected' || this.stateValue.modalOpen || this.localWorkspace?.isOpen) return;
    const generation = this.generation;
    try {
      const picked = await this.pickWorkspaceDirectory('选择本机工作区文件夹');
      const view = this.workspace?.webContents;
      if (picked && generation === this.generation && view && !view.isDestroyed()) {
        const row = this.localWorkspaces.open(picked);
        view.send('geneloop:workspace-selected', row.id);
      }
    } catch { if (!this.window.isDestroyed()) dialog.showErrorBox('本机工作区', '无法打开这个本机文件夹。'); }
  }

  private async pickWorkspaceDirectory(title: string): Promise<string | undefined> {
    if (process.platform !== 'win32' || this.disposed) return;
    const result = await dialog.showOpenDialog(this.window, { title, properties: ['openDirectory'] });
    if (!result.canceled && !this.disposed) return authorizedDirectory(result.filePaths[0]);
  }

  private async localWorkspaceAction(command: unknown, value: unknown) {
    if (process.platform !== 'win32' || this.disposed) throw Error('本机工作区仅支持 Windows。');
    if (command === 'list') return this.localWorkspaces.list(this.stateValue.server, value);
    if (command === 'pick') {
      const generation = this.generation;
      const path = await this.pickWorkspaceDirectory('选择本机工作区文件夹');
      if (!path || generation !== this.generation) return null;
      const token = randomUUID();
      if (this.folderTickets.size >= 16) this.folderTickets.delete(this.folderTickets.keys().next().value!);
      this.folderTickets.set(token, path);
      return { path, token };
    }
    if (command === 'save' && value && typeof value === 'object') {
      const input = value as { id?: unknown; name?: unknown; source?: unknown; cloud?: { workspaceId?: unknown; accountId?: unknown } };
      let binding;
      if (input.cloud) {
        const { workspaceId, accountId } = input.cloud;
        if (typeof workspaceId !== 'string' || !workspaceId || typeof accountId !== 'string' || !accountId) throw Error('无效的云端工作区。');
        binding = { server: this.stateValue.server, workspaceId, accountId };
      }
      const old = binding ? this.localWorkspaces.findBinding(binding) :
        typeof input.id === 'string' ? this.localWorkspaces.get(input.id) : undefined;
      if (!binding && old?.binding) throw Error('请在所属工作区修改绑定。');
      const ticket = (token: unknown) => {
        const path = typeof token === 'string' ? this.folderTickets.get(token) : undefined;
        if (!path) throw Error('请重新选择文件夹。');
        return reopenDirectory(path);
      };
      const directory = input.source === null ? undefined : input.source !== undefined ? ticket(input.source) : old?.directory;
      if (old && old.directory !== directory) this.localWorkspace?.releaseWorkspace(old.id);
      if (binding && !directory) {
        if (old) this.localWorkspaces.remove(old.id);
        return null;
      }
      if (typeof input.name !== 'string' || (!old && !directory)) throw Error('请填写名称并选择源文件夹。');
      const saved = this.localWorkspaces.save({ id: old?.id, name: input.name, directory, binding });
      if (typeof input.source === 'string') this.folderTickets.delete(input.source);
      return saved;
    }
    if (typeof value !== 'string') throw Error('无效的本机工作区。');
    const row = this.localWorkspaces.get(value);
    if (command === 'remove') {
      this.localWorkspace?.releaseWorkspace(row.id);
      return this.localWorkspaces.remove(row.id);
    }
    if (!row.directory) throw Error('请先为工作区添加本机文件夹。');
    if (command === 'reveal') {
      const result = await shell.openPath(reopenDirectory(row.directory));
      if (result) throw Error('无法在资源管理器中打开这个文件夹。');
      return;
    }
    if (command === 'run' && this.currentSession) {
      this.localWorkspace ??= new LocalWorkspacePanel({
        parent: this.window, server: this.stateValue.server, session: this.currentSession,
        onClose: () => {
          if (this.stateValue.phase === 'connected') {
            this.workspace?.setVisible(true);
            this.workspace?.webContents.focus();
          }
        },
      });
      const panel = this.localWorkspace;
      await panel.open(row);
      if (panel !== this.localWorkspace || !panel.isOpen) return;
      this.workspace?.setVisible(false);
      panel.setVisible(this.stateValue.phase === 'connected');
      return;
    }
    throw Error('无效的本机工作区操作。');
  }

  private requireShell(event: IpcMainInvokeEvent): void {
    if (event.sender !== this.window.webContents || event.senderFrame !== this.window.webContents.mainFrame ||
        event.senderFrame.url !== pathToFileURL(this.page).href) throw new Error('此操作仅供桌面连接页面使用。');
  }

  private update(phase: DesktopState['phase'], message = ''): void {
    this.stateValue = { ...this.stateValue, phase, message };
    this.updateTitleBar();
    if (!this.window.isDestroyed()) this.window.webContents.send('geneloop:state', this.state());
  }

  private updateTitleBar(): void {
    if (process.platform !== 'win32' || this.window.isDestroyed()) return;
    const { appearance, phase, modalOpen } = this.stateValue;
    const color = phase === 'connected' && modalOpen
      ? appearance.background.replace(/[0-9a-f]{2}/gi, channel => Math.round(parseInt(channel, 16) * 2 / 3).toString(16).padStart(2, '0'))
      : appearance.background;
    this.window.setTitleBarOverlay({ color, symbolColor: appearance.foreground, height: TITLE_BAR_HEIGHT });
  }

  private fit(): void {
    this.localWorkspace?.fit();
    if (this.workspace && !this.window.isDestroyed()) {
      const [width, height] = this.window.getContentSize();
      this.workspace.setBounds({ x: 0, y: TITLE_BAR_HEIGHT, width, height: Math.max(0, height - TITLE_BAR_HEIGHT) });
    }
  }

  showSettings(): void {
    this.localWorkspace?.setVisible(false);
    this.workspace?.setVisible(false);
    this.update('settings');
  }

  showWorkspace(): void {
    if (this.workspace && this.pageReady && this.stateValue.phase !== 'error') {
      this.workspace.setVisible(!this.localWorkspace?.isOpen);
      this.localWorkspace?.setVisible(true);
      this.update('connected');
    } else void this.connect(this.stateValue.server);
  }

  async openLastDownload(): Promise<void> {
    if (this.lastDownloaded) shell.showItemInFolder(this.lastDownloaded);
    else await dialog.showMessageBox(this.window, { type: 'info', message: '还没有已完成的下载。', detail: '在文件预览中选择下载，完成后可从这里打开所在目录。' });
  }

  async connect(input: string): Promise<void> {
    const server = serverOrigin(input, this.options.allowLoopback);
    const attempt = ++this.generation;
    this.localWorkspace?.dispose();
    this.localWorkspace = undefined;
    this.folderTickets.clear();
    this.removeWorkspace();
    this.pageReady = false;
    this.stateValue.workspaceVisible = false;
    this.stateValue.modalOpen = false;
    this.stateValue.server = server;
    this.update('connecting');
    // 不同服务器使用不同 Cookie / localStorage，保留原生同源登录和传输。
    const partition = 'persist:geneloop-' + createHash('sha256').update(server).digest('hex').slice(0, 24);
    const remoteSession = session.fromPartition(partition);
    this.currentSession = remoteSession;
    remoteSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    remoteSession.setPermissionCheckHandler(() => false);
    const view = new WebContentsView({ webPreferences: {
      session: remoteSession, nodeIntegration: false, contextIsolation: true, sandbox: true,
      preload: join(directory, 'appearance-preload.cjs'),
      webviewTag: false, webSecurity: true, navigateOnDragDrop: false,
    } });
    this.workspace = view;
    view.setVisible(false);
    this.window.contentView.addChildView(view);
    this.fit();
    const fail = (message: string) => {
      if (attempt !== this.generation || this.window.isDestroyed()) return;
      view.setVisible(false);
      this.update('error', message);
    };
    this.frontend = new LocalFrontendHost({ session: remoteSession, server, assets: join(directory, '../assets'), ui: join(directory, '../ui/desktop'), fail });
    this.frontend.install();
    view.webContents.on('ipc-message', (event, channel, value: unknown) => {
      if (channel !== 'geneloop:appearance' || attempt !== this.generation || event.senderFrame !== view.webContents.mainFrame ||
          !sameServer(event.senderFrame.url, server)) return;
      const appearance = readAppearance(value);
      if (!appearance || this.window.isDestroyed()) return;
      this.stateValue.appearance = appearance;
      const presentation = value as { screen?: unknown; modalOpen?: unknown };
      this.stateValue.workspaceVisible = presentation.screen === 'workspace';
      this.stateValue.modalOpen = presentation.modalOpen === true;
      this.updateTitleBar();
      this.window.setBackgroundColor(appearance.background);
      this.window.webContents.send('geneloop:state', this.state());
    });
    view.webContents.on('context-menu', (_event, params) => {
      if (!params.isEditable || attempt !== this.generation || !sameServer(params.frameURL, server)) return;
      const flags = params.editFlags;
      Menu.buildFromTemplate([
        { label: '撤销', role: 'undo', enabled: flags.canUndo },
        { label: '重做', role: 'redo', enabled: flags.canRedo },
        { type: 'separator' },
        { label: '剪切', role: 'cut', enabled: flags.canCut },
        { label: '复制', role: 'copy', enabled: flags.canCopy },
        { label: '粘贴', role: 'paste', enabled: flags.canPaste },
        { label: '全选', role: 'selectAll', enabled: flags.canSelectAll },
      ]).popup({ window: this.window });
    });
    view.webContents.on('will-navigate', (event, url) => {
      if (!sameServer(url, server)) event.preventDefault();
    });
    view.webContents.on('will-redirect', (event, url, _inPlace, isMainFrame) => {
      if (isMainFrame && !sameServer(url, server)) {
        event.preventDefault();
        fail('服务器跳转到了其他地址。请检查连接设置后重试。');
      }
    });
    view.webContents.on('will-attach-webview', event => event.preventDefault());
    view.webContents.setWindowOpenHandler(({ url }) => {
      if (sameServer(url, server)) void view.webContents.loadURL(url).catch(() => fail('页面未能打开，请重新连接。'));
      else {
        const external = externalWebUrl(url);
        if (external) void shell.openExternal(external).catch(() => {});
      }
      return { action: 'deny' };
    });
    view.webContents.on('did-fail-load', (_event, code, _description, _url, isMainFrame) => {
      if (isMainFrame && code !== -3) fail('暂时无法连接 GeneLoop。请检查网络后重试。');
    });
    view.webContents.on('render-process-gone', () => fail('工作区页面已停止，请重新连接以恢复。'));
    const onDownload: DownloadListener = (_event, item, contents) => {
      if (contents !== view.webContents || !ownedDownload(item.getURLChain().length ? item.getURLChain() : [item.getURL()], server)) {
        item.cancel(); return;
      }
      item.setSaveDialogOptions({ title: '保存 GeneLoop 文件', defaultPath: join(this.options.downloadsDirectory, downloadName(item.getFilename())) });
      item.once('done', (_downloadEvent, status) => {
        if (status === 'completed') this.lastDownloaded = item.getSavePath();
      });
    };
    this.downloadListener = onDownload;
    remoteSession.on('will-download', onDownload);
    const timeout = setTimeout(() => {
      if (attempt !== this.generation || view.webContents.isDestroyed()) return;
      view.webContents.stop();
      fail('连接耗时较长，请检查网络或服务器地址后重试。');
    }, 20_000);
    try {
      await view.webContents.loadURL(server);
      if (attempt === this.generation && this.stateValue.phase === 'connecting') {
        this.pageReady = true;
        view.setVisible(true);
        this.update('connected');
      }
    } catch { fail('暂时无法连接 GeneLoop。请检查网络后重试。'); }
    finally { clearTimeout(timeout); }
  }

  private removeWorkspace(): void {
    this.frontend?.dispose();
    this.frontend = undefined;
    if (this.currentSession && this.downloadListener) this.currentSession.removeListener('will-download', this.downloadListener);
    this.downloadListener = undefined;
    this.currentSession = undefined;
    if (this.workspace) {
      if (!this.window.isDestroyed()) this.window.contentView.removeChildView(this.workspace);
      if (!this.workspace.webContents.isDestroyed()) this.workspace.webContents.close();
      this.workspace = undefined;
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.localWorkspace?.dispose();
    ++this.generation;
    this.removeWorkspace();
    for (const channel of ['geneloop:local-workspaces', 'geneloop:state', 'geneloop:retry', 'geneloop:connect', 'geneloop:menu', 'geneloop:settings']) ipcMain.removeHandler(channel);
  }
}
