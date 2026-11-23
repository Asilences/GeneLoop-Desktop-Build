import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,copyFileSync,chmodSync} from 'node:fs';
import {join} from 'node:path';
import {createRequire} from 'node:module';
const hash=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
export async function prepareInstallerCodec(app,destination){
  const lock=JSON.parse(readFileSync(join(app,'installer-codec-lock.json'),'utf8'));
  const platform=process.platform==='win32'?'windows':'macos',entry=lock[platform];
  assert.ok(entry,'当前平台的工具包解码器尚未配置');
  const cache=join(app,'.local','installer-codec-'+lock.version+'-'+process.platform);mkdirSync(cache,{recursive:true});
  const archive=join(cache,platform==='windows'?'codec.7z':'codec.tar.xz');
  const run=(exe,args)=>{const r=spawnSync(exe,args,{stdio:'inherit',windowsHide:true});assert.equal(r.status,0,'构建解码器失败');};
  if(!existsSync(archive)){
    const proxy=spawnSync('git',['config','--get-urlmatch','http.proxy','https://github.com'],{encoding:'utf8',windowsHide:true});
    run(process.platform==='win32'?'curl.exe':'curl',['--fail','--location','--retry','2',...(proxy.status===0?['--proxy',proxy.stdout.trim()]:[]),'--output',archive,entry.url]);
  }
  assert.equal(hash(archive),entry.sha256,'解码器下载校验失败');
  if(!existsSync(join(cache,entry.executable))){
    if(platform==='windows'){
      const require=createRequire(join(app,'package.json')),bootstrap=await require('app-builder-lib/out/toolsets/7zip.js').getPath7za();
      run(bootstrap,['x',archive,'-o'+cache,'-y','-bd']);
    }else run('/usr/bin/tar',['-xf',archive,'-C',cache]);
  }
  const executable=join(cache,entry.executable);if(entry.executableSha256)assert.equal(hash(executable),entry.executableSha256);
  mkdirSync(destination,{recursive:true});const name=platform==='windows'?'7za.exe':'7zz';
  copyFileSync(executable,join(destination,name));if(platform==='macos')chmodSync(join(destination,name),0o755);
  copyFileSync(join(cache,entry.license??'License.txt'),join(destination,'7zip-LICENSE.txt'));
  return {path:join(destination,name),filename:name,sha256:hash(executable),version:lock.version};
}
