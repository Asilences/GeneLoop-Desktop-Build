// Trusted renderer entry. User TSX is bundled for Chromium, never imported into
// this Node process. All subprocesses belong to the upstream DSH managed range.
import { renderMedia, selectComposition, openBrowser, makeCancelSignal } from '@remotion/renderer';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const config = JSON.parse(readFileSync(process.argv[2], 'utf8'));
if (config.browserArgv) process.env.GENELOOP_REMOTION_BROWSER_PREFIX=JSON.stringify(config.browserArgv);
let browserInstance;
const {cancelSignal,cancel}=makeCancelSignal();
const stop=()=>{cancel();void browserInstance?.close({silent:true});};
process.once('SIGTERM',stop);process.once('SIGINT',stop);
const runtime = dirname(fileURLToPath(import.meta.url));
// spawn() cannot address an ASAR entry. Keep esbuild's JS in ASAR and select
// only its native binary from the adjacent unpacked package.
const esbuildName = process.platform === 'win32' ? 'esbuild.exe' : 'bin/esbuild';
process.env.ESBUILD_BINARY_PATH = join(runtime,'node_modules','@esbuild',process.platform+'-'+process.arch,esbuildName)
  .replace(/\.asar([\\/])/,'.asar.unpacked$1');
const {bundle} = await import('@remotion/bundler');
const serveUrl = await bundle({entryPoint:join(config.directory, 'entry.tsx'),
  publicDir:join(config.directory,'public'), outDir:join(config.directory,'bundle'),
  rootDir:config.directory, enableCaching:false, symlinkPublicDir:false,
  webpackOverride:previous => ({...previous, resolve:{...previous.resolve,
    modules:[join(runtime,'node_modules'),...(previous.resolve?.modules || [])]}}),
});
const options = {serveUrl, id:'Main', browserExecutable:config.browser,
  binariesDirectory:config.binaries, timeoutInMilliseconds:30_000, logLevel:'error',
  chromiumOptions:{disableWebSecurity:false},
};
browserInstance = await openBrowser('chrome',{browserExecutable:config.browser,logLevel:'error'});
try {
const composition = await selectComposition({...options,browserInstance});
if (composition.width * composition.height > 1920 * 1080 || composition.width < 16 || composition.height < 16 ||
    composition.durationInFrames / composition.fps > 90 || composition.fps > 60 || composition.fps < 1) {
  throw Error('本机视频规格超出 1080p、60fps、90秒范围。');
}
await renderMedia({...options, browserInstance, cancelSignal, composition, codec:'h264', pixelFormat:'yuv420p',
  outputLocation:join(config.directory,'video.mp4'), concurrency:2,
});
console.log(JSON.stringify({composition:{width:composition.width,height:composition.height,
  fps:composition.fps,frames:composition.durationInFrames}, remotionVersion:'4.0.539'}));
} finally {await browserInstance.close({silent:true});}
