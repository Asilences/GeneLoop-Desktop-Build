import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { inSceneScratch, publishArtifacts } from './local-artifacts.mjs';
import { runNativeProcess } from './native-process.mjs';

const run = promisify(execFile);
const maxSourceBytes = 80 * 1024 * 1024;
const input = ['-protocol_whitelist', 'file,pipe', '-f', 'mov', '-enable_drefs', '0', '-use_absolute_path', '0'];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

async function execute(bin, args, directory, signal) {
  signal.throwIfAborted();
  try {
    return (await run(bin, args, {cwd:directory, signal, timeout:100_000, windowsHide:true,
      maxBuffer:512 * 1024, env:{SystemRoot:process.env.SystemRoot, TEMP:directory, TMP:directory}})).stdout;
  } catch (error) {
    signal.throwIfAborted();
    throw Error('本机媒体工具未完成。请检查 FFmpeg 安装、素材格式或剪辑长度。', {cause:error});
  }
}

async function probe(tools, name, directory, signal) {
  const result = JSON.parse(await execute(tools.ffprobe, ['-v','error', ...input, '-show_entries',
    'format=duration:stream=codec_type,width,height,duration,avg_frame_rate', '-of','json', name], directory, signal));
  const video = result.streams?.find(stream => stream.codec_type === 'video');
  const duration = Number(result.format?.duration);
  if (!video || !Number.isFinite(duration) || duration <= 0 ||
      !Number.isInteger(video.width) || !Number.isInteger(video.height) || video.width < 1 || video.height < 1 || video.width * video.height > 4096 * 2160) {
    throw Error('需要含视频轨的 MP4/MOV，分辨率不得超过本机上限。');
  }
  return { duration, width:video.width, height:video.height, fps:video.avg_frame_rate,
    audio:result.streams.some(stream => stream.codec_type === 'audio') };
}

function stage(reader, path, name, directory, limit) {
  if (typeof path !== 'string' || !/\.(mp4|mov)$/i.test(path)) throw Error('视频素材限工作区内的 MP4/MOV 相对路径。');
  const bytes = reader.readBytes(path, limit);
  writeFileSync(join(directory, name), bytes, {flag:'wx'});
  return {sha256:sha(bytes), bytes:bytes.length};
}

export async function probeLocalVideo(reader, tools, path, signal) {
  return inSceneScratch(async directory => {
    const source = stage(reader, path, 'source.mp4', directory, maxSourceBytes);
    return {path, ...source, ...await probe(tools, 'source.mp4', directory, signal)};
  });
}

export async function renderNativeRemotion(ctx, reader, writer, tools, source, assetList, signal, onReport) {
  if (!tools.remotion || typeof source !== 'string' || !source.trim() || Buffer.byteLength(source) > 128*1024 ||
      typeof assetList !== 'string' || assetList.length > 16_384) throw Error('本机 Remotion 未安装或工程超出限制。');
  const paths = JSON.parse(assetList);
  if (!Array.isArray(paths) || paths.length > 8 || new Set(paths).size !== paths.length ||
      paths.some(path=>typeof path !== 'string' || !/\.(mp4|mov|png|jpg|jpeg|mp3|wav)$/i.test(path))) {
    throw Error('请输入不重复的工作区素材相对路径。');
  }
  return inSceneScratch(async directory => {
    const {mkdirSync} = await import('node:fs');
    mkdirSync(join(directory,'public'));
    let remaining = 16*1024*1024;
    const assets = paths.map((path,index)=>{
      const bytes = reader.readBytes(path,remaining);
      if (!bytes.length) throw Error('渲染素材为空。');
      remaining -= bytes.length;
      const name = 'asset-'+(index+1)+path.slice(path.lastIndexOf('.')).toLowerCase();
      writeFileSync(join(directory,'public',name),bytes,{flag:'wx'});
      return {path,name,sha256:sha(bytes)};
    });
    writeFileSync(join(directory,'entry.tsx'),source,{flag:'wx'});
    const config = join(directory,'render.json');
    const browser = process.platform === 'win32' ? {
      argv:[tools.remotion.browser],enforcement:'chromium-renderer-sandbox',
    } : undefined;
    const launcher = fileURLToPath(new URL('./native/remotion-browser.exe',import.meta.url)).replace(/\.asar([\\/])/,'.asar.unpacked$1');
    writeFileSync(config,JSON.stringify({directory,...tools.remotion,...(browser?{browser:launcher,browserArgv:browser.argv}:{})}),{flag:'wx'});
    const executed = await runNativeProcess(ctx,[process.execPath,fileURLToPath(new URL('./local-remotion-entry.mjs',import.meta.url)),config],
      directory,signal,{confine:process.platform !== 'win32'});
    const rendered = JSON.parse(executed.stdout.trim().split('\n').at(-1));
    const media = await probe(tools,'video.mp4',directory,signal);
    if (media.width !== rendered.composition.width || media.height !== rendered.composition.height ||
        Math.abs(media.duration-rendered.composition.frames/rendered.composition.fps) > 0.15) throw Error('本机渲染规格核验失败。');
    await execute(tools.ffmpeg,['-v','error','-nostdin','-xerror',...input,'-i','video.mp4',
      '-map','0:v:0','-map','0:a?','-f','null','-'],directory,signal);
    for (const asset of assets) if (sha(reader.readBytes(asset.path,16*1024*1024)) !== asset.sha256) throw Error('来源素材已变化，请重新渲染。');
    const output = join(directory,'video.mp4');
    if (statSync(output).size > maxSourceBytes) throw Error('本机渲染产物过大。');
    const bytes = readFileSync(output);
    const receipt = {schema_version:1,execution:process.platform+'-local-remotion',
      sandboxEnforcement:browser?.enforcement ?? executed.enforcement,
      sandboxScope:browser?'browser-renderer':'renderer-process',source_sha256:sha(Buffer.from(source)),assets,
      remotionVersion:rendered.remotionVersion,output:{...media,sha256:sha(bytes),fullyDecoded:true}};
    return {...receipt,artifacts:publishArtifacts(writer,onReport,signal,[
      {extension:'mp4',bytes},{extension:'tsx',bytes:Buffer.from(source)},
      {extension:'json',bytes:Buffer.from(JSON.stringify(receipt,null,2))},
    ])};
  });
}

