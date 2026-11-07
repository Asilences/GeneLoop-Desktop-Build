import {contextBridge,ipcRenderer} from 'electron';
contextBridge.exposeInMainWorld('geneLoopTools',Object.freeze({
  command:(name:string,value?:unknown)=>ipcRenderer.invoke('geneloop:tool-packs',name,value),
  onState:(callback:(state:unknown)=>void)=>{const listener=(_event:unknown,state:unknown)=>callback(state);ipcRenderer.on('geneloop:tool-pack-state',listener);return()=>ipcRenderer.removeListener('geneloop:tool-pack-state',listener);},
}));
