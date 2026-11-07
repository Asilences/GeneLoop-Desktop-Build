// Runtime-only fixes reuse the already published and fully checked tool set.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {cpSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
const runId=process.env.DELIVERY_RUN;assert.match(runId??'',/^\d+$/);
assert.equal(process.env.GITHUB_REPOSITORY,'Asilences/GeneLoop-Desktop-Build');
assert.equal(process.platform,'darwin');
function run(bin,args,cwd=process.cwd()){const r=spawnSync(bin,args,{cwd,encoding:'utf8',stdio:['ignore','pipe','pipe']});assert.equal(r.status,0,bin+' 复用步骤失败');return r.stdout;}
const repo=process.env.GITHUB_REPOSITORY;
assert.equal(JSON.parse(run('gh',['api','repos/'+repo+'/actions/runs/'+runId])).conclusion,'success');
const input=resolve('.local/repack-input');mkdirSync(input,{recursive:true});
run('gh',['run','download',runId,'--repo',repo,'--name','desktop-macos-'+process.arch+'-'+runId,'--dir',input]);
run('shasum',['-a','256','--check','SHA256SUMS.txt'],input);
const dmg=join(input,'GeneLoop-Desktop-0.3.0-preview.19-macOS-'+process.arch+'.dmg');
const mount=resolve('.local/repack-mounted');mkdirSync(mount,{recursive:true});
run('hdiutil',['attach','-readonly','-nobrowse','-mountpoint',mount,dmg]);
try{
 const resource=join(mount,'GeneLoop Desktop.app/Contents/Resources');
 const catalog=JSON.parse(readFileSync(join(resource,'tool-packs.json')));
 const proof=JSON.parse(readFileSync(join(input,'preservation.json')));
 assert.equal(catalog.platform,process.platform);assert.equal(catalog.arch,process.arch);
 assert.equal(proof.toolsetId,catalog.toolsetId);assert.equal(proof.allToolsRetained,true);
 assert.equal(proof.filesBefore,catalog.packages.reduce((n,p)=>n+p.files.length,0));
 assert.equal(readFileSync(join(resource,'tool-packs.json'),'utf8'),readFileSync(join(input,'tool-packs.json'),'utf8'));
 const output=resolve('.local/tool-pack-build');mkdirSync(output,{recursive:true});
 for(const name of ['tool-packs.json','preservation.json','publication-receipt.json'])cpSync(join(input,name),join(output,name));
 cpSync(join(resource,'installer-tools'),join(output,'installer-tools'),{recursive:true,verbatimSymlinks:true});
 const restored=resolve('.local/public-tool-restore');mkdirSync(restored,{recursive:true});
 cpSync(join(input,'download-receipt.json'),join(restored,'download-receipt.json'));
 writeFileSync(join(output,'reused-delivery.json'),JSON.stringify({producerRun:Number(runId),toolsetId:catalog.toolsetId,runtimeOnly:true,repeatToolPublication:false}));
 console.log(JSON.stringify({reusedToolset:catalog.toolsetId,arch:process.arch,producerRun:Number(runId)}));
}finally{run('hdiutil',['detach',mount]);}