export async function renderHybridVideo(reader, writer, tools, source, assetList, signal, approve, onReport, onPhase) {
  const sourceBytes = Buffer.byteLength(source);
  if (!source.trim() || sourceBytes > 128 * 1024 || assetList.length > 16_384) throw Error('Remotion 工程超出大小限制。');
  const paths = JSON.parse(assetList);
  if (!Array.isArray(paths) || paths.length > 8 || new Set(paths).size !== paths.length ||
      paths.some(path => typeof path !== 'string' || !/\.(mp4|mov|png|jpg|jpeg|mp3|wav)$/i.test(path))) {
    throw Error('请输入不重复的工作区素材相对路径。');
  }
  let remaining = 16 * 1024 * 1024;
  const assets = paths.map((path, index) => {
    const bytes = reader.readBytes(path, remaining);
    if (!bytes.length) throw Error('渲染素材为空。');
    remaining -= bytes.length;
    return { path, bytes, sha256: sha(bytes), name: 'asset-' + (index+1) + path.slice(path.lastIndexOf('.')).toLowerCase() };
  });
  if (!await approve({ sourceBytes, assets:assets.map(({path, bytes}) => ({path, bytes:bytes.length})) })) {
    return { status:'denied', message:'用户取消了服务器渲染。本轮不要再次请求上传，可改用本机工具。' };
  }
  signal.throwIfAborted();
  onPhase?.('remote-render');
  let video;
  try { video = await fetchRenderedVideo(source, assets, signal); }
  finally { onPhase?.('local'); }
  const digest = sha(video);
  return inSceneScratch(async directory => {
    writeFileSync(join(directory, 'video.mp4'), video, {flag:'wx'});
    const info = await probe(tools, 'video.mp4', directory, signal);
    await execute(tools.ffmpeg, ['-v','error','-nostdin','-xerror', ...input,'-i','video.mp4',
      '-map','0:v:0','-map','0:a?','-f','null','-'], directory, signal);
    const receipt = {schema_version:1, execution:'server-remotion', source_sha256:sha(Buffer.from(source)),
      assets:assets.map(({path, name, sha256}) => ({path, name, sha256})), output:{...info, sha256:digest, fullyDecoded:true}};
    return {...receipt, artifacts:publishArtifacts(writer, onReport, signal, [
      {extension:'mp4', bytes:video}, {extension:'tsx', bytes:Buffer.from(source)},
      {extension:'json', bytes:Buffer.from(JSON.stringify(receipt, null, 2))},
    ])};
  });
}

async function fetchRenderedVideo(source, assets, signal) {
  const endpoint = new URL('../video/render', process.env.DEEPSEEK_BASE_URL + '/');
  const response = await fetch(endpoint, {
    method:'POST', redirect:'error', signal:AbortSignal.any([signal, AbortSignal.timeout(270_000)]),
    headers:{'content-type':'application/json', authorization:'Bearer ' + process.env.DEEPSEEK_API_KEY},
    body:JSON.stringify({ source, assets:assets.map(({name, bytes, sha256}) => ({name, bytes:bytes.toString('base64'), sha256})) }),
  });
  if (!response.ok) {
    await response.body?.cancel();
    throw Error('服务器渲染未完成，请检查 Remotion 工程、素材或服务状态。');
  }
  const length = Number(response.headers.get('content-length'));
  if (response.headers.get('content-type') !== 'video/mp4' || !Number.isSafeInteger(length) || length < 1 || length > maxSourceBytes || !response.body) {
    await response.body?.cancel();
    throw Error('服务器返回了无效的渲染产物。');
  }
  const chunks = [];
  let received = 0;
  for await (const chunk of response.body) {
    received += chunk.length;
    if (received > length) throw Error('服务器渲染产物超出预期长度。');
    chunks.push(chunk);
  }
  const video = Buffer.concat(chunks);
  const digest = sha(video);
  if (received !== length || digest !== response.headers.get('x-geneloop-sha256')) throw Error('服务器渲染产物摘要校验失败。');
  return video;
}

