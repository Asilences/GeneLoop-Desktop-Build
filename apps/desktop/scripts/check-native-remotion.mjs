import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const app = process.cwd();
const runtime = resolve(process.env.GENELOOP_NATIVE_RUNTIME || 'runtime-bundle');
const imports = file => import(pathToFileURL(join(runtime,file)).href);
const {Context} = await imports('node_modules/@deepseek-ai/cordis/lib/index.js').catch(()=>import('@deepseek-ai/cordis'));
const {LocalSandboxProvider} = await imports('node_modules/@deepseek-ai/dsh-sandbox-local/lib/index.js').catch(()=>import('@deepseek-ai/dsh-sandbox-local'));
const {LocalSubprocessRuntime} = await imports('node_modules/@deepseek-ai/dsh-subprocess-local/lib/index.js').catch(()=>import('@deepseek-ai/dsh-subprocess-local'));
const {renderNativeRemotion,renderLocalVideo,probeLocalVideo} = await imports('local-video.mjs');
const {nativeVideoTools}=await imports('local-video-workflow.mjs');
const {removeScratchDirectory} = await imports('local-artifacts.mjs');
const {openWorkspaceReader,openReportWriter} = await imports('local-files.mjs');
const toolRoot=resolve(process.env.GENELOOP_NATIVE_TOOLS || 'desktop-tools-bundle');
const manifest = JSON.parse(readFileSync(join(toolRoot,'manifest.json'),'utf8'));
const suffix = process.platform === 'win32'?'.exe':'';
const compositor = process.platform === 'win32'?'win32-x64-msvc':'darwin-'+process.arch;
const modules = runtime.endsWith('.asar')?runtime+'.unpacked/node_modules':resolve('node_modules');
const tools = {
  ffmpeg:join(toolRoot,'ffmpeg/ffmpeg'+suffix),ffprobe:join(toolRoot,'ffmpeg/ffprobe'+suffix),
  remotion:{browser:resolve(toolRoot,manifest.browser),binaries:join(modules,'@remotion/compositor-'+compositor)},
};
const root = realpathSync(mkdtempSync(join(tmpdir(),'geneloop-remotion-')));
const ctx = new Context();
new LocalSandboxProvider(ctx,{runnerCommand:[],runnerFailureSignatures:[],probeTimeoutMs:10000});
new LocalSubprocessRuntime(ctx);
mkdirSync(join(root,'workspace'));
const reader = openWorkspaceReader(join(root,'workspace')),writer = openReportWriter(join(root,'workspace'));
// No model involved: exercise real TSX bundling, native Chrome, compositor,
// FFmpeg decoding, source preservation and artifact publication.
const source = `import React from 'react'; import {registerRoot,Composition,AbsoluteFill,useCurrentFrame} from 'remotion';
const Scene=()=>{const frame=useCurrentFrame();return <AbsoluteFill style={{background:'#142530',color:'white',fontSize:36,alignItems:'center',justifyContent:'center'}}>GeneLoop {frame}</AbsoluteFill>};
registerRoot(()=> <Composition id="Main" component={Scene} durationInFrames={12} fps={12} width={640} height={360}/>);`;
try {
  process.chdir(root);
  const samples=8000,wav=Buffer.alloc(44+samples*2);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);
  wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);
  wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(samples*2,40);
  for(let i=0;i<samples;i++)wav.writeInt16LE(Math.round(16384*Math.sin(2*Math.PI*440*i/16000)),44+i*2);
  writeFileSync(join(root,'workspace/tone.wav'),wav);
  // This check exercises v4 media contracts. Official shell composition is
  // exercised by check-native-common; this fixture grants only project paths.
  const common={resolvePath:path=>join(root,'video-project',path)};
  const videoTools=nativeVideoTools(ctx,reader,writer,tools,AbortSignal.timeout(180000),undefined,common);
  const invoke=(name,args)=>videoTools.find(t=>t.name==='mcp__native_video__'+name).execute(args);
  const asset=await invoke('pin_asset',{name:'tone.wav'});
  const audio=await invoke('probe_media',{source_id:asset.source_id});
  assert.ok(audio.streams.some(stream=>stream.codec_type==='audio'&&Number(stream.sample_rate)===16000));
  const legacy=nativeVideoTools(ctx,reader,writer,tools,AbortSignal.timeout(180000));
  await assert.rejects(legacy.find(t=>t.name==='mcp__native_video__run_command').execute({command:'powershell Get-ChildItem'}));
  // A generated entry must never become a Node-side webpack inline loader.
  const marker=join(root,'forbidden-loader-marker');
  // A mislabeled image is still untrusted input and must not execute in Node.
  writeFileSync(join(root,'workspace','loader.png'),`require('node:fs').writeFileSync(${JSON.stringify(marker)},'loader executed');module.exports=()=>'';`);
  const loaderSource=`import '!!./public/asset-1.png!react';`;
  await assert.rejects(renderNativeRemotion(ctx,reader,writer,tools,loaderSource,'["loader.png"]',AbortSignal.timeout(30_000)));
  assert.equal(existsSync(marker),false,'生成的视频代码不得作为 Node 加载器执行');
  const receipt = await invoke('render_source',{text:source});
  const preview=await videoTools.find(t=>t.name==='mcp__native_video__inspect_render').execute({seconds:[0,0.5]},{signal:AbortSignal.timeout(90000)});
  assert.equal(preview.content.filter(block=>block.type==='image').length,2);
  assert.equal(preview.result.preview_width,640);assert.equal(preview.result.preview_height,360);
  await invoke('write_source',{text:source+'\n'});
  await assert.rejects(videoTools.find(t=>t.name==='mcp__native_video__inspect_render').execute({seconds:[0]},{signal:AbortSignal.timeout(90000)}));
  assert.equal(receipt.execution,process.platform+'-local-remotion');
  assert.equal(receipt.output.width,640);assert.equal(receipt.output.height,360);
  assert.equal(receipt.output.fullyDecoded,true);assert.equal(receipt.artifacts.length,3);
  assert.ok(readFileSync(join(root,'workspace','GeneLoop 输出',receipt.artifacts[0].name)).length>1000);
  writeFileSync(join(root,'workspace','source.mp4'),readFileSync(join(root,'workspace','GeneLoop 输出',receipt.artifacts[0].name)));
  const media=await probeLocalVideo(reader,tools,'source.mp4',AbortSignal.timeout(30_000));
  const clip=await renderLocalVideo(reader,writer,tools,JSON.stringify([
    {path:'source.mp4',sha256:media.sha256,start:0,end:0.25},
    {path:'source.mp4',sha256:media.sha256,start:0.5,end:0.75},
  ]),AbortSignal.timeout(180_000),undefined,ctx);
  assert.equal(clip.output?.width??clip.width,1280);assert.equal(clip.output?.height??clip.height,720);
  assert.ok(Math.abs((clip.output?.duration??clip.duration)-0.5)<0.12);
  console.log(JSON.stringify({diagnostic:true,inlineLoaderRejected:true,timelineTrimAndConcat:true,nativeAudioProbe:true,actualFrameInspection:true,...receipt}));
} finally {
  reader.close();writer.close();await ctx.fiber.dispose();process.chdir(app);
  assert.ok(root.startsWith(realpathSync(tmpdir())));
  removeScratchDirectory(root,realpathSync(tmpdir()));
}
