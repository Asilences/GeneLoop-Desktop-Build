// Build-only acquisition. Runtime tasks never download dependencies.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureBrowser } from '@remotion/renderer';
import {installNativePythonDeps} from './native-python-deps.mjs';
import {prepareNativeExtras} from './prepare-native-extras.mjs';

assert.equal(process.platform,'darwin','此准备步骤必须在真实 macOS 上执行。');
const app = fileURLToPath(new URL('../',import.meta.url)),repo = resolve(app,'../..');
const root = join(app,'.local','macos-tools-'+process.arch);
mkdirSync(root,{recursive:true});
const targets = {
  arm64:{cpu:'aarch64',officeCpu:'aarch64',officeSha:'9f24fe83ab1ed5c95eb3df580119f32932f713e577feeac02bf619fb00749b55',sha:'353d5f1b4fd2715e7053f12f068435d5bbad16b91e057006b5d01e0925709a7e'},
  x64:{cpu:'x86_64',officeCpu:'x86-64',officeSha:'0af062779cc17f6f852918b2424c745f7dd2d20d51d7fb8a0925eb92ec0417a7',sha:'37c38fda76fec1fbf310adcbafb7f0d96af13b5511bf8ea954c3aa8eec185734'},
};
const target=targets[process.arch];assert.ok(target,'不支持此 Mac 架构。');
// The installable skill lives under skills/ppt-master, not the repository root.
// Preserve the existing byte lock instead of replacing it with a nearby tag.
const pptMaster={commit:'440557b8dc7c7257b69c04a0b014d5c50a78e6cb',
  archiveSha256:'080565fa68ab0cf4c8f75dbb3e0095a8ddd636298766bea394a9daf21c94de4d'};
function run(bin,args,options={}) {
  const result=spawnSync(bin,args,{cwd:repo,stdio:'inherit',...options});
  if(result.error) throw result.error;
  assert.equal(result.status,0,bin+' 构建步骤失败');
}
async function download(url,path,expected) {
  if(!existsSync(path)) run('curl',['--fail','--location','--retry','3','--output',path,url]);
  const hash=createHash('sha256').update(readFileSync(path)).digest('hex');
  assert.equal(hash,expected,'下载包校验和不匹配');
}
const pythonArchive=join(root,'python.tar.gz');
await download('https://github.com/astral-sh/python-build-standalone/releases/download/20261026/'+
  'cpython-3.12.16%2B20261026-'+target.cpu+'-apple-darwin-install_only_stripped.tar.gz',pythonArchive,target.sha);
if(!existsSync(join(root,'python')))run('python3',['-c',
  "import tarfile,sys;tarfile.open(sys.argv[1]).extractall(sys.argv[2],filter='data')",pythonArchive,root]);
const python=join(root,'python/bin/python3');
installNativePythonDeps(python,app);

const skill=join(root,'ppt-master');
if(!existsSync(skill)) {
  const archive=join(root,'ppt-master-'+pptMaster.commit+'.tar.gz');
  await download('https://codeload.github.com/hugohe3/ppt-master/tar.gz/'+pptMaster.commit,archive,pptMaster.archiveSha256);
  const extracted=join(root,'upstream');mkdirSync(extracted,{recursive:true});
  run(python,['-c',"import tarfile,sys;tarfile.open(sys.argv[1]).extractall(sys.argv[2],filter='data')",archive,extracted]);
  run(python,['scripts/install-ppt-master.py','--source',join(extracted,'ppt-master-'+pptMaster.commit,'skills/ppt-master'),'--destination',skill]);
}
const officeArchive=join(root,'libreoffice.dmg');
const officeUrl='https://download.documentfoundation.org/libreoffice/stable/26.8.2/mac/'+target.cpu+
  '/LibreOffice_26.8.2_MacOS_'+target.officeCpu+'.dmg';
const officeHash=target.officeSha;
await download(officeUrl,officeArchive,officeHash);
const mount=join(root,'office-mounted');mkdirSync(mount,{recursive:true});
run('hdiutil',['attach','-nobrowse','-readonly','-mountpoint',mount,officeArchive]);
try {
  const browser=await ensureBrowser({logLevel:'error'});assert.ok(browser.path);
  run(process.execPath,[join(app,'scripts/stage-desktop-tools.mjs')],{env:{...process.env,
    GENELOOP_DESKTOP_PYTHON_ROOT:join(root,'python'),GENELOOP_PPT_MASTER_ROOT:skill,
    GENELOOP_DESKTOP_LIBREOFFICE_ROOT:join(mount,'LibreOffice.app'),
    GENELOOP_FFMPEG_DIRECTORY:join(app,'node_modules/@remotion/compositor-darwin-'+process.arch),
    GENELOOP_DESKTOP_BROWSER:browser.path,
  }});
} finally {run('hdiutil',['detach',mount]);}
prepareNativeExtras(join(app,'desktop-tools-bundle/python/bin/geneloop-python'),join(app,'desktop-tools-bundle'));
run(join(app,'desktop-tools-bundle/python/bin/geneloop-python'),['-B',join(app,'scripts/prepare-native-speech.py'),join(app,'desktop-tools-bundle/speech')]);
writeFileSync(join(root,'build-inputs.json'),JSON.stringify({platform:process.platform,arch:process.arch,
  python:{version:'3.12.16+20261026',sha256:target.sha},libreoffice:{version:'26.8.2',sha256:officeHash},
  remotion:'4.0.539',pptMaster:{version:'6.6.0',...pptMaster}},null,2)+'\n');
