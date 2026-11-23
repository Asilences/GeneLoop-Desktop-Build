import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createReadStream,lstatSync,readFileSync,readdirSync,readlinkSync} from 'node:fs';
import {dirname,isAbsolute,join,relative,resolve} from 'node:path';
import {validateToolCatalog} from '../dist/tool-pack-store.js';
// Called by afterPack, before code signing may legitimately alter Mach-O signatures.
export async function verifyCompleteTools(resources,input){
 const data=JSON.parse(readFileSync(input,'utf8'));
 const roster=data.kind==='geneloop-complete-tool-roster-v1';
 if(roster){
  assert.equal(data.schema,1);assert.ok(Array.isArray(data.files)&&data.files.length>0&&data.files.length<=100000);
  assert.equal(createHash('sha256').update(JSON.stringify(data.files)).digest('hex'),data.toolsetId);
  const paths=new Set(),anchor=resolve('.');for(const f of data.files){assert.ok(typeof f.path==='string'&&!/^[/\\]|^[A-Za-z]:/.test(f.path)&&!f.path.includes('\\')&&f.path.split('/').every(p=>p&&p!=='.'&&p!=='..')&&!/[\x00-\x1f]/.test(f.path));assert.ok(!paths.has(f.path.toLowerCase()));paths.add(f.path.toLowerCase());assert.match(f.sha256,/^[a-f0-9]{64}$/);assert.ok(Number.isSafeInteger(f.bytes)&&f.bytes>=0);assert.ok(!f.kind||f.kind==='symlink');if(f.kind==='symlink'){assert.equal(typeof f.target,'string');const dest=relative(anchor,resolve(dirname(join(anchor,f.path)),f.target));assert.ok(process.platform!=='win32'&&!isAbsolute(f.target)&&dest!=='..'&&!dest.startsWith('../')&&!dest.startsWith('..\\'));}}
 }
 const catalog=roster?data:validateToolCatalog(data);
 assert.equal(catalog.platform,process.platform);assert.equal(catalog.arch,process.arch);
 const root=join(resources,'geneloop-tools'),files=roster?catalog.files:catalog.packages.flatMap(p=>p.files),expected=new Set(files.map(f=>f.path));let actual=0;
 function walk(dir,prefix=''){for(const item of readdirSync(dir,{withFileTypes:true})){
  const name=prefix?prefix+'/'+item.name:item.name,path=join(dir,item.name);
  if(item.isDirectory()&&!item.isSymbolicLink())walk(path,name);else{assert.ok(expected.has(name),'Unexpected copied tool: '+name);actual++;}
 }}walk(root);assert.equal(actual,files.length);
 let index=0;const start=performance.now();
 await Promise.all(Array.from({length:12},async()=>{while(index<files.length){const f=files[index++],path=join(root,f.path),s=lstatSync(path);
  if(f.kind==='symlink'){assert.ok(s.isSymbolicLink());assert.equal(readlinkSync(path),f.target);}
  else{assert.ok(s.isFile()&&!s.isSymbolicLink());assert.equal(s.size,f.bytes);const h=createHash('sha256');for await(const b of createReadStream(path))h.update(b);assert.equal(h.digest('hex'),f.sha256,'Copied tool differs: '+f.path);}
 }}));
 return {at:new Date().toISOString(),platform:process.platform,arch:process.arch,toolsetId:catalog.toolsetId,files:actual,
  allToolsRetained:true,allToolBytesMatchBeforeSigning:true,seconds:(performance.now()-start)/1000,modelRequests:0};
}
