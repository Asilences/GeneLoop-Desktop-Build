import {createHash} from 'node:crypto';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,extname,join} from 'node:path';
import {inSceneScratch,publishArtifacts} from './local-artifacts.mjs';
import {pptPython} from './local-ppt-master.mjs';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
function relativePath(path) {
  if(typeof path!=='string'||!path||path.length>512||/[\\:\x00-\x1f]/.test(path)||
    path.split('/').some(part=>!part||part==='.'||part==='..'||/[. ]$/.test(part)||
      /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part))) throw Error('需要普通的工作区相对路径，目录使用 / 分隔。');
  return path;
}
function version(reader,path,expected,limit=16*1024*1024) {
  const bytes=reader.readBytes(relativePath(path),limit);
  if(typeof expected!=='string'||!/^[a-f0-9]{64}$/.test(expected)||sha(bytes)!==expected) throw Error('来源版本已变化，请重新读取并核对 SHA-256。');
  return bytes;
}
async function fixedTool(tools,scratch,signal,action,source,plan) {
  const input=join(scratch,'request.json');writeFileSync(input,JSON.stringify(plan),{flag:'wx'});
  const result=await pptPython(tools,scratch,signal,'src.adapters.desktop_scene_tools',[action,source,input]);
  if(result.error)throw Error('本机工具无法处理该资料：'+result.error);
  return result;
}

export async function analyzeLocalData(reader,tools,signal,{path,sha256,table=1,x='',y='',export_csv=false},writer,onReport,inspect=false) {
  if(!/\.(csv|tsv|xlsx|json|pdf|docx|txt|md)$/i.test(path)||!Number.isInteger(table)||table<1||
    typeof x!=='string'||typeof y!=='string'||typeof export_csv!=='boolean')throw Error('请选择支持的表格材料和正整数表号。');
  const bytes=version(reader,path,sha256);
  return inSceneScratch(async scratch=>{
    const input=join(scratch,'source'+extname(path).toLowerCase());writeFileSync(input,bytes,{flag:'wx'});
    const result=await fixedTool(tools,scratch,signal,inspect?'tables':'data',input,{table,x,y,export:export_csv});
    version(reader,path,sha256);signal.throwIfAborted();
    // Python 的短期凭证只在本次快照内有效，不向后续轮次暴露。
    for(const row of [result.summary,result.correlation])if(row)delete row.source_id;
    const csv=result.csv;delete result.csv;
    const receipt={path,sha256,...result};
    if(export_csv&&typeof csv==='string')receipt.artifacts=publishArtifacts(writer,onReport,signal,[
      {extension:'csv',bytes:Buffer.from(csv,'utf8')},{extension:'json',bytes:Buffer.from(JSON.stringify(receipt,null,2))},
    ]);
    return receipt;
  });
}

export async function auditLocalPaper(reader,tools,signal,planText) {
  if(typeof planText!=='string'||planText.length>32768)throw Error('论文核验计划过大。');
  const plan=JSON.parse(planText);
  if(!plan||Object.keys(plan).some(key=>!['main','files','bbl'].includes(key))||!Array.isArray(plan.files)||
    !plan.files.length||plan.files.length>32)throw Error('需要 main、files:[{path,sha256}] 和可选 bbl。');
  relativePath(plan.main);if(plan.bbl)relativePath(plan.bbl);
  const seen=new Set();let total=0;
  const files=plan.files.map(row=>{
    if(!row||Object.keys(row).sort().join(',')!=='path,sha256'||!/\.(tex|bib|bbl)$/i.test(row.path))throw Error('仅核验明确列出的 TeX/BibTeX/BBL 来源。');
    const key=relativePath(row.path).toLowerCase();if(seen.has(key))throw Error('来源路径重复。');seen.add(key);
    const bytes=version(reader,row.path,row.sha256,1024*1024);total+=bytes.length;
    if(total>8*1024*1024)throw Error('论文源材料总大小超过 8 MiB。');return{...row,bytes};
  });
  if(!files.some(row=>row.path===plan.main)||plan.bbl&&!files.some(row=>row.path===plan.bbl))throw Error('主文件与 BBL 必须包含在来源清单中。');
  return inSceneScratch(async scratch=>{
    for(const row of files){const target=join(scratch,'inputs',row.path);mkdirSync(dirname(target),{recursive:true});writeFileSync(target,row.bytes,{flag:'wx'});}
    const result=await fixedTool(tools,scratch,signal,'paper',join(scratch,'inputs'),plan);
    for(const row of files)version(reader,row.path,row.sha256,1024*1024);
    return{...result,sources:plan.files};
  });
}

export async function exportLocalFiles(reader,writer,tools,signal,planText,onReport) {
  if(typeof planText!=='string'||planText.length>32768)throw Error('文件整理计划过大。');
  const plan=JSON.parse(planText);
  if(!Array.isArray(plan)||!plan.length||plan.length>32)throw Error('需要 1–32 个 {path,sha256,target} 条目。');
  const targets=new Set();let total=0;
  return inSceneScratch(async scratch=>{
    const files=plan.map((row,index)=>{
      if(!row||Object.keys(row).sort().join(',')!=='path,sha256,target')throw Error('文件条目需要 path、sha256、target。');
      const target=relativePath(row.target),key=target.toLowerCase();
      if(targets.has(key))throw Error('归档目标路径重复。');targets.add(key);
      const bytes=version(reader,row.path,row.sha256,16*1024*1024);total+=bytes.length;
      if(total>64*1024*1024)throw Error('整理文件总大小超过 64 MiB。');
      const source='input-'+index;writeFileSync(join(scratch,source),bytes,{flag:'wx'});
      return{source,target};
    });
    const result=await fixedTool(tools,scratch,signal,'archive',join(scratch,'source'),{files});
    if(result.path!=='collection.zip')throw Error('无效的归档产物。');
    const bytes=readFileSync(join(scratch,result.path));if(sha(bytes)!==result.sha256)throw Error('归档摘要不匹配。');
    for(const row of plan)version(reader,row.path,row.sha256,16*1024*1024);
    const receipt={sources:plan,sha256:result.sha256,originalsChanged:false};
    return{...receipt,artifacts:publishArtifacts(writer,onReport,signal,[{extension:'zip',bytes},
      {extension:'json',bytes:Buffer.from(JSON.stringify(receipt,null,2))}])};
  });
}
