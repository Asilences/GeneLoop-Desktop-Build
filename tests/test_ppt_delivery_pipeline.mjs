import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
import {deliveryDependencies,pptDeliveryTool,pptPreparationTool,pptDeliveryScene,pptDeliveryGraphTools,registerPptDeliveryTool,recordPptDeliveryReuse,managedExportProject,managedDefaultExport,validatePptPublication} from '../src/adapters/ppt_delivery_pipeline.ts';
import {deliveryProgress} from '../src/adapters/ppt_delivery_state.ts';

test('unchanged objective defects converge while actual improvement or new content permits repair',()=>{
 const failed={mechanical_status:'failed',page_receipts:[{text_sha256:'content'}],findings:[{rule:'text_contrast',page:1,object:'title',severity:'error',ratio:1.9}]};
 assert.equal(deliveryProgress(failed,failed).status,'stalled');
 assert.equal(deliveryProgress(failed,{...failed,findings:[{...failed.findings[0],ratio:3.0}]}).status,'repair_needed');
 assert.equal(deliveryProgress(failed,{...failed,page_receipts:[{text_sha256:'new-content'}]}).status,'repair_needed');
 assert.equal(deliveryProgress(failed,{mechanical_status:'passed'}).status,'checked');
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
 assert.match(guard(execution('python3 -c "import fitz; p=fitz.open(\'/work/outputs/presentation.pdf\')[0]; p.get_text(\'rawdict\')"')),/finalize_ppt/);
 assert.equal(guard(execution('python3 -c "import fitz; p=fitz.open(\'/work/inputs/paper.pdf\')[0]; p.get_text(\'dict\')"')),undefined);
 assert.equal(guard(execution('cat /work/projects/deck/spec_lock.md')),undefined);
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
