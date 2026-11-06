import koffi from 'koffi';
import { randomUUID } from 'node:crypto';
import { closeSync, constants, fstatSync, fsyncSync, openSync, readSync, realpathSync, writeFileSync } from 'node:fs';
import { isAbsolute } from 'node:path';

if (!['darwin', 'linux'].includes(process.platform)) throw Error('此平台没有本机文件访问实现。');
const libc = koffi.load(process.platform === 'darwin' ? '/usr/lib/libSystem.B.dylib' : 'libc.so.6');
// mode is variadic in libc. Apple ARM64 passes variadic arguments on the
// stack; declaring it as a fixed fourth argument can create unreadable files.
const openat = libc.func('int openat(int directory, const char *name, int flags, ...)');
const mkdirat = libc.func('int mkdirat(int directory, const char *name, unsigned int mode)');
const unlinkat = libc.func('int unlinkat(int directory, const char *name, int flags)');
const dup = libc.func('int dup(int file)');
// Intel macOS also exports the legacy 32-bit-inode ABI as plain readdir.
// Match the modern dirent layout used below instead of decoding that ABI.
const directorySymbol = name => process.platform === 'darwin' && process.arch === 'x64' ? name+'$INODE64' : name;
const fdopendir = libc.func(directorySymbol('fdopendir'), 'void *', ['int']);
const readdir = libc.func(directorySymbol('readdir'), 'void *', ['void *']);
const closedir = libc.func('int closedir(void *directory)');
const rewinddir = libc.func(directorySymbol('rewinddir'), 'void', ['void *']);
const directoryFlags = constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW;
const maxBytes = 256 * 1024;

function parts(path) {
  if (typeof path !== 'string' || path.length > 2048 || isAbsolute(path) || path.includes('\0')) {
    throw Error('请输入工作区内的相对路径。');
  }
  const names = path.split('/');
  if (names.some(name => !name || name === '.' || name === '..')) throw Error('相对路径不能越过工作区。');
  return names;
}

function child(parent, name, flags, mode = 0) {
  const fd = openat(parent, name, flags | constants.O_NOFOLLOW, 'unsigned int', mode);
  if (fd < 0) throw Error('无法打开授权目录内的文件，或该路径使用了链接。');
  return fd;
}

function root(directory) {
  if (!isAbsolute(directory) || realpathSync(directory) !== directory) throw Error('工作区目录已指向其他位置。');
  const fd = openSync(directory, directoryFlags);
  if (!fstatSync(fd).isDirectory()) { closeSync(fd); throw Error('工作区必须是目录。'); }
  return fd;
}

function entries(fd) {
  const copy = dup(fd);
  if (copy < 0) throw Error('无法读取目录。');
  const directory = fdopendir(copy);
  if (!directory) { closeSync(copy); throw Error('无法读取目录。'); }
  rewinddir(directory);
  const result = [];
  try {
    for (let pointer; (pointer = readdir(directory));) {
      const header = Buffer.from(koffi.decode(pointer, 'uint8_t', 24));
      const recordLength = header.readUInt16LE(16);
      const nameOffset = process.platform === 'darwin' ? 21 : 19;
      if (recordLength <= nameOffset || recordLength > 4096) throw Error('目录记录格式无效。');
      const record = Buffer.from(koffi.decode(pointer, 'uint8_t', recordLength));
      const end = record.indexOf(0, nameOffset);
      if (end < 0) throw Error('目录文件名格式无效。');
      const name = new TextDecoder('utf-8', {fatal:true}).decode(record.subarray(nameOffset, end));
      if (name === '.' || name === '..') continue;
      let item;
      try { item = child(fd, name, constants.O_RDONLY | constants.O_NONBLOCK); }
      catch { continue; }
      try {
        const info = fstatSync(item);
        if (!info.isDirectory() && !info.isFile()) continue;
        if (result.length === 200) return {entries:result, truncated:true};
        result.push({name, kind:info.isDirectory() ? 'directory' : 'file'});
      } finally { closeSync(item); }
    }
    return {entries:result, truncated:false};
  } finally { closedir(directory); }
}

export function openWorkspaceReader(directory) {
  const handle = root(directory);
  let closed = false;
  function withEntry(path, isDirectory, read) {
    if (closed) throw Error('工作区授权已关闭。');
    if (path === '' && isDirectory) return read(handle);
    const handles = [];
    try {
      const names = parts(path);
      let parent = handle;
      for (const [index, name] of names.entries()) {
        const flags = index < names.length - 1 || isDirectory ? directoryFlags : constants.O_RDONLY | constants.O_NONBLOCK;
        parent = child(parent, name, flags);
        handles.push(parent);
      }
      return read(parent);
    } finally { for (const fd of handles.reverse()) closeSync(fd); }
  }
  function readBytes(path, limit = maxBytes) {
    return withEntry(path, false, fd => {
      const before = fstatSync(fd);
      if (!before.isFile() || before.nlink !== 1 || before.size > limit) throw Error('文件超过读取限制，或不是单链接普通文件。');
      const bytes = Buffer.alloc(before.size + 1);
      let length = 0, count;
      while (length < bytes.length && (count = readSync(fd, bytes, length, bytes.length - length, null))) length += count;
      const after = fstatSync(fd);
      if (length !== before.size || after.size !== before.size || after.mtimeMs !== before.mtimeMs || after.nlink !== 1) {
        throw Error('文件在读取期间发生变化。');
      }
      return bytes.subarray(0, length);
    });
  }
  return {
    list(path = '') { return withEntry(path, true, entries); },
    readBytes,
    readText(path) { return new TextDecoder('utf-8', {fatal:true}).decode(readBytes(path)); },
    close() { if (!closed) { closed = true; closeSync(handle); } },
  };
}

export function openReportWriter(directory) {
  const source = root(directory);
  let output, closed = false;
  function ensureOutput() {
    if (output !== undefined) return output;
    mkdirat(source, 'GeneLoop 输出', 0o700);
    output = child(source, 'GeneLoop 输出', directoryFlags);
    return output;
  }
  function writeArtifacts(items) {
    if (closed) throw Error('输出目录授权已关闭。');
    if (!Array.isArray(items) || !items.length || items.length > 4 || items.some(({extension, bytes}) =>
      !['md','pptx','pdf','mp4','json','tsx','csv','zip'].includes(extension) || !Buffer.isBuffer(bytes) || !bytes.length || bytes.length > 80 * 1024 * 1024)) {
      throw Error('交付物的类型、数量或大小超出本机限制。');
    }
    const fd = ensureOutput(), pending = [], id = randomUUID();
    try {
      for (const {extension, bytes} of items) {
        const name = 'GeneLoop-' + id + '.' + extension;
        const file = child(fd, name, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600);
        pending.push(name);
        try { writeFileSync(file, bytes); fsyncSync(file); }
        finally { closeSync(file); }
      }
      return pending.map((name, i) => ({name, bytes:items[i].bytes.length}));
    } catch (error) {
      let cleanupFailed = false;
      for (const name of pending) if (unlinkat(fd, name, 0) !== 0) cleanupFailed = true;
      if (cleanupFailed) throw Error('产物写入失败，部分文件清理失败。', {cause:error});
      throw error;
    }
  }
  return {
    writeArtifacts,
    writeMarkdown(text) {
      const bytes = Buffer.from(text, 'utf8');
      if (!bytes.length || bytes.length > maxBytes) throw Error('报告必须为 1 至 256 KiB。');
      return writeArtifacts([{extension:'md', bytes}])[0];
    },
    close() { if (!closed) { closed = true; if (output !== undefined) closeSync(output); closeSync(source); } },
  };
}
