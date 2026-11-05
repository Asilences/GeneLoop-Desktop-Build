import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { inSceneScratch, publishArtifacts } from './local-artifacts.mjs';

export async function createLocalPresentation(plan, reader, writer, signal, onReport) {
  if (typeof plan !== 'string' || Buffer.byteLength(plan) > 256 * 1024) throw Error('演示文稿计划超出本机限制。');
  const deck = JSON.parse(plan);
  if (deck?.layout_policy !== undefined || !Array.isArray(deck?.slides) || deck.slides.some(slide =>
    slide?.image !== undefined || slide?.visible_sources !== undefined)) {
    throw Error('本机演示文稿请使用结构化文字、表格、图表和流程图，来源放入每页 sources。');
  }
  const sources = [];
  let imageBytes = 0;
  for (const [index,slide] of deck.slides.entries()) {
    if (!slide || !Object.hasOwn(slide, 'image_path')) continue;
    const path = slide.image_path;
    if (typeof path !== 'string' || !/\.png$/i.test(path)) throw Error('图片需要授权目录中的 PNG 相对路径。');
    const bytes = reader.readBytes(path, 6 * 1024 * 1024);
    if (bytes.length < 33 || bytes.subarray(0,8).toString('hex') !== '89504e470d0a1a0a' ||
        bytes.toString('ascii',12,16) !== 'IHDR') throw Error('无效的 PNG 图件。');
    imageBytes += bytes.length;
    if (imageBytes > 12 * 1024 * 1024) throw Error('演示文稿的图件总大小超过 12 MiB。');
    sources.push({page:index + 1,path,sha256:createHash('sha256').update(bytes).digest('hex')});
    slide.image = {data:'image/png;base64,'+bytes.toString('base64'), width:bytes.readUInt32BE(16), height:bytes.readUInt32BE(20)};
    delete slide.image_path;
  }
  const { render } = await import('./local-ppt-render.mjs');
  return inSceneScratch(async directory => {
    signal.throwIfAborted();
    const output = join(directory, 'presentation.pptx');
    const {layout_manifest:layout} = await render(deck, output);
    const size = statSync(output).size;
    if (size < 4 || size > 30 * 1024 * 1024) throw Error('PPTX 输出超出本机限制。');
    const bytes = readFileSync(output);
    if (bytes.readUInt32LE(0) !== 0x04034b50) throw Error('PPTX 文件格式无效。');
    const receipt = Buffer.from(JSON.stringify({...layout, images:sources,
      pptx_sha256:createHash('sha256').update(bytes).digest('hex')}, null, 2));
    const artifacts = publishArtifacts(writer, onReport, signal, [{extension:'pptx', bytes}, {extension:'json', bytes:receipt}]);
    return { pages: layout.slides.length, layout_checks: layout.checks, artifacts };
  });
}
