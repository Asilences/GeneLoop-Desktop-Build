import {app,nativeTheme} from 'electron';
import type {BrowserWindow} from 'electron';
import {createHash} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';

/** Shell不能读取ASAR内部的图标；用品牌摘要命名的实体ICO更新窗口的任务栏信息。 */
export function bindWindowsBrand(window:BrowserWindow,assets:string):()=>void{
  if(process.platform!=='win32')return ()=>{};
  const update=()=>{
    if(window.isDestroyed())return;
    const dark=nativeTheme.shouldUseDarkColorsForSystemIntegratedUI;
    try{
      const bytes=readFileSync(join(assets,dark?'icon-dark.ico':'icon.ico'));
      const digest=createHash('sha256').update(bytes).digest('hex').slice(0,16);
      const cache=join(app.getPath('userData'),'brand-icons');mkdirSync(cache,{recursive:true});
      const file=join(cache,'geneloop-fractal-'+digest+'.ico');
      if(!existsSync(file)||!readFileSync(file).equals(bytes))writeFileSync(file,bytes);
      window.setIcon(file);
      const command='"'+process.execPath+'"'+(app.isPackaged?'':' "'+app.getAppPath()+'"');
      window.setAppDetails({appId:app.isPackaged?'ai.geneloop.desktop':'ai.geneloop.desktop.development',
        appIconPath:file,appIconIndex:0,relaunchCommand:command,relaunchDisplayName:'GeneLoop Desktop'});
    }catch{
      // 图标缓存不可写不阻断启动，窗口仍使用当前随包的品牌图。
      window.setIcon(join(assets,dark?'tray-dark.png':'icon.png'));
    }
  };
  update();nativeTheme.on('updated',update);
  return ()=>nativeTheme.removeListener('updated',update);
}
