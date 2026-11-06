import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, realpathSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import PptxGenJS from 'pptxgenjs';
import { Context } from '@deepseek-ai/cordis';
import { LocalSubprocessRuntime } from '@deepseek-ai/dsh-subprocess-local';
const runtime=resolve(process.env.GENELOOP_NATIVE_RUNTIME || 'runtime-bundle');
const toolRoot=resolve(process.env.GENELOOP_NATIVE_TOOLS || 'desktop-tools-bundle');
const {openWorkspaceReader,openReportWriter}=await import(pathToFileURL(join(runtime,'local-files.mjs')).href);
const {readPptMaterial,fillPptTemplate,editPptTemplate}=await import(pathToFileURL(join(runtime,'local-ppt-master.mjs')).href);
const {removeScratchDirectory}=await import(pathToFileURL(join(runtime,'local-artifacts.mjs')).href);
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
  const signal=AbortSignal.timeout(180_000);
  const template=await readPptMaterial('template.pptx',1,reader,tools,signal);
  const source=await readPptMaterial('source.txt',1,reader,tools,signal);
  assert.match(template.text,/TITLE/);assert.match(source.text,/Synthetic/);
  const receipt=await fillPptTemplate('template.pptx',template.sha256,JSON.stringify({values:{TITLE:'GeneLoop native acceptance'},
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
  console.log(JSON.stringify({diagnostic:true,platform:process.platform,arch:process.arch,pptx:true,pdf:true,
    templateUnchanged:true,ordinaryTemplateEdited:true,execution:receipt.execution}));
} finally {
  reader.close();writer.close();await ctx.fiber.dispose();process.chdir(previous);
  removeScratchDirectory(root,realpathSync(tmpdir()));
}
