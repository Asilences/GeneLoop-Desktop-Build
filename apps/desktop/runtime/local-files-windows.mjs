import koffi from 'koffi';
import { randomUUID } from 'node:crypto';
import { win32 } from 'node:path';

const READ_ATTRIBUTES = 0x80;
const LIST_DIRECTORY = 1;
const WRITE_REPORT = 0x40010000; // GENERIC_WRITE | DELETE for partial-write cleanup.
const CREATE_NEW = 1;
const GENERIC_READ = 0x80000000;
const SHARE_READ_WRITE = 3; // Deliberately omit FILE_SHARE_DELETE.
const OPEN_EXISTING = 3;
const OPEN_REPARSE_POINT = 0x00200000;
const BACKUP_SEMANTICS = 0x02000000;
const DIRECTORY = 0x10;
const REPARSE_POINT = 0x400;
const NO_MORE_FILES = 18;
const ALREADY_EXISTS = 183;
const FILE_FULL_DIRECTORY_INFO = 14;
const FILE_FULL_DIRECTORY_RESTART_INFO = 15;
const FILE_DISPOSITION_INFO = 4;
const MAX_ENTRIES = 200;
const MAX_BYTES = 256 * 1024;
const MAX_PATH_UNITS = 32768;

const kernel = koffi.load('kernel32.dll');
const createFile = kernel.func('intptr_t __stdcall CreateFileW(const char16_t *path, uint32_t access, uint32_t share, void *security, uint32_t disposition, uint32_t flags, void *templateFile)');
const createDirectory = kernel.func('int __stdcall CreateDirectoryW(const char16_t *path, void *security)');
const getInfo = kernel.func('int __stdcall GetFileInformationByHandle(intptr_t file, void *information)');
const getPath = kernel.func('uint32_t __stdcall GetFinalPathNameByHandleW(intptr_t file, void *path, uint32_t length, uint32_t flags)');
const readFile = kernel.func('int __stdcall ReadFile(intptr_t file, void *data, uint32_t length, _Out_ uint32_t *read, void *overlapped)');
const getDirectoryInfo = kernel.func('int __stdcall GetFileInformationByHandleEx(intptr_t file, int infoClass, void *info, uint32_t size)');
const getLastError = kernel.func('uint32_t __stdcall GetLastError()');
const writeFile = kernel.func('int __stdcall WriteFile(intptr_t file, void *data, uint32_t length, _Out_ uint32_t *written, void *overlapped)');
const flushFile = kernel.func('int __stdcall FlushFileBuffers(intptr_t file)');
const setInfo = kernel.func('int __stdcall SetFileInformationByHandle(intptr_t file, int infoClass, void *info, uint32_t size)');
const closeHandle = kernel.func('int __stdcall CloseHandle(intptr_t file)');

function open(path, access, disposition = OPEN_EXISTING, share = SHARE_READ_WRITE) {
  const handle = createFile(path, access, share, null, disposition, BACKUP_SEMANTICS | OPEN_REPARSE_POINT, null);
  if (handle === -1 || handle === -1n) throw Error('无法打开授权目录内的文件或目录。');
  return handle;
}

function info(handle) {
  // BY_HANDLE_FILE_INFORMATION is thirteen DWORDs on both Win32 and Win64.
  const bytes = Buffer.alloc(52);
  if (!getInfo(handle, bytes)) throw Error('无法验证文件句柄。');
  const attributes = bytes.readUInt32LE(0);
  if (attributes & REPARSE_POINT) throw Error('授权目录中禁止使用重解析点。');
  return {
    directory: Boolean(attributes & DIRECTORY),
    links: bytes.readUInt32LE(40),
    size: bytes.readUInt32LE(32) > 0 ? Infinity : bytes.readUInt32LE(36),
  };
}

function finalPath(handle) {
  const bytes = Buffer.alloc(MAX_PATH_UNITS * 2);
  const length = getPath(handle, bytes, MAX_PATH_UNITS, 0);
  if (!length || length >= MAX_PATH_UNITS) throw Error('无法确定目录句柄的实际路径。');
  return bytes.toString('utf16le', 0, length * 2);
}

