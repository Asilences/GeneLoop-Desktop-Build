// Preserve every tool file. Distribution changes only; no tool pruning here.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createReadStream,existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,readlinkSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {join,resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {prepareInstallerCodec} from './prepare-installer-codec.mjs';
const app=fileURLToPath(new URL('../',import.meta.url));
const source=resolve(process.argv[2]??join(app,'desktop-tools-bundle'));
const output=resolve(process.argv[3]??join(app,'.local','tool-pack-build'));
assert.ok(existsSync(join(source,'manifest.json'))&&existsSync(join(source,'.geneloop-tools')),'需要已验证的完整工具目录');
mkdirSync(output,{recursive:true});
const original=JSON.parse(readFileSync(join(source,'manifest.json'),'utf8'));
assert.equal(original.platform,process.platform);assert.equal(original.arch,process.arch);
const codec=await prepareInstallerCodec(app,join(output,'installer-tools'));
const definitions=[
  ['workspace','场景与材料工具',true,['source','ppt-master','ocr','fonts','python-data','manifest.json','.geneloop-tools']],
  ['python','数据与文档运行库',true,['python']],['office','Office 与演示文稿',true,['libreoffice']],
  ['browser','页面预览',true,['chromium']],['media','音视频工具',true,['ffmpeg']],
  ['converters','材料格式转换',true,['extras']],['speech','离线语音与字幕对齐',false,['speech']],
];
const sha=async path=>{const h=createHash('sha256');for await(const chunk of createReadStream(path))h.update(chunk);return h.digest('hex');};
const entries=[];
async function walk(directory){
  for(const item of readdirSync(directory,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
    const path=join(directory,item.name),name=relative(source,path).split('\\').join('/'),s=lstatSync(path);
    if(s.isSymbolicLink()){
      const target=readlinkSync(path),dest=resolve(directory,target),rel=relative(source,dest);
      assert.ok(!isAbsolute(target)&&rel!=='..'&&!rel.startsWith('..\\')&&!rel.startsWith('../'),'工具链接必须位于发行目录内');
      entries.push({path:name,kind:'symlink',target,bytes:0,sha256:createHash('sha256').update(target).digest('hex')});
    }else if(s.isDirectory())await walk(path);
    else {assert.ok(s.isFile());entries.push({path:name,bytes:s.size,sha256:await sha(path),mode:s.mode&0o777});}
  }
}
await walk(source);
const selected=new Set(),packages=[];
for(const [id,label,required,prefixes]of definitions){
  const files=entries.filter(row=>prefixes.some(p=>row.path===p||row.path.startsWith(p+'/')));
  if(!files.length)continue;
  for(const row of files){assert.ok(!selected.has(row.path));selected.add(row.path);}
  const content=createHash('sha256').update(JSON.stringify(files)).digest('hex');
  const filename=id+'-'+content.slice(0,16)+'.7z',archive=join(output,filename),list=join(output,id+'.list');
  // List-file input is literal, UTF-8 and entirely controlled by the build.
  assert.ok(files.every(row=>!/[\r\n\0]/.test(row.path)));
  writeFileSync(list,files.map(row=>row.path).join('\n')+'\n');
  const receipt=archive+'.complete.json',pending=archive+'.pending';
  let reusable=false;
  if(existsSync(archive)&&existsSync(receipt)){
    const saved=JSON.parse(readFileSync(receipt,'utf8'));
    reusable=saved.content===content&&saved.sha256===await sha(archive);
  }
  // Even a cancelled compressor can leave a structurally valid partial archive.
  // Reuse therefore requires our successful-build receipt, not just a CRC test.
  if(existsSync(archive)&&!reusable)rmSync(archive);
  if(!reusable){
    if(existsSync(pending))rmSync(pending);
    const result=spawnSync(codec.path,['a','-t7z',pending,'@'+list,'-spd','-scsUTF-8','-sccUTF-8','-mx=7','-m0=LZMA2:d=64m','-ms=256m','-mmt=4','-mqs=on','-snl','-bd','-bb0'],{cwd:source,stdio:'inherit',windowsHide:true});
    assert.equal(result.status,0,'工具包构建失败：'+id);
    renameSync(pending,archive);
  }
  const archiveSha=await sha(archive);
  writeFileSync(receipt,JSON.stringify({content,sha256:archiveSha}));
  packages.push({id,label,required,filename,sha256:archiveSha,bytes:lstatSync(archive).size,unpackedBytes:files.reduce((n,f)=>n+f.bytes,0),files});
  console.log(JSON.stringify({id,files:files.length,archiveBytes:lstatSync(archive).size}));
}
assert.equal(selected.size,entries.length,'存在未分配到工具包的文件，停止生成小安装包');
const toolsetId=createHash('sha256').update(JSON.stringify(packages.map(p=>[p.id,p.sha256]))).digest('hex');
const baseUrl=process.env.GENELOOP_TOOL_PACK_BASE_URL??null;
if(baseUrl){const url=new URL(baseUrl);assert.equal(url.protocol,'https:');assert.ok(!url.username&&!url.password);}
const catalog={schema:1,toolsetId,platform:process.platform,arch:process.arch,baseUrl,codec:{filename:codec.filename,sha256:codec.sha256,version:codec.version},packages};
writeFileSync(join(output,'tool-packs.json'),JSON.stringify(catalog)+'\n');
writeFileSync(join(output,'preservation.json'),JSON.stringify({filesBefore:entries.length,filesInPacks:selected.size,allToolsRetained:true,unpackedBytes:entries.reduce((n,f)=>n+f.bytes,0),downloadBytes:packages.reduce((n,p)=>n+p.bytes,0),toolsetId},null,2));
