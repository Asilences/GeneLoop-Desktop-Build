import { BrowserWindow, WebContentsView, dialog, ipcMain, session, shell, Menu, nativeTheme } from 'electron';
import type { IpcMainInvokeEvent, Session, Event, DownloadItem, WebContents } from 'electron';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { downloadName, externalWebUrl, ownedDownload, sameServer, serverOrigin } from './policy.ts';
import { saveSettings } from './settings.ts';
import type { Settings } from './settings.ts';
import { LocalFrontendHost } from './frontend.ts';
import { TITLE_BAR_HEIGHT, LIGHT_APPEARANCE, DARK_APPEARANCE, readAppearance } from './appearance.ts';
import type { Appearance } from './appearance.ts';

const directory = dirname(fileURLToPath(import.meta.url));
type DownloadListener = (event: Event, item: DownloadItem, contents: WebContents) => void;
export type DesktopState = { phase: 'connecting' | 'connected' | 'error' | 'settings'; server: string; message: string; version: string; appearance: Appearance; workspaceVisible: boolean };

export class DesktopWorkspace {
  readonly window: BrowserWindow;
  workspace: WebContentsView | undefined;
  frontend: LocalFrontendHost | undefined;
  readonly ready: Promise<void>;
  private currentSession?: Session;
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
    const appearance = nativeTheme.shouldUseDarkColors ? DARK_APPEARANCE : LIGHT_APPEARANCE;
    this.stateValue = { phase: 'connecting', server: settings.server, message: '', version: options.version, appearance, workspaceVisible: false };
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
    ipcMain.handle('geneloop:state', event => { this.requireShell(event); return this.state(); });
    ipcMain.handle('geneloop:menu', (event, name: unknown) => {
      this.requireShell(event);
      if (name !== 'app' && name !== 'edit') return;
      if (this.pageReady && this.stateValue.phase === 'connected') this.workspace?.webContents.focus();
      Menu.getApplicationMenu()?.getMenuItemById('desktop-' + name)?.submenu?.popup({ window: this.window, x: name === 'app' ? 8 : 58, y: TITLE_BAR_HEIGHT });
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

  private requireShell(event: IpcMainInvokeEvent): void {
    if (event.sender !== this.window.webContents || event.senderFrame !== this.window.webContents.mainFrame ||
        event.senderFrame.url !== pathToFileURL(this.page).href) throw new Error('此操作仅供桌面连接页面使用。');
  }

  private update(phase: DesktopState['phase'], message = ''): void {
    this.stateValue = { ...this.stateValue, phase, message };
    if (!this.window.isDestroyed()) this.window.webContents.send('geneloop:state', this.state());
  }

  private fit(): void {
    if (this.workspace && !this.window.isDestroyed()) {
      const [width, height] = this.window.getContentSize();
      this.workspace.setBounds({ x: 0, y: TITLE_BAR_HEIGHT, width, height: Math.max(0, height - TITLE_BAR_HEIGHT) });
    }
  }

  showSettings(): void {
    this.workspace?.setVisible(false);
    this.update('settings');
  }

  showWorkspace(): void {
    if (this.workspace && this.pageReady && this.stateValue.phase !== 'error') {
      this.workspace.setVisible(true);
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
    this.removeWorkspace();
    this.pageReady = false;
    this.stateValue.workspaceVisible = false;
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
      this.stateValue.workspaceVisible = (value as { screen?: unknown }).screen === 'workspace';
      if (process.platform === 'win32') this.window.setTitleBarOverlay({ color: appearance.background, symbolColor: appearance.foreground, height: TITLE_BAR_HEIGHT });
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
    ++this.generation;
    this.removeWorkspace();
    for (const channel of ['geneloop:state', 'geneloop:retry', 'geneloop:connect', 'geneloop:menu', 'geneloop:settings']) ipcMain.removeHandler(channel);
  }
}
