import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,utimesSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {digest} from '../src/motif_core/runtime/online_skill_runtime.mjs';
import {assertSupportedJsonSchema,ToolRuntime} from '@deepseek-ai/dsh-tools';
import {Context} from '@deepseek-ai/cordis';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {deliveryDependencies,pptDeliveryTool,pptPreparationTool,pptPreviewTool,pptSourceState,pptTaskAcceptance,pptCurrentDeliveryFiles,pptDeliveryScene,pptDeliveryGraphTools,registerPptDeliveryTool,recordPptDeliveryReuse,managedExportProject,managedDefaultExport,directManagedProject,validatePptPublication,pptPublicationPlan,pptReviewPages,recordPptVisualObservation,cachedPptDelivery,pptImageInModel} from '../src/adapters/ppt/delivery/ppt_delivery_pipeline.ts';
import {deliveryProgress} from '../src/adapters/ppt/delivery/ppt_delivery_state.ts';
import {recordPptDeliverySources,capturePptLearningSources} from '../src/adapters/ppt/delivery/ppt_delivery_pipeline.ts';

test('optional learning evidence failure cannot revoke an otherwise current delivery',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-optional-capture-')),output=join(workspace,'task');mkdirSync(output);
 const task={workspace,output,request:{learning_eligible:true},stats:{}};
 assert.equal(capturePptLearningSources(task,{delivery_id:'valid-artifact',page_receipts:[{source:'/work/projects/missing.svg'}]}, {},{}),false);
 assert.equal(task.stats.ppt_learning_capture_failed,true);
 assert.equal(JSON.parse(readFileSync(join(output,'ppt-delivery-audit.jsonl'),'utf8')).kind,'ppt_learning_source_capture_failed');
});
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';

test('a delivered SVG remains available to delayed learning after the next chat turn edits it',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-source-freeze-')),output=join(workspace,'task');
 const folder=join(workspace,'code/projects/deck/svg_output');mkdirSync(folder,{recursive:true});mkdirSync(output);
 const raw='<svg xmlns="http://www.w3.org/2000/svg"><text>Original current content</text></svg>';
 const version=createHash('sha256').update(raw).digest('hex'),page=join(folder,'one.svg');writeFileSync(page,raw);
 const task={workspace,output,request:{learning_eligible:true}},receipt={delivery_id:'delivered',page_receipts:[{source:'/work/projects/deck/svg_output/one.svg',source_sha256:version}]};
 recordPptDeliverySources(task,receipt,{callId:'finalize-original'},{project:'/work/projects/deck'});
 writeFileSync(page,'<svg><text>New turn changed content</text></svg>');
 assert.equal(readFileSync(join(output,'reuse-evidence',version),'utf8'),raw);
 const proof=JSON.parse(readFileSync(join(output,'ppt-native-pages.jsonl'),'utf8').trim());
 assert.equal(proof.sha256,version);assert.equal(proof.call_id,'finalize-original');
 assert.throws(()=>recordPptDeliverySources(task,receipt,{callId:'stale'},{}),/delivery_source_changed/);
});

test('an evaluation opt-out does not archive extra SVG training bytes',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-source-optout-')),output=join(workspace,'task');mkdirSync(output);
 recordPptDeliverySources({workspace,output,request:{learning_eligible:false}},
  {delivery_id:'holdout',page_receipts:[{source:'/work/projects/not-read.svg',source_sha256:'a'.repeat(64)}]},
  {callId:'finalize'},{});
 assert.throws(()=>readFileSync(join(output,'reuse-evidence','a'.repeat(64))),/ENOENT/);
 assert.equal(JSON.parse(readFileSync(join(output,'ppt-native-pages.jsonl'),'utf8').trim()).delivery_id,'holdout');
});

async function modelObservation(hooks,request){
 for await(const _ of hooks.get('llm/stream')(request,async function*(){})){}
}

test('asynchronous image preparation preserves the installed LlmRuntime streaming contract',async()=>{
 const ctx=new Context();new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
 new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
 const value={task:{scene:{id:'ppt'}}};
 try{
  registerPptDeliveryTool(ctx,()=>value);
  // A free middleware terminal tests the real Runtime waterfall, not a model.
  const marker={type:'finish',finish:{kind:'stop'}};
  const terminal=ctx.on('llm/stream',async function*(){yield marker;},{global:true});
  const chunks=[];
  for await(const chunk of ctx.llm.stream({provider:'diagnostic-only',model:'diagnostic',sessionId:'s',messages:[]}))chunks.push(chunk);
  assert.deepEqual(chunks,[marker]);assert.equal(value.pptModelImages.size,0);
  terminal();
  const deny=ctx.on('llm/stream',()=>{throw Error('unapproved_task_request');},{global:true});
  assert.throws(()=>ctx.llm.stream({provider:'diagnostic-only',model:'diagnostic',sessionId:'s',messages:[]}),/unapproved_task_request/);
  deny();
 }finally{await ctx.fiber.dispose();}
});

test('literal Generate exports continue through the authorized tool and retain parent lineage',async()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-continued-'));
 mkdirSync(join(workspace,'code/projects/deck'),{recursive:true});
 const task={workspace,output:workspace,status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true}};
 let wrapper,guard,child,nextCalls=0;
 const ctx={on:(name,fn)=>{if(name==='tools/execute')wrapper=fn;},tools:{register(){},guard:fn=>guard=fn,
  async execute(execution){child=execution;return {isError:false,value:{mechanical_status:'passed',artifacts:[]}};}}};
 registerPptDeliveryTool(ctx,()=>({task}));
 const command='python3 /opt/geneloop/ppt-master/scripts/svg_to_pptx.py /work/projects/deck --with-notes';
 const execution={name:'bash',callId:'parent',token:Symbol('parent'),arguments:{command},agent:{session:{id:'s'}},signal:new AbortController().signal};
 assert.equal(guard(execution),undefined);
 const result=await wrapper(execution,()=>{nextCalls++;});
 assert.equal(nextCalls,0);assert.equal(child.parent,execution.token);assert.equal(child.name,'finalize_ppt');
 assert.equal(result.value.exitCode,0);assert.match(result.value.stdout.text,/continued_by/);
 assert.match(readFileSync(join(workspace,'ppt-delivery-audit.jsonl'),'utf8'),/arguments_sha256/);
 for(const suffix of ['; rm a',' -o /work/outputs/custom.pptx',' --roundtrip',' | tail -2'])assert.equal(directManagedProject(command+suffix),null);
});

