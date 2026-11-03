import { contextBridge, ipcRenderer } from 'electron';

// 控制桥只属于安装包内连接页面；工作区仅有不暴露页面API的颜色观察preload。
contextBridge.exposeInMainWorld('geneLoopDesktop', Object.freeze({
  state: () => ipcRenderer.invoke('geneloop:state'),
  connect: (server: string) => ipcRenderer.invoke('geneloop:connect', server),
  retry: () => ipcRenderer.invoke('geneloop:retry'),
  menu: (name: 'app' | 'edit' | 'view') => ipcRenderer.invoke('geneloop:menu', name),
  settings: () => ipcRenderer.invoke('geneloop:settings'),
  onState: (callback: (value: unknown) => void) => {
    const listener = (_event: unknown, value: unknown) => callback(value);
    ipcRenderer.on('geneloop:state', listener);
    return () => ipcRenderer.removeListener('geneloop:state', listener);
  },
}));
