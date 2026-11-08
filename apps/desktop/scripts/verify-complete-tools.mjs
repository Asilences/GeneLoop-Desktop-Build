import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createReadStream,lstatSync,readFileSync,readdirSync,readlinkSync} from 'node:fs';
import {join} from 'node:path';
import {validateToolCatalog} from '../dist/tool-pack-store.js';
// Called by afterPack, before code signing may legitimately alter Mach-O signatures.
export async function verifyCompleteTools(resources,input){
 const catalog=validateToolCatalog(JSON.parse(readFileSync(input,'utf8')));
 assert.equal(catalog.platform,process.platform);assert.equal(catalog.arch,process.arch);
 const root=join(resources,'geneloop-tools'),files=catalog.packages.flatMap(p=>p.files),expected=new Set(files.map(f=>f.path));let actual=0;
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
