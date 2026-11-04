import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('localWorkspace', Object.freeze({
  state: () => ipcRenderer.invoke('geneloop-local:state'),
  start: (input: { prompt: string; scene: string; continuation?: string }) => ipcRenderer.invoke('geneloop-local:start', input),
  cancel: () => ipcRenderer.invoke('geneloop-local:cancel'),
  reveal: (name: string) => ipcRenderer.invoke('geneloop-local:reveal', name),
  onUpdate: (callback: (event: unknown) => void) => {
    ipcRenderer.on('geneloop-local:update', (_event, value: unknown) => callback(value));
  },
}));
