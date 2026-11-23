import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {inflateRawSync} from 'node:zlib';
import {assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
import {buildPptDeck,patchPptDeck,readPptDeck} from '../src/adapters/ppt/authoring/ppt_deck_engine.ts';
import {pptDeckBuildTool,pptDeckPatchTool} from '../src/adapters/ppt/authoring/ppt_deck_contract.ts';
import {pptThemes} from '../src/adapters/ppt/authoring/ppt_design.ts';
const hash=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
function fixture(){const parent=mkdtempSync(join(tmpdir(),'ppt-deck-'));return {root:join(parent,'project'),
 theme:pptThemes().themes[0],fontFamily:process.platform==='win32'?'Microsoft YaHei':'Noto Sans CJK SC',imagePath:path=>{throw Error('unexpected image path: '+path);}};}
const plan=()=>({title:'Structured content',slides:[{layout:'cover',title:'Meaning < x > and **literal**'},
 {layout:'bullets',title:'Result',bullets:['1.60 → 1.35','a_b_c is literal'],notes:'Original notes\nSecond line',sources:['Table 1, source-id: paper-A']}],target_slide_count:2,strict_slide_count:true});
function parts(bytes){
 const result=new Map();
 for(let i=0;i<bytes.length-30;i++)if(bytes.readUInt32LE(i)===0x04034b50){
  const method=bytes.readUInt16LE(i+8),size=bytes.readUInt32LE(i+18),n=bytes.readUInt16LE(i+26),extra=bytes.readUInt16LE(i+28);
  if(bytes.readUInt16LE(i+6)&8)throw Error('test zip requires local lengths');
  const start=i+30+n+extra,raw=bytes.subarray(start,start+size);result.set(bytes.subarray(i+30,i+30+n).toString(),method===8?inflateRawSync(raw):raw);i=start+size-1;
 }return result;
}
test('both content-only native contracts are valid official tool schemas',()=>{
 assertSupportedJsonSchema(pptDeckBuildTool.parameters);assertSupportedJsonSchema(pptDeckPatchTool.parameters);
 assert.equal(JSON.stringify(pptDeckBuildTool).includes('expected_page_sha256'),false);
 assert.deepEqual(pptDeckBuildTool.parameters.properties.plan.properties.language.enum,['zh','en','bilingual']);
 assert.ok(pptDeckBuildTool.parameters.properties.plan.properties.slides.items.properties.layout.enum.includes('chart'));
});

test('ordinary locale codes and the observed legacy bar chart preserve data without retries',async()=>{
 const options=fixture();
 const result=await buildPptDeck({...options,plan:{title:'Locale and chart boundary',language:'zh-CN',slides:[
  {layout:'bar_chart',title:'Hours',chart:{labels:['计划','实际'],values:[120,108],unit:'小时'},notes:'These are controlled test values.'}]}});
 assert.equal(result.slide_count,1);const saved=readPptDeck(options.root);assert.equal(saved.language,'zh');
 assert.equal(saved.slides[0].layout,'chart');assert.deepEqual(saved.slides[0].chart.categories,['计划','实际']);
 assert.deepEqual(saved.slides[0].chart.series[0].values,[120,108]);
 const invalid=fixture();await assert.rejects(()=>buildPptDeck({...invalid,plan:{title:'Wrong interface',slides:[{layout:'two_column',title:'Existing SVG layout'}]}}),/plan\.slides\[0\].layout=two_column.*compose_ppt_page/);
 assert.equal(existsSync(invalid.root),false);
});
test('whole deck preserves literal facts and notes, revision zero, stable IDs, non-target OOXML and restart',async()=>{
 const options=fixture();const result=await buildPptDeck({...options,plan:plan()});
 assert.equal(result.revision,0);assert.equal(result.model_requests_inside,0);assert.equal(result.slide_count,2);
 const before=readPptDeck(options.root),old=parts(readFileSync(join(options.root,'deck.pptx')));
 assert.equal(before.slides[0].title,'Meaning < x > and **literal**');
 assert.equal(before.slides[1].bullets[1],'a_b_c is literal');assert.match(before.slides[1].notes,/Table 1/);
 const patched=await patchPptDeck({...options,expected_revision:0,edits:[{slide_id:result.slides[1].id,changes:{title:'Revised result',bullets:['1.60 → 1.35','a_b_c remains']}}]});
 assert.equal(patched.revision,1);const after=readPptDeck(options.root);
 assert.deepEqual(after.slides[0],before.slides[0]);assert.equal(after.slides[1].id,before.slides[1].id);
 assert.equal(after.slides[1].notes,before.slides[1].notes);
 const next=parts(readFileSync(join(options.root,'deck.pptx')));
 assert.deepEqual(next.get('ppt/slides/slide1.xml'),old.get('ppt/slides/slide1.xml'));
 assert.deepEqual(next.get('ppt/notesSlides/notesSlide1.xml'),old.get('ppt/notesSlides/notesSlide1.xml'));
 // Recovery uses persisted JSON only, not the previous in-memory result.
 const restarted=await patchPptDeck({...fixture(),root:options.root,expected_revision:1,edits:[]});
 assert.equal(restarted.revision,1);assert.equal(restarted.changed,false);
});

test('global citations survive in every slide and unknown fields report the exact rejected key',async()=>{
 const options=fixture();await buildPptDeck({...options,plan:{...plan(),sources:['source-global'],slides:plan().slides}});
 for(const slide of readPptDeck(options.root).slides)assert.match(slide.notes,/source-global/);
 const invalid=fixture();await assert.rejects(()=>buildPptDeck({...invalid,plan:{...plan(),arbitrary:'not accepted'}}),/plan unknown=\["arbitrary"\].*allowed=/);
 assert.equal(existsSync(invalid.root),false);
});

test('strict slide count defaults to the supplied plan and still rejects pagination expansion',async()=>{
 const options=fixture(),input=plan();delete input.target_slide_count;
 const result=await buildPptDeck({...options,plan:input});assert.equal(result.slide_count,2);
 const invalid=fixture();await assert.rejects(()=>buildPptDeck({...invalid,plan:{title:'Rows',strict_slide_count:true,
  slides:[{layout:'table',title:'All rows',rows:[['H'],...Array.from({length:10},(_,n)=>[String(n)])]}]}}),/after_pagination=2/);
 assert.equal(existsSync(invalid.root),false);
});

test('a partial draft can append missing pages in the same project without discarding existing content',async()=>{
 const options=fixture(),first=await buildPptDeck({...options,plan:{title:'Partial draft',slides:[{layout:'cover',title:'Retained',notes:'Keep original'}]}});
 const before=readPptDeck(options.root),bytes=parts(readFileSync(join(options.root,'deck.pptx')));
 const after=await patchPptDeck({...options,expected_revision:0,edits:[],append_slides:Array.from({length:5},(_,n)=>({layout:'bullets',title:'Added '+n,bullets:['Current facts']}))});
 assert.equal(after.slide_count,6);assert.equal(after.revision,1);assert.equal(after.added_slide_ids.length,5);
 assert.deepEqual(readPptDeck(options.root).slides[0],before.slides[0]);
 // Adding pages changes the global total in the footer, but no other part.
 assert.equal(parts(readFileSync(join(options.root,'deck.pptx'))).get('ppt/slides/slide1.xml').toString().replace('01 / 06','01 / 01'),bytes.get('ppt/slides/slide1.xml').toString());
 const committed=hash(join(options.root,'deck.pptx'));
 await assert.rejects(()=>patchPptDeck({...options,expected_revision:1,edits:[],append_slides:Array.from({length:6},()=>({layout:'cover',title:'Invalid'}))}),/append_requires/);
 assert.equal(hash(join(options.root,'deck.pptx')),committed);
});
test('conflict, malformed later patch, no-op and external edits preserve committed bytes',async()=>{
 const options=fixture(),first=await buildPptDeck({...options,plan:plan()}),original=hash(join(options.root,'deck.pptx'));
 const conflict=await patchPptDeck({...options,expected_revision:1,edits:[]});assert.equal(conflict.error.current_revision,0);
 await assert.rejects(()=>patchPptDeck({...options,expected_revision:0,edits:[{slide_id:first.slides[0].id,changes:{title:'must not commit'}},
  {slide_id:'unknown',changes:{title:'bad'}}]}),/slide_id_unknown/);
 assert.equal(hash(join(options.root,'deck.pptx')),original);assert.equal(readPptDeck(options.root).revision,0);
 const noop=await patchPptDeck({...options,expected_revision:0,edits:[{slide_id:first.slides[1].id,changes:{title:'Result'}}]});
 assert.equal(noop.changed,false);assert.equal(hash(join(options.root,'deck.pptx')),original);
 writeFileSync(join(options.root,'deck.pptx'),'Office manual edit');
 await assert.rejects(()=>patchPptDeck({...options,expected_revision:0,edits:[]}),/external_edit_preserved/);
 assert.equal(readFileSync(join(options.root,'deck.pptx'),'utf8'),'Office manual edit');
});
test('table pagination is admitted before writing, retains final row and rejects strict page mismatch',async()=>{
 const options=fixture(),rows=[['Model','Score'],...Array.from({length:17},(_,i)=>['M'+i,String(i+.125)])];
 const table={title:'Experiments',slides:[{layout:'table',title:'All results',rows,notes:'Conditions remain'}],target_slide_count:1,strict_slide_count:true};
 await assert.rejects(()=>buildPptDeck({...options,plan:table}),/after_pagination=3/);assert.equal(existsSync(options.root),false);
 const result=await buildPptDeck({...options,plan:{...table,strict_slide_count:false}});
 assert.equal(result.slide_count,3);assert.equal(result.warnings[0].actual,3);
 const saved=readPptDeck(options.root);assert.deepEqual(saved.slides[2].rows,[rows[0],rows[17]]);
 const archive=parts(readFileSync(join(options.root,'deck.pptx')));
 assert.match(archive.get('ppt/slides/slide3.xml').toString(),/16.125/);
 assert.equal(saved.slides[0].notes,'Conditions remain');
});
test('native chart and embedded image remain real Office objects',async()=>{
 const options=fixture(),image=join(join(options.root,'..'),'input.png');
 writeFileSync(image,Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64'));
 const result=await buildPptDeck({...options,imagePath:path=>{assert.equal(path,'/work/inputs/image.png');return image;},plan:{title:'Objects',slides:[
  {layout:'image-right',title:'Image',image:{src:'/work/inputs/image.png',alt:'Local illustration'},bullets:['Local source']},
  {layout:'chart',title:'Original values',chart:{kind:'column',categories:['A','B'],series:[{name:'Accuracy',values:[1.60,1.35]}]}}]}});
 assert.equal(result.slide_count,2);const archive=parts(readFileSync(join(options.root,'deck.pptx')));
 assert.ok([...archive.keys()].some(n=>/^ppt\/charts\/chart\d+.xml$/.test(n)));
 assert.ok([...archive.keys()].some(n=>n.startsWith('ppt/embeddings/')));
 assert.ok([...archive.keys()].some(n=>n.startsWith('ppt/media/')));
 const chart=[...archive.entries()].find(([n])=>/^ppt\/charts\/chart\d+.xml$/.test(n))[1].toString();
 assert.match(chart,/<(?:\w+:)?min\b[^>]*val="0"/,'Column chart must include a zero baseline');
 const doc=readPptDeck(options.root);assert.equal(doc.brand.panelColor,'#F1F2F4');
});
test('unsupported parameters, numerical strings and aborted build never write a partial project',async()=>{
 for(const bad of [{...plan(),slides:[{layout:'quote',title:'x'.repeat(221)}]},
  {...plan(),slides:[{layout:'chart',title:'bad',chart:{categories:['A'],series:[{name:'n',values:['2']}]}}]},
  {...plan(),slides:[{layout:'table',title:'bad',rows:[['a'],['x'.repeat(61)]]}]}]){
  const options=fixture();await assert.rejects(()=>buildPptDeck({...options,plan:bad}));assert.equal(existsSync(options.root),false);
 }
 const options=fixture(),controller=new AbortController();controller.abort();
 await assert.rejects(()=>buildPptDeck({...options,plan:plan(),signal:controller.signal}));assert.equal(existsSync(options.root),false);
});
