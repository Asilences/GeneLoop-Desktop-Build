import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdirSync,existsSync,readFileSync,cpSync,writeFileSync,chmodSync} from 'node:fs';
import {join} from 'node:path';
const hashes={'NotoSansCJKsc-Regular.otf':'2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b',
  'OFL.txt':'6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'};
export function stageCjkFont(app,destination) {
  if(process.platform!=='darwin')return;
  const cache=join(app,'.local','cjk-font'),out=join(destination,'fonts');mkdirSync(cache,{recursive:true});mkdirSync(out,{recursive:true});
  const run=(exe,args)=>{const r=spawnSync(exe,args,{stdio:'inherit'});if(r.status!==0)throw Error('Native font build failed');};
  for(const [name,hash]of Object.entries(hashes)) {
    const file=join(cache,name),remote=name==='OFL.txt'?'LICENSE':'Sans/OTF/SimplifiedChinese/'+name;
    if(!existsSync(file))run('curl',['--fail','--location','--retry','2','--output',file,'https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/'+remote]);
    if(createHash('sha256').update(readFileSync(file)).digest('hex')!==hash)throw Error('CJK font version differs');
    cpSync(file,join(out,name));
  }
  run('clang',[join(app,'native/MacFonts.c'),'-O2','-framework','CoreFoundation','-framework','CoreText','-o',join(out,'register-font')]);
  chmodSync(join(out,'register-font'),0o755);run('codesign',['--force','--sign','-',join(out,'register-font')]);
  writeFileSync(join(out,'manifest.json'),JSON.stringify({source:'notofonts/noto-cjk',version:'Sans2.004',scope:'session',files:hashes},null,2)+'\n');
}
