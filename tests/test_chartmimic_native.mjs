import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,readdirSync,renameSync,symlinkSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {apply} from '../scenarios/chartmimic/native_tools.ts';
import {apply as applyCapabilities} from '../scenarios/chartmimic/capability_tools.ts';
import {apply as applyBinding} from '../scenarios/chartmimic/binding_tools.ts';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';

test('native chart image tool preserves original bytes and confines pixels to task workspace',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'chart-native-')),workspace=join(directory,'workspace');
 const previous=Object.fromEntries(['GENELOOP_CHART_WORKSPACE','GENELOOP_CHART_RUN','GENELOOP_CHART_CONTAINER'].map(k=>[k,process.env[k]]));
 try{
  for(const name of ['inputs','code','outputs/code'])mkdirSync(join(workspace,name),{recursive:true});
  const bytes=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==','base64');
  writeFileSync(join(workspace,'inputs/reference.png'),bytes);
  const outsideDirectory=join(directory,'evaluation');mkdirSync(outsideDirectory);
  const outside=join(outsideDirectory,'evaluation.png');writeFileSync(outside,bytes);
  const escapePath=process.platform==='win32'?'inputs/escape/evaluation.png':'inputs/escape.png';
  if(process.platform==='win32')symlinkSync(outsideDirectory,join(workspace,'inputs/escape'),'junction');
  else symlinkSync(outside,join(workspace,escapePath),'file');
  process.env.GENELOOP_CHART_WORKSPACE=workspace;process.env.GENELOOP_CHART_RUN=directory;process.env.GENELOOP_CHART_CONTAINER='unused';
  const tools=new Map();let captured;
  apply({tools:{register:tool=>tools.set(tool.name,tool)},get:name=>name==='attachments'?{saveImage:async value=>{captured=value;return {id:'actual-image-attachment'};}}:undefined});
  assert.deepEqual([...tools.keys()],['execute','read_image']);
  const imageTool=tools.get('read_image');
  const value=await imageTool.execute({file_path:'/work/inputs/reference.png'},{callId:'pixels'});
  assert.deepEqual(captured.data,bytes);
  assert.equal(captured.mediaType,'image/png');
  assert.deepEqual(imageTool.output.render({},value)[1],{type:'image',attachment:{id:'actual-image-attachment'}});
  const audit=JSON.parse(readFileSync(join(directory,'native-tools.jsonl'),'utf8').trim());
  assert.equal(audit.image_bytes,bytes.length);
  await assert.rejects(imageTool.execute({file_path:'/etc/passwd'},{callId:'outside'}),/outside_workspace/);
  await assert.rejects(imageTool.execute({file_path:'/work/'+escapePath},{callId:'escape'}),/not_regular_input/);
 }finally{
  for(const [key,value] of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}
  rmSync(directory,{recursive:true,force:true});
 }
});

test('empty frozen Store view cannot grant a capability or import a nonexistent Runtime',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'chart-catalog-')),workspace=join(directory,'workspace');
 const names=['GENELOOP_CHART_WORKSPACE','GENELOOP_CHART_RUN','GENELOOP_CHART_RUNTIME','GENELOOP_CHART_BUNDLE','GENELOOP_CHART_BUNDLE_SHA256'];
 const previous=Object.fromEntries(names.map(key=>[key,process.env[key]]));
 try{
  mkdirSync(workspace);const bundle=join(directory,'bundle.json');
  const raw=JSON.stringify({snapshot:{digest:null,roots:[],capabilities:[]},libraries:[],capabilities:[]});
  writeFileSync(bundle,raw);
  process.env.GENELOOP_CHART_WORKSPACE=workspace;process.env.GENELOOP_CHART_RUN=directory;
  process.env.GENELOOP_CHART_RUNTIME=join(directory,'nonexistent-runtime');process.env.GENELOOP_CHART_BUNDLE=bundle;
  process.env.GENELOOP_CHART_BUNDLE_SHA256=createHash('sha256').update(raw).digest('hex');
  const tools=new Map();applyCapabilities({tools:{register:tool=>tools.set(tool.name,tool)}});
  assert.equal(tools.get('capability_list').parameters.properties.capability_id.type,'string');
  assert.deepEqual(await tools.get('capability_list').execute({},{callId:'list'}),{snapshot_sha256:null,capabilities:[]});
  await assert.rejects(tools.get('capability_list').execute({include_audit:true},{callId:'audit-without-selection'}),/selected_capability_required/);
  await assert.rejects(tools.get('capability_list').execute({capability_id:'invented'},{callId:'unknown-list'}),/not_in_frozen_library/);
  await assert.rejects(tools.get('capability_call').execute({capability_id:'invented',input_files:[],
   output_directory:'/work/outputs/rendered'},{callId:'unknown'}),/not_in_frozen_library/);
  writeFileSync(bundle,raw+' ');
  await assert.rejects(tools.get('capability_list').execute({},{callId:'changed'}),/bundle_changed/);
 }finally{
  for(const [key,value] of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}
  rmSync(directory,{recursive:true,force:true});
 }
});

