import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {pptFinalTaskAcceptance,pptFinalDeliveryFiles,pptDeliveryRequested} from '../src/adapters/ppt/delivery/ppt_task_completion.ts';
import {deliveryDependencies,reusePptImages} from '../src/adapters/ppt/delivery/ppt_delivery_pipeline.ts';
import {pptLiteralEdit,verifiedLiteralPptEdits} from '../src/adapters/ppt/authoring/ppt_input_policy.ts';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
function fixture(){
 const workspace=mkdtempSync(join(tmpdir(),'ppt-final-manuscript-'));
 const output=join(workspace,'task'),files=join(workspace,'outputs/code');mkdirSync(output);mkdirSync(files,{recursive:true});
 const task={workspace,output,started_at:new Date(Date.now()-10000).toISOString(),scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},
  scene_options:{allow_output:true},stats:{ppt_work_started:true},ppt_initial_sources:{}};
 const artifacts=[['deck.pptx',Buffer.from([0x50,0x4b,3,4,0,0])],['deck.pdf',Buffer.from('%PDF-1.5 preview')],['page.png',Buffer.from('png')]].map(([name,bytes])=>{
  writeFileSync(join(files,name),bytes);return {path:'/work/outputs/'+name,bytes:bytes.length,sha256:sha(bytes)};
 });
 function present(time=Date.now()-100){
  const rows=artifacts.slice(0,2).map(file=>({...file,name:'outputs/code/'+file.path.split('/').at(-1)}));
  writeFileSync(join(output,'events.jsonl'),[
   {type:'geneloop/presented-proof',time,data:{callId:'present-current',files:rows}},
   {type:'deliverables/presented',time:time+1,data:{callId:'present-current',files:rows}}
  ].map(JSON.stringify).join('\n'));
 }
 return {workspace,output,files,task,artifacts,present};
}
function generate(f,name='deck'){
 const project=join(f.workspace,'code/projects',name);mkdirSync(join(project,'svg_output'),{recursive:true});
 writeFileSync(join(project,'svg_output/one.svg'),'<svg/>');writeFileSync(join(project,'spec_lock.md'),'spec');
 writeFileSync(join(project,'delivery.json'),'{}');return project;
}

test('native PPTX editing completes through same-turn host proofs, without a Generate receipt',()=>{
 const f=fixture();assert.equal(pptFinalTaskAcceptance(f.task).passed,false);f.present();
 assert.equal(pptFinalTaskAcceptance(f.task).selection,'native_presented_current_bytes');
 writeFileSync(join(f.files,'deck.pptx'),'changed');assert.equal(pptFinalTaskAcceptance(f.task).passed,false);
});
test('past-turn publication and corrupt native formats cannot grant completion',()=>{
 const f=fixture();f.present(Date.now()-20000);assert.equal(pptFinalTaskAcceptance(f.task).passed,false);
 writeFileSync(join(f.files,'deck.pptx'),'not pptx');f.artifacts[0].sha256=sha(Buffer.from('not pptx'));f.artifacts[0].bytes=8;
 f.present();assert.equal(pptFinalTaskAcceptance(f.task).passed,false);
});
test('a Generate manuscript still needs its own current host export',()=>{
 const f=fixture();generate(f);f.present();assert.equal(pptFinalTaskAcceptance(f.task).passed,false);
});

test('a requested generation or revision cannot succeed after only reading or emitting a textual tool call',()=>{
 for(const text of ['帮我做一个15页的ppt','继续修改第3页，保留其他页','Continue editing the same presentation. Simplify slide 2 only.',
  '请根据附件制作一份科研汇报PPT','I need help creating a slide deck from the file.']){
  const f=fixture();f.task.stats={};f.task.request={content:[{type:'text',text}]};
  assert.equal(pptDeliveryRequested(f.task),true,text);
  assert.deepEqual(pptFinalTaskAcceptance(f.task),{required:true,passed:false,reason:'ppt_requested_delivery_missing'});
 }
});

test('explicit literal edit only closes on the exact approved targets and no extra work',()=>{
 const f=fixture();f.task.scene_inputs=[{file:'original.pptx'}];
 const text='请修改附件中的 PPTX，只修改第 3 页。将“43 min”替换为“39 min”。将“92%”替换为“95%”。其他页面保持不变。交付可编辑 PPTX、同版 PDF 和逐页预览。';
 f.task.request={content:[{type:'text',text}]};
 const intent=pptLiteralEdit(f.task);
 assert.equal(intent.page,3);
 const edits=intent.replacements.map(({before,after})=>({page:3,action:'replace_text',expected_text:before,text:after}));
 assert.equal(verifiedLiteralPptEdits(intent,edits),true);
 const grouped={page:3,action:'replace_text',expected_text:'43 min\n92%\n60 completed visits',text:'39 min\n95%\n60 completed visits'};
 assert.equal(verifiedLiteralPptEdits(intent,[grouped]),true);
 assert.equal(verifiedLiteralPptEdits(intent,[{...grouped,text:grouped.text.replace('60','59')}]),false);
 assert.equal(verifiedLiteralPptEdits(intent,[{...grouped,expected_text:grouped.expected_text+'\n92%',text:grouped.text+'\n95%'}]),false);
 assert.equal(verifiedLiteralPptEdits(intent,[...edits.slice(0,1),{...edits[1],page:4}]),false);
 assert.equal(verifiedLiteralPptEdits(intent,edits.slice(0,1)),false);
 f.task.request.content[0].text=text+'再增加一页说明。';
 assert.equal(pptLiteralEdit(f.task),undefined);
});