test('failed cached exports retain repair instructions even when their intermediate artifact bytes exist',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-failed-cache-'));
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const path=join(workspace,'outputs/code/deck.pptx');writeFileSync(path,'diagnostic');
 const receipt={key:'version',mechanical_status:'failed',findings:[{rule:'speaker_notes_missing'}],artifacts:[{
  path:'/work/outputs/deck.pptx',bytes:10,sha256:createHash('sha256').update('diagnostic').digest('hex')}]};
 const task={workspace,output:workspace};
 assert.equal(cachedPptDelivery(task,receipt,'version').next_action,'repair_specific_findings_before_rechecking');
 assert.equal(cachedPptDelivery(task,{...receipt,retryable:true},'version'),null);
 const passed={...receipt,mechanical_status:'passed'};
 assert.equal(cachedPptDelivery(task,passed,'version').next_action,'present_current_delivery');
 writeFileSync(path,'changed');assert.equal(cachedPptDelivery(task,passed,'version'),null);
 assert.equal(cachedPptDelivery(task,receipt,'new-version'),null);
});

test('visual observation reuses only the exact successful image version returned to the model',async()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-image-version-'));
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const file=join(workspace,'outputs/code/page.png');writeFileSync(file,'first-image');
 const version=createHash('sha256').update('first-image').digest('hex');
 const task={workspace,output:workspace},path='/work/outputs/page.png';
 const receipt={artifacts:[{path,sha256:version}]};
 const execution={name:'read_image',callId:'image-one',arguments:{file_path:path}};
 const image={type:'image',attachment:{attachmentId:'sha256:'+version}};
 await recordPptVisualObservation(task,execution,{isError:true,content:[image]});
 await recordPptVisualObservation(task,execution,{content:[{type:'text',text:'not an image'}]});
 assert.equal(pptReviewPages(task,receipt).length,1);
 await recordPptVisualObservation(task,execution,{content:[image]});
 assert.equal(pptReviewPages(task,receipt).length,0);
 const changed=createHash('sha256').update('changed-image').digest('hex');
 assert.equal(pptReviewPages(task,{artifacts:[{path,sha256:changed}]}).length,1);
 writeFileSync(file,'changed-image');
 await recordPptVisualObservation(task,execution,{content:[image]});
 assert.equal(pptReviewPages(task,{artifacts:[{path,sha256:changed}]}).length,1);
});

test('image reuse observes the model request, preserves the first image, and leaves child previews intact',async()=>{
 const hooks=new Map(),value={task:{scene:{id:'ppt'}}};
 let projection=true;
 const options=resolveAdapterOptions({});
 registerPptDeliveryTool({on:(name,fn)=>hooks.set(name,fn),get:name=>name==='llm'?{imageRequestPricing:()=>({priceImages:refs=>refs.map(()=>({visualTokens:projection?1:0}))})}:
  {readImageRequest:async()=>({bytes:100})},tools:{register(){},guard(){}}},()=>value,{},()=>options);
 const image={type:'image',attachment:{attachmentId:'sha256:'+'a'.repeat(64)}},newImage={type:'image',attachment:{attachmentId:'sha256:'+'b'.repeat(64)}};
 const content=[{type:'text',text:'Original receipt'},image,newImage];
 const result={content,isError:false,value:{}};const execution={callId:'outer',agent:{session:{id:'owned'}}};
 await modelObservation(hooks,{sessionId:'owned',model:'deepseek-flash',messages:[]});
 assert.deepEqual(await hooks.get('tools/post-execute')(execution,result,async()=>({kind:'accept'})),{kind:'accept'});
 const previous={role:'user',content:[{type:'tool-result',content:[image]}]},saved=JSON.stringify(previous);
 await modelObservation(hooks,{sessionId:'owned',model:'deepseek-flash',messages:[previous]});
 const decision=await hooks.get('tools/post-execute')(execution,result,async()=>({kind:'accept',content}));
 assert.equal(decision.content[0].text,'Original receipt');assert.equal(decision.content[1].type,'text');
 assert.match(decision.content[1].text,/不代表质量通过/);assert.deepEqual(decision.content[2],newImage);
 assert.equal(JSON.stringify(previous),saved);assert.equal(result.content[1].type,'image');
 value.writeInternalCalls=new Set(['outer']);
 assert.deepEqual(await hooks.get('tools/post-execute')(execution,result,async()=>({kind:'accept'})),{kind:'accept'});
 await modelObservation(hooks,{sessionId:'owned',model:'deepseek-flash',messages:[]});
 value.writeInternalCalls.clear();
 assert.deepEqual(await hooks.get('tools/post-execute')(execution,result,async()=>({kind:'accept'})),{kind:'accept'},'After compaction removes the image, rereading supplies pixels again');
 projection=false;await modelObservation(hooks,{sessionId:'owned',model:'deepseek-flash',messages:[previous]});
 assert.deepEqual(await hooks.get('tools/post-execute')(execution,result,async()=>({kind:'accept'})),{kind:'accept'},'An adapter-offloaded or text-only occurrence cannot suppress a new image');
 projection=true;options.maxInlineRequestImageBytes=1;
 await modelObservation(hooks,{sessionId:'owned',model:'deepseek-flash',messages:[previous]});
 assert.deepEqual(await hooks.get('tools/post-execute')(execution,result,async()=>({kind:'accept'})),{kind:'accept'},'Files API failure and tighter inline fallback must preserve ordinary rereading');
});

