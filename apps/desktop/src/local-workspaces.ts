import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, realpathSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname } from 'node:path';

export type WorkspaceBinding = { server: string; accountId: string; workspaceId: string };
export type LocalWorkspace = { id: string; name: string; directory?: string; binding?: WorkspaceBinding; updatedAt: number };
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

export class LocalWorkspaceStore {
  private entries: LocalWorkspace[];
  constructor(private file: string) {
    try {
      const data = JSON.parse(readFileSync(file, 'utf8'));
      if (data?.version !== 1 || !Array.isArray(data.items)) throw Error('Invalid workspace index');
      this.entries = data.items.filter((row: LocalWorkspace) => typeof row?.id === 'string' &&
        typeof row.name === 'string' && (row.directory === undefined || localPath(row.directory)) &&
        (row.binding === undefined || (typeof row.binding?.server === 'string' &&
          typeof row.binding.accountId === 'string' && typeof row.binding.workspaceId === 'string')) &&
        Number.isFinite(row.updatedAt)).map(({ id, name, directory, binding, updatedAt }: LocalWorkspace) =>
          ({ id, name, directory, binding, updatedAt }));
    } catch { this.entries = []; }
  }
  list(server: string, accountId: unknown): LocalWorkspace[] {
    return this.entries.filter(row => !row.binding || (row.binding.server === server && row.binding.accountId === accountId));
  }
  findBinding(binding: WorkspaceBinding): LocalWorkspace | undefined {
    return this.list(binding.server, binding.accountId).find(row => row.binding?.workspaceId === binding.workspaceId);
  }
  get(id: string): LocalWorkspace {
    const row = this.entries.find(item => item.id === id);
    if (!row) throw Error('找不到该本机工作区。');
    return { ...row };
  }
  open(directory: string): LocalWorkspace {
    return this.entries.find(row => !row.binding && row.directory && samePath(row.directory, directory)) ??
      this.save({ directory, name: basename(directory) || directory });
  }
  save(value: { id?: string; name: string; directory?: string; binding?: WorkspaceBinding }): LocalWorkspace {
    const name = value.name.trim();
    if (!name || name.length > 80) throw Error('工作区名称需为 1–80 字。');
    const directory = value.directory && reopenDirectory(value.directory);
    if (!value.binding && directory && this.entries.some(row => !row.binding && row.id !== value.id && row.directory && samePath(row.directory, directory))) {
      throw Error('这个文件夹已经是一个本机工作区。');
    }
    const row = { id: value.id ?? randomUUID(), name, directory, binding: value.binding, updatedAt: Date.now() };
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
