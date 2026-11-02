import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {request} from 'node:http';
const typed={skip:!process.features?.typescript};
function temporary(){return realpathSync(mkdtempSync(join(tmpdir(),'geneloop-video-test-')));}
function cleanup(root){assert.ok(root.startsWith(realpathSync(tmpdir())+sep)&&root.includes('geneloop-video-test-'));rmSync(root,{recursive:true,force:true});}
function installation(root){
 const runtimeRoot=join(root,'runtime'),mediaToolsRoot=join(root,'media');
 for(const path of ['runtime/node_modules/remotion','runtime/node_modules/@remotion/cli','media/node_modules/@ffmpeg-installer/linux-x64'])mkdirSync(join(root,path),{recursive:true});
 writeFileSync(join(runtimeRoot,'node_modules/remotion/package.json'),'{"version":"4.0.539"}');
 writeFileSync(join(runtimeRoot,'node_modules/@remotion/cli/remotion-cli.js'),'fixture');
 writeFileSync(join(mediaToolsRoot,'node_modules/@ffmpeg-installer/linux-x64/ffmpeg'),'fixture');
 return {runtimeRoot,mediaToolsRoot,image:'sha256:'+'a'.repeat(64)};
}
test('Video recipe uses fixed runtime and only the owning Session; caller cannot choose host mounts or network',{skip:!process.features?.typescript||process.platform!=='linux'},async()=>{
 const {videoConfiguration,videoCommand}=await import('../src/adapters/geneloop_video.ts');
 const root=temporary(),session='session-11111111-1111-4111-8111-111111111111';
 try{
  const config=installation(root);mkdirSync(join(root,'sessions',session,'work'),{recursive:true});
  assert.deepEqual(videoConfiguration(config),config);
  assert.throws(()=>videoConfiguration({...config,image:'mutable:latest'}));
  assert.throws(()=>videoConfiguration({...config,network:'host'}));
  const recipe=videoCommand(root,session,'node --version',config),argv=recipe.argv;
  assert.equal(argv[0],'/usr/bin/docker');assert.equal(argv[argv.indexOf('--network')+1],'none');
  assert.ok(argv.includes('--read-only'));assert.ok(argv.includes('--cap-drop=ALL'));
  assert.ok(!argv.some(s=>s.includes('docker.sock')||s.includes('accounts.json')||s.includes('DEEPSEEK_API_KEY')));
  assert.ok(argv.includes(`type=bind,source=${root}/sessions/${session}/work/remotion/public,target=/work/public,readonly`));
  assert.throws(()=>videoCommand(root,'session-22222222-2222-4222-8222-222222222222','true',config));
  assert.throws(()=>videoCommand(root,session,'',config));
  writeFileSync(join(config.runtimeRoot,'.env'),'private');assert.throws(()=>videoConfiguration(config));
  if(process.platform!=='win32'){
   const foreign='session-33333333-3333-4333-8333-333333333333';symlinkSync(join(root,'sessions',session),join(root,'sessions',foreign));
   assert.throws(()=>videoCommand(root,foreign,'true',config));
  }
 }finally{cleanup(root);}
});
test('A gateway without video installation rejects the video endpoint',typed,async()=>{
 if(process.platform==='win32')return;
 const {startCommandBroker}=await import('../src/adapters/geneloop_command_broker.ts');const root=temporary();
 const broker=await startCommandBroker({output:root,python:'/usr/bin/python3',node:process.execPath});
 try{
  const status=await new Promise((done,reject)=>{const req=request({socketPath:broker.socketPath,path:'/video',method:'POST'},res=>{res.resume();res.on('end',()=>done(res.statusCode));});req.on('error',reject);req.end(JSON.stringify({session:'session-11111111-1111-4111-8111-111111111111',command:'true'}));});
  assert.equal(status,400);
 }finally{broker.close();cleanup(root);}
});
test('Video artifacts need current task, actual decode receipt and unchanged media/source; copies stay immutable',typed,async()=>{
 const {verifiedVideoFiles,comparisonArtifacts,captureComparisonDeliveries}=await import('../src/adapters/harless_comparison_artifacts.ts');
 const root=temporary(),work=join(root,'work'),task='a'.repeat(32),folder=join(work,'outputs/video',task);
 mkdirSync(folder,{recursive:true});const eventsPath=join(root,'tasks',task,'events.jsonl');mkdirSync(join(root,'tasks',task),{recursive:true});writeFileSync(eventsPath,'');
 try{
  const files=['video.mp4','source.tsx'].map(name=>{const data=Buffer.from('verified '+name),path=join(folder,name);writeFileSync(path,data);return{name:`outputs/video/${task}/${name}`,bytes:data.length,sha256:createHash('sha256').update(data).digest('hex')};});
  const receipt={schema_version:1,kind:'video-delivery-v1',task_id:task,full_video_decode:true,source_version:files[1].sha256,files};
  const save=()=>writeFileSync(join(folder,'delivery.json'),JSON.stringify(receipt));save();
  assert.equal(verifiedVideoFiles(work,eventsPath).size,2);
  assert.equal(verifiedVideoFiles(work,join(root,'tasks','b'.repeat(32),'events.jsonl')).size,0);
  receipt.full_video_decode=false;save();assert.equal(verifiedVideoFiles(work,eventsPath).size,0);receipt.full_video_decode=true;save();
  const service=comparisonArtifacts(root),ctx={turn:'native-'+task,lane:'baseline',attempt:0,workspace:work,adapter:'video',status:'completed',eventsPath};
  const rows=captureComparisonDeliveries(service,ctx);assert.equal(rows.length,2);assert.ok(rows.every(r=>r.verification==='video-delivery-v1'));
  assert.equal(service.read(ctx.turn,'baseline',rows.find(r=>r.name.endsWith('.mp4'))).toString(),'verified video.mp4');
  writeFileSync(join(folder,'video.mp4'),'tamper');assert.equal(verifiedVideoFiles(work,eventsPath).size,0);
  assert.equal(captureComparisonDeliveries(service,{...ctx,turn:'unverified'}).length,0);
  assert.equal(service.read(ctx.turn,'baseline',rows.find(r=>r.name.endsWith('.mp4'))).toString(),'verified video.mp4');
  assert.throws(()=>service.read(ctx.turn,'motif',rows[0]));
 }finally{cleanup(root);}
});
