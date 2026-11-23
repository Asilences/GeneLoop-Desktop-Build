// Run with the packaged Electron in Node mode, on a fresh per-test profile.
import assert from 'node:assert/strict';
import {existsSync,mkdirSync,readFileSync,realpathSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const resources=resolve(process.argv[2]),output=resolve(process.argv[3]);
assert.ok(existsSync(join(resources,'app.asar')));
mkdirSync(output,{recursive:true});
const root=realpathSync(output);
const catalog=JSON.parse(readFileSync(join(resources,'tool-packs.json'),'utf8'));
const {ToolPackStore}=await import(pathToFileURL(join(resources,'app.asar/dist/tool-pack-store.js')).href);
let last=0;const started=Date.now();
const store=new ToolPackStore(catalog,{home:join(root,'toolsets'),codecDirectory:join(resources,'installer-tools'),change(){
  if(Date.now()-last>25000){last=Date.now();console.log(JSON.stringify(store.state().rows.map(r=>({id:r.id,phase:r.phase,received:r.received}))));}
}});
assert.equal(store.state().rows.every(r=>r.phase==='pending'),true,'需要全新下载验收目录');
assert.equal(store.state().configured,true);
await store.prepare();
assert.equal(store.state().ready,true);assert.ok(store.state().rows.every(r=>r.phase==='ready'));
const receipt={schema:1,platform:process.platform,arch:process.arch,toolsetId:catalog.toolsetId,baseUrl:catalog.baseUrl,downloadBytes:catalog.packages.reduce((n,p)=>n+p.bytes,0),filesVerified:catalog.packages.reduce((n,p)=>n+p.files.length,0),allPacksReady:store.state().rows.length===catalog.packages.length,allSevenPacksReady:catalog.packages.length===7&&store.state().rows.length===7,seconds:(Date.now()-started)/1000,tools:store.tools,realModelRequests:0};
writeFileSync(join(root,'download-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));
