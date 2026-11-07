const {readFileSync,existsSync}=require('node:fs');
const {join,resolve}=require('node:path');
const config=JSON.parse(JSON.stringify(require('./package.json').build));
if(process.env.GENELOOP_DESKTOP_TOOL_PACKS==='1'){
  const root=resolve(process.env.GENELOOP_TOOL_PACK_OUTPUT||join(__dirname,'.local/tool-pack-build'));
  if(!existsSync(join(root,'preservation.json')))throw Error('先完成工具包构建与文件保留核对');
  const proof=JSON.parse(readFileSync(join(root,'preservation.json'),'utf8'));
  if(!proof.allToolsRetained||proof.filesBefore!==proof.filesInPacks)throw Error('工具文件保留核对失败');
  const catalog=JSON.parse(readFileSync(join(root,'tool-packs.json'),'utf8'));
  if(catalog.toolsetId!==proof.toolsetId||catalog.platform!==process.platform||catalog.arch!==process.arch||
    catalog.packages.reduce((n,p)=>n+p.files.length,0)!==proof.filesBefore||
    !existsSync(join(root,'installer-tools',catalog.codec.filename)))throw Error('工具目录、平台或解码器不匹配');
  const published=require('./tool-releases.json').releases[process.platform+'-'+process.arch];
  if(published?.toolsetId===catalog.toolsetId&&!catalog.baseUrl)throw Error('该工具版本已有下载源，请重新生成工具目录');
  config.extraResources=[{from:join(root,'tool-packs.json'),to:'tool-packs.json'},{from:join(root,'installer-tools'),to:'installer-tools'}];
}else{
  const root=resolve(process.env.GENELOOP_DESKTOP_TOOLS_STAGE||join(__dirname,'desktop-tools-bundle'));
  const manifest=existsSync(join(root,'manifest.json'))?JSON.parse(readFileSync(join(root,'manifest.json'),'utf8')):null;
  if(manifest?.profile?.scope!=='six-scenes-ppt-authoring'||existsSync(join(root,'speech'))||
    !existsSync(join(root,'skills/geneloop-ppt/SKILL.md')))
    throw Error('完整离线包的工具目录已过期，请按当前六场景范围重新准备工具；不能复用旧语音目录。');
  config.extraResources=config.extraResources.map(row=>row.to==='geneloop-tools'?{...row,from:root}:row);
}
module.exports=config;
