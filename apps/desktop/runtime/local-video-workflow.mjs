// Web Remotion contracts, backed by native FFmpeg/Chromium and official DSH shell.
import {defineTool} from '@deepseek-ai/dsh-tools';
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,existsSync,lstatSync} from 'node:fs';
import {join,dirname} from 'node:path';
import sharp from 'sharp';
import {inSceneScratch} from './local-artifacts.mjs';
import {runNativeProcess} from './native-process.mjs';
import {renderNativeRemotion} from './local-video.mjs';
import {workflowToolName} from './native-workflow-catalog.mjs';
import {workflowOutput} from './local-workflow-output.mjs';
import {nativeVideoToolsV3} from './local-video-legacy.mjs';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const string={type:'string',required:true};
const output={schema:{type:'json'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]};
const mediaPattern=/\.(mp4|mov|webm|mkv|mp3|wav|m4a|aac|ogg|png|jpg|jpeg|webp|gif|svg)$/i;
export function nativeVideoTools(ctx,reader,writer,media,signal,onReport,common) {
  if(!common)return nativeVideoToolsV3(ctx,reader,writer,media,signal,onReport);
  const nonce=randomUUID(),assets=new Map();let source='',version=sha(Buffer.alloc(0)),lastRender,lastVideo;
  const taskPath=path=>common?.resolvePath(path);
  function save(path,bytes){const full=taskPath(path);if(!full)return;mkdirSync(dirname(full),{recursive:true});writeFileSync(full,bytes);}
  function current(){
    const full=taskPath('src/index.tsx');
    if(full&&existsSync(full)){if(!lstatSync(full).isFile()||lstatSync(full).nlink!==1)throw Error('源码文件类型已变化');source=readFileSync(full,'utf8');}
    version=sha(Buffer.from(source));return version;
  }
  const pin=name=>{
    if(typeof name!=='string'||!mediaPattern.test(name))throw Error('请选择本轮实际媒体文件名');
    const bytes=reader.readBytes(name,80*1024*1024),digest=sha(bytes);
    const source_id='source-'+sha(Buffer.from(nonce+'\0'+name+'\0'+digest)).slice(0,32);
    if(!assets.has(source_id)&&assets.size>=8)throw Error('本机一轮最多固定8份素材');
    const row={source_id,source_version:digest,name,path:name,bytes:bytes.length};assets.set(source_id,row);
    save('public/'+name,bytes);return row;
  };
  const pinned=id=>{const row=assets.get(id);if(!row)throw Error('未知source_id，请先pin_asset');
    if(sha(reader.readBytes(row.path,80*1024*1024))!==row.source_version)throw Error('素材已变化，请重新固定');return row;};
  async function probe(row){
    const bytes=reader.readBytes(row.path,80*1024*1024);
    if(/\.(png|jpg|jpeg|webp|gif|svg)$/i.test(row.path)){
      const info=await sharp(bytes,{limitInputPixels:64*1024*1024}).metadata();
      return {...row,streams:[{codec_type:'video',codec_name:info.format,width:info.width,height:info.height}],kind:'image'};
    }
    return inSceneScratch(async scratch=>{
      const ext=row.path.split('.').at(-1).toLowerCase(),file=join(scratch,'source.'+ext);writeFileSync(file,bytes,{flag:'wx'});
      const format=['mp4','mov','m4a'].includes(ext)?'mov':['webm','mkv'].includes(ext)?'matroska':ext;
      const result=await runNativeProcess(ctx,[media.ffprobe,'-v','error','-protocol_whitelist','file,pipe','-f',format,
        ...(format==='mov'?['-enable_drefs','0','-use_absolute_path','0']:[]),'-i',file,'-show_streams','-show_format','-of','json'],scratch,signal,{timeoutMs:100000});
      const info=JSON.parse(result.stdout);pinned(row.source_id);
      return {...row,duration_seconds:Number(info.format?.duration),streams:info.streams};
    });
  }
  const write=text=>{if(typeof text!=='string'||!text.trim()||Buffer.byteLength(text)>100000)throw Error('TSX需要1至100000个UTF8字节');
    source=text;save('src/index.tsx',text);return {source_version:current(),digest_scope:'src/index.tsx'};};
  async function render(expected){
    if(expected!==current()||!source)throw Error('需要当前源码版本');
    const rows=[...assets.keys()].map(pinned);
    lastRender=await renderNativeRemotion(ctx,reader,writer,media,source,JSON.stringify(rows.map(r=>r.path)),signal,onReport,
      {assetBytes:128*1024*1024,assetNames:rows.map(r=>r.name),onRenderedVideo:bytes=>{lastVideo=bytes;}});
    save('out/video.mp4',lastVideo);return {...lastRender,source_version:version};
  }
  async function inspect(seconds){
    if(!lastRender||lastRender.source_sha256!==current()||!lastVideo)throw Error('请先渲染当前源码');
    const info=lastRender.output,fpsParts=info.fps.split('/').map(Number),fps=fpsParts[0]/(fpsParts[1]||1);
    if(!Array.isArray(seconds)||!seconds.length||seconds.length>8||seconds.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<0||x>=info.duration))throw Error('请选择实际时长内1至8个抽帧时间');
    const selected=seconds.map(value=>({requested_seconds:value,frame_index:Math.floor(value*fps),frame_seconds:Math.floor(value*fps)/fps}));
    const metadata={...lastRender,source_version:version,selected_output_seconds:seconds,selected_output_frames:selected,preview_width:info.width,preview_height:info.height,quality:'model_must_review_real_pixels; not_independently_passed'};
    return inSceneScratch(async scratch=>{
      const video=join(scratch,'video.mp4');writeFileSync(video,lastVideo);const content=[];
      for(const [i,frame]of selected.entries()){
        const path=join(scratch,'frame-'+i+'.rgb');
        await runNativeProcess(ctx,[media.ffmpeg,'-v','error','-nostdin','-protocol_whitelist','file,pipe','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',video,
          '-vf','select=eq(n\\,'+frame.frame_index+')','-vsync','0','-frames:v','1','-c:v','rawvideo','-pix_fmt','rgb24','-f','rawvideo','-n',path],scratch,signal,{timeoutMs:100000});
        const pixels=readFileSync(path);if(pixels.length!==info.width*info.height*3)throw Error('抽帧像素尺寸不符');
        const jpeg=await sharp(pixels,{raw:{width:info.width,height:info.height,channels:3}}).jpeg({quality:90}).toBuffer();
        content.push({type:'image',mimeType:'image/jpeg',data:jpeg.toString('base64')});
      }
      return {result:metadata,content,execution:process.platform+'-local'};
    });
  }
  const tool=(name,description,parameters,execute)=>defineTool({name:workflowToolName('video',name),description,parameters,output,execute});
  const imageOutput=workflowOutput(ctx,({seconds})=>inspect(seconds));
  return [
    tool('list_assets','列出授权目录中的媒体文件名、字节和SHA256；递归忽略链接和GeneLoop输出目录。',{},async()=>{
      const found=[];const walk=(path='',depth=0)=>{if(depth>12)throw Error('目录层级过深，请选择具体文件夹');
        for(const item of reader.list(path)){const name=(path?path+'/':'')+item.name;if(item.kind==='directory')walk(name,depth+1);else if(item.kind==='file'&&mediaPattern.test(name)){
          if(found.length>=512)throw Error('素材太多，请选择具体文件夹');const bytes=reader.readBytes(name,80*1024*1024);found.push({name,bytes:bytes.length,sha256:sha(bytes)});
        }}
      };walk();return {assets:found};}),
    tool('pin_asset','按实际媒体文件名固定source_id/source_version；Remotion使用staticFile(name)。',{name:string},async({name})=>pin(name)),
    tool('probe_media','按已固定source_id读取真实媒体流信息。',{source_id:string},async({source_id})=>probe(pinned(source_id))),
    tool('probe_asset','按实际文件名固定并读取真实媒体信息。',{name:string},async({name})=>probe(pin(name))),
    tool('read_source','读取src/index.tsx和当前SHA256。',{},async()=>({text:(current(),source),source_version:version,digest_scope:'src/index.tsx'})),
    tool('write_source','保存TSX源码并返回实际版本。',{text:string},async({text})=>write(text)),
    tool('render_composition','在本机渲染Main，解码实际视频并交付MP4/TSX/回执。',{source_version:string},async({source_version})=>render(source_version)),
    tool('render_source','保存模型撰写的TSX并实际渲染。',{text:string},async({text})=>render(write(text).source_version)),
    defineTool({name:workflowToolName('video','inspect_render'),description:'返回渲染后视频指定时间的原尺寸真实像素和帧号。模型不支持图像时明确说明未目视核验。',
      parameters:{seconds:{type:'array',required:true,items:{type:'number'}}},...imageOutput,output:{...imageOutput.output,schema:{type:'json'}}}),
    tool('write_notes','将剪辑说明保存到新的Markdown产物。',{text:string},async({text})=>{const file=writer.writeMarkdown(text);onReport?.(file);return file;}),
    tool('run_command','在本轮视频工程执行原生命令。Windows使用PowerShell，Mac使用Bash；FFmpeg/FFprobe/Node/Python已提供。没有Linux容器或自动云端回退。',{command:string,timeout_seconds:{type:'integer'}},async({command,timeout_seconds=180})=>{
      if(!common)throw Error('媒体命令需要本机工具协议v4；请更新网关');return common.command(command,timeout_seconds);
    }),
  ];
}
