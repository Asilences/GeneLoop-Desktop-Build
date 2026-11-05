import { defineTool } from '@deepseek-ai/dsh-tools';
import { localSceneTools } from './local-scenes.mjs';
import { summarizeTable } from './local-data.mjs';
import { readPaperPage, checkCitationKeys } from './local-paper.mjs';
import { createLocalPresentation } from './local-ppt.mjs';
import { exportPptMaster, readPptMasterGuide, readPptMaterial, fillPptTemplate, createPptSourceReader } from './local-ppt-master.mjs';
import { probeLocalVideo, renderLocalVideo, renderHybridVideo, renderNativeRemotion } from './local-video.mjs';

const string = { type: 'string', required: true };
const jsonOutput = {
  schema: { type: 'json' },
  render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
};

export function registerLocalFileTools(scope, reader, writer, onReport, scene = 'files', signal, media, approveVideo, ppt, onVideoPhase, nativeContext) {
  const names = localSceneTools(scene);
  if (!names) throw Error('不支持该本机场景。');
  const tools = [
    defineTool({
      name: 'local_list',
      description: '列出授权工作区内的一级目录项。path 为相对目录，空字符串表示根目录。',
      parameters: { path: string },
      output: jsonOutput,
      async execute({ path }) { return reader.list(path); },
    }),
    defineTool({
      name: 'local_read',
      description: '读取授权工作区内相对路径所指的 UTF-8 文本，最多 256 KiB。',
      parameters: { path: string },
      output: { schema: { type: 'string' }, render: (_args, text) => [{ type: 'text', text }] },
      async execute({ path }) { return reader.readText(path); },
    }),
    defineTool({
      name: 'local_search',
      description: '在指定 UTF-8 文件中搜索区分大小写的字面文本，返回命中行号，每次最多 50 行。',
      parameters: { path: string, query: string },
      output: jsonOutput,
      async execute({ path, query }) {
        if (!query.length || query.length > 256 || /[\r\n]/.test(query)) throw Error('请输入 1 至 256 字符的单行搜索词。');
        const matches = [];
        let lineNumber = 0;
        for (const line of reader.readText(path).split(/\r\n|\n|\r/)) {
          lineNumber++;
          if (!line.includes(query)) continue;
          if (matches.length === 50) return { path, matches, truncated: true };
          matches.push(lineNumber);
        }
        return { path, matches, truncated: false };
      },
    }),
  ];
  tools.push(defineTool({
      name: 'local_save_report',
      description: '在本机工作区的「GeneLoop 输出」文件夹中创建一份 Markdown 文件，返回文件名。请在报告中附上来源相对路径。',
      parameters: { markdown: string },
      output: jsonOutput,
      async execute({ markdown }) {
        const report = writer.writeMarkdown(markdown);
        onReport?.(report);
        return report;
      },
  }));
  if (scene === 'data') tools.push(defineTool({
    name: 'local_data_summarize',
    description: '在本机精确计算 UTF-8 CSV/TSV 的数值列统计。返回行数、分组和、均值、极值、缺失数及源文件 SHA-256；不分组时传入空字符串。',
    parameters: { path: string, column: string, group_by: string },
    output: jsonOutput,
    async execute(input) { return summarizeTable(reader, input); },
  }));
  if (scene === 'paper' || scene === 'ppt') tools.push(
    defineTool({
      name: 'local_paper_read_page',
      description: '本机读取含文本层的 PDF 指定页或 UTF-8 文本材料第 1 页，返回文件 SHA-256、页码和原文。扫描页需要其他工具。',
      parameters: { path: string, page: { type: 'number', required: true } },
      output: jsonOutput,
      async execute(input) { return readPaperPage(reader, input); },
    }),
  );
  if (scene === 'paper') tools.push(defineTool({
      name: 'local_paper_check_citations',
      description: '核验 LaTeX 稿件引用键在 BibTeX 文献表中的匹配、缺失、重复情况，返回行号和两个来源的 SHA-256。',
      parameters: { manuscript: string, bibliography: string },
      output: jsonOutput,
      async execute(input) { return checkCitationKeys(reader, input); },
    }));
  if (scene === 'ppt') tools.push(defineTool({
    name: 'local_ppt_create',
    description: '用本机科研版式生成可编辑 PPTX。plan 是 JSON 对象字符串 {title,template?,slides:[{title,bullets,sources,notes?,layout?,image_path?,table?,chart?,process?,comparison?}]}。每页提供 sources，PNG 图使用工作区相对路径 image_path。只在确有演示文稿需求时调用。版式检查不是目视验收。',
    parameters: {plan:string}, output:jsonOutput,
    async execute({plan}) { return createLocalPresentation(plan, reader, writer, signal, onReport); },
  }));
  if (scene === 'ppt' && ppt) tools.push(defineTool({
    name: 'local_ppt_master_guide',
    description: '读取锁定版 ppt-master 的官方说明，section 为 skill（入口）、generate（生成工作流）或 spec（设计规格）。使用 ppt-master 导出前先核对所需指南。',
    parameters: {section:string},
    output: {schema:{type:'string'},render:(_args,text)=>[{type:'text',text}]},
    async execute({section}) { return readPptMasterGuide(ppt, section); },
  }), defineTool({
    name: 'local_ppt_master_export',
    description: '用锁定的 ppt-master 和本机 LibreOffice 验收并导出可编辑 PPTX 及 PDF。plan 是 JSON 对象字符串 {spec,pages:[{svg,notes}],sources?:[{path,sha256}]}。spec 是设计规格 Markdown。SVG 仅接受自包含的静态形状与文本。每页提供 Markdown 演讲备注。使用的材料应带读取时的摘要。',
    parameters: {plan:string}, output:jsonOutput,
    async execute({plan}) { return exportPptMaster(plan, writer, ppt, signal, onReport, reader); },
  }), defineTool({
    name: 'local_ppt_read_material',
    description: '读取本机授权目录内的 PDF/PPTX 页或 DOCX/文本/CSV/TSV 段。返回来源摘要，PPTX 还列出 {{FIELD}} 模板字段。page 从 1 起。',
    parameters: {path:string,page:{type:'number',required:true}}, output:jsonOutput,
    async execute({path,page}) { return readPptMaterial(path,page,reader,ppt,signal); },
  }), defineTool({
    name: 'local_ppt_fill_template',
    description: '在 PPTX 副本中填写原有 {{FIELD}} 单行文字字段，保留母版、主题、图表和未编辑部件。先读取模板页取得字段和 SHA-256。plan 是 JSON 字符串 {values:{字段名:文字},sources?:[{path,sha256}]}，交付原生 PPTX、PDF 和回执。',
    parameters: {path:string,sha256:string,plan:string}, output:jsonOutput,
    async execute({path,sha256,plan}) { return fillPptTemplate(path,sha256,plan,reader,writer,ppt,signal,onReport); },
  }));
  if (scene === 'ppt' && ppt) {
    const sources = createPptSourceReader(reader, ppt, signal);
    tools.push(defineTool({
      name: 'local_ppt_pin_source',
      description: '固定一份授权目录中的 PPT 源材料版本，返回当前会话可用的 source_id 和文件 SHA-256。path 是相对路径。',
      parameters: {path:string},
      output: jsonOutput,
      async execute({path}) { return sources.pin(path); },
    }), defineTool({
      name: 'local_ppt_read_source',
      description: '从已固定版本的 PPT 源材料中读取第 page 页或段。source_id 来自当前会话的固定来源工具，文件变化时拒绝读取。',
      parameters: {source_id:string,page:{type:'number'}},
      output: jsonOutput,
      async execute({source_id,page = 1}) { return sources.read(source_id,page); },
    }));
  }
  if (scene === 'video') tools.push(
    defineTool({
      name: 'local_video_probe', description: '在本机读取授权 MP4/MOV 的时长、尺寸、音轨和文件摘要。path 为相对路径。',
      parameters:{path:string}, output:jsonOutput,
      async execute({path}) { return probeLocalVideo(reader, media, path, signal); },
    }),
    defineTool({
      name: 'local_video_render',
      description: '在本机生成视频。简单裁剪拼接：plan 是 JSON 数组字符串 [{path,sha256,start,end}]，sha256 取自 local_video_probe，使用秒。复杂合成（需本机 Remotion）：plan 是 JSON 对象字符串 {source,assets}，source 是独立 React/Remotion TSX，registerRoot 注册 Main；assets 是工作区素材路径数组，按顺序用 staticFile("asset-1.小写扩展名") 引用。不上传素材，禁止外部 URL。最多8份素材、合计16MiB、90秒，Remotion 最多1080p/60fps。',
      parameters:{plan:string}, output:jsonOutput,
      async execute({plan}) {
        const value=JSON.parse(plan);
        if (Array.isArray(value)) return renderLocalVideo(reader,writer,media,plan,signal,onReport);
        if (!value || Object.keys(value).sort().join(',') !== 'assets,source' || !media.remotion || !nativeContext) {
          throw Error('本机 Remotion 未就绪，或视频计划格式无效。不会自动转到服务器。');
        }
        return renderNativeRemotion(nativeContext,reader,writer,media,value.source,JSON.stringify(value.assets),signal,onReport);
      },
    }),
  );
  let remoteRenderPending = false;
  if (scene === 'video' && approveVideo) tools.push(defineTool({
    name: 'hybrid_video_render',
    description: '用服务器的 Remotion 沙箱渲染复杂合成。source 为完整 TSX 入口，调用 registerRoot 并注册 Main。assets 是工作区相对文件路径的 JSON 数组字符串，按顺序使用 staticFile("asset-1.扩展名") 等引用，扩展名用小写。最多 8 个素材，合计 16 MiB。每次上传前须由用户确认。简单裁剪和拼接优先用本机工具。返回的文件保存到本机 GeneLoop 输出。',
    parameters: {source:string, assets:string}, output:jsonOutput,
    async execute({source, assets}) {
      if (remoteRenderPending) throw Error('已有服务器渲染正在等待确认或执行。');
      remoteRenderPending = true;
      try { return await renderHybridVideo(reader, writer, media, source, assets, signal, approveVideo, onReport, onVideoPhase); }
      finally { remoteRenderPending = false; }
    },
  }));
  const allowed = new Set(names);
  // Hide every global tool. Scoped registrations below are unaffected by this mask.
  scope.tools.restrict({ allow: [] });
  scope.tools.guard(call => allowed.has(call.name) ? undefined : '工具不在当前本机场景的权限内。');
  for (const tool of tools) scope.tools.register(tool);
}
