/** Local, lazy, model-free deck engine. This is shared engineering, not RSI. */
import {existsSync,lstatSync,mkdirSync,readFileSync,realpathSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {pptDeckLayouts,pptDeckLanguages} from './ppt_deck_contract.ts';

const vendor=new URL('../../../../scenarios/ppt_master/third_party/dsh-ppt/',import.meta.url);
export const deckEngineCommit='f2263f5260cf9453d1ad5d3c9a85c55ee3999c70';
export const deckLayouts=pptDeckLayouts;
let enginePromise:Promise<any>|undefined;
export function loadPptDeckEngine(){
 return enginePromise??=(async()=>{
  const manifest=JSON.parse(readFileSync(new URL('PROVENANCE.json',vendor),'utf8'));
  if(manifest.commit!==deckEngineCommit)throw Error('ppt_deck_engine_version_changed');
  for(const [name,version] of Object.entries(manifest.adapted_sha256??manifest.files)){
   if(!/^deck-[a-z-]+\.mjs$/.test(name)||hash(readFileSync(new URL(name,vendor)))!==version)throw Error('ppt_deck_engine_bytes_changed');
  }
  return {advanced:await import('../../../../scenarios/ppt_master/third_party/dsh-ppt/deck-advanced.mjs'),
   core:await import('../../../../scenarios/ppt_master/third_party/dsh-ppt/deck-core.mjs')};
 })().catch(error=>{enginePromise=undefined;throw error;});
}
const hash=(bytes:any)=>createHash('sha256').update(bytes).digest('hex');
const fail=(message:string):never=>{throw Error(message);};
const plain=(value:any)=>value!==null&&typeof value==='object'&&!Array.isArray(value);
function language(value:any){
 if(value===undefined)return 'zh';
 if(typeof value==='string'&&/^zh(?:[-_][a-z0-9-]+)?$/i.test(value))return 'zh';
 if(typeof value==='string'&&/^en(?:[-_][a-z0-9-]+)?$/i.test(value))return 'en';
 if(pptDeckLanguages.includes(value))return value;
 fail('ppt_deck_language_invalid: language must be zh, en or bilingual; zh-CN/en-US locale aliases are accepted');
}
function keys(value:any,allowed:string[],label:string){
 if(!plain(value))fail('ppt_deck_fields_invalid: '+label+' must be an object');
 const unknown=Object.keys(value).filter(key=>!allowed.includes(key));
 if(unknown.length)fail('ppt_deck_fields_invalid: '+label+' unknown='+JSON.stringify(unknown).slice(0,300)+'; allowed='+allowed.join('/'));
}
function text(value:any,label:string,limit=10000){
 if(typeof value!=='string'||value.length>limit||/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(value))fail('ppt_deck_text_invalid: '+label);
 return value;
}
function slidesInput(slides:any[],imagePath:(path:string)=>string,patch=false){
 if(!Array.isArray(slides)||!slides.length||slides.length>120)fail('ppt_deck_slides_required_1_to_120');
 return slides.map((slide,index)=>{
  keys(slide,['layout','title','subtitle','kicker','text','bullets','rows','notes','image','chart','sources'],'slides['+index+']');
  const next=structuredClone(slide);
  // Compatibility at the boundary: preserve values, not the old renderer API.
  if(next.layout==='bar_chart'){
   next.layout='chart';
   if(next.chart?.labels!==undefined||next.chart?.values!==undefined){
    if(next.chart.categories!==undefined||next.chart.series!==undefined)fail('ppt_deck_chart_interface_ambiguous');
    keys(next.chart,['labels','values','unit','caption'],'legacy chart');
    next.chart={kind:'column',categories:next.chart.labels,series:[{name:next.chart.unit??'数值',values:next.chart.values}],
     ...(next.chart.unit!==undefined?{unit:next.chart.unit}:{}),...(next.chart.caption!==undefined?{caption:next.chart.caption}:{})};
   }
  }
  if(!patch&&(typeof next.title!=='string'||!next.title.trim()))fail('ppt_deck_title_required: plan.slides['+index+'].title');
  if(next.layout!==undefined&&!deckLayouts.includes(next.layout)||!patch&&next.layout===undefined)
   fail('ppt_deck_layout_unsupported: plan.slides['+index+'].layout='+String(next.layout)+
    '; build_ppt uses '+deckLayouts.join('/')+'. two_column/image_text belong to compose_ppt_page (managed_svg).');
  for(const key of ['title','subtitle','kicker','text','notes'])if(next[key]!==undefined)text(next[key],key);
  if(next.layout==='quote'&&(next.title??next.text??'').length>220)fail('ppt_deck_quote_over_220_no_truncation');
  if(next.bullets!==undefined){
   if(!Array.isArray(next.bullets)||next.bullets.length>8||next.bullets.some((v:any)=>typeof v!=='string'||!v.trim()))fail('ppt_deck_bullets_require_1_to_8_strings');
   next.bullets.forEach((v:string)=>text(v,'bullets'));
  }
  if(next.rows!==undefined){
   if(!Array.isArray(next.rows)||next.rows.length<2||next.rows.length>961||
     !Array.isArray(next.rows[0])||next.rows[0].length<1||next.rows[0].length>8||
     next.rows.some((row:any)=>!Array.isArray(row)||row.length!==next.rows[0].length||row.some((v:any)=>typeof v!=='string'||[...v].length>60)))
    fail('ppt_deck_table_requires_rectangular_strings_max_8_columns_60_characters');
  }
  if(next.layout==='table'&&!next.rows)fail('ppt_deck_table_rows_required');
  if(next.image!==undefined){
   keys(next.image,['src','alt','caption','fit'],'image');
   if(typeof next.image.src!=='string'||!['contain','cover'].includes(next.image.fit??'contain'))fail('ppt_deck_image_parameters_invalid');
   for(const key of ['alt','caption'])if(next.image[key]!==undefined)text(next.image[key],key);
   // Host authorizes and resolves a local file. No URL, data URI or arbitrary host path.
   next.image.src=imagePath(next.image.src);
  }
  if(next.chart!==undefined){
   keys(next.chart,['kind','categories','series','unit','caption'],'chart');
   if(!['column','bar','line','pie'].includes(next.chart.kind??'column')||!Array.isArray(next.chart.categories)||!Array.isArray(next.chart.series))fail('ppt_deck_chart_invalid');
   if(next.chart.categories.some((v:any)=>typeof v!=='string'||!v.trim()))fail('ppt_deck_chart_categories_require_strings');
   for(const series of next.chart.series){
    keys(series,['name','values'],'series');text(series.name,'series.name');
    if(!Array.isArray(series.values)||series.values.some((v:any)=>typeof v!=='number'||!Number.isFinite(v)))fail('ppt_deck_chart_values_require_finite_numbers');
   }
  }
  if(next.sources!==undefined){
   if(!Array.isArray(next.sources)||next.sources.length>100)fail('ppt_deck_sources_invalid');
   const refs=next.sources.map((v:any)=>text(v,'sources',2000));
   if(refs.length)next.notes=(next.notes?next.notes+'\n\n':'')+'Sources:\n'+refs.join('\n');
   delete next.sources;
  }
  return next;
 });
}
function checked(path:string,directory=false){
 const stat=lstatSync(path);
 if(stat.isSymbolicLink()||realpathSync(path)!==resolve(path)||(directory?!stat.isDirectory():!stat.isFile()||stat.nlink!==1))
  fail('ppt_deck_path_changed');
 return path;
}
function snapshot(root:string){
 checked(root,true);
 const file=checked(join(root,'deck.json')),marker=JSON.parse(readFileSync(checked(join(root,'geneloop-deck.json')),'utf8'));
 const document=JSON.parse(readFileSync(file,'utf8'));
 if(marker.source_type!=='native_json'||marker.engine_commit!==deckEngineCommit||document.dataModel!==undefined)fail('ppt_deck_source_type_or_engine_changed');
 for(const extension of ['pptx','html']){
  if(hash(readFileSync(checked(join(root,'deck.'+extension))))!==document.artifacts?.[extension])fail('ppt_deck_external_edit_preserved_use_native_edit_or_new_project');
 }
 return {file,marker,document};
}
export function readPptDeck(root:string){const {document}=snapshot(root);return document;}

/** Root is a new, host-approved directory; commit the whole first project once. */
export async function buildPptDeck(options:any){
 const {root,signal}=options;signal?.throwIfAborted();
 keys(options.plan,['title','slides','theme','language','target_slide_count','strict_slide_count','sources'],'plan');
 if(typeof options.plan.title!=='string'||!options.plan.title.trim())fail('ppt_deck_title_required');
 text(options.plan.title,'title',2000);
 // Strict without a separate target means preserve the supplied page plan.
 // Do not silently accept extra pages introduced by table pagination.
 const target=options.plan.target_slide_count??(options.plan.strict_slide_count&&Array.isArray(options.plan.slides)?options.plan.slides.length:undefined);
 if(target!==undefined&&(!Number.isSafeInteger(target)||target<1||target>120))fail('ppt_deck_target_slide_count_1_to_120');
 if(options.plan.strict_slide_count!==undefined&&typeof options.plan.strict_slide_count!=='boolean')fail('ppt_deck_strict_slide_count_boolean');
 if(options.plan.strict_slide_count&&target===undefined)fail('ppt_deck_strict_slide_count_requires_target');
 const lang=language(options.plan.language);
 const globalSources=options.plan.sources;
 if(globalSources!==undefined&&(!Array.isArray(globalSources)||globalSources.some((v:any)=>typeof v!=='string'||!v.trim())))fail('ppt_deck_sources_require_strings');
 const slides=slidesInput(Array.isArray(options.plan.slides)?options.plan.slides.map((slide:any)=>{
  if(!globalSources?.length||!plain(slide))return slide;
  if(slide.sources!==undefined&&!Array.isArray(slide.sources))fail('ppt_deck_sources_invalid');
  return {...slide,sources:[...new Set([...(slide.sources??[]),...globalSources])]};
 }):options.plan.slides,options.imagePath);
 const {advanced,core}=await loadPptDeckEngine();
 const normalized=core.normalizeSlides(slides,120,lang);
 if(options.plan.strict_slide_count&&normalized.length!==target)fail('ppt_deck_page_count_conflict: requested='+target+', after_pagination='+normalized.length);
 // Admission completes before any project directory or partial export exists.
 checked(dirname(root),true);if(existsSync(root))fail('ppt_deck_project_exists_use_patch_ppt');
 const stage=join(dirname(root),'.deck-'+randomUUID());mkdirSync(stage,{mode:0o700});
 try{
  const theme=options.theme;
  const mix=(background:string,foreground:string)=>'#'+[0,1,2].map(i=>Math.round(
   parseInt(background.slice(1+i*2,3+i*2),16)*.94+parseInt(foreground.slice(1+i*2,3+i*2),16)*.06).toString(16).padStart(2,'0')).join('');
  const result=await advanced.buildDeckAsync({title:options.plan.title,slides,theme:'swiss',lang,
   brand:{primaryColor:theme.colors.accent,backgroundColor:theme.colors.bg,textColor:theme.colors.text,
    panelColor:mix(theme.colors.bg,theme.colors.text),mutedColor:theme.colors.muted,secondaryColor:theme.colors.primary,fontFamily:options.fontFamily},
   maxSlides:120,outputDir:stage,fileName:'deck',cwd:stage,signal});
  if(result.slideCount!==normalized.length)fail('ppt_deck_normalized_page_count_changed');
  const marker={version:1,source_type:'native_json',engine_commit:deckEngineCommit,theme_id:theme.id,
   font_family:options.fontFamily,requested_slide_count:target??null,strict_slide_count:options.plan.strict_slide_count===true};
  writeFileSync(join(stage,'geneloop-deck.json'),JSON.stringify(marker)+'\n',{flag:'wx',mode:0o600});
  signal?.throwIfAborted();if(existsSync(root))fail('ppt_deck_project_creation_conflict');
  renameSync(stage,root);
  return deckView(readPptDeck(root),marker,target!==undefined&&normalized.length!==target?
   [{code:'target_slide_count_differs_after_pagination',requested:target,actual:normalized.length}]:[]);
 }finally{if(existsSync(stage)){checked(stage,true);rmSync(stage,{recursive:true});}}
}
export function deckView(document:any,marker:any={},warnings:any[]=[]){
 return {source_type:'native_json',deck_id:document.deckId,revision:document.revision,theme:marker.theme_id,
  slides:document.slides.map((s:any,i:number)=>({page:i+1,id:s.id,title:s.title,layout:s.layout})),
  slide_count:document.slides.length,warnings:[...warnings,...(document.quality?.issues??[])],
  model_requests_inside:0,optimization_kind:'shared_engineering'};
}
/** Stable IDs only. Errors and no-op cannot create a new revision. */
export async function patchPptDeck(options:any){
 const {root,signal}=options;signal?.throwIfAborted();
 const state=snapshot(root),revision=options.expected_revision;
 if(!Number.isSafeInteger(revision)||revision!==state.document.revision)return {status:'rejected',error:{code:'ppt_deck_revision_conflict',current_revision:state.document.revision},...deckView(state.document,state.marker)};
 if(!Array.isArray(options.edits)||options.edits.length>120)fail('ppt_deck_edits_invalid');
 const seen=new Set();
 const edits=options.edits.map((edit:any)=>{
  keys(edit,['slide_id','changes'],'edits');
  if(typeof edit.slide_id!=='string'||seen.has(edit.slide_id))fail('ppt_deck_stable_slide_id_required_once');
  seen.add(edit.slide_id);
  const old=state.document.slides.find((s:any)=>s.id===edit.slide_id);
  if(!old)fail('ppt_deck_slide_id_unknown: current_revision='+state.document.revision+'; use edits=[] to read current stable IDs; append_slides adds missing pages');
  const patch=slidesInput([edit.changes],options.imagePath,true)[0];
  // Existing embedded assets stay bound; do not re-open filesystem paths.
  const merged={...old,...patch};
  if(merged.layout==='quote'&&(merged.title??merged.text??'').length>220)fail('ppt_deck_quote_over_220_no_truncation');
  return {slide:edit.slide_id,patch};
 });
 const {advanced,core}=await loadPptDeckEngine();
 for(const edit of edits){
  const old=state.document.slides.find((s:any)=>s.id===edit.slide);
  if(core.normalizeSlides([{...old,...edit.patch}],120,state.document.language).length!==1)fail('ppt_deck_patch_pagination_requires_explicit_page_plan');
 }
 const append=options.append_slides===undefined?undefined:slidesInput(options.append_slides,options.imagePath);
 if(append&&(append.length>5||core.normalizeSlides(append,120,state.document.language).length+state.document.slides.length>120))
  fail('ppt_deck_append_requires_1_to_5_pages_total_max_120');
 if(!edits.length&&!append)return {...deckView(state.document,state.marker),changed:false};
 await advanced.editDeck({deckPath:state.file,expectedRevision:revision,edits,...(append?{append}:{}),cwd:root,signal});
 const after=readPptDeck(root);
 for(const old of state.document.slides){
  if(!seen.has(old.id)&&JSON.stringify(old)!==JSON.stringify(after.slides.find((s:any)=>s.id===old.id)))fail('ppt_deck_non_target_slide_changed');
 }
 return {...deckView(after,state.marker),changed:after.revision!==revision,affected_slide_ids:[...seen],
  added_slide_ids:after.slides.filter((s:any)=>!state.document.slides.some((old:any)=>old.id===s.id)).map((s:any)=>s.id)};
}
