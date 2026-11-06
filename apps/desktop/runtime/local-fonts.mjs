import {readFileSync,lstatSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {createHash} from 'node:crypto';
import {runNativeProcess} from './native-process.mjs';
export async function ensureNativeFonts(ctx,tools,cwd,signal) {
  if(process.platform!=='darwin'||!tools?.sourceRoot)return;
  const root=join(dirname(tools.sourceRoot),'fonts'),font=join(root,'NotoSansCJKsc-Regular.otf');
  const stat=lstatSync(font);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.size>20*1024*1024||createHash('sha256').update(readFileSync(font)).digest('hex')!=='2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b')throw Error('随包中文字体无效。');
  await runNativeProcess(ctx,[join(root,'register-font'),font],cwd,signal,{timeoutMs:20000});
}
