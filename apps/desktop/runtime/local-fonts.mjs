import {readFileSync,lstatSync,writeFileSync,mkdirSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {createHash} from 'node:crypto';
import {runNativeProcess} from './native-process.mjs';
export function nativeFontEnvironment(tools,cwd) {
  if(process.platform!=='darwin')return {};
  const root=dirname(tools.sourceRoot),fontRoot=join(root,'fonts'),cache=join(cwd,'font-cache'),config=join(cwd,'fontconfig.xml');
  mkdirSync(cache,{recursive:true,mode:0o700});
  const escape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const directories=[fontRoot,join(root,'libreoffice/Contents/Resources/fonts/truetype')];
  writeFileSync(config,'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'+directories.map(p=>'<dir>'+escape(p)+'</dir>').join('')+'<cachedir>'+escape(cache)+'</cachedir></fontconfig>',{mode:0o600});
  return {FONTCONFIG_FILE:config,SAL_FONTPATH_PRIVATE:fontRoot};
}
export async function ensureNativeFonts(ctx,tools,cwd,signal) {
  if(process.platform!=='darwin'||!tools?.sourceRoot)return;
  const root=join(dirname(tools.sourceRoot),'fonts'),font=join(root,'NotoSansCJKsc-Regular.otf');
  const stat=lstatSync(font);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.size>20*1024*1024||createHash('sha256').update(readFileSync(font)).digest('hex')!=='2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b')throw Error('随包中文字体无效。');
  await runNativeProcess(ctx,[join(root,'register-font'),font],cwd,signal,{timeoutMs:20000});
}
