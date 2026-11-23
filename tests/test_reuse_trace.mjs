import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,symlinkSync,readdirSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createArtifactTrace,createReuseTrace} from '../src/adapters/artifact_motif_trace.ts';
test('native boundaries preserve before/after bytes without following links or rewriting sources',t=>{
 const root=realpathSync(mkdtempSync(join(tmpdir(),'reuse-boundary-')));t.after(()=>rmSync(root,{recursive:true,force:true}));
 const work=join(root,'work'),output=join(root,'task');mkdirSync(join(work,'code'),{recursive:true});mkdirSync(join(work,'inputs'));mkdirSync(output);
 const path=join(work,'code/data.json');writeFileSync(path,'[1]');writeFileSync(join(root,'private.json'),'secret');symlinkSync(join(root,'private.json'),join(work,'code/link.json'));
 const tracker=createReuseTrace(work,output),execution={callId:'call',name:'bash',arguments:{command:'observed command'}};
 tracker.before(execution);writeFileSync(path,'[2]');tracker.after(execution,{isError:false,content:[]});
 const record=JSON.parse(readFileSync(join(output,'reuse-boundaries.jsonl'),'utf8'));
 assert.notEqual(record.before.files['code/data.json'].sha256,record.after.files['code/data.json'].sha256);
 assert.deepEqual(Object.keys(record.before.files),['code/data.json']);assert.equal(record.before.scope,'bounded_text_files_not_all_files');
 assert.equal(readFileSync(join(output,'reuse-evidence',record.before.files['code/data.json'].sha256),'utf8'),'[1]');
 assert.equal(readFileSync(path,'utf8'),'[2]');assert.equal(readdirSync(join(output,'reuse-evidence')).length,2);
});

test('Artifact captures SVG and a sixth directory level while Script keeps its previous scope',t=>{
 const work=realpathSync(mkdtempSync(join(tmpdir(),'artifact-boundary-')));
 t.after(()=>rmSync(work,{recursive:true,force:true}));
 const code=join(work,'code'),deep=join(code,'one/two/three/four/five/six');
 mkdirSync(deep,{recursive:true});writeFileSync(join(deep,'nested.txt'),'deep');
 writeFileSync(join(code,'preview.svg'),'<svg/>');writeFileSync(join(code,'ordinary.txt'),'text');
 const execution={callId:'call',name:'tool',arguments:{}};
 const capture=(kind,factory)=>{
  const output=join(work,kind),tracker=factory(work,output);
  tracker.before(execution);tracker.after(execution,{isError:false});
  return JSON.parse(readFileSync(join(output,'reuse-boundaries.jsonl'),'utf8')).before;
 };
 const artifact=capture('artifact',createArtifactTrace),script=capture('script',createReuseTrace);
 assert.equal(artifact.scope,'bounded_text_and_svg_files');assert.equal(artifact.complete,true);
 assert.deepEqual(Object.keys(artifact.files).sort(),['code/one/two/three/four/five/six/nested.txt','code/ordinary.txt','code/preview.svg']);
 assert.equal(script.scope,'bounded_text_files_not_all_files');assert.equal(script.complete,false);
 assert.deepEqual(Object.keys(script.files),['code/ordinary.txt']);
});

test('an unreadable directory aborts Artifact evidence and is skipped in Script evidence',t=>{
 const work=realpathSync(mkdtempSync(join(tmpdir(),'artifact-unreadable-')));
 t.after(()=>rmSync(work,{recursive:true,force:true}));
 writeFileSync(join(work,'inputs'),'not a directory');
 mkdirSync(join(work,'code'));writeFileSync(join(work,'code/source.txt'),'example');
 const execution={callId:'call',name:'tool',arguments:{}},result={isError:false};
 const archive=join(work,'artifact'),artifact=createArtifactTrace(work,archive);
 artifact.before(execution);artifact.after(execution,result);
 assert.equal(existsSync(join(archive,'reuse-boundaries.jsonl')),false);
 const journal=join(work,'script'),script=createReuseTrace(work,journal);
 script.before(execution);script.after(execution,result);
 const record=JSON.parse(readFileSync(join(journal,'reuse-boundaries.jsonl'),'utf8'));
 assert.deepEqual(Object.keys(record.before.files),['code/source.txt']);
});
