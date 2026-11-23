import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {verifyCompleteTools} from '../apps/desktop/scripts/verify-complete-tools.mjs';
const hash=value=>createHash('sha256').update(value).digest('hex');
test('complete-source roster verifies copied bytes and rejects changed files, duplicate and escaping names',async()=>{
 const home=mkdtempSync(resolve('.local/roster-check-')),resources=join(home,'resources'),root=join(resources,'geneloop-tools');mkdirSync(root,{recursive:true});writeFileSync(join(root,'public.py'),'public');
 const path=join(home,'roster.json');
 const save=files=>writeFileSync(path,JSON.stringify({schema:1,kind:'geneloop-complete-tool-roster-v1',platform:process.platform,arch:process.arch,toolsetId:hash(JSON.stringify(files)),files}));
 const row={path:'public.py',bytes:6,sha256:hash('public')};save([row]);assert.equal((await verifyCompleteTools(resources,path)).allToolsRetained,true);
 writeFileSync(join(root,'public.py'),'edited');await assert.rejects(()=>verifyCompleteTools(resources,path),/Copied tool differs/);
 save([{...row,path:'../outside'}]);await assert.rejects(()=>verifyCompleteTools(resources,path));
 save([row,row]);await assert.rejects(()=>verifyCompleteTools(resources,path));
 save([{...row,kind:'symlink',target:'../outside'}]);await assert.rejects(()=>verifyCompleteTools(resources,path));
});
