import koffi from 'koffi';
import { win32 } from 'node:path';

const READ_ATTRIBUTES = 0x80;
const GENERIC_READ = 0x80000000;
const SHARE_READ_WRITE = 3; // Deliberately omit FILE_SHARE_DELETE.
const OPEN_EXISTING = 3;
const OPEN_REPARSE_POINT = 0x00200000;
const BACKUP_SEMANTICS = 0x02000000;
const DIRECTORY = 0x10;
const REPARSE_POINT = 0x400;
const MAX_BYTES = 256 * 1024;
const MAX_PATH_UNITS = 32768;

const kernel = koffi.load('kernel32.dll');
const createFile = kernel.func('intptr_t __stdcall CreateFileW(const char16_t *path, uint32_t access, uint32_t share, void *security, uint32_t disposition, uint32_t flags, void *templateFile)');
const getInfo = kernel.func('int __stdcall GetFileInformationByHandle(intptr_t file, void *information)');
const getPath = kernel.func('uint32_t __stdcall GetFinalPathNameByHandleW(intptr_t file, void *path, uint32_t length, uint32_t flags)');
const readFile = kernel.func('int __stdcall ReadFile(intptr_t file, void *data, uint32_t length, _Out_ uint32_t *read, void *overlapped)');
const closeHandle = kernel.func('int __stdcall CloseHandle(intptr_t file)');

function open(path, access) {
  const handle = createFile(path, access, SHARE_READ_WRITE, null, OPEN_EXISTING, BACKUP_SEMANTICS | OPEN_REPARSE_POINT, null);
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
    oversized: bytes.readUInt32LE(32) > 0 || bytes.readUInt32LE(36) > MAX_BYTES,
  };
}

function finalPath(handle) {
  const bytes = Buffer.alloc(MAX_PATH_UNITS * 2);
  const length = getPath(handle, bytes, MAX_PATH_UNITS, 0);
  if (!length || length >= MAX_PATH_UNITS) throw Error('无法确定目录句柄的实际路径。');
  return bytes.toString('utf16le', 0, length * 2);
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

// 在授权时打开根目录。每级子目录使用禁止跟随重解析点的句柄，并持有
// 至读取结束，避免在校验后由另一个进程替换为 junction。
export function openWorkspaceReader(directory) {
  if (!/^[A-Za-z]:[\\/]/.test(directory)) throw Error('首版本机工作区仅支持本地盘符路径。');
  const root = open(win32.toNamespacedPath(directory), READ_ATTRIBUTES);
  let canonical;
  try {
    if (!info(root).directory) throw Error('工作区必须是目录。');
    canonical = finalPath(root);
    if (!/^\\\\\?\\[A-Za-z]:\\/.test(canonical)) throw Error('无法验证本地盘符。');
  } catch (error) {
    closeHandle(root);
    throw error;
  }
  let closed = false;
  return {
    readText(relativePath) {
      if (closed) throw Error('工作区授权已关闭。');
      const parts = relativeParts(relativePath);
      const handles = [];
      try {
        let path = canonical;
        for (const [index, part] of parts.entries()) {
          const isFile = index === parts.length - 1;
          const next = path.endsWith('\\') ? path + part : path + '\\' + part;
          const handle = open(next, isFile ? GENERIC_READ : READ_ATTRIBUTES);
          handles.push(handle);
          const metadata = info(handle);
          const actual = finalPath(handle);
          if (!actual.toLowerCase().startsWith((path.endsWith('\\') ? path : path + '\\').toLowerCase())) {
            throw Error('实际文件路径不在已验证的目录内。');
          }
          if (!isFile) {
            if (!metadata.directory) throw Error('相对路径包含非目录成员。');
            path = actual;
            continue;
          }
          if (metadata.directory || metadata.links !== 1 || metadata.oversized) {
            throw Error('仅支持不超过 256 KiB 的普通文本文件。');
          }
          const bytes = Buffer.alloc(MAX_BYTES + 1);
          const length = [0];
          if (!readFile(handle, bytes, bytes.length, length, null) || length[0] > MAX_BYTES) {
            throw Error('文本读取失败或超过 256 KiB。');
          }
          return new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, length[0]));
        }
      } finally {
        for (const handle of handles.reverse()) closeHandle(handle);
      }
    },
    close() {
      if (closed) return;
      closed = true;
      closeHandle(root);
    },
  };
}