export async function renderLocalVideo(reader, writer, tools, plan, signal, onReport) {
  if (typeof plan !== 'string' || plan.length > 16_384) throw Error('时间线过长。');
  const segments = JSON.parse(plan);
  if (!Array.isArray(segments) || segments.length < 1 || segments.length > 8 ||
      segments.some(row => !row || Object.keys(row).sort().join(',') !== 'end,path,sha256,start' ||
        typeof row.path !== 'string' || typeof row.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(row.sha256) || !Number.isFinite(row.start) || !Number.isFinite(row.end) ||
        row.start < 0 || row.end - row.start < 0.1)) throw Error('时间线需要 1–8 个含 path/sha256/start/end 的片段，请先探测素材。');
  const plannedDuration = segments.reduce((sum, row) => sum + row.end - row.start, 0);
  if (plannedDuration > 90) throw Error('本机视频预览版最长交付 90 秒。');
  return inSceneScratch(async directory => {
    const sources = new Map();
    let sourceBytes = 0;
    const inputs = [], filters = [], pads = [];
    for (const [index, row] of segments.entries()) {
      signal.throwIfAborted();
      let source = sources.get(row.path);
      if (!source) {
        const name = 'source-' + sources.size + '.mp4';
        const version = stage(reader, row.path, name, directory, Math.min(maxSourceBytes, 240 * 1024 * 1024 - sourceBytes));
        sourceBytes += version.bytes;
        source = {name, ...version, ...await probe(tools, name, directory, signal)};
        sources.set(row.path, source);
      }
      if (row.sha256 !== source.sha256) throw Error('素材内容已变化，请重新探测。');
      if (row.end > source.duration + 0.05) throw Error('剪辑片段超出素材时长。');
      const duration = (row.end - row.start).toFixed(3);
      inputs.push(...input, '-ss', row.start.toFixed(3), '-t', duration, '-i', source.name);
      filters.push('['+index+':v:0]setpts=PTS-STARTPTS,'+
        'scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,'+
        'pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v'+index+']');
      const audio = source.audio
        ? '['+index+':a:0]aresample=48000,aformat=channel_layouts=stereo,asetpts=N/SR/TB,apad'
        : 'anullsrc=r=48000:cl=stereo';
      filters.push(audio+',atrim=duration='+duration+'[a'+index+']');
      pads.push('[v'+index+'][a'+index+']');
    }
    // Concatenate decoded audio and encode AAC once, avoiding per-clip encoder delay.
    filters.push(pads.join('')+'concat=n='+segments.length+':v=1:a=1[vcat][audio]', '[vcat]fps=30[video]');
    await execute(tools.ffmpeg, ['-v','error','-nostdin','-xerror','-filter_complex_threads','2', ...inputs,
      '-filter_complex',filters.join(';'),'-map','[video]','-map','[audio]','-map_metadata','-1','-map_chapters','-1',
      '-c:v','libx264','-preset','veryfast','-threads','4','-c:a','aac','-ar','48000','-ac','2',
      '-movflags','+faststart','-n','video.mp4'], directory, signal);
    const media = await probe(tools, 'video.mp4', directory, signal);
    if (Math.abs(media.duration - plannedDuration) > 0.1 + segments.length * 0.06 ||
        media.width !== 1280 || media.height !== 720 || media.fps !== '30/1' || !media.audio) {
      throw Error('导出视频的时长、画面规格或音轨验证失败。');
    }
    await execute(tools.ffmpeg, ['-v','error','-nostdin','-xerror', ...input,'-i','video.mp4',
      '-map','0:v:0','-map','0:a:0','-f','null','-'], directory, signal);
    const output = join(directory, 'video.mp4');
    if (statSync(output).size > 80 * 1024 * 1024) throw Error('导出视频超过本机交付上限。');
    const bytes = readFileSync(output);
    const receipt = Buffer.from(JSON.stringify({schema_version:1, segments, sources:[...sources].map(([path, source]) => ({
      path, sha256:source.sha256, bytes:source.bytes,
    })), output:{...media, sha256:sha(bytes), fullyDecoded:true}}, null, 2));
    return { ...media, artifacts:publishArtifacts(writer, onReport, signal, [
      {extension:'mp4', bytes}, {extension:'json', bytes:receipt},
    ]) };
  });
}
