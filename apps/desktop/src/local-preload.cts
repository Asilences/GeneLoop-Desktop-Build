import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('localWorkspace', Object.freeze({
  state: () => ipcRenderer.invoke('geneloop-local:state'),
  chooseOutput: () => ipcRenderer.invoke('geneloop-local:output'),
  start: (prompt: string) => ipcRenderer.invoke('geneloop-local:start', prompt),
  cancel: () => ipcRenderer.invoke('geneloop-local:cancel'),
  reveal: (name: string) => ipcRenderer.invoke('geneloop-local:reveal', name),
  onUpdate: (callback: (event: unknown) => void) => {
    ipcRenderer.on('geneloop-local:update', (_event, value: unknown) => callback(value));
  },
}));
