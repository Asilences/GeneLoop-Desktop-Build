import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {buildPptDeck,readPptDeck} from '../src/adapters/ppt/authoring/ppt_deck_engine.ts';
import {pptThemes} from '../src/adapters/ppt/authoring/ppt_design.ts';
import {acceptPptDeckReceipt,pptReadyDelivery,pptTaskAcceptance,pptSourceState,validatePptPublication,cachedPptDelivery} from '../src/adapters/ppt/delivery/ppt_delivery_pipeline.ts';
import {stagePptDeck} from '../apps/desktop/scripts/stage-ppt-deck.mjs';
const sha=raw=>createHash('sha256').update(raw).digest('hex');
test('native JSON current receipts use shared publication and invalidate on source or output mutation',async()=>{
 const workspace=mkdtempSync(join(tmpdir(),'ppt-deck-delivery-')),output=join(workspace,'task');
 mkdirSync(join(workspace,'code/projects'),{recursive:true});mkdirSync(output);mkdirSync(join(workspace,'outputs/code'),{recursive:true});
 const task={workspace,output,stats:{ppt_work_started:true},request:{task_id:'t'},scene:{id:'ppt',ppt_execution_strategy:'ppt_master'},scene_options:{allow_output:true},ppt_initial_sources:{}};
 const root=join(workspace,'code/projects/deck');await buildPptDeck({root,theme:pptThemes().themes[0],fontFamily:'Noto Sans CJK SC',imagePath:()=>{},plan:{title:'A',slides:[{layout:'bullets',title:'Fact',bullets:['1.35']}]}});
 const artifacts=['presentation.pptx','presentation.pdf','page-001.png'].map((name,i)=>{
  const raw=i===0?readFileSync(join(root,'deck.pptx')):Buffer.from('diagnostic-'+name);
  writeFileSync(join(workspace,'outputs/code',name),raw);return {path:'/work/outputs/'+name,sha256:sha(raw),bytes:raw.length};
 });
 const receipt={kind:'ppt_native_json_v1',mechanical_status:'passed',project:'/work/projects/deck',revision:0,key:'a'.repeat(64),delivery_id:'first',
  deck_source:{path:'/work/projects/deck/deck.json',sha256:sha(readFileSync(join(root,'deck.json'))),pptx_path:'/work/projects/deck/deck.pptx',pptx_sha256:sha(readFileSync(join(root,'deck.pptx')))},
  dependencies:{files:['deck.json','geneloop-deck.json'].map(path=>({path,sha256:sha(readFileSync(join(root,path)))}))},page_receipts:[{page:1}],artifacts,findings:[],review_pages:[]};
 acceptPptDeckReceipt(task,receipt);assert.equal(pptTaskAcceptance(task).passed,true);assert.equal(pptReadyDelivery(task)[0].revision,0);
 assert.equal(validatePptPublication(task,[{path:'/work/outputs/presentation.pptx'}]),undefined);
 assert.equal(cachedPptDelivery(task,receipt,receipt.key).reused_checks,true);
 const before=pptSourceState(workspace);const json=readPptDeck(root);json.slides[0].title='New unexported title';writeFileSync(join(root,'deck.json'),JSON.stringify(json));
 assert.notDeepEqual(pptSourceState(workspace),before);assert.equal(pptTaskAcceptance(task).passed,false);assert.deepEqual(pptReadyDelivery(task),[]);
 assert.throws(()=>acceptPptDeckReceipt(task,receipt),/not_current/);
});
test('desktop bundles only local engine modules, lazy load creates no service and native host owns render/authorization',async()=>{
 const destination=mkdtempSync(join(tmpdir(),'ppt-deck-bundle-'));const staged=stagePptDeck(resolve('.'),destination);
 assert.equal(staged.resident_services,0);const {createLocalPptDeckTools}=await import(pathToFileURL(join(destination,'local-ppt-deck.mjs')));
 let authorized=0,rendered=0;const projects=join(destination,'projects');mkdirSync(projects);
 const host={authorize:()=>{authorized++;},projectRoot:name=>join(projects,name),imagePath:()=>{throw Error('unexpected');},
  theme:()=>pptThemes().themes[0],render:async()=>{rendered++;return {mechanical_status:'diagnostic_no_Office',artifacts:[]};}};
 const native=createLocalPptDeckTools(host);assert.equal(authorized,0);assert.equal(rendered,0);
 const definitions=await native.definitions();assert.equal(definitions.pptDeckBuildTool.name,'build_ppt');
 const result=await native.build({name:'local',plan:{title:'Local',slides:[{layout:'cover',title:'本地执行'}]}},{signal:new AbortController().signal});
 assert.equal(result.revision,0);assert.equal(readPptDeck(join(projects,'local')).slides[0].title,'本地执行');
 assert.equal(authorized,3);assert.equal(rendered,1);
 const denied=createLocalPptDeckTools({...host,authorize(){throw Error('permission denied');}});
 await assert.rejects(()=>denied.build({},{}),/permission denied/);
});
