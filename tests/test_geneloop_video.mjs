import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {request} from 'node:http';
import {EventEmitter} from 'node:events';
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
 const {videoConfiguration,videoCommand,videoProjectCommand}=await import('../src/adapters/geneloop_video.ts');
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
  assert.ok(argv.includes('geneloop.session='+session));
  const desktop=videoProjectCommand(recipe.project,'node --version',config);
  assert.ok(desktop.argv.includes(`type=bind,source=${recipe.project},target=/work,readonly`));
  assert.throws(()=>videoCommand(root,'session-22222222-2222-4222-8222-222222222222','true',config));
  assert.throws(()=>videoCommand(root,session,'',config));
  writeFileSync(join(config.runtimeRoot,'.env'),'private');assert.throws(()=>videoConfiguration(config));
  if(process.platform!=='win32'){
   const foreign='session-33333333-3333-4333-8333-333333333333';symlinkSync(join(root,'sessions',session),join(root,'sessions',foreign));
   assert.throws(()=>videoCommand(root,foreign,'true',config));
  }
 }finally{cleanup(root);}
});
test('桌面 Remotion 只接受固定素材名称、字节摘要和入口源码',typed,async()=>{
 const {desktopVideoInput}=await import('../src/adapters/geneloop_desktop_video.ts');
 const bytes=Buffer.from('sample');
 const asset={name:'asset-1.png',bytes:bytes.toString('base64'),sha256:createHash('sha256').update(bytes).digest('hex')};
 const parse=(assets,extra={})=>desktopVideoInput(Buffer.from(JSON.stringify({source:'registerRoot(Entry)',assets,...extra})));
 assert.deepEqual(parse([asset]).assets,[{name:asset.name,bytes}]);
 assert.throws(()=>parse([{...asset,name:'../outside.png'}]));
 assert.throws(()=>parse([{...asset,bytes:'AA=='}]));
 assert.throws(()=>parse([asset,{...asset,name:asset.name.toUpperCase()}]));
 assert.throws(()=>parse([asset],{command:'pwd'}));
});
test('拒绝桌面渲染时只生成待授权的文件清单',async()=>{
 const {renderHybridVideo}=await import('../apps/desktop/runtime/local-video.mjs');
 const source='registerRoot(Entry)';
 let approval;
 const result=await renderHybridVideo({
  readBytes(path){assert.equal(path,'素材/录屏.mp4');return Buffer.from('fixture');},
 },null,null,source,JSON.stringify(['素材/录屏.mp4']),new AbortController().signal,request=>{
  approval=request;
  return false;
 });
 assert.equal(result.status,'denied');
 assert.deepEqual(approval,{sourceBytes:Buffer.byteLength(source),assets:[{path:'素材/录屏.mp4',bytes:7}]});
});
test('桌面 Remotion 拒绝无凭证请求及非视频任务，且不读取上传内容',typed,async()=>{
 const {createDesktopModelRoute,DESKTOP_MODEL_PATH}=await import('../scripts/harless_desktop_model.mjs');
 const control=await import('node:http').then(({createServer})=>createServer((req,res)=>{req.resume();res.end('{}');}));
 await new Promise(resolve=>control.listen(0,'127.0.0.1',resolve));
 let reads=0;
 const route=createDesktopModelRoute({
  config:{desktopLocalModel:{accountIds:['test'],videoRendering:true},apiKey:'fixture',
   memberPolicy:{control_token:'fixture'},upstreamBrokerPort:control.address().port,upstreamControlPort:control.address().port},
  videoRenderer:{},json:(res,status,body)=>Object.assign(res,{status,body}),
  requireOrigin:()=>true,sessionHash:()=> 'session',isSessionActive:()=>true,
  readBounded:req=>{reads++;return Buffer.from(req.input);},
 });
 try{
  const denied=new EventEmitter(),path=DESKTOP_MODEL_PATH+'/video/render';
  await route.handle({method:'POST',headers:{}},denied,path);
  assert.equal(denied.status,403);
  const lease=new EventEmitter();
  await route.handle({method:'POST',headers:{},input:'{"scene":"ppt"}'},lease,DESKTOP_MODEL_PATH+'/lease',{id:'test'});
  assert.equal(lease.status,200);
  assert.equal(lease.body.videoRendering,undefined);
  const headers={authorization:'Bearer '+lease.body.token};
  const wrong=new EventEmitter();
  await route.handle({method:'POST',headers},wrong,path);
  assert.equal(wrong.status,403);
  assert.equal(reads,1);
  await route.handle({method:'DELETE',headers},new EventEmitter(),DESKTOP_MODEL_PATH+'/lease');
  const videoLease=new EventEmitter();
  await route.handle({method:'POST',headers:{},input:'{"scene":"video"}'},videoLease,DESKTOP_MODEL_PATH+'/lease',{id:'test'});
  assert.equal(videoLease.body.videoRendering,true);
  const videoHeaders={authorization:'Bearer '+videoLease.body.token};
  const invalid=new EventEmitter();
  await route.handle({method:'POST',headers:videoHeaders,input:'{"command":"pwd"}'},invalid,path);
  assert.equal(invalid.status,422);
  await route.handle({method:'DELETE',headers:videoHeaders},new EventEmitter(),DESKTOP_MODEL_PATH+'/lease');
 }finally{route.close();control.closeAllConnections();await new Promise(resolve=>control.close(resolve));}
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
