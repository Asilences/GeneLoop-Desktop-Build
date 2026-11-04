import { defineTool } from '@deepseek-ai/dsh-tools';

const string = { type: 'string', required: true };
const jsonOutput = {
  schema: { type: 'json' },
  render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
};

export function registerLocalFileTools(scope, reader, writer, onReport) {
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
  const allowed = new Set(tools.map(tool => tool.name));
  scope.tools.guard(call => allowed.has(call.name) ? undefined : '工具不在本机文件管理权限内。');
  for (const tool of tools) scope.tools.register(tool);
}