test('same-conversation observations survive a follow-up but cannot authorize another workspace or unseen pixels',async()=>{
 const root=mkdtempSync(join(tmpdir(),'ppt-followup-images-')),workspace=join(root,'workspace');
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const version=createHash('sha256').update('pixels').digest('hex'),ref='sha256:'+'c'.repeat(64),path='/work/outputs/page.png';
 writeFileSync(join(workspace,'outputs/code/page.png'),'pixels');
 const first={workspace,output:join(root,'tasks/one')},second={workspace,output:join(root,'tasks/two')};
 mkdirSync(first.output,{recursive:true});mkdirSync(second.output,{recursive:true});
 await recordPptVisualObservation(first,{name:'read_image',callId:'one',arguments:{file_path:path}},
  {content:[{type:'image',attachment:{attachmentId:ref}}]},{saveImage:async()=>({attachmentId:ref})});
 const artifact={path,sha256:version},images=new Set([ref]);
 assert.equal(pptImageInModel(second,artifact,images),true);
 assert.equal(pptImageInModel(second,artifact,new Set()),false);
 assert.equal(pptImageInModel({...second,workspace:join(root,'someone-else')},artifact,images),false);
 assert.equal(pptImageInModel(second,{...artifact,sha256:'d'.repeat(64)},images),false);
});

test('an identical loaded skill is referenced once while its canonical entry and source catalog remain intact',async()=>{
 const hooks=new Map(),value={task:{scene:{id:'ppt'}}};
 registerPptDeliveryTool({on:(n,f)=>hooks.set(n,f),tools:{register(){},guard(){}}},()=>value);
 const text='Exact integrated skill instructions',entry={text,source_id:'versioned-skill',files:[{name:'current.pdf'}],runtime_policy:{text:'Current policy'}};
 const result={value:entry,content:[{type:'text',text:JSON.stringify(entry)}]},execution={name:'mcp__ppt_master__read_skill_entry',agent:{session:{id:'s'}}};
 await modelObservation(hooks,{sessionId:'s',messages:[{content:[{type:'tool-result',content:[{type:'text',text:'<skill_content name="ppt-master">'+text+'</skill_content>'}]}]}]});
 const decision=await hooks.get('tools/post-execute')(execution,result,async()=>({kind:'accept'}));
 const view=JSON.parse(decision.content[0].text);
 assert.equal(view.text,undefined);assert.equal(view.text_reused_from,'already_loaded_native_ppt_master_skill');
 assert.deepEqual(view.files,entry.files);assert.deepEqual(view.runtime_policy,entry.runtime_policy);assert.equal(result.value.text,text);
 const changed={...result,value:{...entry,text:text+' changed'}};
 assert.deepEqual(await hooks.get('tools/post-execute')(execution,changed,async()=>({kind:'accept'})),{kind:'accept'});
});

test('normalized image observations bind the current source bytes before asynchronous storage',async()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-image-normalized-'));
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const file=join(workspace,'outputs/code/page.png');writeFileSync(file,'source-image');
 const version=createHash('sha256').update('source-image').digest('hex');
 const task={workspace,output:workspace},path='/work/outputs/page.png';
 const normalized='sha256:'+'a'.repeat(64),execution={name:'read_image',arguments:{file_path:path}};
 const result={content:[{type:'image',attachment:{attachmentId:normalized}}]};
 await recordPptVisualObservation(task,execution,result,{async saveImage({data}){
  assert.equal(data.toString(),'source-image');writeFileSync(file,'later-change');
  return {attachmentId:normalized};
 }});
 assert.equal(pptReviewPages(task,{artifacts:[{path,sha256:version}]}).length,0);
 const later=createHash('sha256').update('later-change').digest('hex');
 assert.equal(pptReviewPages(task,{artifacts:[{path,sha256:later}]}).length,1);
});

test('unchanged objective defects converge while actual improvement or new content permits repair',()=>{
 const failed={mechanical_status:'failed',page_receipts:[{text_sha256:'content'}],findings:[{rule:'text_contrast',page:1,object:'title',severity:'error',ratio:1.9}]};
 assert.equal(deliveryProgress(failed,failed).status,'stalled');
 assert.equal(deliveryProgress(failed,{...failed,findings:[{...failed.findings[0],ratio:3.0}]}).status,'repair_needed');
 assert.equal(deliveryProgress(failed,{...failed,page_receipts:[{text_sha256:'new-content'}]}).status,'repair_needed');
 assert.equal(deliveryProgress(failed,{mechanical_status:'passed'}).status,'checked');
 const detail={...failed,findings:[{rule:'text_overflow',severity:'error',page:1,object:'title',detail:'x=10, overflow=12%'}]};
 assert.equal(deliveryProgress(detail,{...detail,findings:[{...detail.findings[0],detail:'x=11, overflow=12%'}]}).status,'stalled');
});

