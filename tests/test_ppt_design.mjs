import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
import {pptThemes,pptStartTool,pptDesignTool,pptPageTool,startPptProject,registerPptDesignTools} from '../src/adapters/ppt/authoring/ppt_design.ts';

function fixture(){
  const workspace=mkdtempSync(join(tmpdir(),'ppt-design-'));
  mkdirSync(join(workspace,'code'));
  return {workspace,status:'running',scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true}};
}

test('a text-only presentation can create a versioned project and retry without overwriting edits',()=>{
  const task=fixture(),args={name:'ordinary',title:'Product launch',theme:'bento',slide_count:8};
  const result=startPptProject(task,args);
  assert.equal(result.project,'/work/projects/ordinary');
  const path=join(task.workspace,'code/projects/ordinary/design_spec.md');
  writeFileSync(path,'user revised the outline');
  assert.equal(startPptProject(task,args).reused_project,true);
  assert.equal(readFileSync(path,'utf8'),'user revised the outline');
  assert.throws(()=>startPptProject(task,{...args,title:'different request'}),/already_exists/);
  for(const name of ['../outside','/work/projects/other','a\\b','a/b'])assert.throws(()=>startPptProject(task,{...args,name}),/parameters_invalid/);
  assert.throws(()=>startPptProject(task,{...args,slide_count:0}),/parameters_invalid/);
});

test('catalogs are compact and component schemas are disclosed only on request',async()=>{
  assertSupportedJsonSchema(pptStartTool.parameters);assertSupportedJsonSchema(pptDesignTool.parameters);assertSupportedJsonSchema(pptPageTool.parameters);
  assert.equal(new Set(pptThemes().themes.map(row=>row.id)).size,21);
  const task=fixture(),tools=new Map();
  const schema={type:'object',properties:{title:{type:'string'}}};
  const value={task,context:{library:{programs:[{id:'p',component:{summary:'Current content page',parameters_schema:schema}}]}}};
  registerPptDesignTools({tools:{register:tool=>tools.set(tool.name,tool)}},()=>value);
  const execution={agent:{session:{id:'current'}}};
  const result=await tools.get('read_ppt_design').execute({category:'education'},execution);
  assert.deepEqual(result,JSON.parse(JSON.stringify(result)),'Official tool outputs must be lossless JSON');
  assert.equal(Object.hasOwn(result,'guide'),false);
  assert.equal(result.content_limits.bar_chart.max_bars,6);
  assert.equal(result.layouts_for,'compose_ppt_page_only');
  assert.equal(result.native_json.tool,'build_ppt');
  assert.ok(result.native_json.layouts.includes('chart'));
  assert.equal(result.native_json.layouts.includes('bar_chart'),false);
  assert.ok(result.themes.length>=2);assert.ok(result.themes.every(row=>!row.provenance&&!row.font_sizes_pt));
  assert.deepEqual((await tools.get('read_ppt_design').execute({component_ids:['p']},execution)).components[0].parameters_schema,schema);
  const guided=await tools.get('read_ppt_design').execute({guide:true},execution);
  assert.match(guided.guide,/母版/);
  assert.deepEqual(guided.skill_references.map(row=>row.id),['academic-template','slide-maker-edit','dsh-ppt-engine']);
  assert.ok(guided.skill_references.every(row=>row.adapted===true&&row.executable===false&&/^[a-f0-9]{64}$/.test(row.sha256)));
  assert.ok(guided.skill_references.every(row=>row.text.length<5000),'References must stay adapted and bounded, never the full upstream workflow');
  for(const args of [{},{theme:'general'},{guide:false},{component_ids:['p']}]){
    const output=await tools.get('read_ppt_design').execute(args,execution);
    assert.deepEqual(output,JSON.parse(JSON.stringify(output)));
  }
  await assert.rejects(()=>tools.get('read_ppt_design').execute({component_ids:['foreign']},execution),/not_available/);
  await assert.rejects(()=>tools.get('compose_ppt_page').execute({content:{project:'/work/projects/example',page:'slide_03.svg',layout:'bullets',title:'Example'}},execution),/TOP-LEVEL/);
  task.scene_options.allow_output=false;
  await assert.rejects(()=>tools.get('start_ppt').execute({name:'no',title:'Denied'},execution),/not_authorized/);
  await assert.rejects(()=>tools.get('compose_ppt_page').execute({},execution),/not_authorized/);
});

test('page revision conflicts and missing layout inputs return actionable data before any subprocess',async()=>{
 const task=fixture(),tools=new Map();
 startPptProject(task,{name:'versioned',title:'A deck',theme:'general',slide_count:3});
 registerPptDesignTools({tools:{register:tool=>tools.set(tool.name,tool)}},()=>({task,context:{}}));
 const execution={agent:{session:{id:'current'}}};
 const args={project:'/work/projects/versioned',page:'one.svg',layout:'two_column',content:{title:'A title'}};
 const missing=await tools.get('compose_ppt_page').execute(args,execution);
 assert.equal(missing.error.code,'ppt_page_content_missing');assert.deepEqual(missing.error.fields,['columns']);
 writeFileSync(join(task.workspace,'code/projects/versioned/svg_output/one.svg'),'<svg>current text</svg>');
 const conflict=await tools.get('compose_ppt_page').execute({...args,expected_page_sha256:'old-sha'},execution);
 assert.equal(conflict.error.code,'ppt_page_version_conflict');assert.match(conflict.error.current_page_sha256,/^[a-f0-9]{64}$/);
 assert.equal(readFileSync(join(task.workspace,'code/projects/versioned/svg_output/one.svg'),'utf8'),'<svg>current text</svg>');
});
