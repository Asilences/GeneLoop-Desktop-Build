// Refresh only public scene implementation/configuration in a verified tool copy.
// Native executables and all six existing tool groups remain unchanged.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createReadStream,existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,readlinkSync,realpathSync,renameSync,rmSync,writeFileSync} from 'node:fs';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {stageWorkflowSource} from './stage-workflow-source.mjs';
import {stagePptProfile} from './stage-ppt-profile.mjs';
const app=fileURLToPath(new URL('../',import.meta.url)),repo=resolve(app,'../..');
export async function refreshCompleteSource(input,output){
 const root=realpathSync(input),manifest=JSON.parse(readFileSync(join(root,'manifest.json'),'utf8'));
 assert.equal(manifest.platform,process.platform);assert.equal(manifest.arch,process.arch);
 assert.equal(manifest.profile.scope,'six-scenes-ppt-authoring');assert.ok(existsSync(join(root,'.geneloop-tools')));
 const source=join(root,'source'),fresh=join(root,'source-refresh');
 assert.equal(realpathSync(source),source);assert.ok(!existsSync(fresh));
 mkdirSync(fresh);stageWorkflowSource(repo,fresh);
 // Both absolute targets are checked against the same verified generated bundle.
 assert.equal(dirname(source),root);assert.equal(dirname(fresh),root);assert.ok(!lstatSync(source).isSymbolicLink());
 rmSync(source,{recursive:true});renameSync(fresh,source);stagePptProfile(app,root);
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