test('shared delivery tool is offered to both PPT modes and retains the original Graph surface',()=>{
 assertSupportedJsonSchema(pptDeliveryTool.parameters);
 assertSupportedJsonSchema(pptPreparationTool.parameters);
 const scene={id:'ppt',ppt_execution_strategy:'ppt_master',allowed_tools:['bash']};
 assert.equal(pptDeliveryScene(scene,false),scene);
 const enabled=pptDeliveryScene(scene,true);
 assert.ok(enabled.allowed_tools.includes('finalize_ppt'));
 assert.ok(enabled.allowed_tools.includes('prepare_ppt'));
 assert.deepEqual(pptDeliveryGraphTools(enabled,[{name:'bash'},pptDeliveryTool]),[{name:'bash'}]);
 assert.throws(()=>pptDeliveryGraphTools(scene,[pptDeliveryTool]),/schema_changed/);
});

test('Generate exporter routing leaves source-preserving workflows and help available',()=>{
 const command='python3 /opt/geneloop/ppt-master/scripts/svg_to_pptx.py "/work/projects/deck" -o /work/outputs/deck.pptx';
 assert.equal(managedExportProject(command),'/work/projects/deck');
 assert.equal(managedExportProject(command+' --roundtrip'),null);
 assert.equal(managedExportProject(command+' --source authoring-svg-flat'),null);
 assert.equal(managedExportProject('cat /opt/geneloop/ppt-master/scripts/svg_to_pptx.py'),null);
 assert.equal(managedExportProject('python3 /opt/geneloop/ppt-master/scripts/svg_to_pptx.py --help'),null);
 assert.equal(managedDefaultExport('cd /work && P=/work/projects/deck && python3 /opt/geneloop/ppt-master/scripts/svg_to_pptx.py $P 2>&1 | tail -25'),true);
 assert.equal(managedDefaultExport('F=$(python3 /opt/geneloop/ppt-master/scripts/svg_to_pptx.py .)'),true);
 assert.equal(managedDefaultExport('export SKILL_DIR=/opt/geneloop/ppt-master; P=/work/projects/deck; python3 "$SKILL_DIR/scripts/svg_to_pptx.py" "$P"; echo "EXIT:$?"'),true);
 assert.equal(managedDefaultExport('python3 "${SKILL_DIR}/scripts/svg_to_pptx.py" "$P"'),true);
 assert.equal(managedDefaultExport(command+' --source=authoring-svg-flat'),false);
 assert.equal(managedDefaultExport(command+' --source=svg_output'),true);
});

test('the actual Harness guard redirects supported Generate exports to the shared entry',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-export-guard-'));
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});writeFileSync(join(project,'spec_lock.md'),'spec');
 let guard;const task={status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},workspace,output:workspace};
 registerPptDeliveryTool({tools:{guard:fn=>guard=fn,register(){}}},()=>({task}));
 const execution={name:'bash',agent:{session:{id:'current'}},arguments:{command:'python3 /opt/geneloop/ppt-master/scripts/svg_to_pptx.py /work/projects/deck'}};
 assert.match(guard(execution),/finalize_ppt/);
 assert.match(guard({...execution,arguments:{command:'P=/work/projects/deck && python3 /opt/geneloop/ppt-master/scripts/svg_to_pptx.py $P'}}),/finalize_ppt/);
 assert.match(guard({...execution,arguments:{command:'export SKILL_DIR=/opt/geneloop/ppt-master; P=/work/projects/deck; python3 "$SKILL_DIR/scripts/svg_to_pptx.py" "$P"; echo "EXIT:$?"'}}),/finalize_ppt/);
 assert.equal(guard({...execution,arguments:{command:execution.arguments.command+' --roundtrip'}}),undefined);
 assert.match(guard({...execution,arguments:{command:'python3 /opt/geneloop/ppt-master/scripts/svg_quality_checker.py /work/projects/deck --stage final --json'}}),/finalize_ppt/);
 assert.match(guard({...execution,arguments:{command:'python3 -c "import cairosvg; cairosvg.svg2png(url=\'/work/projects/deck/svg_output/slide_01.svg\', output_width=2048)"'}}),/finalize_ppt/);
 assert.match(guard({...execution,arguments:{command:'rsvg-convert /work/projects/deck/svg_output/slide_01.svg -o /work/preview.png'}}),/finalize_ppt/);
 assert.equal(guard({...execution,arguments:{command:'python3 -c "import cairosvg; cairosvg.svg2png(url=\'/work/inputs/diagram.svg\')"'}}),undefined);
});

test('delivery dependencies change on source, manifest and notes revisions',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-delivery-deps-'));
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});
 writeFileSync(join(project,'delivery.json'),'{}');writeFileSync(join(project,'svg_output/slide_01.svg'),'<svg/>');
 const first=deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json');
 assert.ok(first.files.some(row=>row.path==='svg_output/slide_01.svg'));
 writeFileSync(join(project,'scratch-debug.txt'),'diagnostic scratch');
 assert.deepEqual(first.files,deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json').files);
 mkdirSync(join(project,'images'));writeFileSync(join(project,'images/figure.png'),'first asset');
 writeFileSync(join(project,'svg_output/slide_01.svg'),'<svg><image href="../images/figure.png"/></svg>');
 const withAsset=deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json');
 assert.ok(withAsset.files.some(row=>row.path==='images/figure.png'));
 writeFileSync(join(project,'images/figure.png'),'updated asset');
 assert.notDeepEqual(withAsset.files,deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json').files);
 writeFileSync(join(project,'svg_output/slide_01.svg'),'<svg/>');
 mkdirSync(join(project,'validation'));
 writeFileSync(join(project,'validation/presentation.report.json'),'generated export report');
 const generated=deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json');
 assert.deepEqual(first.files,generated.files);
 writeFileSync(join(project,'validation/source-review.json'),'source review');
 const review=deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json');
 assert.notDeepEqual(first.files,review.files);
 writeFileSync(join(project,'svg_output/slide_01.svg'),'<svg>changed</svg>');
 const second=deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json');
 assert.notDeepEqual(first.files,second.files);
 mkdirSync(join(project,'notes'));writeFileSync(join(project,'notes/total.md'),'Current notes');writeFileSync(join(project,'notes/slide_01.md'),'Derived notes');
 writeFileSync(join(project,'delivery.json'),JSON.stringify({notes_source:'total'}));
 const total=deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json');
 assert.ok(total.files.some(row=>row.path==='notes/total.md'));
 assert.ok(!total.files.some(row=>row.path==='notes/slide_01.md'));
 assert.throws(()=>deliveryDependencies(workspace,'/work/projects/deck','/work/inputs/other.json'),/changed|outside/);
});

