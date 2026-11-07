// Bound this delivery's transient artifact footprint below the included 2 GB.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readdirSync,statSync} from 'node:fs';
import {join} from 'node:path';
const root='.local/macos-delivery';let bytes=0;for(const n of readdirSync(root))bytes+=statSync(join(root,n)).size;
assert.ok(bytes<600*1024**2,'DMG 中转超过本轮预留大小，不能继续占用免费存储');
const deadline=Date.now()+30*60*1000;
while(Date.now()<deadline){
 const r=spawnSync('gh',['api','repos/Asilences/GeneLoop-Desktop-Build/actions/artifacts?per_page=100'],{encoding:'utf8'});assert.equal(r.status,0);
 const v=JSON.parse(r.stdout);assert.ok(v.total_count<=100);
 const active=v.artifacts.filter(a=>!a.expired).reduce((n,a)=>n+a.size_in_bytes,0);
 if(active+bytes+4*1024**2<1400*1024**2){console.log(JSON.stringify({artifactSpaceReady:true,activeBytes:active,deliveryBytes:bytes}));process.exit(0);}
 console.log(JSON.stringify({waitingForTemporaryArtifactCleanup:true,activeBytes:active}));await new Promise(r=>setTimeout(r,15000));
}
throw Error('等待临时产物清理超时，不扩大存储或付费');
