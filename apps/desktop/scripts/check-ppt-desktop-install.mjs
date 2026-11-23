// Deterministic acceptance using the installed Electron, Python, Office and PPT assets.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,readdirSync,realpathSync,writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const [resourcesArg,outputArg]=process.argv.slice(2);
assert.ok(process.versions.electron&&resourcesArg&&outputArg,'Run with the packaged Electron executable in Node mode and supply resources/output paths.');
assert.equal(process.env.GENELOOP_PPT_MASTER_ROOT,undefined);
const resources=realpathSync(resourcesArg),runtime=join(resources,'geneloop-runtime.asar'),bundle=join(resources,'geneloop-tools');
const output=resolve(outputArg);mkdirSync(output,{recursive:false});
const workspace=join(output,'workspace');mkdirSync(workspace);
assert.ok(!existsSync(join(bundle,'ppt-master')),'Legacy external PPT Master directory must be absent.');
const thirdParty=join(bundle,'ppt-deck/scenarios/ppt_master/third_party');
const provenance=JSON.parse(readFileSync(join(thirdParty,'ppt-master-provenance.json'),'utf8'));
const tools={sourceRoot:join(bundle,'source'),skill:join(thirdParty,'ppt-master'),deck:join(bundle,'local-ppt-deck.mjs'),
  python:join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python'),
  soffice:join(bundle,process.platform==='win32'?'libreoffice/program/soffice.com':'libreoffice/Contents/MacOS/soffice')};