test('delivery execution checks active task and output authorization',async()=>{
 let tool,current;
 registerPptDeliveryTool({tools:{register:value=>tool=value}},()=>current);
 for(const value of [null,{task:{status:'completed'}},{task:{status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:false}}}]){
  current=value;await assert.rejects(()=>tool.execute({},{agent:{session:{id:'current'}}}),/not_authorized/);
 }
});

test('font diagnostics route through the deterministic role calibration entry',()=>{
 let guard;
 const task={status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'}};
 registerPptDeliveryTool({tools:{guard:fn=>guard=fn,register(){}}},()=>({task}));
 const execution=command=>({name:'bash',agent:{session:{id:'s'}},arguments:{command}});
 assert.match(guard(execution('fc-match "Noto Sans CJK SC"')),/prepare_ppt/);
 assert.match(guard(execution('python3 /opt/geneloop/ppt-master/scripts/text_measure.py calibrate /work/projects/deck --outline')),/prepare_ppt/);
 assert.match(guard(execution('python3 -c "import text_measure as tm; print(tm.measure_text)"')),/prepare_ppt/);
 assert.match(guard(execution('python3 -c "from text_measure import wrap_text, measure_text"')),/prepare_ppt/);
 assert.match(guard(execution('python3 -c "import fitz; p=fitz.open(\'/work/outputs/presentation.pdf\')[0]; p.get_text(\'rawdict\')"')),/finalize_ppt/);
 assert.equal(guard(execution('python3 -c "import fitz; p=fitz.open(\'/work/inputs/paper.pdf\')[0]; p.get_text(\'dict\')"')),undefined);
 assert.equal(guard(execution('cat /work/projects/deck/spec_lock.md')),undefined);
});

test('PPT inspection schema is native and shared by both modes without becoming a learned Graph edge',()=>{
 assertSupportedJsonSchema(pptPreviewTool.parameters);
 for(const mode of ['baseline','execute']){
  const scene=pptDeliveryScene({id:'ppt',ppt_execution_strategy:'ppt_master',allowed_tools:[],mode},true);
  assert.ok(scene.allowed_tools.includes('inspect_ppt_region'));
  assert.deepEqual(pptDeliveryGraphTools(scene,[pptPreviewTool]),[]);
 }
});

test('completion requires a current complete export after deck work, while unchanged conversation is text-only',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-completion-'));
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});
 mkdirSync(join(project,'notes'));writeFileSync(join(project,'notes/one.md'),'speaker notes');
 writeFileSync(join(project,'delivery.json'),'{}');writeFileSync(join(project,'spec_lock.md'),'spec');
 writeFileSync(join(project,'svg_output/one.svg'),'<svg/>');
 const output=join(workspace,'task');mkdirSync(join(output,'ppt-delivery-receipts'),{recursive:true});
 const task={workspace,output,scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true},stats:{},ppt_initial_sources:{}};
 assert.equal(pptTaskAcceptance(task).reason,'ppt_delivery_not_delivered');
 task.ppt_initial_sources=pptSourceState(workspace);
 assert.deepEqual(pptTaskAcceptance(task),{required:false,passed:true},'a speech/script discussion need not export another deck');
 task.stats.ppt_work_started=true;
 assert.equal(pptTaskAcceptance(task).passed,false);
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const artifacts=['deck.pptx','deck.pdf','page-001.png'].map(name=>{
  const bytes=Buffer.from(name);writeFileSync(join(workspace,'outputs/code',name),bytes);
  return {path:'/work/outputs/'+name,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
 });
 const receipt={project:'/work/projects/deck',delivery_id:'host',mechanical_status:'passed',page_receipts:[{page:1}],
  dependencies:deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json'),artifacts};
 const path=join(output,'ppt-delivery-receipts','a'.repeat(64)+'.json');
 writeFileSync(path,JSON.stringify({...receipt,mechanical_status:'failed'}));assert.equal(pptTaskAcceptance(task).passed,false);
 writeFileSync(path,JSON.stringify({...receipt,artifacts:artifacts.slice(0,2)}));assert.equal(pptTaskAcceptance(task).passed,false);
 writeFileSync(path,JSON.stringify(receipt));assert.equal(pptTaskAcceptance(task).passed,true);
 assert.deepEqual([...pptCurrentDeliveryFiles(task).keys()].map(p=>p.split(/[\\/]/).at(-1)),['deck.pptx','deck.pdf','page-001.png']);
 writeFileSync(join(workspace,'outputs/code/deck.pptx'),'tampered');assert.equal(pptCurrentDeliveryFiles(task).size,0);
 writeFileSync(join(workspace,'outputs/code/deck.pptx'),'deck.pptx');
 writeFileSync(join(project,'notes/one.md'),'changed notes');assert.equal(pptTaskAcceptance(task).passed,false,'old export cannot cover new notes');
 assert.equal(pptCurrentDeliveryFiles(task).size,0,'a current receipt never covers later edits');
});

