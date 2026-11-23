import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,chmodSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {apply} from '../src/adapters/research_native_tools.ts';

function fixture(generic=false,extra=false){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'research-native-'))),workspace=join(root,'workspace'),run=join(root,'run');
 for(const dir of ['inputs','code','outputs/code'])mkdirSync(join(workspace,dir),{recursive:true});mkdirSync(run);
 const saved={...process.env};
 for(const key of Object.keys(process.env))if(key.startsWith('GENELOOP_RESEARCH_'))delete process.env[key];
 const prefix=generic?'GENELOOP_RESEARCH_':'GENELOOP_CHART_';
 Object.assign(process.env,{[prefix+'CONTAINER']:'fixture-container',[prefix+'WORKSPACE']:workspace,[prefix+'RUN']:run});
 if(extra){mkdirSync(join(root,'media'));process.env.GENELOOP_RESEARCH_WORKDIR='/workspace/program';process.env.GENELOOP_RESEARCH_IMAGE_ROOTS=JSON.stringify([{virtual:'/workspace',host:join(root,'media')}]);}
 const tools=new Map(),images=[];
 apply({tools:{register:tool=>tools.set(tool.name,tool)},get:name=>name==='attachments'?{
  async saveImage(value){images.push(value);return {attachmentId:'test-image',mediaType:value.mediaType};}}:undefined});
 return {root,workspace,run,tools,images,close(){process.env=saved;rmSync(root,{recursive:true,force:true});}};
}

test('compatible and generic envs preserve original image bytes and namespace guards',async()=>{
 for(const generic of [false,true]){
  const f=fixture(generic);
  try{
   const bytes=Buffer.from('original-pixel-fixture');writeFileSync(join(f.workspace,'inputs','reference.png'),bytes);
   const tool=f.tools.get('read_image'),result=await tool.execute({file_path:'/work/inputs/reference.png'},{callId:'image'});
   assert.deepEqual(f.images[0].data,bytes);assert.equal(result.path,'/work/inputs/reference.png');
   await assert.rejects(tool.execute({file_path:'/outside/reference.png'},{callId:'escape'}),/outside_workspace/);
  }finally{f.close();}
 }
});

test('host configured video image directory stays outside text-program learning evidence',async()=>{
 const f=fixture(true,true);
 try{
  writeFileSync(join(f.root,'media','frame.jpg'),'frame');
  const tool=f.tools.get('read_image');
  const value=await tool.execute({file_path:'/workspace/frame.jpg'},{callId:'video-image'});
  assert.equal(value.path,'/workspace/frame.jpg');assert.equal(f.images[0].data.toString(),'frame');
  writeFileSync(join(f.workspace,'inputs','spec.png'),'program-input');
  await tool.execute({file_path:'/workspace/program/inputs/spec.png'},{callId:'project-image'});
  assert.equal(f.images[1].data.toString(),'program-input','specific task project mapping precedes broader image directory');
  await assert.rejects(tool.execute({file_path:'/workspace/../missing.jpg'},{callId:'escape'}));
  await assert.rejects(tool.execute({file_path:'/unconfigured/frame.jpg'},{callId:'unknown'}),/outside_workspace/);
 }finally{f.close();}
});

test('actual execute IO captures distinct before/after bytes for the original learner',
 {skip:process.platform==='win32'?'POSIX executable fixture; no Docker/model required':false},async()=>{
 const f=fixture(true);
 try{
  const bin=join(f.root,'bin');mkdirSync(bin);
  const docker=join(bin,'docker');writeFileSync(docker,`#!${process.execPath}\nimport {writeFileSync} from 'node:fs';\nwriteFileSync(process.env.FIXTURE_CHANGED_FILE,'after');process.stdout.write('done');\n`);chmodSync(docker,0o700);
  const target=join(f.workspace,'code','input.json');writeFileSync(target,'before');
  process.env.PATH=bin+':'+process.env.PATH;process.env.FIXTURE_CHANGED_FILE=target;
  const result=await f.tools.get('execute').execute({command:'fixture command'},{callId:'native-id'});
  assert.equal(result.stdout,'done');assert.equal(result.returncode,0);
  const rows=readFileSync(join(f.run,'native-tools.jsonl'),'utf8').trim().split('\n').map(JSON.parse),finished=rows.at(-1);
  assert.equal(finished.sequence,'call-1');assert.equal(finished.call_id,'native-id');
  const before=JSON.parse(readFileSync(finished.boundary.path)),after=JSON.parse(readFileSync(finished.after_boundary.path));
  assert.ok(existsSync(join(before.workspace,'command-tmp')),'original Artifact Runtime temporary namespace exists');
  assert.ok(existsSync(join(after.workspace,'command-tmp')));
  assert.equal(before.before.complete,true);assert.equal(after.after.complete,true);
  assert.equal(readFileSync(before.before.files['code/input.json'].path,'utf8'),'before');
  assert.equal(readFileSync(after.after.files['code/input.json'].path,'utf8'),'after');
  assert.notEqual(before.before.files['code/input.json'].sha256,after.after.files['code/input.json'].sha256);
 }finally{f.close();}
});

test('oversize evidence remains incomplete rather than being silently admitted',
 {skip:process.platform==='win32'?'POSIX executable fixture; no Docker/model required':false},async()=>{
 const f=fixture();
 try{
  const bin=join(f.root,'bin');mkdirSync(bin);const docker=join(bin,'docker');
  writeFileSync(docker,`#!${process.execPath}\nprocess.stdout.write('ok');\n`);chmodSync(docker,0o700);
  process.env.PATH=bin+':'+process.env.PATH;
  writeFileSync(join(f.workspace,'code','large.bin'),Buffer.alloc(1_000_001));
  await f.tools.get('execute').execute({command:'fixture command'},{callId:'large'});
  const row=JSON.parse(readFileSync(join(f.run,'native-tools.jsonl'),'utf8').trim().split('\n').at(-1));
  assert.equal(JSON.parse(readFileSync(row.boundary.path)).before.complete,false);
 }finally{f.close();}
});
