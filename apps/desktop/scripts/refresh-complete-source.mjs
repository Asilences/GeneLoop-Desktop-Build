// Refresh only public scene implementation/configuration in a verified tool copy.
// Native executables and all six existing tool groups remain unchanged.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createReadStream,copyFileSync,existsSync,lstatSync,mkdirSync,mkdtempSync,readFileSync,readdirSync,readlinkSync,realpathSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {stageWorkflowSource} from './stage-workflow-source.mjs';
import {stagePptProfile} from './stage-ppt-profile.mjs';
import {stageDesktopPpt} from './stage-ppt-desktop.mjs';
import {stageRsiPrivacy} from './stage-rsi-privacy.mjs';
const app=fileURLToPath(new URL('../',import.meta.url)),repo=resolve(app,'../..');
export async function refreshCompleteSource(input,output,{preparePrivacy=false}={}){
 const root=realpathSync(input),manifest=JSON.parse(readFileSync(join(root,'manifest.json'),'utf8'));
 assert.equal(manifest.platform,process.platform);assert.equal(manifest.arch,process.arch);
 assert.equal(manifest.profile.scope,'six-scenes-ppt-authoring');assert.ok(existsSync(join(root,'.geneloop-tools')));
 const source=join(root,'source'),fresh=mkdtempSync(join(root,'source-refresh-'));
 assert.equal(realpathSync(source),source);
 stageWorkflowSource(repo,fresh);
 // Rebuild in a separate generated directory: published tool inputs may already
 // contain a deck engine, and stageDesktopPpt intentionally refuses overwrite.
 const pptFresh=mkdtempSync(join(root,'ppt-refresh-'));
 const {ppt_master:presentation}=stageDesktopPpt(repo,pptFresh);
 const deck=join(root,'ppt-deck');
 if(existsSync(deck)){
  assert.equal(realpathSync(deck),deck);assert.ok(!lstatSync(deck).isSymbolicLink());
  rmSync(deck,{recursive:true});
 }
 renameSync(join(pptFresh,'ppt-deck'),deck);
 copyFileSync(join(pptFresh,'local-ppt-deck.mjs'),join(root,'local-ppt-deck.mjs'));
 presentation.root=join(root,relative(pptFresh,presentation.root));
 assert.equal(dirname(pptFresh),root);rmSync(pptFresh,{recursive:true});
 const legacy=join(root,'ppt-master');
 if(existsSync(legacy)){
  assert.equal(realpathSync(legacy),legacy);assert.ok(lstatSync(legacy).isDirectory());
  rmSync(legacy,{recursive:true});
 }
 manifest.ppt_master=presentation.sha256;
 manifest.ppt_resources={root:relative(root,presentation.root).split('\\').join('/'),files:presentation.files};
 writeFileSync(join(root,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
 if(process.platform==='win32'){
  const pth=join(root,'python/python312._pth'),scripts='../'+manifest.ppt_resources.root+'/scripts';
  const text=readFileSync(pth,'utf8').replaceAll('../ppt-master/scripts',scripts);
  writeFileSync(pth,text);
 }
 // Both absolute targets are checked against the same verified generated bundle.
 assert.equal(dirname(source),root);assert.equal(dirname(fresh),root);assert.ok(!lstatSync(source).isSymbolicLink());
 rmSync(source,{recursive:true});renameSync(fresh,source);stagePptProfile(app,root);
 if(preparePrivacy)stageRsiPrivacy(root);
 const files=[];
 async function walk(dir){for(const item of readdirSync(dir,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
  const path=join(dir,item.name),name=relative(root,path).split('\\').join('/');
  if(name.split('/').includes('__pycache__')||/\.py[co]$/.test(name))continue;
  const s=lstatSync(path);if(s.isDirectory()&&!s.isSymbolicLink())await walk(path);
  else if(s.isSymbolicLink()){const target=readlinkSync(path),dest=relative(root,resolve(dirname(path),target));assert.ok(!dest.startsWith('..')&&!/^[A-Za-z]:/.test(target)&&!target.startsWith('/'));files.push({path:name,kind:'symlink',target,bytes:0,sha256:createHash('sha256').update(target).digest('hex')});}
  else{assert.ok(s.isFile());const h=createHash('sha256');for await(const b of createReadStream(path))h.update(b);files.push({path:name,bytes:s.size,sha256:h.digest('hex')});}
 }}await walk(root);
 const record={schema:1,kind:'geneloop-complete-tool-roster-v1',platform:process.platform,arch:process.arch,
  toolsetId:createHash('sha256').update(JSON.stringify(files)).digest('hex'),files};
 mkdirSync(dirname(resolve(output)),{recursive:true});writeFileSync(output,JSON.stringify(record,null,2)+'\n');return record;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const record=await refreshCompleteSource(resolve(process.argv[2]),resolve(process.argv[3]));
 console.log(JSON.stringify({toolsetId:record.toolsetId,files:record.files.length,bytes:record.files.reduce((n,f)=>n+f.bytes,0),publicSourceRefreshed:true,nativeToolsUnchanged:true}));
}
