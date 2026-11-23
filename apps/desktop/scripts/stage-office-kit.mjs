// Build-time only. Keep the original complete Office tree for rollback outside
// the Kit distribution; installed tools never fetch npm packages or engines.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {cpSync,existsSync,mkdirSync,readFileSync,renameSync,writeFileSync,chmodSync} from 'node:fs';
import {join,resolve,dirname,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const app=fileURLToPath(new URL('../',import.meta.url));
export function stageOfficeKit(directory=join(app,'desktop-tools-bundle')){
const bundle=resolve(directory);
const prefix=resolve(process.env.GENELOOP_OFFICE_KIT_SOURCE??join(app,'.local','office-kit-'+process.platform+'-'+process.arch));
const run=(bin,args)=>{const r=spawnSync(bin,args,{stdio:'inherit',windowsHide:true});if(r.error)throw r.error;assert.equal(r.status,0,'Office Kit 构建步骤未完成');};
assert.ok(['win32','darwin'].includes(process.platform));
assert.ok(process.arch==='x64'||process.platform==='darwin'&&process.arch==='arm64','尚未适配此桌面目标');
if(!existsSync(join(prefix,'node_modules/@deepseek-ai/libreoffice-kit/package.json'))){
 mkdirSync(prefix,{recursive:true});for(const name of ['package.json','package-lock.json'])cpSync(join(app,'office-kit',name),join(prefix,name));
 const cli=[process.env.npm_execpath,join(dirname(process.execPath),'node_modules/npm/bin/npm-cli.js'),
   join(dirname(process.execPath),'../lib/node_modules/npm/bin/npm-cli.js')].find(p=>p&&existsSync(p));
 assert.ok(cli,'请通过 npm run tools:office 准备 Kit');
 run(process.execPath,[cli,'ci','--prefix',prefix,'--ignore-scripts','--no-audit','--no-fund','--registry=https://registry.npmjs.org']);
}
const identity=JSON.parse(readFileSync(join(prefix,'node_modules/@deepseek-ai/libreoffice-kit/package.json')));assert.equal(identity.version,'0.2.3');
const nativePackage=join(prefix,'node_modules/@deepseek-ai/libreoffice-kit-'+process.platform+'-'+process.arch+'/package.json');
assert.ok(existsSync(nativePackage),'不能以 WASM 代替目标系统原生引擎');
assert.equal(JSON.parse(readFileSync(nativePackage)).version,identity.version,'原生引擎与 Kit 版本必须一致');
mkdirSync(bundle,{recursive:true});const target=join(bundle,'libreoffice');
if(existsSync(target)){
 assert.ok(!existsSync(join(target,'office-kit.json')),'Kit 已准备，不覆盖未知或已使用的目录');
 const previous=join(bundle,'../office-rollback-'+process.platform+'-'+process.arch);assert.ok(!existsSync(previous),'回退目录已存在，请使用新的构建目录');renameSync(target,previous);
}
mkdirSync(target);
cpSync(join(prefix,'node_modules'),join(target,'node_modules'),{recursive:true,verbatimSymlinks:true,filter:p=>{
 const name=relative(join(prefix,'node_modules'),p).split('\\').join('/');
 // Native target only. The optional WASM copy duplicates the Office engine;
 // it is never a fallback for the desktop's explicitly native contract.
 return name!=='.bin'&&!name.startsWith('.bin/')&&name!=='@deepseek-ai/libreoffice-kit-wasm'&&!name.startsWith('@deepseek-ai/libreoffice-kit-wasm/');
}});
cpSync(join(app,'runtime/office-kit-bridge.mjs'),join(target,'bridge.mjs'));
cpSync(join(app,'runtime/office-metafile.mjs'),join(target,'office-metafile.mjs'));
const executable=join(target,process.platform==='win32'?'program/soffice.com':'Contents/MacOS/soffice');mkdirSync(dirname(executable),{recursive:true});
if(process.platform==='win32')run(join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/csc.exe'),['/nologo','/target:exe','/platform:x64','/out:'+executable,join(app,'native/OfficeKitLauncher.cs')]);
else{writeFileSync(executable,'#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "$(/usr/bin/dirname "$0")/../.." && pwd -P)\n: "${GENELOOP_OFFICE_NODE:?本机 Office 宿主未配置}"\nexport ELECTRON_RUN_AS_NODE=1\nexec "$GENELOOP_OFFICE_NODE" "$ROOT/bridge.mjs" "$@"\n');chmodSync(executable,0o755);}
writeFileSync(join(target,'office-kit.json'),JSON.stringify({schema:1,version:identity.version,platform:process.platform,arch:process.arch,native:true,node:'trusted desktop host',unsupportedStandalone:['rtf','emf','wmf']}));
console.log(JSON.stringify({office:'libreoffice-kit',version:identity.version,platform:process.platform,arch:process.arch,target}));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)stageOfficeKit(process.argv[2]);
