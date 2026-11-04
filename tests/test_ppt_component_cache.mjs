import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {readComponentCache,saveComponentCache} from '../src/adapters/ppt_component_cache.ts';
import {artifactInvocation,registerArtifactContext} from '../src/adapters/artifact_motif_runtime.ts';
const sha=data=>createHash('sha256').update(data).digest('hex');

test('component output cache verifies bytes and copies into a fresh directory',()=>{
 const root=mkdtempSync(join(tmpdir(),'ppt-component-cache-')),source=join(root,'source');mkdirSync(source);
 const text='<svg>Current content</svg>';writeFileSync(join(source,'page.svg'),text);
 const receipt={files:[{path:'page.svg',bytes:Buffer.byteLength(text),sha256:sha(text)}],stdout:'ok',stderr:''};
 assert.equal(saveComponentCache(join(root,'cache'),'a'.repeat(64),source,receipt),true);
 assert.equal(saveComponentCache(join(root,'cache'),'a'.repeat(64),source,receipt),false);
 const destination=join(root,'new');assert.ok(readComponentCache(join(root,'cache'),'a'.repeat(64),destination));
 assert.equal(readFileSync(join(destination,'page.svg'),'utf8'),text);
 writeFileSync(join(root,'cache','a'.repeat(64),'page.svg'),'corrupt');
 assert.throws(()=>readComponentCache(join(root,'cache'),'a'.repeat(64),join(root,'other')),/cache_bytes_changed/);
});

test('component binding creates current data only after validating typed parameters',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-component-call-'));mkdirSync(join(workspace,'code'));
 const schema={type:'object',properties:{title:{type:'string'}},required:['title'],additionalProperties:false};
 const program={id:'layout',inputs:[{format:'json',suffix:'.json',shape:{object:{title:'string'}},source_origin:'model_artifact'}],
  component:{parameters_schema:schema},certification:{},input_argument_indices:[0],output_argument_index:1,argument_count:2};
 registerArtifactContext('component-diagnostic',{workspace,library:{programs:[program],digest:'d'},allowOutput:true,audit(){}});
 assert.throws(()=>artifactInvocation('component-diagnostic','geneloop-component '+JSON.stringify({id:'layout',parameters:{title:4},output:'/work/outputs/new'})),/component_parameters_invalid/);
 const job=artifactInvocation('component-diagnostic','geneloop-component '+JSON.stringify({id:'layout',parameters:{title:'Independent current content'},output:'/work/outputs/new'}));
 assert.equal(JSON.parse(job.bound[0].data).title,'Independent current content');
 assert.ok(artifactInvocation('component-diagnostic',"geneloop-component '"+JSON.stringify({id:'layout',parameters:{title:'Independent current content'},output:'/work/outputs/new'})+"'"));
 registerArtifactContext('component-diagnostic',null);
});

test('denied output permission refuses component binding before creating current-data files',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-component-denied-'));mkdirSync(join(workspace,'code'));
 registerArtifactContext('component-denied',{workspace,library:{programs:[]},allowOutput:false,audit(){}});
 assert.throws(()=>artifactInvocation('component-denied','geneloop-component {"id":"x","parameters":{},"output":"/work/outputs/new"}'),/output_not_authorized/);
 assert.equal(existsSync(join(workspace,'code','.geneloop-component-inputs')),false);
 registerArtifactContext('component-denied',null);
});

test('equivalent nested parameter objects share canonical input bytes regardless of key order',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-component-order-'));mkdirSync(join(workspace,'code'));
 const schema={type:'object',properties:{title:{type:'string'},style:{type:'object',properties:{size:{type:'number'},color:{type:'string'}},required:['size','color'],additionalProperties:false}},required:['title','style'],additionalProperties:false};
 const program={id:'ordered',inputs:[{format:'json',suffix:'.json',shape:{object:{style:{object:{color:'string',size:'number'}},title:'string'}},source_origin:'model_artifact'}],
  component:{parameters_schema:schema},certification:{},input_argument_indices:[0],output_argument_index:1,argument_count:2};
 registerArtifactContext('component-order',{workspace,library:{programs:[program],digest:'d'},allowOutput:true,audit(){}});
 const call=parameters=>artifactInvocation('component-order','geneloop-component '+JSON.stringify({id:'ordered',parameters,output:'/work/outputs/new'}));
 const a=call({title:'Current',style:{size:24,color:'blue'}}),b=call({style:{color:'blue',size:24},title:'Current'});
 assert.equal(a.bound[0].path,b.bound[0].path);assert.deepEqual(a.bound[0].data,b.bound[0].data);
 registerArtifactContext('component-order',null);
});
