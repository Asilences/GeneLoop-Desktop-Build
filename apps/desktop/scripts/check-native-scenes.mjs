// 无模型诊断：只验证新增的跨平台工具闭环，不调用模型或修改用户资料。
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync,mkdtempSync,readFileSync,realpathSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import JSZip from 'jszip';
import {Context} from '@deepseek-ai/cordis';
import {LocalSubprocessRuntime} from '@deepseek-ai/dsh-subprocess-local';
const runtime=resolve(process.env.GENELOOP_NATIVE_RUNTIME||'runtime-bundle');
const toolsRoot=resolve(process.env.GENELOOP_NATIVE_TOOLS||'desktop-tools-bundle');
const load=name=>import(pathToFileURL(join(runtime,name)).href);
const {openWorkspaceReader,openReportWriter}=await load('local-files.mjs');
const {createPptSourceReader}=await load('local-ppt-master.mjs');
const {analyzeLocalData,auditLocalPaper,exportLocalFiles}=await load('local-scene-tools.mjs');
const {localSceneTools}=await load('local-scenes.mjs');
const {registerLocalFileTools}=await load('local-file-tools.mjs');
const {removeScratchDirectory}=await load('local-artifacts.mjs');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const previous=process.cwd(),root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-scene-tools-')));
const workspace=join(root,'workspace');mkdirSync(join(workspace,'chapters'),{recursive:true});
const ctx=new Context();new LocalSubprocessRuntime(ctx);
const tools={python:join(toolsRoot,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python'),
  sourceRoot:join(toolsRoot,'source'),nativeContext:ctx};
const files={
  'source.md':'GeneLoop source evidence.',
  'table.json':JSON.stringify([{x:1,y:2,note:'=1+1'},{x:2,y:4,note:'literal'},{x:3,y:6,note:''}]),
  'main.tex':'\\input{chapters/intro}\n\\cite{known,missing}\n\\bibliography{refs}',
  'chapters/intro.tex':'\\label{dup}\n\\label{dup}',
  'refs.bib':'@article{known, title={Actual local fixture}}',
};
for(const [path,text]of Object.entries(files))writeFileSync(join(workspace,path),text);
const zip=new JSZip(),s='http://schemas.openxmlformats.org/spreadsheetml/2006/main',r='http://schemas.openxmlformats.org/officeDocument/2006/relationships';
zip.file('_rels/.rels',`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="${r}/officeDocument" Target="xl/workbook.xml"/></Relationships>`);
zip.file('xl/workbook.xml',`<workbook xmlns="${s}" xmlns:r="${r}"><sheets><sheet name="Evidence" sheetId="1" r:id="rId1"/></sheets></workbook>`);
zip.file('xl/_rels/workbook.xml.rels',`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="${r}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`);
const sheet=`<worksheet xmlns="${s}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>x</t></is></c><c r="B1" t="inlineStr"><is><t>y</t></is></c></row><row r="2"><c r="A2"><v>1</v></c><c r="B2"><v>2</v></c></row><row r="3"><c r="A3"><v>2</v></c></row><row r="4"><c r="A4"><v>3</v></c><c r="B4"><v>6</v></c></row></sheetData></worksheet>`;
zip.file('xl/worksheets/sheet1.xml',sheet);
writeFileSync(join(workspace,'table.xlsx'),await zip.generateAsync({type:'nodebuffer'}));
zip.file('xl/worksheets/sheet1.xml',sheet.replace('<v>2</v>','<f>1+1</f><v>2</v>'));
writeFileSync(join(workspace,'formula.xlsx'),await zip.generateAsync({type:'nodebuffer'}));
const reader=openWorkspaceReader(workspace),writer=openReportWriter(workspace);
const version=path=>sha(reader.readBytes(path,16*1024*1024));
try {
  process.chdir(root);const signal=AbortSignal.timeout(180_000);
  for(const scene of ['chat','files','data','paper','ppt','video'])assert.ok(localSceneTools(scene).includes('local_document_read'));
  for(const legacy of [false,true]) {
    const names=[];
    const scope={tools:{restrict(){},guard(){},register(tool){names.push(tool.name);}}};
    registerLocalFileTools(scope,reader,writer,undefined,'data',signal,undefined,undefined,tools,undefined,ctx,legacy);
    assert.equal(names.includes('local_document_read'),!legacy);
    assert.equal(names.includes('local_data_analyze'),!legacy);
    assert.ok(names.includes('local_data_summarize'));
  }
  const documents=createPptSourceReader(reader,tools,signal),pinned=documents.pin('table.xlsx');
  assert.match((await documents.read(pinned.source_id,1)).text,/Sheet Evidence/);
  const json=await analyzeLocalData(reader,tools,signal,{path:'table.json',sha256:version('table.json'),x:'x',y:'y',export_csv:true},writer);
  assert.equal(json.summary.rows,3);assert.equal(json.correlation.pearson_r,1);
  assert.equal(json.csv_escaped_text_cells,1);
  assert.match(readFileSync(join(workspace,'GeneLoop 输出',json.artifacts[0].name),'utf8'),/'=1\+1/);
  const excel=await analyzeLocalData(reader,tools,signal,{path:'table.xlsx',sha256:version('table.xlsx'),x:'x',y:'y',export_csv:true},writer);
  assert.equal(excel.summary.columns[1].missing,1);assert.equal(excel.correlation.complete_pairs,2);
  assert.equal(excel.artifacts.length,2);assert.equal(excel.correlation.pearson_r,1);
  await assert.rejects(analyzeLocalData(reader,tools,signal,{path:'formula.xlsx',sha256:version('formula.xlsx')},writer),/formula/);
  const plan={main:'main.tex',files:['main.tex','chapters/intro.tex','refs.bib'].map(path=>({path,sha256:version(path)}))};
  const paper=await auditLocalPaper(reader,tools,signal,JSON.stringify(plan));
  assert.deepEqual(paper.missing_cited_keys,['missing']);assert.equal(paper.duplicate_labels.length,1);
  const sourceVersion=version('source.md');
  const result=await exportLocalFiles(reader,writer,tools,signal,JSON.stringify([{path:'source.md',sha256:sourceVersion,target:'资料/notes.md'}]));
  const archive=await JSZip.loadAsync(readFileSync(join(workspace,'GeneLoop 输出',result.artifacts[0].name)));
  assert.equal(await archive.file('资料/notes.md').async('string'),files['source.md']);
  await assert.rejects(exportLocalFiles(reader,writer,tools,signal,JSON.stringify([{path:'source.md',sha256:sourceVersion,target:'../outside.md'}])),/相对路径/);
  assert.equal(version('source.md'),sourceVersion);
  writeFileSync(join(workspace,'table.xlsx'),Buffer.from('changed'));
  await assert.rejects(documents.read(pinned.source_id,1),/变化/);
  console.log(JSON.stringify({diagnostic:true,platform:process.platform,arch:process.arch,realModelRequests:0,
    commonDocuments:true,jsonAndXlsxTables:true,sparseCells:true,formulaRejected:true,sourceVersionGuard:true,
    descriptiveAndCorrelation:true,multiFilePaperAudit:true,archiveCopyOnly:true,archiveTraversalRejected:true}));
}finally{
  reader.close();writer.close();await ctx.fiber.dispose();process.chdir(previous);removeScratchDirectory(root,realpathSync(tmpdir()));
}
