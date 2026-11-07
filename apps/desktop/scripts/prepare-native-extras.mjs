// Build-only dependencies for the locked Skill. No runtime package downloads.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {chmodSync,copyFileSync,cpSync,existsSync,mkdirSync,readFileSync,readdirSync,rmSync,writeFileSync} from 'node:fs';
import {basename,dirname,join,resolve,sep} from 'node:path';
import {gunzipSync} from 'node:zlib';
import {fileURLToPath} from 'node:url';
const app=fileURLToPath(new URL('../',import.meta.url));
const lock=JSON.parse(readFileSync(join(app,'native-extra-tools-lock.json'),'utf8'));
const hash=data=>createHash('sha256').update(data).digest('hex');
function run(exe,args,env=process.env){const r=spawnSync(exe,args,{env,encoding:'utf8',windowsHide:true,maxBuffer:8*1024**2});if(r.status!==0)throw Error('工具构建失败 '+basename(exe)+': '+(r.stderr||r.stdout));return r.stdout;}
function download(asset,directory){
  assert.match(asset.sha256,/^[a-f0-9]{64}$/);assert.ok(asset.url.startsWith('https://github.com/'));
  mkdirSync(directory,{recursive:true});const path=join(directory,asset.name);
  if(!existsSync(path)){
    const proxy=spawnSync('git',['config','--get-urlmatch','http.proxy','https://github.com'],{encoding:'utf8',windowsHide:true});
    run(process.platform==='win32'?'curl.exe':'curl',['--fail','--location','--retry','2',...(proxy.status===0?['--proxy',proxy.stdout.trim()]:[]),'--output',path,asset.url]);
  }
  assert.equal(hash(readFileSync(path)),asset.sha256,'下载的离线工具校验失败：'+asset.name);return path;
}
export function prepareNativeExtras(python,bundle){
  const platform=process.platform,arch=process.arch,cache=join(app,'.local','extra-tools-'+platform+'-'+arch);
  assert.ok(resolve(bundle).startsWith(resolve(app)+sep),'只允许更新桌面构建副本');
  mkdirSync(cache,{recursive:true});assert.ok(existsSync(join(bundle,'.geneloop-tools')));
  const suffix=platform==='win32'?'windows-x86_64':arch==='arm64'?'arm64-macOS':'x86_64-macOS';
  const pandoc=lock.pandoc.assets.find(a=>a.name.endsWith(suffix+'.zip'));assert.ok(pandoc);
  const archive=download(pandoc,cache),unpack=join(cache,'pandoc');mkdirSync(unpack,{recursive:true});
  run(python,['-B','-c',"import pathlib,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); root=pathlib.Path(sys.argv[2]).resolve(); assert all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts and '\\\\' not in n for n in z.namelist()); z.extractall(root)",archive,unpack]);
  const files=readdirSync(unpack,{recursive:true});const exe=files.find(n=>basename(n)===(platform==='win32'?'pandoc.exe':'pandoc'));assert.ok(exe);
  const pandocRoot=join(bundle,'extras','pandoc');mkdirSync(pandocRoot,{recursive:true});
  cpSync(join(unpack,dirname(exe)),pandocRoot,{recursive:true});chmodSync(join(pandocRoot,basename(exe)),0o755);
  const copyright=files.find(n=>/^(COPYRIGHT|COPYING|LICENSE)(\.|$)/i.test(basename(n)));
  if(copyright)copyFileSync(join(unpack,copyright),join(pandocRoot,'COPYRIGHT'));
  if(platform==='darwin'){
    const media=join(bundle,'ffmpeg');
    for(const name of ['ffmpeg','ffprobe']){
      const asset=lock.macMedia.assets.find(a=>a.name===name+'-darwin-'+arch+'.gz');assert.ok(asset);
      const raw=gunzipSync(readFileSync(download(asset,cache)));
      const direct=lock.macMedia.assets.find(a=>a.name===name+'-darwin-'+arch);assert.equal(hash(raw),direct.sha256);
      writeFileSync(join(media,name),raw);chmodSync(join(media,name),0o755);
      const linked=run('/usr/bin/otool',['-L',join(media,name)]).split('\n').slice(1).map(x=>x.trim().split(' (')[0]).filter(Boolean);
      assert.ok(linked.every(x=>x.startsWith('/usr/lib/')||x.startsWith('/System/Library/')),'完整FFmpeg必须可独立迁移');
      run('/usr/bin/codesign',['--force','--sign','-',join(media,name)]);
    }
    for(const name of ['LICENSE','README']){
      const asset=lock.macMedia.assets.find(a=>a.name==='darwin-'+arch+'.'+name);copyFileSync(download(asset,cache),join(media,'static-'+name));
    }
  }
  // One browser shared by Playwright and Remotion; never duplicate Chromium.
  const browserCache=join(cache,'playwright');mkdirSync(browserCache,{recursive:true});
  const env={...process.env,PLAYWRIGHT_BROWSERS_PATH:browserCache,PYTHONDONTWRITEBYTECODE:'1'};
  run(python,['-B','-m','playwright','install','chromium','--only-shell'],env);
  const shell=readdirSync(browserCache).find(n=>n.startsWith('chromium_headless_shell-'));assert.ok(shell);
  const folder=join(browserCache,shell),list=readdirSync(folder,{recursive:true});
  const browser=list.find(n=>basename(n)===(platform==='win32'?'chrome-headless-shell.exe':'chrome-headless-shell'));assert.ok(browser);
  const target=join(bundle,'chromium',shell);mkdirSync(target,{recursive:true});cpSync(folder,target,{recursive:true});
  const manifest=JSON.parse(readFileSync(join(bundle,'manifest.json'),'utf8'));
  const old=manifest.browser;
  manifest.browser=['chromium',shell,browser.split('\\').join('/')].join('/');
  manifest.browser_sha256=hash(readFileSync(join(bundle,manifest.browser)));
  manifest.extraTools={pandoc:lock.pandoc.version,media:platform==='darwin'?lock.macMedia.version:'existing-full-windows',playwrightBrowser:shell};
  writeFileSync(join(bundle,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  // Remove only the previous generated flat browser files, after the new one is complete.
  if(old==='chromium/'+basename(old)){
    for(const entry of readdirSync(join(bundle,'chromium'),{withFileTypes:true}))if(entry.name!==shell){
      const path=resolve(bundle,'chromium',entry.name);assert.ok(path.startsWith(resolve(bundle,'chromium')+sep));
      rmSync(path,{recursive:true,force:true});
    }
  }
  const tokenCache=join(bundle,'python-data','tiktoken');mkdirSync(tokenCache,{recursive:true});
  run(python,['-B','-c',"import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')"],{...process.env,TIKTOKEN_CACHE_DIR:tokenCache});
  writeFileSync(join(bundle,'extras','provenance.json'),JSON.stringify({platform,arch,pandoc,media:platform==='darwin'?lock.macMedia:undefined,browser:shell},null,2));
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const bundle=join(app,'desktop-tools-bundle');
  prepareNativeExtras(join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python'),bundle);
}