test('certification JSON submission validates real roles and writes exact values only inside declared files',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'chart-binding-')),workspace=join(directory,'workspace');
 const names=['GENELOOP_CHART_WORKSPACE','GENELOOP_CHART_RUN','GENELOOP_CHART_RUNTIME','GENELOOP_CHART_BINDING','GENELOOP_CHART_BINDING_SHA256'];
 const previous=Object.fromEntries(names.map(key=>[key,process.env[key]]));
 try{
  mkdirSync(join(workspace,'code'),{recursive:true});
  const spec={format:'chartmimic_current_json_binding_v1',files:[
   {role:'chart_spec',path:'/work/plot-spec.json'},{role:'parameters',path:'/work/parameters.json'}],
   parameters:{type:'object',properties:{
    chart_spec:{type:'object',properties:{title:{type:'string'},rows:{type:'array'}},required:['title','rows'],additionalProperties:false},
    parameters:{type:'object',properties:{visible:{type:'boolean'}},required:['visible'],additionalProperties:false}
   },required:['chart_spec','parameters'],additionalProperties:false}};
  const path=join(directory,'binding.json'),raw=JSON.stringify(spec);writeFileSync(path,raw);
  Object.assign(process.env,{GENELOOP_CHART_WORKSPACE:workspace,GENELOOP_CHART_RUN:directory,
   GENELOOP_CHART_RUNTIME:fileURLToPath(new URL('..',import.meta.url)),
   GENELOOP_CHART_BINDING:path,GENELOOP_CHART_BINDING_SHA256:createHash('sha256').update(raw).digest('hex')});
  const tools=new Map();applyBinding({tools:{register:tool=>tools.set(tool.name,tool)}});
  assert.deepEqual([...tools.keys()],['submit_binding']);
  const submit=tools.get('submit_binding');
  assert.deepEqual(submit.parameters.properties.chart_spec.properties.rows.items,{});
  assert.equal((await submit.execute({chart_spec:{},parameters:{visible:true}},{callId:'incomplete'})).status,'invalid');
  assert.deepEqual(readdirSync(join(workspace,'code')),[]);
  const values={chart_spec:{title:'Current "quoted" title\n第二行',rows:[1,2]},parameters:{visible:true}};
  const written=await submit.execute(values,{callId:'complete'});
  assert.equal(written.status,'written');
  assert.deepEqual(JSON.parse(readFileSync(join(workspace,'code/plot-spec.json'))),values.chart_spec);
  assert.deepEqual(JSON.parse(readFileSync(join(workspace,'code/parameters.json'))),values.parameters);
  for(const file of written.files)assert.equal(file.sha256,createHash('sha256').update(readFileSync(join(workspace,'code',file.path.slice('/work/'.length)))).digest('hex'));
  assert.equal((await submit.execute({...values,another_role:{}},{callId:'undeclared-role'})).status,'invalid');
  const outsideDirectory=join(directory,'external-code');mkdirSync(outsideDirectory);
  const outside=join(outsideDirectory,'parameters.json');writeFileSync(outside,'original');
  if(process.platform==='win32'){
   renameSync(join(workspace,'code'),join(workspace,'original-code'));
   symlinkSync(outsideDirectory,join(workspace,'code'),'junction');
  }else{
   rmSync(join(workspace,'code/parameters.json'));
   symlinkSync(outside,join(workspace,'code/parameters.json'),'file');
  }
  await assert.rejects(submit.execute(values,{callId:'symlink-target'}),/target_changed/);
  assert.equal(readFileSync(outside,'utf8'),'original');
 }finally{
  for(const [key,value] of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}
  rmSync(directory,{recursive:true,force:true});
 }
});
