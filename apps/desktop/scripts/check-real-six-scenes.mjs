// One small real-model task per scene. Synthetic inputs only, no mock provider.
// Run using the actual packaged Electron with ELECTRON_RUN_AS_NODE=1.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,readdirSync,realpathSync,writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const resources=resolve(process.argv[2]),toolRoot=resolve(process.argv[3]),destination=resolve(process.argv[4]);
const runtime=join(resources,'geneloop-runtime.asar');
assert.ok(existsSync(runtime)&&existsSync(join(resources,'app.asar')));
const token=process.env.GENELOOP_TEST_DEEPSEEK_API_KEY?.trim();
delete process.env.GENELOOP_TEST_DEEPSEEK_API_KEY;
assert.ok(token,'需要仅用于本轮真实验收的临时模型凭据');
const endpoint='https://api.deepseek.com',model='deepseek-flash';
const preflight=await fetch(endpoint+'/models',{headers:{authorization:'Bearer '+token},signal:AbortSignal.timeout(30000)});
assert.equal(preflight.status,200,'临时模型凭据检查未通过');
assert.ok((await preflight.json()).data.some(m=>m.id===model),'测试模型不可用，不能用其他模型冒充');
const {startLocalWorker}=await import(pathToFileURL(join(resources,'app.asar/dist/local-runtime.js')).href);
const requireRuntime=createRequire(join(runtime,'package.json'));
const PptxGenJS=requireRuntime('pptxgenjs');
const manifest=JSON.parse(readFileSync(join(toolRoot,'manifest.json'),'utf8'));
assert.equal(manifest.platform,process.platform);assert.equal(manifest.arch,process.arch);
const win=process.platform==='win32';
const ppt={python:join(toolRoot,win?'python/python.exe':'python/bin/geneloop-python'),skill:join(toolRoot,'ppt-master'),sourceRoot:join(toolRoot,'source'),soffice:join(toolRoot,win?'libreoffice/program/soffice.com':'libreoffice/Contents/MacOS/soffice')};
const media={ffmpeg:join(toolRoot,'ffmpeg/ffmpeg'+(win?'.exe':'')),ffprobe:join(toolRoot,'ffmpeg/ffprobe'+(win?'.exe':'')),remotion:{browser:realpathSync(join(toolRoot,manifest.browser)),binaries:join(runtime+'.unpacked','node_modules/@remotion/compositor-'+(win?'win32-x64-msvc':'darwin-'+process.arch))}};
for(const p of [ppt.python,ppt.soffice,media.ffmpeg,media.ffprobe,media.remotion.browser])assert.ok(existsSync(p));
mkdirSync(destination,{recursive:true});const out=realpathSync(destination);
assert.ok(!existsSync(join(out,'summary.json')),'为本轮验收创建新目录，不覆盖旧结果');
const nonce='GL-'+randomUUID().slice(0,8),records=[];
const sha=value=>createHash('sha256').update(value).digest('hex');
const summary=()=>writeFileSync(join(out,'summary.json'),JSON.stringify({schema:1,platform:process.platform,arch:process.arch,version:JSON.parse(readFileSync(join(resources,'app.asar/package.json'),'utf8')).version,provider:'DeepSeek official',model,reasoning:'off',modelLocation:'cloud',agentAndToolsLocation:'local',syntheticInputs:true,fullWorkflows:true,commonCapabilities:true,cases:records},null,2)+'\n');
const cases={
 chat:{prompt:'请只回答 17 乘以 23 的计算结果。不需要读取文件。',answer:/391/},
 files:{files:{'record.txt':'Synthetic acceptance record: '+nonce+'\n'},prompt:'这是一次简单本机验收。用 local_read 读取 record.txt，再用 local_save_report 保存一份 Markdown，准确记下记录编号并注明来源。无需整理、移动或压缩文件。',text:[nonce,'record.txt'],tools:['local_read','local_save_report']},
 data:{files:{'measurements.csv':'group,amount\nA,0.10\nA,0.20\nB,2.10\nB,\n'},prompt:'简单本机数据验收：用 local_data_summarize 对 measurements.csv 按 group 汇总 amount，再用 local_save_report 保存 Markdown。明确写出 A 合计、B 合计及 B 的缺失值数量，注明来源。只需要这份汇总，不需要 PDF 或绘图，也无需联网。',text:['0.3','2.1'],tools:['local_data_summarize','local_save_report']},
 paper:{files:{'draft.tex':'Synthetic reference \\cite{known,missing}.\n','references.bib':'@article{known,title={Synthetic known source},year={2024}}\n'},prompt:'简单本机静态引用验收：用 local_paper_check_citations 检查 draft.tex 与 references.bib，再用 local_save_report 保存 Markdown，列出匹配的 known 和缺失的 missing。只做静态检查，不联网、不虚构 DOI 或作者。',text:['known','missing'],tools:['local_paper_check_citations','local_save_report']},
 ppt:{files:{'material.txt':'Controlled synthetic study: 46 percent efficiency. Evidence '+nonce+'.\n'},prompt:'这是现有模板的局部修订验收，不是从零设计。先用 local_ppt_read_material 读取 template.pptx 第1页和 material.txt，获取当前 shape_id 和 text_sha256。再用 local_ppt_edit_template 将标题框 Acceptance placeholder 改成 Native 46 percent，保留副标题 PRESERVE THIS SUBTITLE 和母版，生成副本并交付 PPTX/PDF。不要改写原模板，也不要新建 PPT Master 工程。',tools:['local_ppt_read_material','local_ppt_edit_template']},
 video:{prompt:'简单本机 Remotion 验收：用 local_video_render 渲染 1 秒视频。plan 为 JSON 对象字符串，包含 source 和 assets:[]。source 是可独立执行的 React/Remotion TSX，import React、Composition、AbsoluteFill、registerRoot，注册 id="Main"、宽640、高360、fps=30、durationInFrames=30，纯深蓝背景、白字 NATIVE VIDEO。只用本机 Remotion，不用 hybrid_video_render，不需下载素材。',tools:['local_video_render']},
};
function events(home){const root=join(home,'dsh');if(!existsSync(root))return [];return readdirSync(root,{recursive:true}).filter(p=>p.endsWith('.jsonl')).flatMap(p=>readFileSync(join(root,p),'utf8').split('\n').filter(Boolean).map(s=>{const r=JSON.parse(s);return r.event??r;}));}
for(const [scene,test]of Object.entries(cases)){
 const directory=join(out,scene),home=join(out,scene+'-agent');mkdirSync(directory);const inputs={};
 for(const [name,value]of Object.entries(test.files??{})){writeFileSync(join(directory,name),value);inputs[name]=sha(readFileSync(join(directory,name)));}
 if(scene==='ppt'){
  const deck=new PptxGenJS();deck.layout='LAYOUT_WIDE';const slide=deck.addSlide();
  slide.addText('Acceptance placeholder',{x:0.7,y:0.7,w:11,h:1,fontSize:28,fontFace:'Arial'});
  slide.addText('PRESERVE THIS SUBTITLE',{x:0.7,y:2,w:11,h:1,fontSize:16,fontFace:'Arial'});
  await deck.writeFile({fileName:join(directory,'template.pptx')});inputs['template.pptx']=sha(readFileSync(join(directory,'template.pptx')));
 }
 const record={scene,passed:false,seconds:0,modelResponses:0,usage:{},inputsUnchanged:false,artifacts:[],toolCalls:[],status:'pending'};records.push(record);summary();
 const updates=[],started=Date.now();let worker;
 try{
  worker=startLocalWorker({executable:process.execPath,runtime,home,directory:realpathSync(directory),scene,sessionId:randomUUID(),ppt,media,endpoint,token,model,prompt:test.prompt,legacyTools:false,fullWorkflows:true,commonCapabilities:true,approveFilePlan:async()=>true,onUpdate:event=>{updates.push(event);if(event.kind==='question')worker?.cancel();}});
  const timeout=setTimeout(()=>worker.stop(),540000).unref();try{await worker.closed;}finally{clearTimeout(timeout);}
  const log=events(home),responses=log.filter(e=>e.type==='assistant/message'&&e.data?.usage);
  record.modelResponses=responses.length;
  record.usage=Object.fromEntries(['inputTokens','cacheReadTokens','outputTokens','totalTokens'].map(k=>[k,responses.reduce((n,e)=>n+(e.data.usage[k]??0),0)]));
  record.toolCalls=log.filter(e=>e.type==='tool/call').map(e=>e.data?.name).filter(Boolean);
  record.status=updates.findLast(e=>e.kind==='done')?.status??'unknown';
  assert.equal(record.status,'completed','真实 Agent 任务没有完成');assert.ok(responses.length>0&&record.usage.outputTokens>0,'没有真实模型用量证据');
  for(const [name,digest]of Object.entries(inputs))assert.equal(sha(readFileSync(join(directory,name))),digest,'不能改写输入原件');record.inputsUnchanged=true;
  for(const name of test.tools??[])assert.ok(record.toolCalls.includes(name),'未实际调用要求的本机工具 '+name);
  const reports=[...new Set(updates.filter(e=>e.kind==='report').map(e=>e.report.name))];
  for(const name of reports){assert.match(name,/^GeneLoop-[a-f0-9-]+\.[a-z0-9]+$/);const file=join(directory,'GeneLoop 输出',name);record.artifacts.push({name,bytes:readFileSync(file).length,sha256:sha(readFileSync(file))});}
  const artifact=ext=>{const a=record.artifacts.find(a=>a.name.endsWith('.'+ext));assert.ok(a,'缺少交付 '+ext);return join(directory,'GeneLoop 输出',a.name);};
  if(test.answer)assert.match(updates.filter(e=>e.kind==='answer').map(e=>e.text).join('\n'),test.answer);
  if(test.text){const report=readFileSync(artifact('md'),'utf8');for(const text of test.text)assert.ok(report.includes(text),'报告未包含实际证据 '+text);if(scene==='data')assert.match(report,/1|一/);}
  if(scene==='ppt'){
   assert.match(readFileSync(artifact('pdf')).subarray(0,5).toString(),/%PDF-/);
   const xml=execFileSync(ppt.python,['-B','-c','import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); print(z.read("ppt/slides/slide1.xml").decode())',artifact('pptx')],{encoding:'utf8',windowsHide:true});
   assert.ok(xml.includes('Native 46 percent')&&xml.includes('PRESERVE THIS SUBTITLE'));
  }
  if(scene==='video'){
   const video=artifact('mp4');const info=JSON.parse(execFileSync(media.ffprobe,['-v','error','-show_streams','-show_format','-of','json',video],{encoding:'utf8',windowsHide:true}));
   const stream=info.streams.find(s=>s.codec_type==='video');assert.equal(stream.width,640);assert.equal(stream.height,360);assert.ok(Math.abs(Number(info.format.duration)-1)<0.15);
   execFileSync(media.ffmpeg,['-v','error','-nostdin','-i',video,'-f','null','-'],{windowsHide:true,stdio:'pipe'});
  }
  record.passed=true;
 }catch(error){record.failure=error instanceof Error?error.message:'验收失败';}
 finally{record.seconds=(Date.now()-started)/1000;summary();console.log(JSON.stringify(record));}
}
assert.ok(records.every(r=>r.passed),'六场景真实任务验收尚未全部通过；保留失败证据，不改写为成功');