const require=createRequire(join(thirdParty,'dsh-ppt/package.json'));
const {unzipSync}=require('fflate');
const decode=bytes=>Buffer.from(bytes).toString('utf8');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const signal=AbortSignal.timeout(600_000);
const paths=name=>pathToFileURL(join(runtime,name)).href;
const moduleConfig={runtime,workspace,tools,output,provenance};
writeFileSync(join(output,'config.json'),JSON.stringify(moduleConfig));
const sharp=createRequire(paths('node_modules/sharp/package.json'))('sharp');
await sharp(Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="420" height="280" viewBox="0 0 420 280"><rect width="420" height="280" fill="#eaf2fa"/><rect x="55" y="156" width="58" height="69" rx="4" fill="#6595d4"/><rect x="144" y="122" width="58" height="103" rx="4" fill="#4f81c5"/><rect x="233" y="88" width="58" height="137" rx="4" fill="#366ab0"/><rect x="322" y="52" width="58" height="173" rx="4" fill="#245495"/><path d="M40 225H391" stroke="#17365d" stroke-width="3"/></svg>'))
  .png().toFile(join(workspace,'figure.png'));

const plugin=join(output,'check.mjs');
writeFileSync(plugin,`
import assert from 'node:assert/strict';
import {copyFileSync,existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {openLocalFileAgent} from ${JSON.stringify(paths('local-agent.mjs'))};
import {LocalAttachmentStore} from ${JSON.stringify(paths('node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js'))};
import {createUserMessage} from ${JSON.stringify(paths('node_modules/@deepseek-ai/dsh-llm/lib/index.js'))};
export const inject=['agents','tools','subprocess','sandboxPolicy'];
export function apply(ctx) { void (async()=>{
  const {tools,workspace,output}=JSON.parse(readFileSync(${JSON.stringify(join(output,'config.json'))},'utf8'));
  const sessionId=randomUUID(),signal=AbortSignal.timeout(540_000),hash=bytes=>createHash('sha256').update(bytes).digest('hex');
  const home=process.env.DSH_HOME,work=join(home,'task-workspaces',sessionId);
  const config={directory:workspace,model:{provider:'deepseek-official',model:'deepseek-flash'},signal,sessionId,scene:'ppt',ppt:tools,
    fullWorkflows:true,commonCapabilities:true,nativePptDeck:true};
  let handle,stage='open';
  const written=join(workspace,'GeneLoop 输出');
  const save=(label,value)=>writeFileSync(join(output,label+'.json'),JSON.stringify(value,null,2));
  const outputFile=(receipt,ext)=>join(written,(receipt.published??receipt.artifacts).find(row=>row.name.endsWith('.'+ext)).name);
  try {
    new LocalAttachmentStore(ctx,{dshHome:home});
    handle=await openLocalFileAgent(ctx,config);
    handle.agent.session.append('user/message',createUserMessage({source:{kind:'user'},
      content:[{type:'text',text:'三页 PPT 本机诊断'}]}),{surfaceOp:'append'});
    const call=async(name,args)=>{
      stage=name;
      const r=await ctx.tools.execute({callId:randomUUID(),name,arguments:args,agent:handle.agent,signal});
      assert.equal(r.isError,false,JSON.stringify(r));
      return r.value;
    };
    assert.ok(ctx.tools.get('build_ppt',handle.agent));assert.ok(ctx.tools.get('patch_ppt',handle.agent));
    await call('local_import_sources',{sources:[{path:'figure.png',sha256:hash(readFileSync(join(workspace,'figure.png')))}]});
    const base=await call('build_ppt',{name:'acceptance',plan:{title:'桌面演示 · Desktop PPT',theme:'general',language:'bilingual',strict_slide_count:true,target_slide_count:3,
      slides:[{layout:'image-right',title:'桌面演示 Desktop PPT',bullets:['本机生成 · Native local execution'],image:{src:'inputs/figure.png',alt:'Sample growth chart'},notes:'Cover notes'},
      {layout:'chart',title:'双系列数据',chart:{kind:'column',categories:['Jan','Feb'],series:[{name:'Baseline',values:[11,14]},{name:'Updated',values:[16,19]}]},notes:'Chart notes'},
      {layout:'table',title:'结果表',rows:[['Month','Count'],['Jan','11'],['Feb','14']],notes:'Table notes'}]}});
    save('native',base);assert.equal(base.mechanical_status,'passed',JSON.stringify(base));assert.equal(base.slide_count,3);
    assert.equal(base.published.length,4);
    const source=join(workspace,'original.pptx');
    copyFileSync(outputFile(base,'pptx'),source);
    const originalSha=hash(readFileSync(source));
    const modified=await call('patch_ppt',{project:base.project,expected_revision:base.revision,
      edits:[{slide_id:base.slides[1].id,changes:{title:'双系列数据 · 修订'}}]});
    save('patched',modified);assert.equal(modified.mechanical_status,'passed',JSON.stringify(modified));
    assert.equal(modified.revision,base.revision+1);
    assert.deepEqual(modified.affected_slide_ids,[base.slides[1].id]);
    const conflict=await call('patch_ppt',{project:base.project,expected_revision:base.revision,edits:[]});
    assert.equal(conflict.status,'rejected');assert.equal(conflict.error.current_revision,modified.revision);
    await handle.close();
    handle=await openLocalFileAgent(ctx,{...config,resume:true});
    const current=await call('patch_ppt',{project:base.project,expected_revision:modified.revision,edits:[]});
    assert.equal(current.revision,modified.revision);assert.equal(current.changed,false);
    const material=await call('local_ppt_read_material',{path:'original.pptx',page:1});
    const title=material.shapes.find(row=>row.text.includes('Desktop PPT'));
    assert.ok(title);
    const edited=await call('local_ppt_edit_template',{path:'original.pptx',sha256:originalSha,
      plan:JSON.stringify({edits:[{page:1,shape_id:title.shape_id,before_sha256:title.text_sha256,text:'修改封面 Revised Cover'}]})});
    save('edited',edited);assert.equal(edited.status,'passed');assert.equal(edited.artifacts.length,4);
    assert.equal(hash(readFileSync(source)),originalSha);
    const svgProject=join(work,'projects','svg');
    mkdirSync(join(svgProject,'svg_output'),{recursive:true});mkdirSync(join(svgProject,'notes'));
    writeFileSync(join(svgProject,'spec_lock.md'),'# Spec Lock\\n\\n## canvas\\n- viewBox: 0 0 1280 720\\n\\n## pptx_structure\\n- mode: flat\\n\\n## colors\\n- background: #FFFFFF\\n- text: #172B4D\\n- accent: #3366CC\\n\\n## typography\\n- font_family: Arial\\n- title: 40\\n- body: 24\\n');
    writeFileSync(join(svgProject,'design_spec.md'),'# Native desktop SVG acceptance');
    for(let page=1;page<=3;page++){
      const stem='slide_0'+page;
      writeFileSync(join(svgProject,'svg_output',stem+'.svg'),'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#FFFFFF"/><text x="80" y="110" font-family="Arial" font-size="40" fill="#172B4D">Desktop SVG '+page+'</text></svg>');
      writeFileSync(join(svgProject,'notes',stem+'.md'),'SVG notes '+page);
    }
    const prepared=await call('prepare_ppt',{project:'projects/svg'});
    assert.equal(prepared.status,'prepared');
    const finalized=await call('finalize_ppt',{project:'projects/svg'});
    save('svg',finalized);assert.equal(finalized.mechanical_status,'passed');assert.equal(finalized.published.length,4);
    save('worker',{ok:true,stage,modelRequests:0,svg:true,project:base.project,sessionId,originalSha,
      native:outputFile(base,'pptx'),patched:outputFile(modified,'pptx'),edited:outputFile(edited,'pptx'),svgPath:outputFile(finalized,'pptx'),
      nativePng:outputFile(base,'zip'),patchedPng:outputFile(modified,'zip'),editedPng:outputFile(edited,'zip'),svgPng:outputFile(finalized,'zip'),
      nativePdf:outputFile(base,'pdf'),patchedPdf:outputFile(modified,'pdf'),editedPdf:outputFile(edited,'pdf'),svgPdf:outputFile(finalized,'pdf')});
  }catch(error){save('worker',{ok:false,stage,error:error.message,stack:error.stack});}
  finally{await handle?.close();process.exit(0);}
})(); }
`);
const patch=join(output,'patch.json');
writeFileSync(patch,JSON.stringify([{id:'persistent-pwsh',disabled:true},{id:'persistent-bash',disabled:true},
  {id:'plugin-package-inventory-deepseek',disabled:true},{insert:[{name:pathToFileURL(plugin).href}]}]));
const env={SystemRoot:process.env.SystemRoot,WINDIR:process.env.WINDIR,HOME:output,USERPROFILE:output,APPDATA:output,LOCALAPPDATA:output,
  TEMP:output,TMP:output,TMPDIR:output,DSH_HOME:join(output,'dsh'),ELECTRON_RUN_AS_NODE:'1'};
const child=spawn(process.execPath,[join(runtime,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'--profile','sdk-minimal','--patch',patch],
  {cwd:output,env,signal,stdio:['pipe','pipe','pipe'],windowsHide:true});
child.stdout.pipe(process.stdout);child.stderr.pipe(process.stderr);
const exit=await new Promise((done,fail)=>{child.once('error',fail);child.once('close',done);});
assert.equal(exit,0);
const evidence=JSON.parse(readFileSync(join(output,'worker.json'),'utf8'));
assert.equal(evidence.ok,true,JSON.stringify(evidence));
const unpack=file=>unzipSync(readFileSync(file));
const native=unpack(evidence.native),patched=unpack(evidence.patched),edited=unpack(evidence.edited);
for(const file of [native,patched,edited]){
  const chart=Object.entries(file).filter(([name])=>/^ppt\/charts\/chart\d+\.xml$/.test(name)).map(([,bytes])=>decode(bytes)).join('');
  assert.match(chart,/Baseline/);assert.match(chart,/Updated/);
  assert.match(chart,/>19</);assert.match(decode(file['ppt/slides/slide3.xml']),/<a:tbl>/);
  assert.ok(Object.keys(file).some(name=>/^ppt\/media\/.+\.png$/i.test(name)));
  for(const index of [1,2,3])assert.ok(file['ppt/notesSlides/notesSlide'+index+'.xml']);
}
assert.match(decode(patched['ppt/slides/slide2.xml']),/修订/);
assert.match(decode(edited['ppt/slides/slide1.xml']),/Revised Cover/);
assert.deepEqual(native['ppt/slides/slide2.xml'],edited['ppt/slides/slide2.xml']);
assert.deepEqual(native['ppt/slides/slide3.xml'],edited['ppt/slides/slide3.xml']);
for(const name of Object.keys(native).filter(name=>/^ppt\/(?:charts|notesSlides)\//.test(name)))
  assert.deepEqual(native[name],edited[name],name);
for(const path of [evidence.nativePdf,evidence.patchedPdf,evidence.editedPdf,evidence.svgPdf])
  assert.equal(decode(readFileSync(path).subarray(0,5)),'%PDF-');
const pages=['page-001.png','page-002.png','page-003.png'];
for(const path of [evidence.nativePng,evidence.patchedPng,evidence.editedPng,evidence.svgPng])
  assert.deepEqual(Object.keys(unpack(path)),pages);
const before=unpack(evidence.nativePng),after=unpack(evidence.patchedPng),editPreviews=unpack(evidence.editedPng);
for(const index of [0,2])assert.deepEqual(before[pages[index]],after[pages[index]],'Non-target page changed after patch.');
for(const index of [1,2])assert.deepEqual(before[pages[index]],editPreviews[pages[index]],'Non-target page changed after editing input copy.');
assert.notDeepEqual(before[pages[1]],after[pages[1]]);
assert.notDeepEqual(before[pages[0]],editPreviews[pages[0]]);
assert.equal(sha(readFileSync(join(workspace,'original.pptx'))),evidence.originalSha);
const summary={ok:true,diagnostic:true,version:'0.4.0',platform:process.platform,arch:process.arch,
  resources:provenance.bundle_sha256,files:provenance.file_count,legacyExternalPptMaster:false,modelRequests:0,
  nativeDeck:true,stableRevision:true,conversationReopened:true,threeSlideSvg:true,inputEdit:true,editableChartAndTable:true,notes:true,untouchedPagePixels:true,
  output,filesProduced:readdirSync(join(workspace,'GeneLoop 输出')).length};
writeFileSync(join(output,'summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary));
