// Deterministic native MCP integration, not a model/quality acceptance test.
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,realpathSync,readdirSync,existsSync,linkSync,unlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import {LocalSubprocessRuntime} from '@deepseek-ai/dsh-subprocess-local';
import PptxGenJS from 'pptxgenjs';
const runtime=resolve(process.env.GENELOOP_NATIVE_RUNTIME||'runtime-bundle'),bundle=resolve(process.env.GENELOOP_NATIVE_TOOLS||'desktop-tools-bundle');
const coreOnly=process.argv.includes('--core');
const {openWorkspaceReader,openReportWriter}=await import(pathToFileURL(join(runtime,'local-files.mjs')).href);
const {createNativeWorkflows}=await import(pathToFileURL(join(runtime,'local-workflows.mjs')).href);
const {workflowToolName}=await import(pathToFileURL(join(runtime,'native-workflow-catalog.mjs')).href);
const {workflowOutput}=await import(pathToFileURL(join(runtime,'local-workflow-output.mjs')).href);
const {ToolRuntime}=await import(pathToFileURL(join(runtime,'node_modules/@deepseek-ai/dsh-tools/lib/index.js')).href);
const {SystemPrompt}=await import(pathToFileURL(join(runtime,'node_modules/@deepseek-ai/dsh-system-prompt/lib/index.js')).href);
const {createScope}=await import(pathToFileURL(join(runtime,'node_modules/@deepseek-ai/dsh-scope/lib/index.js')).href);
const {removeScratchDirectory}=await import(pathToFileURL(join(runtime,'local-artifacts.mjs')).href);
const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-full-scenes-'))),prior=process.cwd(),workspace=join(root,'workspace');
mkdirSync(workspace);
writeFileSync(join(workspace,'main.tex'),'\\documentclass{article}\n\\begin{document}\\cite{known,missing}\\bibliography{refs}\\end{document}');
writeFileSync(join(workspace,'refs.bib'),'@article{known,title={Synthetic native source},year={2024},author={Example, Test}}');
writeFileSync(join(workspace,'notes.txt'),'Synthetic local evidence.');
writeFileSync(join(workspace,'data.csv'),'x,y\n1,2\n2,3\n3,5\n4,7\n5,9\n6,10\n');
const template=new PptxGenJS();template.addSlide().addText('Synthetic native workflow evidence',{x:1,y:1,w:8,h:1,fontSize:28});
await template.writeFile({fileName:join(workspace,'source.pptx')});
const sha=data=>createHash('sha256').update(data).digest('hex');
const sources=names=>JSON.stringify(names.map(path=>({path,sha256:sha(readFileSync(join(workspace,path)))})));
const ctx=new Context();new LocalSubprocessRuntime(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx);
const registryScope=createScope(ctx,{}),registered=new Set();
const reader=openWorkspaceReader(workspace),writer=openReportWriter(workspace);
const tools={sourceRoot:join(bundle,'source'),python:join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python'),
  soffice:join(bundle,process.platform==='win32'?'libreoffice/program/soffice.exe':'libreoffice/Contents/MacOS/soffice'),skill:join(bundle,'ppt-master')};
