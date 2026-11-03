import { app, dialog, Menu } from 'electron';
import { join } from 'node:path';
import { loadSettings } from './settings.ts';
import { DesktopWorkspace } from './workspace.ts';

app.setName('GeneLoop Desktop');
app.setAppUserModelId('ai.geneloop.desktop');
if (!app.isPackaged && process.env.GENELOOP_DESKTOP_USER_DATA_DIR) {
  app.setPath('userData', process.env.GENELOOP_DESKTOP_USER_DATA_DIR);
}

let desktop: DesktopWorkspace | undefined;
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
      desktop = new DesktopWorkspace({ settings, settingsFile, version: app.getVersion(), downloadsDirectory: app.getPath('downloads'), allowLoopback });
      desktop.ready.catch(() => { dialog.showErrorBox('GeneLoop Desktop', '连接页面无法启动，请重新安装应用。'); app.quit(); });
    };
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { label: 'GeneLoop', submenu: [
        { label: '返回工作区', click: () => desktop?.showWorkspace() },
        { label: '重新连接', click: () => { if (desktop) void desktop.connect(desktop.state().server); } },
        { label: '连接设置', click: () => desktop?.showSettings() },
        { type: 'separator' },
        { label: '打开最近下载的位置', click: () => { void desktop?.openLastDownload(); } },
        { type: 'separator' },
        { label: '退出 GeneLoop Desktop', role: 'quit' },
      ] },
      { label: '编辑', submenu: [ { role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' } ] },
      { label: '视图', submenu: [ { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'togglefullscreen' } ] },
      { label: '帮助', submenu: [ { label: '关于 GeneLoop Desktop', click: () => {
        if (desktop) void dialog.showMessageBox(desktop.window, { type: 'info', message: 'GeneLoop Desktop ' + app.getVersion(), detail: '当前版本连接 GeneLoop 服务器，Agent 与场景工具在服务器执行。' });
      } } ] },
    ]));
    create();
    app.on('activate', () => {
      if (!desktop || desktop.window.isDestroyed()) create();
      else desktop.window.show();
    });
  }).catch(() => { dialog.showErrorBox('GeneLoop Desktop', '启动失败。请检查服务器地址配置，或从默认安装入口重新打开。'); app.quit(); });
  app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
}