test('a valid old deck cannot hide another unfinished project or corrupt exported bytes',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-multi-completion-'));
 const task={workspace,output:workspace,scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true},stats:{},ppt_initial_sources:{}};
 mkdirSync(join(workspace,'code/projects/new/svg_output'),{recursive:true});writeFileSync(join(workspace,'code/projects/new/svg_output/one.svg'),'<svg/>');
 assert.equal(pptTaskAcceptance(task).passed,false);
 assert.equal(pptTaskAcceptance({...task,scene:{id:'other'}}).required,false);
 assert.equal(pptTaskAcceptance({...task,scene_options:{allow_output:false}}).required,false);
});

test('completion rejects changed exported bytes, unexported second projects and deleted source decks',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-export-coverage-'));
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});
 writeFileSync(join(project,'delivery.json'),'{}');writeFileSync(join(project,'svg_output/one.svg'),'<svg/>');
 const output=join(workspace,'task');mkdirSync(join(output,'ppt-delivery-receipts'),{recursive:true});
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const artifacts=['deck.pptx','deck.pdf','page-001.png'].map(name=>{
  const bytes=Buffer.from(name);writeFileSync(join(workspace,'outputs/code',name),bytes);
  return {path:'/work/outputs/'+name,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
 });
 const task={workspace,output,scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true},stats:{},ppt_initial_sources:{}};
 const receipt={project:'/work/projects/deck',delivery_id:'current',mechanical_status:'passed',page_receipts:[{page:1}],artifacts,
  dependencies:deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json')};
 writeFileSync(join(output,'ppt-delivery-receipts','a'.repeat(64)+'.json'),JSON.stringify(receipt));
 assert.equal(pptTaskAcceptance(task).passed,true);
 const artifact=join(workspace,'outputs/code/deck.pptx');writeFileSync(artifact,'corrupt');
 assert.equal(pptTaskAcceptance(task).passed,false);writeFileSync(artifact,'deck.pptx');
 task.ppt_initial_sources=pptSourceState(workspace);
 mkdirSync(join(workspace,'code/projects/new/svg_output'),{recursive:true});writeFileSync(join(workspace,'code/projects/new/svg_output/one.svg'),'<svg/>');
 assert.equal(pptTaskAcceptance(task).passed,false,'an unchanged exported deck cannot cover unfinished new pages');
 task.ppt_initial_sources=pptSourceState(workspace);
 rmSync(join(workspace,'code/projects/new'),{recursive:true});
 assert.equal(pptTaskAcceptance(task).passed,false,'source deletion is a change, not a text-only conversation');
});

test('native preview requires active ownership, output permission and a current exported PNG',async()=>{
 const tools=new Map();let current;
 registerPptDeliveryTool({tools:{register:tool=>tools.set(tool.name,tool)}},()=>current);
 const preview=tools.get(pptPreviewTool.name),execution={agent:{session:{id:'s'}}};
 for(const owner of [null,{task:{status:'completed'}},{task:{status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:false}}}]){
  current=owner;await assert.rejects(()=>preview.execute({path:'/work/outputs/page.png'},execution),/not_authorized/);
 }
 const workspace=mkdtempSync(join(tmpdir(),'ppt-preview-owner-'));
 current={task:{workspace,output:workspace,status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true}}};
 await assert.rejects(()=>preview.execute({path:'/work/outputs/page.png'},execution),/current_export_png/);
});

test('publication requires a current export and rejects source edits after export',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-publish-'));
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});
 writeFileSync(join(project,'delivery.json'),'{}');writeFileSync(join(project,'spec_lock.md'),'spec');
 writeFileSync(join(project,'svg_output/slide_01.svg'),'<svg/>');
 const output=join(workspace,'task');mkdirSync(output);
 const task={workspace,output};
 assert.match(validatePptPublication(task,[{path:'/work/outputs/result.pptx'}]),/finalize_ppt/);
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});writeFileSync(join(workspace,'outputs/code/result.pptx'),'pptx-bytes');
 const sha256=createHash('sha256').update('pptx-bytes').digest('hex');
 mkdirSync(join(output,'ppt-delivery-receipts'));
 const receipt={project:'/work/projects/deck',mechanical_status:'passed',
  dependencies:deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json'),
  artifacts:[{path:'/work/outputs/result.pptx',sha256,bytes:10}]};
 writeFileSync(join(output,'ppt-delivery-receipts','a'.repeat(64)+'.json'),JSON.stringify(receipt));
 assert.equal(validatePptPublication(task,[{path:'/work/outputs/result.pptx'}]),undefined);
 writeFileSync(join(project,'svg_output/slide_01.svg'),'<svg>new source</svg>');
 assert.match(validatePptPublication(task,[{path:'/work/outputs/result.pptx'}]),/finalize_ppt/);
});

function publicationFixture(){
 const workspace=mkdtempSync(join(tmpdir(),'ppt-publication-version-')),output=join(workspace,'task');
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});mkdirSync(join(project,'notes'));
 writeFileSync(join(project,'delivery.json'),'{}');writeFileSync(join(project,'spec_lock.md'),'spec');
 writeFileSync(join(project,'svg_output/one.svg'),'<svg/>');writeFileSync(join(project,'notes/one.md'),'notes');
 mkdirSync(join(output,'ppt-delivery-receipts'),{recursive:true});mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const artifacts=['deck.pptx','deck.pdf','one.png'].map(name=>{
  writeFileSync(join(workspace,'outputs/code',name),name);
  return {path:'/work/outputs/'+name,bytes:name.length,sha256:createHash('sha256').update(name).digest('hex')};
 });
 const receipt={delivery_id:'current',project:'/work/projects/deck',mechanical_status:'passed',artifacts,page_receipts:[{page:1}],
  dependencies:deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json')};
 const path=join(output,'ppt-delivery-receipts','a'.repeat(64)+'.json');writeFileSync(path,JSON.stringify(receipt));
 return {workspace,output,project,receipt,path,files:artifacts.map(({path})=>({path})),task:{workspace,output}};
}

