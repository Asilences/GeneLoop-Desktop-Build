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
}
module.exports=config;
