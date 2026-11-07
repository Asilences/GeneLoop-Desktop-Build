import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, realpathSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import PptxGenJS from 'pptxgenjs';
import sharp from 'sharp';
import { Context } from '@deepseek-ai/cordis';
import { LocalSubprocessRuntime } from '@deepseek-ai/dsh-subprocess-local';
const runtime=resolve(process.env.GENELOOP_NATIVE_RUNTIME || 'runtime-bundle');
const toolRoot=resolve(process.env.GENELOOP_NATIVE_TOOLS || 'desktop-tools-bundle');
const masterOnly=process.argv.includes('--master-only');
const {openWorkspaceReader,openReportWriter}=await import(pathToFileURL(join(runtime,'local-files.mjs')).href);
const {readPptMaterial,fillPptTemplate,editPptTemplate}=await import(pathToFileURL(join(runtime,'local-ppt-master.mjs')).href);
const {removeScratchDirectory}=await import(pathToFileURL(join(runtime,'local-artifacts.mjs')).href);
const {runNativeProcess}=await import(pathToFileURL(join(runtime,'native-process.mjs')).href);
const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-native-ppt-'))),previous=process.cwd();
mkdirSync(join(root,'workspace'));
const path=join(root,'workspace','template.pptx');
const deck=new PptxGenJS();deck.layout='LAYOUT_WIDE';
const slide=deck.addSlide();slide.addText('{{TITLE}}',{x:1,y:1,w:10,h:1,fontSize:28});
slide.addText('GeneLoop native template',{x:1,y:3,w:10,h:1,fontSize:16});
await deck.writeFile({fileName:path});
writeFileSync(join(root,'workspace','source.txt'),'Synthetic native desktop evidence.');
const reader=openWorkspaceReader(join(root,'workspace')),writer=openReportWriter(join(root,'workspace'));
const ctx=new Context();new LocalSubprocessRuntime(ctx);
const tools={python:join(toolRoot,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python'),
  soffice:join(toolRoot,process.platform==='win32'?'libreoffice/program/soffice.com':'libreoffice/Contents/MacOS/soffice'),
  skill:join(toolRoot,'ppt-master'),sourceRoot:join(toolRoot,'source'),nativeContext:ctx};
try {
  process.chdir(root);
  const signal=AbortSignal.timeout(450_000);let receipt;
  if(!masterOnly){
  const template=await readPptMaterial('template.pptx',1,reader,tools,signal);
  const source=await readPptMaterial('source.txt',1,reader,tools,signal);
  assert.match(template.text,/TITLE/);assert.match(source.text,/Synthetic/);
  receipt=await fillPptTemplate('template.pptx',template.sha256,JSON.stringify({values:{TITLE:'GeneLoop native acceptance'},
    sources:[{path:'source.txt',sha256:source.sha256}]}),reader,writer,tools,signal);
  assert.equal(receipt.status,'passed');assert.equal(receipt.artifacts.length,3);
  assert.match(receipt.execution,/local-ppt-template$/);
  const artifact=extension=>join(root,'workspace','GeneLoop 输出',receipt.artifacts.find(x=>x.name.endsWith('.'+extension)).name);
  assert.ok(readFileSync(artifact('pptx')).length>1000);assert.match(readFileSync(artifact('pdf')).subarray(0,5).toString(),/%PDF-/);
  assert.equal((await readPptMaterial('template.pptx',1,reader,tools,signal)).sha256,template.sha256);
  const relative='GeneLoop 输出/'+receipt.artifacts.find(x=>x.name.endsWith('.pptx')).name;
  const ordinary=await readPptMaterial(relative,1,reader,tools,signal);
  const title=ordinary.shapes.find(row=>row.text==='GeneLoop native acceptance');assert.ok(title);
  const edited=await editPptTemplate(relative,ordinary.sha256,JSON.stringify({edits:[{page:1,shape_id:title.shape_id,
    before_sha256:title.text_sha256,text:'GeneLoop ordinary template'}]}),reader,writer,tools,signal);
  assert.equal(edited.status,'passed');
  const changed=await readPptMaterial('GeneLoop 输出/'+edited.artifacts.find(x=>x.name.endsWith('.pptx')).name,1,reader,tools,signal);
  assert.match(changed.text,/GeneLoop ordinary template/);assert.match(changed.text,/GeneLoop native template/);
  }
  const work=join(root,'authoring'),project=join(work,'projects','deck'),output=join(work,'outputs','delivery');
  for(const directory of [join(project,'svg_output'),join(project,'notes'),join(work,'outputs')])mkdirSync(directory,{recursive:true});
  writeFileSync(join(project,'spec_lock.md'),'# Spec Lock\n\n## canvas\n- viewBox: 0 0 1280 720\n\n## pptx_structure\n- mode: flat\n\n## colors\n- background: #FFFFFF\n- text: #172B4D\n- accent: #3366CC\n\n## typography\n- font_family: Arial\n- title: 40\n- body: 24\n');
  writeFileSync(join(project,'design_spec.md'),'# Native PPT\n\n## Slide 1\nNative PPT Master\nActual embedded image and editable text.\n');
  const image=await sharp({create:{width:4,height:4,channels:3,background:'#3366cc'}}).png().toBuffer();
  writeFileSync(join(project,'svg_output','slide_01_native.svg'),`<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#FFFFFF"/><text x="80" y="110" font-family="Arial" font-size="40" fill="#172B4D">Native PPT Master</text><text x="80" y="180" font-family="Arial" font-size="24" fill="#172B4D">Actual embedded image and editable text.</text><image x="80" y="240" width="160" height="160" href="data:image/png;base64,${image.toString('base64')}"/></svg>`);
  writeFileSync(join(project,'notes','total.md'),'# slide_01_native\n\nSynthetic speaker notes from the official total.md parser.\n');
  const pipeline=async operation=>{
    const request=join(work,operation+'.json');writeFileSync(request,JSON.stringify({operation,work,project,output,skill:tools.skill,soffice:tools.soffice}));
    const result=await runNativeProcess(ctx,[tools.python,'-B','-X','utf8',join(tools.sourceRoot,'src/adapters/desktop_ppt_pipeline.py'),request],work,signal,{timeoutMs:180000});
    return JSON.parse(result.stdout.trim().split('\n').at(-1));
  };
  const prepared=await pipeline('prepare');assert.equal(prepared.status,'prepared');
  assert.equal(prepared.bold.roles.title.weight,'bold');assert.equal(prepared.normal.roles.title.weight,'normal');
  const finalized=await pipeline('finalize');assert.equal(finalized.mechanical_status,'passed',JSON.stringify(finalized));
  assert.ok(finalized.artifacts.some(row=>row.path.endsWith('.pptx')));assert.ok(finalized.artifacts.some(row=>row.path.endsWith('.pdf')));
  assert.match(readFileSync(join(project,'notes','slide_01_native.md'),'utf8'),/Synthetic speaker notes/);
  console.log(JSON.stringify({diagnostic:true,platform:process.platform,arch:process.arch,pptx:true,pdf:true,
    templateUnchanged:!masterOnly,ordinaryTemplateEdited:!masterOnly,officialFontCalibration:true,embeddedRaster:true,totalNotes:true,masterDelivery:true,model_requests:0,execution:receipt?.execution??finalized.execution}));
} finally {
  reader.close();writer.close();await ctx.fiber.dispose();process.chdir(previous);
  removeScratchDirectory(root,realpathSync(tmpdir()));
}
