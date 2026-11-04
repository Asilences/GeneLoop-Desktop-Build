import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, realpathSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, relative, isAbsolute, sep } from 'node:path';

export type LocalWorkspace = { id: string; name: string; directory: string; output?: string; updatedAt: number };
const localPath = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z]:[\\/]/.test(value) && !value.includes('\0');
const samePath = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

export function authorizedDirectory(path: string): string {
  if (!localPath(path)) throw Error('请选择本机磁盘上的文件夹。');
  const resolved = realpathSync.native(path);
  if (!localPath(resolved) || !statSync(resolved).isDirectory()) throw Error('该本机文件夹不可用。');
  return resolved;
}

export function reopenDirectory(path: string): string {
  const resolved = authorizedDirectory(path);
  if (!samePath(resolved, path)) throw Error('文件夹已指向其他位置，请编辑工作区并重新选择。');
  return resolved;
}

export function checkReportDirectory(source: string, output: string): void {
  const contains = (parent: string, child: string) => {
    const rest = relative(parent.toLowerCase(), child.toLowerCase());
    return !isAbsolute(rest) && rest !== '..' && !rest.startsWith('..' + sep);
  };
  if (contains(source, output) || contains(output, source)) throw Error('请选择与源文件夹分离的报告目录。');
}

export class LocalWorkspaceStore {
  private entries: LocalWorkspace[];
  constructor(private file: string) {
    try {
      const data = JSON.parse(readFileSync(file, 'utf8'));
      if (data?.version !== 1 || !Array.isArray(data.items)) throw Error('Invalid workspace index');
      this.entries = data.items.filter((row: LocalWorkspace) => typeof row?.id === 'string' &&
        typeof row.name === 'string' && localPath(row.directory) &&
        (row.output === undefined || localPath(row.output)) && Number.isFinite(row.updatedAt));
    } catch { this.entries = []; }
  }
  list(): LocalWorkspace[] { return this.entries.map(row => ({ ...row })); }
  get(id: string): LocalWorkspace {
    const row = this.entries.find(item => item.id === id);
    if (!row) throw Error('找不到该本机工作区。');
    return { ...row };
  }
  open(directory: string): LocalWorkspace {
    return this.entries.find(row => samePath(row.directory, directory)) ??
      this.save({ directory, name: basename(directory) || directory });
  }
  save(value: { id?: string; name: string; directory: string; output?: string }): LocalWorkspace {
    const name = value.name.trim();
    if (!name || name.length > 80) throw Error('工作区名称需为 1–80 字。');
    const directory = authorizedDirectory(value.directory);
    const output = value.output ? authorizedDirectory(value.output) : undefined;
    if (output) checkReportDirectory(directory, output);
    if (this.entries.some(row => row.id !== value.id && samePath(row.directory, directory))) throw Error('这个文件夹已经是一个本机工作区。');
    const row = { id: value.id ?? randomUUID(), name, directory, output, updatedAt: Date.now() };
    this.write(value.id ? this.entries.map(old => old.id === row.id ? row : old) : [...this.entries, row]);
    return row;
  }
  remove(id: string): void { this.write(this.entries.filter(row => row.id !== id)); }
  private write(items: LocalWorkspace[]): void {
    mkdirSync(dirname(this.file), { recursive: true });
    const temporary = this.file + '.tmp';
    writeFileSync(temporary, JSON.stringify({ version: 1, items }, null, 2) + '\n', { mode: 0o600 });
    renameSync(temporary, this.file);
    this.entries = items;
  }
}
