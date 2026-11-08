import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
import {pptThemes,pptStartTool,pptDesignTool,pptPageTool,startPptProject,registerPptDesignTools} from '../src/adapters/ppt_design.ts';

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
  assert.ok(result.themes.length>=2);assert.ok(result.themes.every(row=>!row.provenance&&!row.font_sizes_pt));
  assert.deepEqual((await tools.get('read_ppt_design').execute({component_ids:['p']},execution)).components[0].parameters_schema,schema);
  assert.match((await tools.get('read_ppt_design').execute({guide:true},execution)).guide,/母版/);
  for(const args of [{},{theme:'general'},{guide:false},{component_ids:['p']}]){
    const output=await tools.get('read_ppt_design').execute(args,execution);
    assert.deepEqual(output,JSON.parse(JSON.stringify(output)));
  }
  await assert.rejects(()=>tools.get('read_ppt_design').execute({component_ids:['foreign']},execution),/not_available/);
  task.scene_options.allow_output=false;
  await assert.rejects(()=>tools.get('start_ppt').execute({name:'no',title:'Denied'},execution),/not_authorized/);
  await assert.rejects(()=>tools.get('compose_ppt_page').execute({},execution),/not_authorized/);
});
