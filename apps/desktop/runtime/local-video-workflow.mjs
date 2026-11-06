import {defineTool} from '@deepseek-ai/dsh-tools';
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,writeFileSync,statSync} from 'node:fs';
import {join} from 'node:path';
import sharp from 'sharp';
import {inSceneScratch} from './local-artifacts.mjs';
import {runNativeProcess} from './native-process.mjs';
import {probeLocalVideo,renderNativeRemotion} from './local-video.mjs';
import {workflowToolName} from './native-workflow-catalog.mjs';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const string={type:'string',required:true};
const output={schema:{type:'json'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]};
const mediaPattern=/\.(mp4|mov|mp3|wav|png|jpg|jpeg)$/i;

export function nativeVideoTools(ctx,reader,writer,media,signal,onReport) {
  const assets=new Map();let source='',version=sha(Buffer.alloc(0)),lastRender;
  const pinned=id=>{const row=assets.get(id);if(!row)throw Error('未知素材，请先pin_asset。');
    if(sha(reader.readBytes(row.path,80*1024*1024))!==row.sha256)throw Error('素材已变化，请重新固定。');return row;};
  async function probe(row) {
    if(/\.(mp4|mov)$/i.test(row.path))return probeLocalVideo(reader,media,row.path,signal);
    const bytes=reader.readBytes(row.path,32*1024*1024);
    if(/\.(png|jpg|jpeg)$/i.test(row.path)) {
      const info=await sharp(bytes,{limitInputPixels:64*1024*1024}).metadata();
      return {...row,width:info.width,height:info.height,format:info.format,kind:'image'};
    }
    return inSceneScratch(async scratch=>{
      const extension=row.path.split('.').at(-1).toLowerCase(),path=join(scratch,'source.'+extension);writeFileSync(path,bytes,{flag:'wx'});
      const result=await runNativeProcess(ctx,[media.ffprobe,'-v','error','-protocol_whitelist','file,pipe','-f',extension,'-i',path,
        '-show_entries','format=duration:stream=codec_type,sample_rate,channels','-of','json'],scratch,signal,{timeoutMs:100000});
      const info=JSON.parse(result.stdout);if(!info.streams?.some(s=>s.codec_type==='audio'))throw Error('该素材没有可读取的音轨。');
      pinned(row.asset_id);return {...row,kind:'audio',...info};
    });
  }
  const write=text=>{
    if(typeof text!=='string'||!text.trim()||Buffer.byteLength(text)>128*1024)throw Error('Remotion源码需要1至128KiB的TSX文字。');
    source=text;version=sha(Buffer.from(text));return {source_version:version,bytes:Buffer.byteLength(text)};
  };
  async function render(expected) {
    if(expected!==version||!source)throw Error('源码版本已变化，请先read_source/write_source。');
    const paths=[...assets.keys()].map(id=>pinned(id).path);
    lastRender=await renderNativeRemotion(ctx,reader,writer,media,source,JSON.stringify(paths),signal,onReport);
    return lastRender;
  }
  async function analyze(command) {
    const plan=JSON.parse(command);
    if(!plan||Object.keys(plan).some(k=>!['operation','asset_id','start','duration'].includes(k)))throw Error('本机媒体命令只接受明确的JSON操作。');
    const row=pinned(plan.asset_id);
    if(plan.operation==='probe')return probe(row);
    if(plan.operation!=='audio_stats')throw Error('使用operation=probe或audio_stats；不执行Linux shell。');
    const start=plan.start??0,duration=plan.duration??30;
    if(!Number.isFinite(start)||start<0||!Number.isFinite(duration)||duration<=0||duration>90||!/\.(mp4|mov|mp3|wav)$/i.test(row.path))throw Error('音轨分析需要媒体素材、非负起点和不超过90秒的时段。');
    return inSceneScratch(async scratch=>{
      const extension=row.path.split('.').at(-1).toLowerCase();
      const path=join(scratch,'source.'+extension),pcm=join(scratch,'samples.pcm');
      writeFileSync(path,reader.readBytes(row.path,80*1024*1024),{flag:'wx'});
      const demux=['mp4','mov'].includes(extension)?['-f','mov','-enable_drefs','0','-use_absolute_path','0']:['-f',extension];
      await runNativeProcess(ctx,[media.ffmpeg,'-v','error','-nostdin','-protocol_whitelist','file,pipe',...demux,'-i',path,
        '-ss',String(start),'-t',String(duration),'-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','-f','s16le','-n',pcm],scratch,signal,{timeoutMs:100000});
      if(statSync(pcm).size>3*1024*1024)throw Error('音轨解码超出本次分析时段。');
      const bytes=readFileSync(pcm),n=Math.floor(bytes.length/2);if(!n)throw Error('该时段没有音频样本。');
      let squares=0,peak=0,mean=0,silent=0;
      for(let i=0;i<n;i++){const x=bytes.readInt16LE(i*2)/32768;squares+=x*x;mean+=x;peak=Math.max(peak,Math.abs(x));if(Math.abs(x)<0.001)silent++;}
      pinned(row.asset_id);const rms=Math.sqrt(squares/n);
      return {asset_id:row.asset_id,sha256:row.sha256,start,requested_seconds:duration,decoded_seconds:n/16000,
        sample_rate:16000,channels:1,samples:n,rms,peak,mean:mean/n,rms_dbfs:rms?20*Math.log10(rms):null,
        peak_dbfs:peak?20*Math.log10(peak):null,silent_sample_fraction:silent/n,analysis:'actual_pcm_not_perceptual_loudness'};
    });
  }
  const tool=(name,description,parameters,execute)=>defineTool({name:workflowToolName('video',name),description,parameters,output,execute});
  return [
    tool('list_assets','列出本机授权目录中的媒体候选和已固定素材；path为空表示根目录。',{path:string},async({path})=>({directory:reader.list(path),pinned:[...assets.values()]})),
    tool('pin_asset','固定本机媒体相对路径的实际版本。已知sha256时一并传入以核对；返回asset_id和Remotion staticFile名称，按固定顺序使用。',{path:string,sha256:{type:'string'}},async({path,sha256})=>{
      if(!mediaPattern.test(path)||assets.size>=8)throw Error('最多固定8份MP4/MOV/MP3/WAV/PNG/JPEG素材。');
      const bytes=reader.readBytes(path,80*1024*1024);if(sha256&&sha(bytes)!==sha256)throw Error('素材已变化。');
      const asset_id=randomUUID(),name='asset-'+(assets.size+1)+'.'+path.split('.').at(-1).toLowerCase();
      const row={asset_id,path,sha256:sha(bytes),name,bytes:bytes.length};assets.set(asset_id,row);return row;
    }),
    tool('probe_media','读取已固定素材的实际尺寸、时长或音轨，不上传素材。',{asset_id:string},async({asset_id})=>probe(pinned(asset_id))),
    tool('probe_asset','核对已固定素材版本并读取媒体信息。',{asset_id:string},async({asset_id})=>probe(pinned(asset_id))),
    tool('read_source','读取本轮当前TSX源码和SHA-256。',{},async()=>({text:source,source_version:version})),
    tool('write_source','保存本轮模型撰写的Remotion TSX，不执行、不覆盖工作区原件。',{text:string},async({text})=>write(text)),
    tool('render_composition','按source_version在本机实际渲染Main并完整解码验收，交付MP4、源码和回执。不转云端。',{source_version:string},async({source_version})=>render(source_version)),
    tool('render_source','保存明确TSX并按同一原生渲染器实际交付；素材仅限此前固定项。',{text:string},async({text})=>render(write(text).source_version)),
    tool('inspect_render','读取本轮实际渲染回执，完整解码不等于画面已目视审阅。',{},async()=>lastRender??{rendered:false}),
    tool('write_notes','将实际剪辑说明保存为新Markdown产物。',{text:string},async({text})=>{const file=writer.writeMarkdown(text);onReport?.(file);return file;}),
    tool('run_command','跨平台媒体分析：command为JSON对象字符串 {operation:"probe"|"audio_stats",asset_id,start?,duration?}。audio_stats解码真实PCM并计算RMS/峰值/静音比例，单次最多90秒。保留媒体分析能力，不接受shell或任意Node命令。',{command:string},async({command})=>analyze(command)),
  ];
}