test('identical preview images in one result are represented once without editing the input set',()=>{
 const picture=id=>({type:'image',attachment:{attachmentId:id}}),seen=new Set(['existing']);
 const blocks=[picture('new'),picture('new'),picture('existing')];
 assert.deepEqual(reusePptImages(blocks,seen).map(row=>row.type),['image','text','text']);
 assert.deepEqual([...seen],['existing']);
 assert.equal(blocks[1].type,'image');
});
test('ordinary discussion, standalone speechwriting and attachment contents do not require another PPT export',()=>{
 for(const text of ['给这份PPT配一个演讲稿','解释PPT第三页中的公式','如何制作一个PPT？','Write speaker notes for this presentation']){
  const f=fixture();f.task.stats={};f.task.request={content:[{type:'text',text},{type:'file',name:'create-ppt.pdf'}]};
  assert.equal(pptDeliveryRequested(f.task),false,text);
  assert.deepEqual(pptFinalTaskAcceptance(f.task),{required:false,passed:true});
 }
});

test('an existing deck accepts natural edit requests without repeating PPT in the instruction',()=>{
 const f=fixture();f.task.stats={};f.task.scene_inputs=[{file:'original.pptx'}];
 for(const text of ['把所有标题居中','请把封面标题替换为年度总结','Center all titles']){
  f.task.request={content:[{type:'text',text}]};
  assert.equal(pptDeliveryRequested(f.task),true,text);assert.equal(pptFinalTaskAcceptance(f.task).passed,false);
 }
 f.task.request={content:[{type:'text',text:'不用修改PPT了，解释一下第三页'}]};
 assert.equal(pptDeliveryRequested(f.task),false);
});
test('explicit current manuscript ignores unselected probe projects but not later source edits',()=>{
 const f=fixture(),project=generate(f);generate(f,'layout-probe');
 mkdirSync(join(f.output,'ppt-delivery-receipts'));
 const receipt={project:'/work/projects/deck',delivery_id:'current-host-export',mechanical_status:'passed',page_receipts:[{page:1}],
  dependencies:deliveryDependencies(f.workspace,'/work/projects/deck','/work/projects/deck/delivery.json'),artifacts:f.artifacts};
 writeFileSync(join(f.output,'ppt-delivery-receipts',('a'.repeat(64))+'.json'),JSON.stringify(receipt));
 assert.equal(pptFinalTaskAcceptance(f.task).passed,false);f.present();
 assert.equal(pptFinalTaskAcceptance(f.task).selection,'explicit_current_manuscript');
 writeFileSync(join(project,'svg_output/one.svg'),'<svg>new content</svg>');assert.equal(pptFinalTaskAcceptance(f.task).passed,false);
});

test('a finished current export is delivered without an extra present or exporting unfinished probes',()=>{
 const f=fixture(),project=generate(f);generate(f,'scratch-probe');
 f.task.request={content:[{type:'text',text:'Make a presentation from the attached paper'}]};
 f.task.stats.ppt_last_delivered_project='/work/projects/deck';
 mkdirSync(join(f.output,'ppt-delivery-receipts'));
 const receipt={project:'/work/projects/deck',delivery_id:'host-export',mechanical_status:'passed',page_receipts:[{page:1}],
  dependencies:deliveryDependencies(f.workspace,'/work/projects/deck','/work/projects/deck/delivery.json'),artifacts:f.artifacts};
 writeFileSync(join(f.output,'ppt-delivery-receipts',('a'.repeat(64))+'.json'),JSON.stringify(receipt));
 assert.equal(pptFinalTaskAcceptance(f.task).selection,'host_current_manuscript');
 assert.equal(pptFinalDeliveryFiles(f.task).size,3);
 writeFileSync(join(project,'svg_output/one.svg'),'<svg>later change</svg>');
 assert.equal(pptFinalTaskAcceptance(f.task).passed,false);assert.equal(pptFinalDeliveryFiles(f.task).size,0);
});

test('host native edit delivery is version bound and includes render artifacts without Generate sources',()=>{
 const f=fixture();f.task.request={content:[{type:'text',text:'请修改第1页标题'}]};
 const source=join(f.files,'original.pptx');writeFileSync(source,'original immutable bytes');
 mkdirSync(join(f.output,'ppt-delivery-receipts'));
 const receipt={kind:'ppt_native_edit_v1',project:'/work/outputs/native-edit',delivery_id:'native-edited',
  mechanical_status:'passed',native_source:{path:'/work/outputs/original.pptx',sha256:sha(Buffer.from('original immutable bytes'))},
  artifacts:f.artifacts,page_receipts:[{page:1}]};
 writeFileSync(join(f.output,'ppt-delivery-receipts','a'.repeat(64)+'.json'),JSON.stringify(receipt));
 assert.equal(pptFinalTaskAcceptance(f.task).passed,true);assert.equal(pptFinalDeliveryFiles(f.task).size,3);
 writeFileSync(source,'changed original');assert.equal(pptFinalTaskAcceptance(f.task).passed,false);
});
