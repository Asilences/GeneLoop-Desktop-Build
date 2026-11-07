// Explicitly publish tool archives only. Installers stay out of Releases.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createReadStream,readFileSync,statSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
const repo='Asilences/GeneLoop-Desktop-Build';
assert.equal(process.env.GITHUB_REPOSITORY,repo);
assert.equal(process.env.RUNNER_OS,'macOS');
const root=resolve(process.argv[2]||'.local/tool-pack-build');
const catalog=JSON.parse(readFileSync(join(root,'tool-packs.json'),'utf8'));
assert.equal(catalog.platform,'darwin');assert.equal(catalog.arch,process.arch);
assert.ok([JSON.stringify(['workspace','python','office','browser','media','converters']),JSON.stringify(['workspace','python','office','browser','media','converters','speech'])].includes(JSON.stringify(catalog.packages.map(p=>p.id))));
const base=new URL(catalog.baseUrl);
assert.equal(base.origin,'https://github.com');assert.ok(!base.username&&!base.password);
const tag=base.pathname.match(/^\/Asilences\/GeneLoop-Desktop-Build\/releases\/download\/(desktop-tools-darwin-(?:arm64|x64)-[a-zA-Z0-9.-]+)\/$/)?.[1];
assert.ok(tag,'需要本轮独立、已固定的工具下载路径');
function gh(args,{input,optional=false}={}){
  const result=spawnSync('gh',args,{encoding:'utf8',input,stdio:['pipe','pipe','pipe']});
  if(result.status!==0){if(optional)return null;throw Error('GitHub 工具发布失败：'+args[0]);}
  return result.stdout;
}
assert.equal(JSON.parse(gh(['api','repos/'+repo])).private,false,'只使用公开构建仓库');
for(const p of catalog.packages){
  assert.match(p.filename,new RegExp('^'+p.id+'-[a-f0-9]{16}\\.7z$'));
  assert.equal(statSync(join(root,p.filename)).size,p.bytes);
  const h=createHash('sha256');for await(const b of createReadStream(join(root,p.filename)))h.update(b);
  assert.equal(h.digest('hex'),p.sha256);
}
const notes=['GeneLoop Desktop macOS '+process.arch+' 完整工具集','',
  '仅发布'+catalog.packages.length+'个工具分包；不含 DMG、应用压缩包、凭据或私人资料。安装后由桌面应用统一下载，逐包及逐文件校验。',
  '工具集：`'+catalog.toolsetId+'`','',
  '| 工具包 | 字节 | SHA-256 |','|---|---:|---|',
  ...catalog.packages.map(p=>'| '+p.filename+' | '+p.bytes+' | `'+p.sha256+'` |'),
  '', '上游许可和来源随包保留。'].join('\n');
const notesPath=join(root,'release-notes.md');writeFileSync(notesPath,notes);
const existing=gh(['api','repos/'+repo+'/releases/tags/'+tag],{optional:true});
if(!existing)gh(['release','create',tag,'--repo',repo,'--draft','--prerelease','--target',process.env.GITHUB_SHA,'--title','GeneLoop Desktop · macOS '+process.arch+' 工具集','--notes-file',notesPath]);
let release=JSON.parse(gh(['api','repos/'+repo+'/releases/tags/'+tag]));
const allowed=new Map(catalog.packages.map(p=>[p.filename,p]));
assert.ok(release.assets.every(a=>allowed.has(a.name)),'Release 存在未知资产');
for(const p of catalog.packages){
  const asset=release.assets.find(a=>a.name===p.filename);
  if(asset){assert.equal(asset.digest,'sha256:'+p.sha256);assert.equal(asset.size,p.bytes);continue;}
  assert.equal(release.draft,true,'不修改已公开版本');
  gh(['release','upload',tag,join(root,p.filename),'--repo',repo]);
  console.log(JSON.stringify({uploaded:p.id,bytes:p.bytes}));
}
release=JSON.parse(gh(['api','repos/'+repo+'/releases/tags/'+tag]));
assert.equal(release.assets.length,catalog.packages.length);
for(const a of release.assets){const p=allowed.get(a.name);assert.ok(p);assert.equal(a.state,'uploaded');assert.equal(a.size,p.bytes);assert.equal(a.digest,'sha256:'+p.sha256);}
if(release.draft)gh(['api','--method','PATCH','repos/'+repo+'/releases/'+release.id,'--input','-'],{input:JSON.stringify({draft:false,prerelease:true,make_latest:'false'})});
const receipt={schema:1,repo,releaseId:release.id,tag,baseUrl:catalog.baseUrl,toolsetId:catalog.toolsetId,platform:catalog.platform,arch:catalog.arch,sourceCommit:process.env.GITHUB_SHA,installerUploaded:false,assets:release.assets.map(a=>({name:a.name,bytes:a.size,digest:a.digest,url:a.browser_download_url}))};
writeFileSync(join(root,'publication-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({published:true,tag,toolsetId:catalog.toolsetId}));
