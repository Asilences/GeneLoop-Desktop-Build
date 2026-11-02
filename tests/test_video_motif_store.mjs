import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,mkdirSync,rmSync,realpathSync,linkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fixedVideoMotifStore} from '../scripts/harless_video_motif_store.mjs';
function fixture(t){const root=realpathSync(mkdtempSync(join(tmpdir(),'video-published-store-'))),round='round-'+ 'a'.repeat(24);t.after(()=>rmSync(root,{recursive:true,force:true}));mkdirSync(join(root,round));writeFileSync(join(root,'latest.json'),JSON.stringify({policy:round+'/policy.json',library:round+'/source-library.json'}));for(const name of ['policy.json','source-library.json','rsi-update.json','rsi-publication.json'])writeFileSync(join(root,round,name),'{}');return {root,round};}
test('published runtime mount admits only the selected complete immutable round',t=>{const {root}=fixture(t);assert.equal(fixedVideoMotifStore(root),root);writeFileSync(join(root,'raw-private-trace.json'),'{}');assert.throws(()=>fixedVideoMotifStore(root),/non-runtime/);});
test('runtime mount rejects pointer traversal before resolving private paths',t=>{const {root}=fixture(t);writeFileSync(join(root,'latest.json'),JSON.stringify({policy:'../policy.json',library:'../source-library.json'}));assert.throws(()=>fixedVideoMotifStore(root),/pointer/);});
test('runtime mount rejects missing receipt and hardlinked runtime files',t=>{const {root,round}=fixture(t),path=join(root,round,'policy.json');rmSync(path);assert.throws(()=>fixedVideoMotifStore(root),/complete/);linkSync(join(root,round,'source-library.json'),path);assert.throws(()=>fixedVideoMotifStore(root),/invalid runtime file/);});
