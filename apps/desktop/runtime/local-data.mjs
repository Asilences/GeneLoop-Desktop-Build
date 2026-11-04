import { createHash } from 'node:crypto';
import { extname } from 'node:path';
import { parse } from 'csv-parse/sync';

const scale = 1_000_000n;
function decimal(text) {
  if (!/^[+-]?\d{1,12}(?:\.\d{1,6})?$/.test(text)) throw Error('数值须为普通十进制，最多 12 位整数和 6 位小数。');
  const [whole, fraction = ''] = text.replace(/^[+-]/, '').split('.');
  const value = BigInt(whole) * scale + BigInt(fraction.padEnd(6, '0'));
  return text.startsWith('-') ? -value : value;
}

function display(value) {
  const sign = value < 0n ? '-' : '';
  const absolute = value < 0n ? -value : value;
  const fraction = (absolute % scale).toString().padStart(6, '0').replace(/0+$/, '');
  return sign + (absolute / scale).toString() + (fraction ? '.' + fraction : '');
}

export function summarizeTable(reader, { path, column, group_by }) {
  const extension = extname(path).toLowerCase();
  if (!['.csv', '.tsv'].includes(extension)) throw Error('支持 UTF-8 CSV 和 TSV。');
  const bytes = reader.readBytes(path);
  const records = parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes), {
    bom: true, delimiter: extension === '.tsv' ? '\t' : ',', skip_empty_lines: true,
  });
  const [header, ...rows] = records;
  if (!header?.length || header.some(name => !name.trim()) || new Set(header).size !== header.length) {
    throw Error('表头必须包含互不重复的列名。');
  }
  if (rows.length > 10_000) throw Error('单张表最多支持 10,000 行。');
  const metric = header.indexOf(column);
  const group = group_by ? header.indexOf(group_by) : -1;
  if (metric < 0 || (group_by && group < 0)) throw Error('找不到指定的数据列或分组列。');
  const groups = new Map();
  for (const row of rows) {
    const key = group < 0 ? '' : row[group];
    const stats = groups.get(key) ?? { count: 0, missing: 0, sum: 0n, min: null, max: null };
    groups.set(key, stats);
    if (groups.size > 200) throw Error('最多支持 200 个分组。');
    const text = row[metric].trim();
    if (!text) { stats.missing++; continue; }
    const value = decimal(text);
    stats.count++;
    stats.sum += value;
    if (stats.min === null || value < stats.min) stats.min = value;
    if (stats.max === null || value > stats.max) stats.max = value;
  }
  return {
    path, sha256: createHash('sha256').update(bytes).digest('hex'), column, group_by: group_by || null, rows: rows.length,
    groups: [...groups].map(([key, stats]) => {
      const { count, missing, sum, min, max } = stats;
      const n = BigInt(count);
      const rounded = count ? (sum + (sum < 0n ? -(n / 2n) : n / 2n)) / n : null;
      return { group: group < 0 ? null : key, count, missing, sum: display(sum),
        mean: rounded === null ? null : display(rounded), min: min === null ? null : display(min), max: max === null ? null : display(max) };
    }),
  };
}
