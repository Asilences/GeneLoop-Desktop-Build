// The maintainer publishes only tool archives using the existing owner channel.
// The native job only reads and verifies that publication; no broader token.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
const catalog=JSON.parse(readFileSync('.local/tool-pack-build/tool-packs.json'));
const repo='Asilences/GeneLoop-Desktop-Build';assert.equal(process.env.GITHUB_REPOSITORY,repo);
const u=new URL(catalog.baseUrl);assert.equal(u.origin,'https://github.com');
const tag=u.pathname.match(/^\/Asilences\/GeneLoop-Desktop-Build\/releases\/download\/(desktop-tools-darwin-(?:arm64|x64)-[a-zA-Z0-9.-]+)\/$/)?.[1];assert.ok(tag);
const until=Date.now()+30*60*1000;let release;
while(Date.now()<until){
 const r=spawnSync('gh',['api','repos/'+repo+'/releases/tags/'+tag],{encoding:'utf8'});
 if(r.status===0){const v=JSON.parse(r.stdout);if(!v.draft&&v.assets.length===catalog.packages.length){release=v;break;}}
 console.log(JSON.stringify({waitingForOwnerToolPublication:tag}));await new Promise(r=>setTimeout(r,15000));
}
assert.ok(release,'工具尚未由维护者发布，停止而不使用错误下载源');
const expected=new Map(catalog.packages.map(p=>[p.filename,p]));
for(const a of release.assets){const p=expected.get(a.name);assert.ok(p);assert.equal(a.size,p.bytes);assert.equal(a.digest,'sha256:'+p.sha256);assert.equal(a.state,'uploaded');}
const receipt={schema:1,repo,releaseId:release.id,tag,baseUrl:catalog.baseUrl,toolsetId:catalog.toolsetId,platform:catalog.platform,arch:catalog.arch,sourceCommit:process.env.GITHUB_SHA,installerUploaded:false,publicationVerified:true,assets:release.assets.map(a=>({name:a.name,bytes:a.size,digest:a.digest,url:a.browser_download_url}))};
writeFileSync('.local/tool-pack-build/publication-receipt.json',JSON.stringify(receipt,null,2));
console.log(JSON.stringify({publicationVerified:true,tag,arch:catalog.arch}));
