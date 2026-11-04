import { defineTool } from '@deepseek-ai/dsh-tools';
import { localSceneTools } from './local-scenes.mjs';
import { summarizeTable } from './local-data.mjs';
import { readPaperPage, checkCitationKeys } from './local-paper.mjs';

const string = { type: 'string', required: true };
const jsonOutput = {
  schema: { type: 'json' },
  render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
};

export function registerLocalFileTools(scope, reader, writer, onReport, scene = 'files') {
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
  if (scene === 'paper') tools.push(
    defineTool({
      name: 'local_paper_read_page',
      description: '本机读取含文本层的 PDF 指定页或 UTF-8 文本材料第 1 页，返回文件 SHA-256、页码和原文。扫描页需要其他工具。',
      parameters: { path: string, page: { type: 'number', required: true } },
      output: jsonOutput,
      async execute(input) { return readPaperPage(reader, input); },
    }),
    defineTool({
      name: 'local_paper_check_citations',
      description: '核验 LaTeX 稿件引用键在 BibTeX 文献表中的匹配、缺失、重复情况，返回行号和两个来源的 SHA-256。',
      parameters: { manuscript: string, bibliography: string },
      output: jsonOutput,
      async execute(input) { return checkCitationKeys(reader, input); },
    }),
  );
  const allowed = new Set(names);
  scope.tools.guard(call => allowed.has(call.name) ? undefined : '工具不在本机文件管理权限内。');
  for (const tool of tools) scope.tools.register(tool);
}
