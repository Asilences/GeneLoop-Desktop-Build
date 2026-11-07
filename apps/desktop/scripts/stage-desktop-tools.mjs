import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync,lstatSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { dirname, isAbsolute, join, relative, basename, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {stageWorkflowSource} from './stage-workflow-source.mjs';
import {stageOcrData} from './stage-ocr-data.mjs';
import {stageCjkFont} from './stage-cjk-font.mjs';
import {stageOfficeKit} from './stage-office-kit.mjs';
import {stagePptProfile} from './stage-ppt-profile.mjs';

const app = fileURLToPath(new URL('../', import.meta.url));
const repo = fileURLToPath(new URL('../../../', import.meta.url));
const destination = resolve(process.env.GENELOOP_DESKTOP_TOOLS_STAGE??join(app, 'desktop-tools-bundle'));
const marker = join(destination, '.geneloop-tools');
const source = variable => {
  if (!process.env[variable]) throw Error('构建工具目录缺少 ' + variable);
  return realpathSync(process.env[variable]);
};
const python = source('GENELOOP_DESKTOP_PYTHON_ROOT');
const skill = source('GENELOOP_PPT_MASTER_ROOT');
const officeEngine=process.env.GENELOOP_DESKTOP_OFFICE_ENGINE??'kit';
if(!['kit','libreoffice'].includes(officeEngine))throw Error('未知 Office 引擎');
const office = officeEngine==='libreoffice'?source('GENELOOP_DESKTOP_LIBREOFFICE_ROOT'):null;
const media = source('GENELOOP_FFMPEG_DIRECTORY');
const browser = source('GENELOOP_DESKTOP_BROWSER');
const browserRoot=process.env.GENELOOP_DESKTOP_BROWSER_ROOT?source('GENELOOP_DESKTOP_BROWSER_ROOT'):dirname(browser);
const browserRelative=relative(browserRoot,browser);
if(browserRelative.startsWith('..')||isAbsolute(browserRelative))throw Error('浏览器必须位于指定的构建输入目录内。');
if (!['win32','darwin'].includes(process.platform)) throw Error('请在 Windows 或 macOS 机器原生准备工具。');
if (existsSync(destination) && (!existsSync(marker) ||
    realpathSync(destination).toLowerCase() !== destination.toLowerCase())) throw Error('无法覆盖未识别的工具目录。');
if (existsSync(destination)) {
  if ([python, skill, office, media, browserRoot].filter(Boolean).some(dir => {
    const path = relative(destination, dir);
    return path === '' || (!path.startsWith('..') && !isAbsolute(path));
  })) throw Error('工具输入必须位于生成目录之外。');
  rmSync(destination, { recursive: true });
}
mkdirSync(destination, { recursive: true });
writeFileSync(marker, 'staging');
const pythonExe=join(python,process.platform==='win32'?'python.exe':'bin/python3');
const profiled=spawnSync(pythonExe,['-B',join(app,'scripts/python-tool-profile.py'),python,join(app,'native-tools-requirements.txt')],{encoding:'utf8',windowsHide:true,maxBuffer:8*1024**2});
if(profiled.status!==0)throw Error('Python 工具依赖未完整准备：'+profiled.stderr);
const pythonProfile=JSON.parse(profiled.stdout),excludedPython=new Set([...pythonProfile.excluded_files,...pythonProfile.excluded_directories]);
cpSync(python, join(destination, 'python'), { recursive: true, verbatimSymlinks:true,filter:path=>{
  const parts=relative(python,path).split(/[\\/]/);
  // Retain the numerical, PDF/OCR and document libraries. Exclude only stale
  // voice dependencies, generated caches/test data and Playwright's duplicate
  // Node executable; the installed desktop supplies its trusted Node host.
  if(parts.some(part=>['edge_tts','__pycache__','tests','test'].includes(part)||part.startsWith('edge_tts-')))return false;
  if(excludedPython.has(parts.join('/')))return false;
  if(/\.py[co]$/.test(parts.at(-1)))return false;
  return !['playwright/driver/node','playwright/driver/node.exe'].includes(parts.slice(-3).join('/'));
} });
const skillLock=JSON.parse(readFileSync(join(repo,'scenarios/ppt_master/skill-lock.json'),'utf8'));
const skillDirectories=new Set();for(const file of Object.keys(skillLock.files)){const parts=file.split('/');parts.pop();while(parts.length){skillDirectories.add(parts.join('/'));parts.pop();}}
cpSync(skill, join(destination, 'ppt-master'), { recursive: true,filter:path=>{
  const name=relative(skill,path).split('\\').join('/');
  if(!name)return true;
  if(lstatSync(path).isSymbolicLink())throw Error('PPT Master不能包含链接：'+name);
  const entry=Object.hasOwn(skillLock.files,name);
  if(entry){if(createHash('sha256').update(readFileSync(path)).digest('hex')!==skillLock.files[name])throw Error('PPT Master文件版本变化：'+name);return true;}
  // Copy only the published roster, including its non-secret .env.example.
  // Ignore private additions and generated caches; retain required directories.
  return skillDirectories.has(name);
}});
stagePptProfile(app,destination);
if(officeEngine==='kit')stageOfficeKit(destination);
else cpSync(office, join(destination, 'libreoffice'), { recursive: true, verbatimSymlinks:true, filter: path => {
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
cpSync(browserRoot,join(destination,'chromium'),{recursive:true,verbatimSymlinks:true});
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
  writeFileSync(pth, 'python312.zip\n.\nsite\nsite/win32\nsite/win32/lib\nsite/pythonwin\nsite/pywin32_system32\n../source\n../ppt-master/scripts\n../ppt-master/scripts/source_to_md\nimport site\n');
} else {
  // python-build-standalone is relocatable; preserve its library layout and
  // expose a real file in place of python3's internal symlink.
  cpSync(realpathSync(join(python,'bin/python3')),join(destination,'python/bin/geneloop-python'));
}
writeFileSync(join(destination,'manifest.json'),JSON.stringify({schema_version:1,
  platform:process.platform,arch:process.arch,browser:'chromium/'+browserRelative.split('\\').join('/'),
  profile:{scope:'six-scenes-ppt-authoring',removedVoiceDistributions:pythonProfile.removed_voice_distributions,
    sharedPlaywrightNode:'trusted-desktop-host',excludedBuildData:['__pycache__','*.pyc','tests','test']},
  office:officeEngine==='kit'?{engine:'libreoffice-kit',version:'0.2.3',native:true}:{engine:'libreoffice'},
  browser_sha256:createHash('sha256').update(readFileSync(browser)).digest('hex'),
  ppt_master:JSON.parse(readFileSync(join(repo,'scenarios/ppt_master/skill-lock.json'),'utf8')).package_sha256,
},null,2)+'\n');
writeFileSync(marker, 'ready');
console.log('已准备离线本机工具：'+process.platform+'/'+process.arch);
