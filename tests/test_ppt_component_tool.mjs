/** Routing and denial diagnostics. These do not measure model use or savings. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
import {pptComponentScene,pptComponentGraphTools,pptComponentTool,registerPptComponentTool,installComponentPage,componentRequest} from '../src/adapters/ppt_component_tool.ts';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';

test('certified page tool is a native supported schema and only offered to Execute PPT',()=>{
 assertSupportedJsonSchema(pptComponentTool.parameters);
 const scene={id:'ppt',ppt_execution_strategy:'ppt_master',allowed_tools:['bash','mcp__ppt_master__pin_source']};
 for(const [mode,available] of [['baseline',true],['shadow',true],['execute',false]])assert.equal(pptComponentScene(scene,mode,available),scene);
 assert.equal(pptComponentScene({...scene,id:'other'},'execute',true).allowed_tools.length,2);
 const offered=pptComponentScene(scene,'execute',true);
 assert.ok(offered.allowed_tools.includes(pptComponentTool.name));
 assert.equal(offered.allowed_tools.includes('execute_ppt_program'),false,'A page component is not a certified write workflow');
 const writing=pptComponentScene(scene,'execute',false,true);
 assert.ok(writing.allowed_tools.includes('execute_ppt_program'));
 assert.ok(writing.allowed_tools.includes('release_ppt_program'));
 assert.equal(writing.allowed_tools.includes(pptComponentTool.name),false);
 assert.equal(pptComponentScene(scene,'baseline',true,true),scene);
 assert.equal(scene.allowed_tools.length,2);
 const tools=[{name:'bash'},pptComponentTool];
 assert.deepEqual(pptComponentGraphTools(offered,tools),[{name:'bash'}]);
 assert.throws(()=>pptComponentGraphTools(scene,tools),/schema_changed/);
 assert.throws(()=>pptComponentGraphTools(offered,[...tools,pptComponentTool]),/schema_changed/);
 assert.throws(()=>pptComponentGraphTools(offered,[{...pptComponentTool,parameters:{type:'object'}}]),/schema_changed/);
});

test('the host installs exact certified SVG bytes and records a native source witness',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-component-install-'));
 mkdirSync(join(workspace,'code/projects/deck/svg_output'),{recursive:true});
 mkdirSync(join(workspace,'outputs/code/component'),{recursive:true});
 mkdirSync(join(workspace,'code/projects/deck/notes'),{recursive:true});
 const svg='<svg>current content</svg>',sha256=createHash('sha256').update(svg).digest('hex');
 writeFileSync(join(workspace,'outputs/code/component/page.svg'),svg);
 const task={workspace,output:workspace},args={id:'p',project:'/work/projects/deck',page:'slide_01.svg',notes:'当前页来源与讲者备注',output:'/work/outputs/component',original_arguments:{id:'p'}};
 const row=installComponentPage(task,args,{files:[{path:'page.svg',sha256}]},'call');
 assert.equal(row.sha256,sha256);
 assert.equal(readFileSync(join(workspace,'code/projects/deck/svg_output/slide_01.svg'),'utf8'),svg);
 assert.equal(readFileSync(join(workspace,'code/projects/deck/notes/slide_01.md'),'utf8'),args.notes);
 assert.throws(()=>installComponentPage(task,args,{files:[{path:'page.svg',sha256}]},'call'),/already_exists/);
 assert.throws(()=>installComponentPage(task,{...args,page:'../overwrite.svg'},{},'call'),/required/);
 assert.equal(installComponentPage(task,{...args,page:'01_conclusion.svg'},{files:[{path:'page.svg',sha256}]},'call-2').native_path,'/work/projects/deck/svg_output/01_conclusion.svg');
 assert.match(readFileSync(join(workspace,'ppt-native-pages.jsonl'),'utf8'),/native_component_install/);
});

test('native page execution independently denies stale, Baseline, no-RSI and read-only tasks',async()=>{
 let tool,current;
 registerPptComponentTool({tools:{register:value=>{tool=value;}}},()=>current);
 for(const row of [undefined,{context:{}},{context:{},task:{status:'completed'}},
  {context:{},task:{status:'running',request:{mode:'baseline'}}},
  {context:{},task:{status:'running',request:{mode:'execute'},selection:{rsi:false}}},
  {context:{},task:{status:'running',request:{mode:'execute'},selection:{rsi:true},scene_options:{allow_output:false}}}]){
  current=row;
  await assert.rejects(()=>tool.execute({},{agent:{session:{id:'current'}}}),/not_authorized/);
 }
 await assert.rejects(()=>tool.execute({},{}),/not_authorized/);
});

test('explicit parameter revision replaces only the expected current page and records its ancestry',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-component-revision-'));
 const directory=join(workspace,'code/projects/deck/svg_output');mkdirSync(directory,{recursive:true});
 mkdirSync(join(workspace,'outputs/code/component'),{recursive:true});
 const old='<svg>old current content</svg>',fresh='<svg>shortened current content</svg>';
 const hash=value=>createHash('sha256').update(value).digest('hex');
 const target=join(directory,'slide_01.svg');writeFileSync(target,old);writeFileSync(join(directory,'slide_02.svg'),'untouched');
 writeFileSync(join(workspace,'outputs/code/component/page.svg'),fresh);
 const task={workspace,output:workspace};
 const args={id:'p',project:'/work/projects/deck',page:'slide_01.svg',output:'/work/outputs/component',expected_page_sha256:hash(old),original_arguments:{id:'p'}};
 const row=installComponentPage(task,args,{files:[{path:'page.svg',sha256:hash(fresh)}]},'revision');
 assert.equal(row.previous_sha256,hash(old));
 assert.equal(readFileSync(target,'utf8'),fresh);
 assert.equal(readFileSync(join(directory,'slide_02.svg'),'utf8'),'untouched');
 assert.throws(()=>installComponentPage(task,args,{files:[{path:'page.svg',sha256:hash(fresh)}]},'stale'),/version_changed/);
 assert.throws(()=>installComponentPage(task,{...args,expected_page_sha256:'bad'},{},'invalid'),/version_changed/);
 assert.throws(()=>installComponentPage(task,{...args,page:'missing.svg'},{},'missing'),/version_changed/);
 assert.equal(readFileSync(target,'utf8'),fresh);
});

test('component inputs accept a version-checked JSON file and report actionable parameter errors',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-component-parameters-'));
 mkdirSync(join(workspace,'code/projects/deck/svg_output'),{recursive:true});mkdirSync(join(workspace,'inputs'));
 const path=join(workspace,'inputs/current.json');writeFileSync(path,JSON.stringify({title:'Current content'}));
 const result=componentRequest({workspace},{id:'p',parameters_file:'/work/inputs/current.json',page:'slide_02.svg'});
 assert.equal(result.project,'/work/projects/deck');assert.equal(result.parameters.title,'Current content');
 assert.throws(()=>componentRequest({workspace},{id:'p'}),/parameters_choice_required/);
 assert.throws(()=>componentRequest({workspace},{id:'p',parameters:{},parameters_file:'/work/inputs/current.json'}),/parameters_choice_required/);
 writeFileSync(path,'{"title":');
 assert.throws(()=>componentRequest({workspace},{id:'p',parameters_file:'/work/inputs/current.json'}),/parameters_json_invalid/);
});

test('installed component sizes are declared without changing existing typography roles',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-component-roles-'));
 const project=join(workspace,'code/projects/deck');mkdirSync(join(project,'svg_output'),{recursive:true});
 mkdirSync(join(workspace,'outputs/code/component'),{recursive:true});
 writeFileSync(join(project,'spec_lock.md'),'## typography\n- body_family: Noto Sans CJK SC\n- body: 20\n\n## icons\n- library: none\n');
 writeFileSync(join(project,'design_spec.md'),'Current content plan');
 const svg='<svg><text font-size="22">Current text</text></svg>',sha256=createHash('sha256').update(svg).digest('hex');
 writeFileSync(join(workspace,'outputs/code/component/page.svg'),svg);
 installComponentPage({workspace,output:workspace},{id:'p',project:'/work/projects/deck',page:'slide.svg',output:'/work/outputs/component',original_arguments:{}},{files:[{path:'page.svg',sha256}]},'roles');
 const spec=readFileSync(join(project,'spec_lock.md'),'utf8');
 assert.match(spec,/- body: 20/);assert.match(spec,/- component_22: 22/);
 assert.ok(spec.indexOf('component_22')<spec.indexOf('## icons'));
 // Simulate a process stopping after spec publication but before design publication.
 writeFileSync(join(project,'design_spec.md'),'Current content plan');
 installComponentPage({workspace,output:workspace},{id:'p',project:'/work/projects/deck',page:'recovered.svg',output:'/work/outputs/component',original_arguments:{}},{files:[{path:'page.svg',sha256}]},'recovered-roles');
 assert.match(readFileSync(join(project,'design_spec.md'),'utf8'),/- component_22: 22 pt/);
 assert.equal(readFileSync(join(project,'spec_lock.md'),'utf8'),spec);
});