function childPrefix(path) {
  return path.endsWith('\\') ? path : path + '\\';
}

function assertChild(handle, path) {
  const actual = finalPath(handle);
  if (!actual.toLowerCase().startsWith(childPrefix(path).toLowerCase())) {
    throw Error('实际文件路径不在已验证的目录内。');
  }
  return actual;
}

function enumerate(handle) {
  const bytes = Buffer.alloc(64 * 1024);
  const entries = [];
  let infoClass = FILE_FULL_DIRECTORY_RESTART_INFO;
  while (getDirectoryInfo(handle, infoClass, bytes, bytes.length)) {
    infoClass = FILE_FULL_DIRECTORY_INFO;
    for (let offset = 0; ;) {
      // FILE_FULL_DIR_INFO stores FileNameLength at byte 60 and UTF-16 FileName at byte 68.
      const next = bytes.readUInt32LE(offset);
      const length = bytes.readUInt32LE(offset + 60);
      const end = offset + 68 + length;
      if (length % 2 || end > bytes.length || (next && (next < 68 + length || offset + next + 68 > bytes.length))) {
        throw Error('目录记录格式无效。');
      }
      const name = bytes.toString('utf16le', offset + 68, end);
      const attributes = bytes.readUInt32LE(offset + 56);
      if (name !== '.' && name !== '..' && !(attributes & REPARSE_POINT)) {
        if (entries.length === MAX_ENTRIES) return { entries, truncated: true };
        entries.push({ name, kind: attributes & DIRECTORY ? 'directory' : 'file' });
      }
      if (!next) break;
      offset += next;
    }
  }
  if (getLastError() !== NO_MORE_FILES) throw Error('无法枚举授权目录。');
  return { entries, truncated: false };
}

function relativeParts(path) {
  if (typeof path !== 'string' || path.length > 2048 || win32.isAbsolute(path)) throw Error('请输入工作区内的相对路径。');
  const parts = path.split(/[\\/]/);
  for (const part of parts) {
    if (!part || /[<>:"|?*\x00-\x1f]|[ .]$/.test(part) ||
        /^(?:con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])(?:\.|$)/i.test(part)) {
      throw Error('路径包含无效或保留的 Windows 文件名。');
    }
  }
  return parts;
}

// 在授权时打开根目录，所有子目录都用句柄固定，直到操作结束。
function openRoot(directory, access) {
  if (!/^[A-Za-z]:[\\/]/.test(directory)) throw Error('首版本机工作区仅支持本地盘符路径。');
  const handle = open(win32.toNamespacedPath(directory), access);
  try {
    if (!info(handle).directory) throw Error('工作区必须是目录。');
    const path = finalPath(handle);
    if (childPrefix(path).toLowerCase() !== childPrefix(win32.toNamespacedPath(directory)).toLowerCase()) {
      throw Error('工作区已指向其他位置。');
    }
    return { handle, path };
  } catch (error) {
    closeHandle(handle);
    throw error;
  }
}