test('successful PPT publication concludes the native tool turn while a failed publication does not',async()=>{
 const f=publicationFixture();Object.assign(f.task,{status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true}});
 const ctx=new Context();new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
 new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
 try{
  const loop=new AgentLoop(ctx,{agents:[]}),agent=await loop.create('ppt-terminal-'+crypto.randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
  let fail=false;
  ctx.tools.register({name:'present',description:'Diagnostic',parameters:{type:'object',properties:{files:{type:'array',items:{type:'object'}}},required:['files']},
   output:{schema:{type:'object'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},
   execute:async()=>{if(fail)throw Error('injected_publication_failure');return {delivered:true};}});
  registerPptDeliveryTool(ctx,()=>({task:f.task}));
  const call=()=>ctx.tools.execute({agent,name:'present',arguments:{files:f.files},callId:crypto.randomUUID(),signal:new AbortController().signal});
  const result=await call();assert.equal(result.isError,false,JSON.stringify(result));assert.equal(result.concludesTurn,true);
  fail=true;const failure=await call();assert.equal(failure.isError,true);assert.equal(failure.concludesTurn,undefined);
 }finally{await ctx.fiber.dispose();}
});

test('publication consumes registered export versions without repeating runtime/report certification or trusting mtime',()=>{
 const f=publicationFixture();
 try{
  f.receipt.dependencies.pipeline_sha256='old-runtime';f.receipt.dependencies.environment={old:true};
  writeFileSync(f.path,JSON.stringify(f.receipt));
  // Old publication rescanned these unrelated project files and rejected them.
  mkdirSync(join(f.project,'validation'));writeFileSync(join(f.project,'validation/extra-diagnostic.json'),'new report');
  writeFileSync(join(f.project,'scratch.svg'),'scratch outside the manuscript');
  utimesSync(join(f.project,'svg_output/one.svg'),new Date('2020-01-01'),new Date('2020-01-01'));
  assert.equal(validatePptPublication(f.task,f.files),undefined);
  assert.equal(validatePptPublication(f.task,f.files),undefined,'repeat delivery adds no export or quality review');
  writeFileSync(join(f.project,'notes/one.md'),'changed');
  assert.match(validatePptPublication(f.task,f.files),/finalize_ppt/);
  writeFileSync(join(f.project,'notes/one.md'),'notes');
  writeFileSync(join(f.project,'svg_output/two.svg'),'<svg/>');
  assert.match(validatePptPublication(f.task,f.files),/finalize_ppt/,'added pages invalidate even when existing bytes are unchanged');
  rmSync(join(f.project,'svg_output/two.svg'));
  assert.equal(validatePptPublication(f.task,f.files),undefined,'unchanged manuscript and previews remain reusable');
  writeFileSync(join(f.workspace,'outputs/code/deck.pptx'),'bad');
  assert.match(validatePptPublication(f.task,f.files),/finalize_ppt/);
 }finally{rmSync(f.workspace,{recursive:true,force:true});}
});

test('missing, stale and unregistered optional PNGs cannot block a current PPTX/PDF bundle',()=>{
 const f=publicationFixture();
 try{
  const extra={path:'/work/outputs/detail.png'};
  let plan=pptPublicationPlan(f.task,[...f.files,extra]);
  assert.deepEqual(plan.files,f.files);assert.equal(plan.omitted.length,1);assert.equal(plan.error,undefined);
  writeFileSync(join(f.workspace,'outputs/code/detail.png'),'unregistered');
  plan=pptPublicationPlan(f.task,[...f.files,extra]);assert.equal(plan.error,undefined);assert.equal(plan.omitted.length,1);
  assert.match(validatePptPublication(f.task,[extra]),/finalize_ppt/,'no valid main file must not be presented as success');
  assert.match(validatePptPublication(f.task,[...f.files,{path:'/work/outputs/old.pptx'}]),/finalize_ppt/,'stale core deliverables still fail');
  const disguised={path:'/work/outputs/not-a-pptx.pptx'};
  writeFileSync(join(f.workspace,'outputs/code/not-a-pptx.pptx'),'one.png');
  assert.match(validatePptPublication(f.task,[disguised]),/finalize_ppt/,'matching preview bytes cannot masquerade as PPTX');
 }finally{rmSync(f.workspace,{recursive:true,force:true});}
});

test('the host current-export registration supersedes older output bytes even if source content and timestamps match',()=>{
 const f=publicationFixture();
 try{
  const old={...f.receipt,delivery_id:'old-profile',artifacts:[{path:'/work/outputs/older.pptx',bytes:5,
   sha256:createHash('sha256').update('older').digest('hex')}]};
  writeFileSync(join(f.workspace,'outputs/code/older.pptx'),'older');
  writeFileSync(join(f.output,'ppt-delivery-receipts','b'.repeat(64)+'.json'),JSON.stringify(old));
  const registration=join(f.output,'ppt-delivery-receipts','current-'+digest(f.receipt.project)+'.json');
  writeFileSync(registration,JSON.stringify(f.receipt));
  assert.equal(validatePptPublication(f.task,f.files),undefined);
  assert.match(validatePptPublication(f.task,[{path:'/work/outputs/older.pptx'}]),/finalize_ppt/);
  writeFileSync(registration,'broken');
  assert.match(validatePptPublication(f.task,f.files),/finalize_ppt/,'a broken current registration cannot resurrect stale receipts');
 }finally{rmSync(f.workspace,{recursive:true,force:true});}
});

test('component execution alone cannot count as final delivery reuse',()=>{
 const output=mkdtempSync(join(tmpdir(),'ppt-delivery-lineage-'));
 const audit=join(output,'artifact-motif-audit.jsonl');
 writeFileSync(audit,JSON.stringify({kind:'component_executed',program_id:'component',receipt:{files:[{path:'page.svg',sha256:'source'}]}})+'\n');
 mkdirSync(join(output,'ppt-delivery-receipts'));
 const receipt={delivery_id:'delivery',mechanical_status:'passed',artifacts:[{path:'/work/outputs/result.pptx',sha256:'deck'}],
  page_receipts:[{page:1,source_sha256:'different-source'}]};
 const file=join(output,'ppt-delivery-receipts','a'.repeat(64)+'.json');
 writeFileSync(file,JSON.stringify(receipt));
 const task={output,stats:{}};
 recordPptDeliveryReuse(task,[{sha256:'deck'}]);assert.equal(task.stats.component_used_in_delivery,undefined);
 receipt.page_receipts[0].source_sha256='source';writeFileSync(file,JSON.stringify(receipt));
 recordPptDeliveryReuse(task,[{sha256:'deck'}]);recordPptDeliveryReuse(task,[{sha256:'deck'}]);
 assert.equal(task.stats.component_used_in_delivery,1);
 assert.equal(readFileSync(audit,'utf8').split('\n').filter(Boolean).length,2);
});

test('publication accepts a host-bound crop and its identical copy, but rejects stale, foreign and altered previews',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-preview-publish-')),output=join(workspace,'task');
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});
 writeFileSync(join(project,'delivery.json'),'{}');writeFileSync(join(project,'svg_output/one.svg'),'<svg/>');
 mkdirSync(join(output,'ppt-delivery-receipts'),{recursive:true});mkdirSync(join(output,'ppt-preview-receipts'));
 mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const artifact=(name,bytes)=>{writeFileSync(join(workspace,'outputs/code',name),bytes);return {path:'/work/outputs/'+name,bytes:Buffer.byteLength(bytes),sha256:createHash('sha256').update(bytes).digest('hex')};};
 const original=artifact('page.png','original png'),preview=artifact('ppt-preview-crop.png','cropped png');
 const task={workspace,output,request:{task_id:'a'.repeat(32)}};
 const delivery={delivery_id:'current',project:'/work/projects/deck',mechanical_status:'passed',artifacts:[original],
  dependencies:deliveryDependencies(workspace,'/work/projects/deck','/work/projects/deck/delivery.json')};
 writeFileSync(join(output,'ppt-delivery-receipts','a'.repeat(64)+'.json'),JSON.stringify(delivery));
 assert.match(validatePptPublication(task,[preview]),/finalize_ppt/,'mere presence of an output PNG is insufficient');
 const receipt={kind:'ppt_preview_v1',task_id:task.request.task_id,delivery_id:delivery.delivery_id,
  dependencies_sha256:digest(delivery.dependencies),source_path:original.path,source_sha256:original.sha256,preview};
 const path=join(output,'ppt-preview-receipts','11111111-1111-4111-8111-111111111111.json');
 writeFileSync(path,JSON.stringify(receipt));assert.equal(validatePptPublication(task,[preview]),undefined);
 const copy=artifact('region-copy.png','cropped png');assert.equal(validatePptPublication(task,[copy]),undefined);
 assert.match(validatePptPublication({...task,request:{task_id:'b'.repeat(32)}},[preview]),/finalize_ppt/);
 writeFileSync(join(workspace,'outputs/code/ppt-preview-crop.png'),'tampered');assert.match(validatePptPublication(task,[copy]),/finalize_ppt/);
 writeFileSync(join(workspace,'outputs/code/ppt-preview-crop.png'),'cropped png');
 writeFileSync(join(project,'svg_output/one.svg'),'<svg>changed</svg>');assert.match(validatePptPublication(task,[preview]),/finalize_ppt/);
});

