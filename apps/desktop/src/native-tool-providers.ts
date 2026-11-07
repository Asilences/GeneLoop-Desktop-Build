import { existsSync, lstatSync, readFileSync, realpathSync } from 'node:fs';
import { isAbsolute } from 'node:path';

// Only the desktop host reads this private configuration. The model cannot
// supply provider registrations or obtain environment/credential values.
export function loadNativeToolProviders(path: string): object | undefined {
  if (!existsSync(path)) return;
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 256 * 1024 ||
      realpathSync(path).toLowerCase() !== path.toLowerCase()) throw Error('本机工具配置文件无效。');
  const config = JSON.parse(readFileSync(path, 'utf8'));
  if (config.format !== 'sss-general-tools-v1' || !Array.isArray(config.providers)) throw Error('本机工具配置版本无效。');
  const credentials: Record<string, string> = {};
  const reference = (value: unknown) => {
    if (typeof value === 'string') return value.replaceAll('${NODE}', process.execPath);
    if (!value || typeof value !== 'object' || Object.keys(value).join(',') !== 'from_env') throw Error('工具配置值无效。');
    const name = (value as { from_env: unknown }).from_env;
    if (typeof name !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) throw Error('工具凭证引用无效。');
    if (process.env[name] !== undefined) credentials[name] = process.env[name]!;
    return value;
  };
  const providers = config.providers.map((raw: Record<string, any>) => {
    const platform = raw.platforms?.[process.platform + '-' + process.arch] ?? raw.platforms?.[process.platform];
    const row = { ...raw, ...platform }; delete row.platforms;
    if (row.transport === 'stdio') {
      row.command = reference(row.command);
      if (typeof row.command !== 'string' || !(isAbsolute(row.command) || row.command === '${PYTHON}'))
        throw Error('本机 MCP 命令需要绝对路径或 ${PYTHON}；请配置当前系统的命令。');
      row.args = (row.args ?? []).map(reference); row.cwd = reference(row.cwd ?? '${SESSION_WORKSPACE}');
      row.env = Object.fromEntries(Object.entries(row.env ?? {}).map(([k,v]) => [k,reference(v)]));
    } else if (row.transport === 'streamable-http') {
      row.url = reference(row.url);
      row.headers = Object.fromEntries(Object.entries(row.headers ?? {}).map(([k,v]) => [k,reference(v)]));
    } else throw Error('本机工具仅支持 stdio 或 streamable-http。');
    return row;
  });
  return { format: config.format, providers, credentials };
}
