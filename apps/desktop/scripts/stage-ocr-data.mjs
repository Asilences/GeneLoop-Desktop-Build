import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdirSync,existsSync,readFileSync,writeFileSync,cpSync,lstatSync} from 'node:fs';
import {join} from 'node:path';
const version='4.1.0';
import {ocrData} from '../runtime/native-ocr-data.mjs';
export {ocrData};
export function stageOcrData(cache,destination) {
  mkdirSync(join(cache,'tessdata'),{recursive:true});mkdirSync(join(destination,'tessdata'),{recursive:true});
  for(const [name,hash]of Object.entries(ocrData)) {
    const source=join(cache,name);
    if(!existsSync(source)) {
      const url='https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/'+version+'/'+(name.startsWith('tessdata/')?name.slice(9):name);
      const result=spawnSync(process.platform==='win32'?'curl.exe':'curl',['--fail','--location','--retry','2','--silent','--show-error',url,'--output',source],{encoding:'utf8',windowsHide:true});
      if(result.status!==0)throw Error('无法准备离线OCR数据：'+name);
    }
    if(lstatSync(source).isSymbolicLink()||createHash('sha256').update(readFileSync(source)).digest('hex')!==hash)throw Error('OCR数据版本不一致：'+name);
    cpSync(source,join(destination,name));
  }
  writeFileSync(join(destination,'manifest.json'),JSON.stringify({schema_version:1,source:'tesseract-ocr/tessdata_fast',version,files:ocrData},null,2)+'\n');
}
