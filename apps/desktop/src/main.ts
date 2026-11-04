import { app, dialog, Menu, Tray, nativeImage } from 'electron';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadSettings } from './settings.ts';
import { DesktopWorkspace } from './workspace.ts';

app.setName('GeneLoop Desktop');
app.setAppUserModelId('ai.geneloop.desktop');
if (!app.isPackaged && process.env.GENELOOP_DESKTOP_USER_DATA_DIR) {
  app.setPath('userData', process.env.GENELOOP_DESKTOP_USER_DATA_DIR);
}

let desktop: DesktopWorkspace | undefined;
let tray: Tray | undefined;
const directory = dirname(fileURLToPath(import.meta.url));
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {
    if (!desktop) return;
    if (desktop.window.isMinimized()) desktop.window.restore();
    desktop.window.show(); desktop.window.focus();
  });
  app.whenReady().then(async () => {
    const settingsFile = join(app.getPath('userData'), 'desktop-settings.json');
    const allowLoopback = !app.isPackaged && process.env.GENELOOP_DESKTOP_ALLOW_HTTP_LOOPBACK === '1';
    const create = () => {
      const settings = loadSettings(settingsFile, process.env.GENELOOP_DESKTOP_URL, allowLoopback);
      desktop = new DesktopWorkspace({ settings, settingsFile, version: app.getVersion(), downloadsDirectory: app.getPath('downloads'), allowLoopback, closeToTray: process.platform === 'win32' });
      desktop.ready.catch(() => { dialog.showErrorBox('GeneLoop Desktop', '连接页面无法启动，请重新安装应用。'); app.quit(); });
    };
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { id: 'desktop-file', label: '文件', submenu: [
        { label: '新会话', accelerator: 'CmdOrCtrl+N', click: () => desktop?.runWorkspaceCommand('new-session') },
        { label: '新建工作区…', click: () => desktop?.runWorkspaceCommand('new-workspace') },
        { label: '打开本机文件夹…', click: () => { void desktop?.openLocalWorkspace(); } },
        { type: 'separator' },
        { label: '添加附件…', accelerator: 'CmdOrCtrl+O', click: () => desktop?.runWorkspaceCommand('attach') },
        { label: '打开最近下载的位置', click: () => { void desktop?.openLastDownload(); } },
        { type: 'separator' },
        { label: '返回工作区', click: () => desktop?.showWorkspace() },
        { label: '重新连接', accelerator: 'CmdOrCtrl+R', click: () => { if (desktop) void desktop.connect(desktop.state().server); } },
        { label: '连接设置', accelerator: 'CmdOrCtrl+,', click: () => desktop?.showSettings() },
        { type: 'separator' },
        { label: '关闭窗口', accelerator: 'CmdOrCtrl+W', click: () => desktop?.window.close() },
        { label: '账户与安全…', click: () => desktop?.runWorkspaceCommand('account-nav') },
        { type: 'separator' },
        { label: '退出 GeneLoop Desktop', role: 'quit', accelerator: 'CmdOrCtrl+Q' },
      ] },
      { id: 'desktop-edit', label: '编辑', submenu: [ { role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' } ] },
      { id: 'desktop-view', label: '视图', submenu: [ { label: '实际大小', role: 'resetZoom' }, { label: '放大', role: 'zoomIn' }, { label: '缩小', role: 'zoomOut' }, { type: 'separator' }, { label: '切换全屏', role: 'togglefullscreen' } ] },
      { id: 'desktop-help', label: '帮助', submenu: [ { label: '关于 GeneLoop Desktop', click: () => {
        if (desktop) void dialog.showMessageBox(desktop.window, { type: 'info', message: 'GeneLoop Desktop ' + app.getVersion(), detail: '云端工作区由 GeneLoop 服务器执行。本机工作区在 Windows 上运行 Agent 和文件工具，模型使用已获授权的云端服务。' });
      } } ] },
    ]));
    create();
    const show = () => {
      if (!desktop || desktop.window.isDestroyed()) create();
      else { if (desktop.window.isMinimized()) desktop.window.restore(); desktop.window.show(); desktop.window.focus(); }
    };
    if (process.platform === 'win32') {
      tray = new Tray(nativeImage.createFromPath(join(directory, '../assets/icon.png')).resize({ width: 20, height: 20 }));
      tray.setToolTip('GeneLoop Desktop');
      tray.setContextMenu(Menu.buildFromTemplate([
        { label: '打开 GeneLoop Desktop', click: show },
        { label: '连接设置', click: () => { show(); desktop?.showSettings(); } },
        { type: 'separator' },
        { label: '退出 GeneLoop Desktop', click: () => app.quit() },
      ]));
      tray.on('click', show);
    }
    app.on('activate', () => {
      if (!desktop || desktop.window.isDestroyed()) create();
      else desktop.window.show();
    });
  }).catch(() => { dialog.showErrorBox('GeneLoop Desktop', '启动失败。请检查服务器地址配置，或从默认安装入口重新打开。'); app.quit(); });
  app.on('before-quit', () => { desktop?.permitClose(); desktop?.dispose(); tray?.destroy(); });
  app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
}
