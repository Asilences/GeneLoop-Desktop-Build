import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const app = process.cwd();
const runtime = resolve(process.env.GENELOOP_NATIVE_RUNTIME || 'runtime-bundle');
const imports = file => import(pathToFileURL(join(runtime,file)).href);
const {Context} = await imports('node_modules/@deepseek-ai/cordis/lib/index.js').catch(()=>import('@deepseek-ai/cordis'));
const {LocalSandboxProvider} = await imports('node_modules/@deepseek-ai/dsh-sandbox-local/lib/index.js').catch(()=>import('@deepseek-ai/dsh-sandbox-local'));
const {LocalSubprocessRuntime} = await imports('node_modules/@deepseek-ai/dsh-subprocess-local/lib/index.js').catch(()=>import('@deepseek-ai/dsh-subprocess-local'));
const {renderNativeRemotion} = await imports('local-video.mjs');
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
  const receipt = await renderNativeRemotion(ctx,reader,writer,tools,source,'[]',AbortSignal.timeout(180_000));
  assert.equal(receipt.execution,process.platform+'-local-remotion');
  assert.equal(receipt.output.width,640);assert.equal(receipt.output.height,360);
  assert.equal(receipt.output.fullyDecoded,true);assert.equal(receipt.artifacts.length,3);
  assert.ok(readFileSync(join(root,'workspace','GeneLoop 输出',receipt.artifacts[0].name)).length>1000);
  console.log(JSON.stringify({diagnostic:true,...receipt}));
} finally {
  reader.close();writer.close();await ctx.fiber.dispose();process.chdir(app);
  assert.ok(root.startsWith(realpathSync(tmpdir())));
  removeScratchDirectory(root,realpathSync(tmpdir()));
}
