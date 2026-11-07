import {app} from 'electron';
import {existsSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {validateToolCatalog,toolsetDirectory} from './tool-pack-store.ts';
const here=dirname(fileURLToPath(import.meta.url));
let catalog:ReturnType<typeof validateToolCatalog>|null|undefined;
export function toolCatalog(){
  if(catalog!==undefined)return catalog;
  const path=app.isPackaged?join(process.resourcesPath,'tool-packs.json'):process.env.GENELOOP_TOOL_PACK_MANIFEST;
  catalog=path&&existsSync(path)?validateToolCatalog(JSON.parse(readFileSync(path,'utf8'))):null;return catalog;
}
export function toolHome(){return join(app.getPath('userData'),'local-tools','toolsets');}
export function localToolDirectory(){
  const c=toolCatalog();return c?join(toolsetDirectory(toolHome(),c.toolsetId),'tools'):app.isPackaged?join(process.resourcesPath,'geneloop-tools'):join(here,'../desktop-tools-bundle');
}
export function localToolsPrepared(){const c=toolCatalog();if(!c)return true;try{return JSON.parse(readFileSync(join(toolsetDirectory(toolHome(),c.toolsetId),'ready.json'),'utf8')).toolsetId===c.toolsetId;}catch{return false;}}
