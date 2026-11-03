import { contextBridge, ipcRenderer } from 'electron';

// 此 preload 只属于安装包内的连接页面，服务器工作区没有 preload。
contextBridge.exposeInMainWorld('geneLoopDesktop', Object.freeze({
  state: () => ipcRenderer.invoke('geneloop:state'),
  connect: (server: string) => ipcRenderer.invoke('geneloop:connect', server),
  retry: () => ipcRenderer.invoke('geneloop:retry'),
  menu: () => ipcRenderer.invoke('geneloop:menu'),
  settings: () => ipcRenderer.invoke('geneloop:settings'),
  onState: (callback: (value: unknown) => void) => {
    const listener = (_event: unknown, value: unknown) => callback(value);
    ipcRenderer.on('geneloop:state', listener);
    return () => ipcRenderer.removeListener('geneloop:state', listener);
  },
}));
