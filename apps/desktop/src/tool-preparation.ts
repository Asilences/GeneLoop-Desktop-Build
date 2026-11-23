import {app,BrowserWindow,dialog,ipcMain,net} from 'electron';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {ToolPackStore} from './tool-pack-store.ts';
import {toolCatalog,toolHome,localToolsPrepared} from './tool-location.ts';

const here=dirname(fileURLToPath(import.meta.url));
export class ToolPreparation{
  private window?:BrowserWindow;private store?:ToolPackStore;
  constructor(private parent:BrowserWindow){
    const catalog=toolCatalog();
    if(catalog)this.store=new ToolPackStore(catalog,{home:toolHome(),codecDirectory:app.isPackaged?join(process.resourcesPath,'installer-tools'):process.env.GENELOOP_TOOL_PACK_CODEC_DIRECTORY??join(here,'../.local/tool-pack-build/installer-tools'),
      fetcher:net.fetch as typeof fetch,change:()=>{if(this.window&&!this.window.isDestroyed())this.window.webContents.send('geneloop:tool-pack-state',this.store?.state());}});
    ipcMain.handle('geneloop:tool-packs',async(event,command:unknown,value:unknown)=>{
      const window=this.window,view=window?.webContents;
      if(!view||event.sender!==view||event.senderFrame!==view.mainFrame||event.senderFrame.url!==pathToFileURL(join(here,'../ui/tool-preparation.html')).href)throw Error('Invalid tool preparation sender');
      if(command==='state')return this.store?.state()??{enabled:false,ready:true,busy:false,rows:[]};
      if(command==='cancel'){this.store?.cancel();return;}
      if(command==='start'){
        if(!this.store)throw Error('工具已随包安装');
        const ids=Array.isArray(value)&&value.every(id=>typeof id==='string')?value:undefined;
        void this.store.prepare(ids).catch(()=>{});return;
      }
      if(command==='import'){
        const result=await dialog.showOpenDialog(window!,{title:'选择已下载的 GeneLoop 工具包文件夹',properties:['openDirectory']});
        if(!result.canceled)this.store?.setLocalSource(result.filePaths[0]);return;
      }
      if(command==='close')window?.close();
    });
  }
  show(visible=true){
    if(this.window&&!this.window.isDestroyed()){this.window.show();this.window.focus();return;}
    this.window=new BrowserWindow({parent:this.parent,width:720,height:760,minWidth:620,minHeight:540,show:visible,title:'本机工具 · GeneLoop Desktop',backgroundColor:'#f8f9fc',autoHideMenuBar:true,
      webPreferences:{preload:join(here,'tool-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
    this.window.setMenu(null);this.window.webContents.on('will-navigate',e=>e.preventDefault());this.window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    void this.window.loadFile(join(here,'../ui/tool-preparation.html'));
  }
  offer(){if(this.store&&!localToolsPrepared())this.show();}
  dispose(){this.store?.cancel();if(this.window&&!this.window.isDestroyed())this.window.destroy();ipcMain.removeHandler('geneloop:tool-packs');}
}
