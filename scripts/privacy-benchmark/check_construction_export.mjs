// Real read-only construction export CLI with a synthetic trusted seed.
// No model, validation execution, production Store or network receiver is used.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const [codeArg,outArg]=process.argv.slice(2),code=resolve(codeArg),out=resolve(outArg);
mkdirSync(out,{recursive:false,mode:0o700});
const {createCapability,capabilityRef,createCapabilitySnapshot}=await import(pathToFileURL(join(code,'src/capability/graph/capability_contract.ts')).href);
const owner='owner@example.com',digest='a'.repeat(64);
const leaf=createCapability({owner,contract:{input_schema:{type:'object'},output_schema:{type:'object'},effects:['read']},
 implementation:{kind:'legacy',legacy_ref:{backend:'artifact_motif',object_id:'diagnostic-operation',library_sha256:digest,
 library_digest:digest,object_sha256:digest,certificate_sha256:digest}},dependencies:[]},{certification:'certified',lifecycle:'active'});
const seed=createCapabilitySnapshot(owner,[capabilityRef(leaf)],[leaf]);
const seedPath=join(out,'seed-private.json'),store=join(out,'empty-store');
writeFileSync(seedPath,JSON.stringify(seed),{mode:0o600});
const before=createHash('sha256').update(readFileSync(seedPath)).digest('hex');
const command=[join(code,'scripts/export-capability-construction-library.mjs'),store,seedPath];
const privateResult=spawnSync(process.execPath,command,{cwd:code,encoding:'utf8',timeout:120000});
assert.equal(privateResult.status,0,'private diagnostic export failed');
assert.equal(JSON.parse(privateResult.stdout).owner,owner);
const publicResult=spawnSync(process.execPath,[...command,'--public'],{cwd:code,encoding:'utf8',timeout:120000});
assert.equal(publicResult.status,1,'public identity-bearing export must be rejected');
assert.equal(publicResult.stdout,'');assert.match(publicResult.stderr,/geneloop_privacy_rejected/);
assert.equal(createHash('sha256').update(readFileSync(seedPath)).digest('hex'),before);
const receipt={total:1,passed:1,id:'construction-library-private-read-and-public-reject',
 scope:'real construction export CLI; synthetic trusted seed and empty private Store; no quality certification claim',
 original_unchanged:true,public_bytes_written:0,cloud_requests:0,production_service_touched:false,
 source_sha256:createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex')};
writeFileSync(join(out,'summary.json'),JSON.stringify(receipt,null,2),{mode:0o600});
console.log(JSON.stringify({total:1,passed:1}));