test('host annotation repairs in failed exports retain final component provenance',()=>{
 const output=mkdtempSync(join(tmpdir(),'ppt-delivery-annotation-lineage-'));
 const audit=join(output,'artifact-motif-audit.jsonl'),before='a'.repeat(64),middle='b'.repeat(64),after='c'.repeat(64);
 writeFileSync(audit,JSON.stringify({kind:'component_executed',program_id:'component',receipt:{files:[{path:'page.svg',sha256:before}]}})+'\n');
 const folder=join(output,'ppt-delivery-receipts');mkdirSync(folder);
 const source='/work/projects/deck/svg_output/slide_01.svg',project='/work/projects/deck';
 const repair=(from,to)=>({source,before_sha256:from,after_sha256:to,operation:'module_annotations_only_v1'});
 writeFileSync(join(folder,'a'.repeat(64)+'.json'),JSON.stringify({project,mechanical_status:'failed',applied_annotation_repairs:[repair(before,middle)]}));
 writeFileSync(join(folder,'b'.repeat(64)+'.json'),JSON.stringify({project,mechanical_status:'failed',applied_annotation_repairs:[repair(middle,after)]}));
 const final={project,delivery_id:'final',mechanical_status:'passed',artifacts:[{path:'/work/outputs/deck.pptx',sha256:'deck'}],
  page_receipts:[{page:1,source,source_sha256:after}]};
 writeFileSync(join(folder,'c'.repeat(64)+'.json'),JSON.stringify(final));
 const task={output,stats:{}};recordPptDeliveryReuse(task,[{sha256:'deck'}]);
 assert.equal(task.stats.component_used_in_delivery,1);
 const second={...final,delivery_id:'changed',page_receipts:[{page:1,source,source_sha256:'d'.repeat(64)}]};
 writeFileSync(join(folder,'d'.repeat(64)+'.json'),JSON.stringify(second));
 recordPptDeliveryReuse(task,[{sha256:'deck'}]);
 assert.equal(task.stats.component_used_in_delivery,1);
});
