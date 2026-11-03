import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { DEFAULT_SERVER, serverOrigin, windowSize } from './policy.ts';

export type Settings = { version: 1; server: string; window: ReturnType<typeof windowSize> };

export function loadSettings(file: string, override?: string, allowLoopback = false): Settings {
  let value: Partial<Settings> = {};
  try {
    const parsed = JSON.parse(readFileSync(file, 'utf8'));
    if (parsed?.version === 1) value = parsed;
  } catch { /* 保留损坏文件；使用默认值继续启动，不清理用户数据。 */ }
  let server = DEFAULT_SERVER;
  try { server = serverOrigin(value.server, allowLoopback); } catch { /* 旧的无效地址不带入导航。 */ }
  if (override !== undefined) server = serverOrigin(override, allowLoopback);
  return { version: 1, server, window: windowSize(value.window) };
}

export function saveSettings(file: string, settings: Settings): void {
  mkdirSync(dirname(file), { recursive: true });
  const temporary = file + '.tmp';
  writeFileSync(temporary, JSON.stringify(settings, null, 2) + '\n', { mode: 0o600 });
  renameSync(temporary, file);
}