process.chdir(root);const signal=AbortSignal.timeout(240000),flows=[];
const controller=scene=>{const flow=createNativeWorkflows(ctx,reader,writer,tools,scene,signal,undefined,(kind,id,catalog)=>{
  for(const tool of catalog) {
    const name=workflowToolName(kind,tool.name);
    registryScope.ctx.tools.register({name,description:tool.description??name,parameters:tool.inputSchema,
      ...workflowOutput(ctx,args=>flow.call(id,tool.name,JSON.stringify(args),async()=>false))});registered.add(name);
  }
});flows.push(flow);return flow;};
try {
  const paper=controller('paper'),opened=await paper.open(sources(['main.tex','refs.bib']),'核验这些明确标记的合成论文材料','{}');
  assert.ok(opened.tools.some(t=>t.name==='fetch_pinned_formal_reference_metadata'));
  assert.ok(opened.tools.some(t=>t.name==='export_current_audit_pdf'));
  const evidence=(await paper.call(opened.workflow_id,'collect_current_local_citation_evidence','{}')).result;
  assert.ok(evidence.citation_id);assert.ok(evidence.source_id);
  const checks=Object.fromEntries(['list_without_citation','citation_without_entry','duplicate_entries','numbering_anomaly','unresolved_or_abnormal_citations','non_citation_brackets']
    .map(key=>[key,{result:'Synthetic diagnostic only',evidence:'main.tex',limitation:'Not an authenticity review'}]));
  const staged=await paper.call(opened.workflow_id,'stage_current_audit',JSON.stringify({scope:'Synthetic native audit renderer diagnostic',citation_checks:checks,references:[{
    number:1,key:'known',short_title:'Synthetic native source',status:'存疑',priority:'P2',source_ids:[],explanation:'Synthetic source; authenticity not reviewed.',evidence_files:['refs.bib']}]}));
  assert.equal(staged.result.staged,true,JSON.stringify(staged));
  const finalized=await paper.call(opened.workflow_id,'finalize_current_audit',JSON.stringify({expected_draft_sha256:staged.result.draft_sha256}));
  const audit=await paper.call(opened.workflow_id,'export_current_audit_pdf',JSON.stringify({report_sha256:finalized.result.report_sha256}));
  assert.equal(audit.isError,undefined,JSON.stringify(audit));assert.ok(audit.artifacts.some(a=>a.name.endsWith('.pdf')),JSON.stringify(audit));
  assert.equal(audit.result.renderer_motif_certified,false);
  const general=controller('chat'),g=await general.open(sources(['notes.txt']),'创建本机资料副本','{"workflow":"general"}');
  const workspaceFlow=controller('chat'),w=await workspaceFlow.open(sources(['notes.txt']),'读取本轮资料','{"workflow":"workspace"}');
  const listing=(await workspaceFlow.call(w.workflow_id,'list_files','{}')).result.files;
  const actual=await workspaceFlow.call(w.workflow_id,'read_file',JSON.stringify({name:listing[0].name,sha256:listing[0].sha256}));
  assert.equal(actual.isError,undefined,JSON.stringify(actual));
  const revision=controller('paper'),rev=await revision.open('[]','核对结构修订入口','{"workflow":"revision"}');
  const revState=await revision.call(rev.workflow_id,'read_task_state','{}');assert.equal(revState.isError,undefined,JSON.stringify(revState));
  const gateway=controller('chat'),gw=await gateway.open(sources(['notes.txt']),'检查实际动态工具目录','{"workflow":"gateway"}');
  const discovery=await gateway.call(gw.workflow_id,'discover_tools','{}');assert.equal(discovery.isError,undefined,JSON.stringify(discovery));
  assert.equal(discovery.result.providers.length,4);assert.ok(discovery.result.providers.every(row=>row.available),JSON.stringify(discovery));
  const manager=controller('files'),managed=await manager.open(sources(['notes.txt']),'整理本轮副本并验证恢复','{"workflow":"management"}');
  assert.equal(managed.tools.length,27);assert.ok(!managed.tools.some(tool=>tool.name==='_native_authorize_plan'));
  await manager.call(managed.workflow_id,'read_task','{}');
  const proposal=await manager.call(managed.workflow_id,'preview_actions',JSON.stringify({actions:[{op:'copy',source:'notes.txt',destination:'整理/notes.txt'}]}));
  assert.equal(proposal.isError,undefined,JSON.stringify(proposal));
  await assert.rejects(manager.call(managed.workflow_id,'execute_plan',JSON.stringify({plan_id:proposal.result.plan_id}),async()=>false));
  const operation=await manager.call(managed.workflow_id,'execute_plan',JSON.stringify({plan_id:proposal.result.plan_id}),async()=>true);
  assert.equal(operation.isError,undefined,JSON.stringify(operation));assert.equal(operation.result.status,'executed_verified');
  const restored=await manager.call(managed.workflow_id,'restore_plan',JSON.stringify({plan_id:proposal.result.plan_id}),async()=>true);
  assert.equal(restored.isError,undefined,JSON.stringify(restored));
  const privateManagement=readdirSync(root).map(name=>join(root,name,'source','.local','turn','work','inputs','notes.txt')).find(existsSync);
  assert.ok(privateManagement);const outsideLink=join(root,'outside-management.txt');linkSync(privateManagement,outsideLink);
  try{
    const blocked=await manager.call(managed.workflow_id,'preview_actions',JSON.stringify({actions:[{op:'copy',source:'notes.txt',destination:'another/notes.txt'}]}));
    assert.equal(blocked.isError,undefined,JSON.stringify(blocked));
    await assert.rejects(manager.call(managed.workflow_id,'execute_plan',JSON.stringify({plan_id:blocked.result.plan_id}),async()=>true),/场景产物类型/);
  }finally{unlinkSync(outsideLink);}
  const capabilities=await general.call(g.workflow_id,'runtime_capabilities','{}');
  assert.equal(capabilities.result.code.available,true,JSON.stringify(capabilities));assert.equal(capabilities.result.ocr.available,true,JSON.stringify(capabilities));
  const text=await general.call(g.workflow_id,'create_text',JSON.stringify({destination:'result.txt',text:'Native MCP output.'}));
  assert.equal(text.artifacts.length,1);assert.equal(readFileSync(join(workspace,'GeneLoop 输出',text.artifacts[0].name),'utf8'),'Native MCP output.');
  const code=await general.call(g.workflow_id,'execute_code',JSON.stringify({program:'const a=await inputs.read_text({name:"notes.txt"}); await outputs.write_text({name:"computed.txt",text:a.text}); return typeof process;'}));
  assert.equal(code.isError,undefined,JSON.stringify(code));
  assert.equal(code.result.runtime,'typescript/quickjs-wasm');assert.equal(code.result.result.value,'undefined');assert.equal(code.artifacts.length,1);
  const report=controller('data'),r=await report.open(sources(['data.csv']),'合成诊断：检查x与y的一元回归；不作因果判断。','{}');
  assert.ok(r.tools.some(t=>t.name==='deliver_report'));assert.ok(r.tools.some(t=>t.name==='render_figures'));
  const inspected=await report.call(r.workflow_id,'inspect_study','{}');assert.equal(inspected.isError,undefined);assert.ok(inspected.result);
  const fileFlow=controller('files'),f=await fileFlow.open(sources(['notes.txt']),'将资料副本整理到整理目录','{}');
  await fileFlow.call(f.workflow_id,'read_task','{}');
  const files=(await fileFlow.call(f.workflow_id,'list_files','{}')).result.files;
  const preview=(await fileFlow.call(f.workflow_id,'preview_actions',JSON.stringify({actions:[{op:'copy',file_ids:[files[0].file_id],destination:'整理/notes.txt',format:'none'}]}))).result;
  await assert.rejects(fileFlow.call(f.workflow_id,'authorize_plan',JSON.stringify({plan_id:preview.plan_id}),async()=>false),/用户尚未确认/);
  const auth=(await fileFlow.call(f.workflow_id,'authorize_plan',JSON.stringify({plan_id:preview.plan_id}),async()=>true)).result;
  const receipt=await fileFlow.call(f.workflow_id,'execute_plan',JSON.stringify({plan_id:preview.plan_id,authorization_id:auth.authorization_id}));
  assert.equal(receipt.result.status,'executed_verified');assert.equal(receipt.artifacts.length,1);
  assert.equal(readFileSync(join(workspace,'notes.txt'),'utf8'),'Synthetic local evidence.');
  const ppt=controller('ppt'),p=await ppt.open(sources(['source.pptx']),'合成诊断：制作一页材料摘要，不做科研效果主张。','{"workflow":"ppt","slides":1}');
  assert.equal(p.tools.length,21);
  if(!coreOnly) {
  const input=(await ppt.call(p.workflow_id,'list_inputs','{}')).result.inputs[0];
  const pinned=(await ppt.call(p.workflow_id,'pin_source',JSON.stringify({document_id:input.document_id}))).result;
  await ppt.call(p.workflow_id,'read_source',JSON.stringify({source_id:pinned.source_id}));
  const deck=await ppt.call(p.workflow_id,'render_deck',JSON.stringify({plan:{title:'Native workflow diagnostic',slides:[{
    title:'Synthetic native workflow',bullets:['Evidence from the approved synthetic source.'],sources:[{source_id:pinned.source_id,page:1}],notes:'Synthetic native integration diagnostic.'}]}}));
  assert.equal(deck.isError,undefined,JSON.stringify(deck));assert.ok(deck.artifacts.some(a=>a.name.endsWith('.pdf')),JSON.stringify(deck));
  const pdf=deck.artifacts.find(a=>a.name.endsWith('.pdf'));
  const skill=await ppt.open(sources(['GeneLoop 输出/'+pdf.name]),'固定并转换合成PDF材料','{"workflow":"skill"}');
  assert.equal(skill.tools.length,5);
  const entry=await ppt.call(skill.workflow_id,'read_skill_entry','{}');assert.equal(entry.isError,undefined,JSON.stringify(entry));
  const listing=entry.result.files[0];
  const pinnedPdf=(await ppt.call(skill.workflow_id,'pin_source',JSON.stringify({name:listing.name,sha256:listing.sha256}))).result;
  const converted=await ppt.call(skill.workflow_id,'convert_source',JSON.stringify({source_id:pinnedPdf.source_id}));
  assert.equal(converted.isError,undefined,JSON.stringify(converted));assert.equal(converted.result.original_modified,false);
  }
  writeFileSync(join(workspace,'data.csv'),'changed');
  await assert.rejects(report.call(r.workflow_id,'inspect_study','{}'),/来源已变化/);
  console.log(JSON.stringify({paper_tools:opened.tools.length,general_tools:g.tools.length,data_tools:r.tools.length,
    file_tools:f.tools.length,ppt_tools:p.tools.length,skill_tools:coreOnly?0:5,dsh_registered:registered.size,core_only:coreOnly,
    ppt_office_delivery:!coreOnly,ppt_source_conversion:!coreOnly,native_code:true,file_approval_and_copy_delivery:true,management_tools:managed.tools.length,workspace_tools:w.tools.length,revision_tools:rev.tools.length,gateway_tools:gw.tools.length,external_hardlink_denied:true,paper_evidence:true,paper_audit_pdf:true,native_output:true,source_invalidation:true,model_requests:0}));
} finally {
  await Promise.allSettled(flows.map(flow=>flow.close()));await registryScope.dispose();reader.close();writer.close();await ctx.fiber.dispose();process.chdir(prior);
  removeScratchDirectory(root,realpathSync(tmpdir()));
}
