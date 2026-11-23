// Build-time only: install the existing pinned privacy implementation, never fetch at app startup.
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {chmodSync,mkdirSync,readFileSync,writeFileSync,existsSync,copyFileSync} from 'node:fs';
import {join,resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const app=fileURLToPath(new URL('../',import.meta.url)),repo=resolve(app,'../..');
function run(exe,args,cwd){const result=spawnSync(exe,args,{cwd,stdio:'inherit',windowsHide:true});if(result.error)throw result.error;if(result.status!==0)throw Error('本机脱敏工具构建失败：'+basename(exe));}
const hash=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
export function stageRsiPrivacy(bundle){
 const lock=JSON.parse(readFileSync(join(repo,'config/rsi-privacy-tools.json'),'utf8'));
 const os=process.platform==='win32'?'Windows':process.platform==='darwin'?'Darwin':'Linux';
 const asset=lock.gitleaks.platforms[os+'-'+process.arch];
 if(!asset)throw Error('当前平台的脱敏工具尚未登记，不能冒充可交付的本机脱敏组件。');
 const folder=join(bundle,'privacy');mkdirSync(folder,{recursive:true});
 const scanner=join(folder,asset.binary);
 const cache=join(app,'.local','rsi-privacy');mkdirSync(cache,{recursive:true});
 const check=spawnSync('git',['config','--get-urlmatch','http.proxy','https://github.com'],{encoding:'utf8',windowsHide:true});
 const proxy=check.status===0?check.stdout.trim():undefined;
 const download=(url,path)=>run(process.platform==='win32'?'curl.exe':'curl',['--fail','--location','--retry','2',...(proxy?['--proxy',proxy]:[]),'--output',path,url]);
 if(!existsSync(scanner)||hash(scanner)!==asset.binary_sha256){
  const archive=join(cache,asset.asset);
  if(!existsSync(archive)||hash(archive)!==asset.archive_sha256)download('https://github.com/gitleaks/gitleaks/releases/download/v'+lock.gitleaks.version+'/gitleaks_'+lock.gitleaks.version+'_'+asset.asset,archive);
  if(hash(archive)!==asset.archive_sha256)throw Error('隐私扫描器下载摘要不匹配。');
  const expanded=join(cache,os+'-'+process.arch);mkdirSync(expanded,{recursive:true});
  run('tar',['-xf',archive,'-C',expanded,asset.binary]);copyFileSync(join(expanded,asset.binary),scanner);
 }
 if(hash(scanner)!==asset.binary_sha256)throw Error('隐私扫描器摘要不匹配。');
 if (process.platform !== 'win32') chmodSync(scanner,0o755);
 const python=join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python');
 const site=join(folder,'site');
 const marker=join(folder,'versions.json'),wanted=JSON.stringify(lock.packages);
 if(!existsSync(marker)||readFileSync(marker,'utf8')!==wanted){
  const requirements=readFileSync(join(repo,'requirements-rsi-privacy.txt'),'utf8'),lines=[];
  for(const line of requirements.trim().split(/\r?\n/)){
   if(!line.includes(' @ ')){lines.push(line);continue;}
   const url=line.split(' @ ')[1],clean=url.split('#')[0],expected=url.split('#sha256=')[1],path=join(cache,clean.split('/').at(-1));
   if(!existsSync(path)||hash(path)!==expected)download(clean,path);
   if(hash(path)!==expected)throw Error('隐私语言模型摘要不匹配。');lines.push(path);
  }
  const local=join(cache,'requirements-local.txt');writeFileSync(local,lines.join('\n')+'\n');
  run(process.env.SSS_PYTHON||(process.platform==='win32'?'python':'python3'),['-m','pip','--python',python,'install','--disable-pip-version-check','--no-compile',
    '--only-binary=:all:','--target',site,'--upgrade',...(proxy?['--proxy',proxy]:[]),'-r',local]);
  writeFileSync(marker,wanted);
 }
 // Verify the installed versions, not only the marker.
 run(python,['-B','-c',
   'import sys;sys.path.insert(0,sys.argv[1]);from src.adapters.rsi_privacy_tools import verify_nlp_versions,verified_gitleaks;verify_nlp_versions();verified_gitleaks(sys.argv[2])',
   site,scanner],join(bundle,'source'));
 run(scanner,['version']);
 return folder;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))stageRsiPrivacy(resolve(process.argv[2]||join(app,'desktop-tools-bundle')));