export function openWorkspaceReader(directory) {
  const root = openRoot(directory, LIST_DIRECTORY | READ_ATTRIBUTES);
  let closed = false;

  function withEntry(relativePath, directory, operation) {
    if (closed) throw Error('工作区授权已关闭。');
    if (relativePath === '' && directory) return operation(root.handle, {});
    const parts = relativeParts(relativePath);
    const handles = [];
    try {
      let path = root.path;
      for (const [index, part] of parts.entries()) {
        const last = index === parts.length - 1;
        const expectsDirectory = !last || directory;
        const access = expectsDirectory ? LIST_DIRECTORY | READ_ATTRIBUTES : GENERIC_READ;
        const handle = open(childPrefix(path) + part, access);
        handles.push(handle);
        const metadata = info(handle);
        path = assertChild(handle, path);
        if (metadata.directory !== expectsDirectory) throw Error('路径成员类型不符。');
        if (last) return operation(handle, metadata);
      }
    } finally {
      for (const handle of handles.reverse()) closeHandle(handle);
    }
  }

  function readBytes(relativePath, limit = MAX_BYTES) {
    return withEntry(relativePath, false, (handle, metadata) => {
      if (metadata.links !== 1 || metadata.size > limit) throw Error('文件超过读取限制，或不是单链接普通文件。');
      const bytes = Buffer.alloc(metadata.size + 1);
      const length = [0];
      if (!readFile(handle, bytes, bytes.length, length, null) || length[0] !== metadata.size) {
        throw Error('文件读取失败或超过限制。');
      }
      return bytes.subarray(0, length[0]);
    });
  }
  return {
    list(relativePath = '') { return withEntry(relativePath, true, enumerate); },
    readBytes,
    readText(relativePath) { return new TextDecoder('utf-8', { fatal: true }).decode(readBytes(relativePath)); },
    close() {
      if (closed) return;
      closed = true;
      closeHandle(root.handle);
    },
  };
}

export function openReportWriter(sourceDirectory) {
  const source = openRoot(sourceDirectory, READ_ATTRIBUTES);
  let output;
  const directory = childPrefix(source.path) + 'GeneLoop 输出';
  function ensureOutput() {
    if (output) return output;
    if (!createDirectory(directory, null) && getLastError() !== ALREADY_EXISTS) {
      throw Error('无法在工作区创建「GeneLoop 输出」文件夹。');
    }
    const handle = open(directory, READ_ATTRIBUTES);
    try {
      if (!info(handle).directory || assertChild(handle, source.path).toLowerCase() !== directory.toLowerCase()) {
        throw Error('无法验证工作区的输出文件夹。');
      }
      return output = { handle, path: directory };
    } catch (error) {
      closeHandle(handle);
      throw error;
    }
  }

  let closed = false;
  function writeArtifacts(items) {
    if (closed) throw Error('输出目录授权已关闭。');
    if (!items.length || items.length > 4 || items.some(({extension, bytes}) =>
      !['md', 'pptx', 'pdf', 'mp4', 'json', 'tsx', 'csv', 'zip', 'txt', 'docx', 'xlsx', 'png'].includes(extension) || !Buffer.isBuffer(bytes) ||
      bytes.length < 1 || bytes.length > 80 * 1024 * 1024)) throw Error('交付物的类型、数量或大小超出本机限制。');
    const { path } = ensureOutput();
    const batch = randomUUID();
    const pending = [];
    try {
      for (const {extension, bytes} of items) {
        const name = 'GeneLoop-' + batch + '.' + extension;
        const handle = open(childPrefix(path) + name, WRITE_REPORT, CREATE_NEW, 0);
        pending.push({ handle, name, bytes: bytes.length });
        assertChild(handle, path);
        const written = [0];
        if (!writeFile(handle, bytes, bytes.length, written, null) || written[0] !== bytes.length || !flushFile(handle)) {
          throw Error('产物写入不完整。');
        }
      }
      return pending.map(({ name, bytes }) => ({ name, bytes }));
    } catch (error) {
      let clean = true;
      for (const {handle} of pending) if (!setInfo(handle, FILE_DISPOSITION_INFO, Buffer.from([1]), 1)) clean = false;
      if (!clean) throw Error('产物写入失败，无法清理本次生成的部分文件。', { cause: error });
      throw error;
    } finally {
      for (const {handle} of pending) closeHandle(handle);
    }
  }
  return {
    writeArtifacts,
    writeMarkdown(text) {
      const length = Buffer.byteLength(text, 'utf8');
      if (!length || length > MAX_BYTES) throw Error('报告必须为 1 至 256 KiB。');
      return writeArtifacts([{ extension: 'md', bytes: Buffer.from(text, 'utf8') }])[0];
    },
    close() {
      if (closed) return;
      closed = true;
      if (output) closeHandle(output.handle);
      closeHandle(source.handle);
    },
  };
}
