import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { dirname, isAbsolute, join, relative, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import {stageWorkflowSource} from './stage-workflow-source.mjs';
import {stageOcrData} from './stage-ocr-data.mjs';
import {stageCjkFont} from './stage-cjk-font.mjs';

const app = fileURLToPath(new URL('../', import.meta.url));
const repo = fileURLToPath(new URL('../../../', import.meta.url));
const destination = join(app, 'desktop-tools-bundle');
const marker = join(destination, '.geneloop-tools');
const source = variable => {
  if (!process.env[variable]) throw Error('构建工具目录缺少 ' + variable);
  return realpathSync(process.env[variable]);
};
const python = source('GENELOOP_DESKTOP_PYTHON_ROOT');
const skill = source('GENELOOP_PPT_MASTER_ROOT');
const office = source('GENELOOP_DESKTOP_LIBREOFFICE_ROOT');
const media = source('GENELOOP_FFMPEG_DIRECTORY');
const browser = source('GENELOOP_DESKTOP_BROWSER');
if (!['win32','darwin'].includes(process.platform)) throw Error('请在 Windows 或 macOS 机器原生准备工具。');
if (existsSync(destination) && (!existsSync(marker) ||
    realpathSync(destination).toLowerCase() !== destination.toLowerCase())) throw Error('无法覆盖未识别的工具目录。');
if (existsSync(destination)) {
  if ([python, skill, office, media, dirname(browser)].some(dir => {
    const path = relative(destination, dir);
    return path === '' || (!path.startsWith('..') && !isAbsolute(path));
  })) throw Error('工具输入必须位于生成目录之外。');
  rmSync(destination, { recursive: true });
}
mkdirSync(destination, { recursive: true });
writeFileSync(marker, 'staging');
cpSync(python, join(destination, 'python'), { recursive: true, verbatimSymlinks:true });
cpSync(skill, join(destination, 'ppt-master'), { recursive: true,filter:path=>{
  const name=basename(path);return name!=='.env'&&!name.startsWith('.env.')&&name!=='.git'&&name!=='.local';
}});
cpSync(office, join(destination, 'libreoffice'), { recursive: true, verbatimSymlinks:true, filter: path => {
  const [top, folder, item] = relative(office, path).toLowerCase().split(/[\\/]/);
  if (top.endsWith('.msi')) return false;
  if (top === 'help') return !folder || ['idxcaption.xsl', 'idxcontent.xsl'].includes(folder);
  if (top === 'share' && folder === 'extensions' && item?.startsWith('dict-')) return false;
  if (top === 'program' && folder === 'resource' && item) {
    return ['common', 'en_us', 'en_gb', 'zh_cn', 'zh_tw'].includes(item);
  }
  return true;
}});
mkdirSync(join(destination, 'ffmpeg'), { recursive: true });
if (process.platform === 'darwin') {
  // The pinned Remotion native package supplies relocatable FFmpeg binaries
  // and their adjacent dylibs. Do not copy Homebrew executables with external
  // /opt/homebrew library dependencies into a distributable application.
  cpSync(media,join(destination,'ffmpeg'),{recursive:true,verbatimSymlinks:true});
}
for (const base of ['ffmpeg', 'ffprobe']) {
  const name = base + (process.platform === 'win32' ? '.exe' : '');
  // Dereference a package-manager link into a real app-owned executable.
  cpSync(realpathSync(join(media,name)), join(destination, 'ffmpeg', name));
}
if (process.platform === 'darwin') {
  // The native package's bare dylib names depend on the working directory.
  // Relocate only app-owned library references, then restore ad-hoc signatures
  // required by Apple Silicon. System library references remain untouched.
  const directory=join(destination,'ffmpeg');
  const run=(bin,args)=>{
    const result=spawnSync(bin,args,{encoding:'utf8'});
    if(result.status!==0)throw Error('Mac 媒体工具重定位失败：'+bin+' '+result.stderr);
    return result.stdout;
  };
  for(const name of readdirSync(directory).filter(name=>['ffmpeg','ffprobe','remotion'].includes(name)||name.endsWith('.dylib'))) {
    const file=join(directory,name);
    const libraries=run('/usr/bin/otool',['-L',file]).split('\n').slice(1)
      .map(line=>line.trim().split(' (')[0]).filter(Boolean);
    let changed=false;
    for(const library of libraries) {
      if(library.startsWith('/usr/lib/')||library.startsWith('/System/Library/')||library.startsWith('@loader_path/'))continue;
      const sibling=basename(library);
      if(!existsSync(join(directory,sibling)))throw Error('Mac 媒体工具缺少相邻动态库：'+sibling);
      run('/usr/bin/install_name_tool',['-change',library,'@loader_path/'+sibling,file]);changed=true;
    }
    if(changed)run('/usr/bin/codesign',['--force','--sign','-',file]);
  }
}
cpSync(dirname(browser),join(destination,'chromium'),{recursive:true,verbatimSymlinks:true});
for (const name of ['LICENSE', 'LICENSE.txt', 'README.txt']) {
  const path = join(media, '..', name);
  if (existsSync(path)) cpSync(path, join(destination, 'ffmpeg', name));
}
for (const path of [
  'scenarios/ppt_master/package.py', 'scenarios/ppt_master/skill-lock.json',
  'scenarios/ppt_master/windows_delivery.py', 'scenarios/ppt_master/windows_source.py',
  'scenarios/research_ppt/documents.py', 'scenarios/research_ppt/validation.py', 'scenarios/research_ppt/web_scope.py',
  'src/adapters/geneloop_upload_limits.py', 'src/adapters/geneloop_upload_limits.json',
  'src/adapters/harless_attachment_text.py', 'src/adapters/ppt_delivery_runner.py',
  'src/adapters/desktop_scene_tools.py', 'src/adapters/paper_static_checks.py', 'src/adapters/session_files.py',
  'scenarios/data_analysis/evidence.py', 'scenarios/data_analysis/table_inputs.py',
  'src/adapters/ppt_design_preflight.py', 'src/adapters/ppt_annotation_repair.py',
]) {
  const target = join(destination, 'source', path);
  mkdirSync(dirname(target), { recursive: true });
  cpSync(join(repo, path), target);
}
stageWorkflowSource(repo,join(destination,'source'));
stageOcrData(join(app,'.local/ocr-data'),join(destination,'ocr'));
stageCjkFont(app,destination);
if (process.platform === 'win32') {
  const pth = join(destination, 'python', 'python312._pth');
  if (!readFileSync(pth, 'utf8').includes('python312.zip')) throw Error('需要 Windows Python 3.12 嵌入式分发。');
  writeFileSync(pth, 'python312.zip\n.\nsite\nsite/win32\nsite/win32/lib\nsite/pythonwin\nsite/pywin32_system32\n../source\n../ppt-master/scripts\n../ppt-master/scripts/source_to_md\n');
} else {
  // python-build-standalone is relocatable; preserve its library layout and
  // expose a real file in place of python3's internal symlink.
  cpSync(realpathSync(join(python,'bin/python3')),join(destination,'python/bin/geneloop-python'));
}
writeFileSync(join(destination,'manifest.json'),JSON.stringify({schema_version:1,
  platform:process.platform,arch:process.arch,browser:'chromium/'+basename(browser),
  browser_sha256:createHash('sha256').update(readFileSync(browser)).digest('hex'),
  ppt_master:JSON.parse(readFileSync(join(repo,'scenarios/ppt_master/skill-lock.json'),'utf8')).package_sha256,
},null,2)+'\n');
writeFileSync(marker, 'ready');
console.log('已准备离线本机工具：'+process.platform+'/'+process.arch);
