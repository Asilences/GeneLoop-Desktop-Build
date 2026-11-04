import { createHash } from 'node:crypto';
import { extname } from 'node:path';

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const decode = bytes => new TextDecoder('utf-8', { fatal: true }).decode(bytes);
const pdfLimit = 8 * 1024 * 1024;
const textLimit = 24_000;

export async function readPaperPage(reader, { path, page }) {
  if (!Number.isInteger(page) || page < 1) throw Error('页码须为正整数。');
  const extension = extname(path).toLowerCase();
  if (['.txt', '.md', '.tex', '.bib'].includes(extension)) {
    if (page !== 1) throw Error('文本材料只有第 1 页。');
    const bytes = reader.readBytes(path);
    const text = decode(bytes);
    return { path, sha256: hash(bytes), page, pages: 1, text: text.slice(0, textLimit), truncated: text.length > textLimit };
  }
  if (extension !== '.pdf') throw Error('支持含文本层的 PDF 和 UTF-8 文本材料。');
  const bytes = reader.readBytes(path, pdfLimit);
  const { getDocument } = await import('pdfjs-dist/legacy/build/pdf.mjs');
  const packageUrl = import.meta.resolve('pdfjs-dist/package.json');
  const task = getDocument({
    data: Uint8Array.from(bytes), isEvalSupported: false, useWorkerFetch: false, useSystemFonts: false,
    cMapUrl: new URL('cmaps/', packageUrl).href, standardFontDataUrl: new URL('standard_fonts/', packageUrl).href,
    disableFontFace: true, enableXfa: false, stopAtErrors: true, verbosity: 0,
  });
  try {
    const pdf = await task.promise;
    if (page > pdf.numPages) throw Error('页码超出 PDF 页数。');
    const content = await (await pdf.getPage(page)).getTextContent();
    const text = content.items.map(item => (item.str || '') + (item.hasEOL ? '\n' : ' ')).join('').trim();
    if (!text) throw Error('该页没有可读取的文字层。');
    return { path, sha256: hash(bytes), page, pages: pdf.numPages, text: text.slice(0, textLimit), truncated: text.length > textLimit };
  } finally {
    await task.destroy();
  }
}

export function checkCitationKeys(reader, { manuscript, bibliography }) {
  if (extname(manuscript).toLowerCase() !== '.tex' || extname(bibliography).toLowerCase() !== '.bib') {
    throw Error('引用键核验需要 LaTeX 源文件与 BibTeX 参考文献文件。');
  }
  const source = reader.readBytes(manuscript), bib = reader.readBytes(bibliography);
  const referenceCounts = new Map();
  for (const match of decode(bib).matchAll(/^\s*@(?!comment\b|preamble\b|string\b)[a-z]+\s*[({]\s*([^\s,{}()]+)\s*,/gim)) {
    const key = match[1];
    referenceCounts.set(key, (referenceCounts.get(key) ?? 0) + 1);
  }
  const text = decode(source).replace(/(?<!\\)%[^\r\n]*/g, '');
  const cited = [];
  let line = 1, newline = text.indexOf('\n');
  for (const match of text.matchAll(/\\(?:cite|citep|citet|parencite|textcite|autocite)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]*)\}/g)) {
    while (newline >= 0 && newline < match.index) { line++; newline = text.indexOf('\n', newline + 1); }
    for (const key of match[1].split(',').map(value => value.trim()).filter(Boolean)) {
      if (cited.length >= 1000) throw Error('单次最多核验 1,000 个引用键。');
      const count = referenceCounts.get(key) ?? 0;
      cited.push({ key, line, status: count === 1 ? 'matched' : count ? 'duplicate' : 'missing' });
    }
  }
  return { manuscript: { path: manuscript, sha256: hash(source) }, bibliography: { path: bibliography, sha256: hash(bib) }, citations: cited };
}
