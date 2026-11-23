#!/usr/bin/env node
/** Explicit local JEV call. No shell parsing and no API keys in argv. */
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { judgeWithJev, JevError } from '../src/adapters/kouri_jev.ts';
const root = dirname(dirname(fileURLToPath(import.meta.url)));
process.chdir(root);
if (existsSync(join(root, '.env'))) process.loadEnvFile(join(root, '.env'));
const sample = { model: 'jev', state: '帮我把退款赶紧处理一下，已经三天了。', questions: {
  urgent: { type: 'noul', instructions: '这句话是否紧急？' },
  team: { type: 'choice', instructions: '该由哪个团队处理？', criteria: {
    billing: '退款、付款、账单', technical: '故障、接口、账号', other: '其他' } } } };
try {
  const args = process.argv.slice(2);
  if (!args.length || args.includes('--help')) {
    console.log('用法: npm run jev -- --example | --input <request.json|-> [--config <私有配置路径>] [--records <目录>] [--timeout-ms <毫秒>]');
    console.log('Node 22.18+。不传输入仅显示帮助，不产生付费调用。');
  } else {
    const options = {}; let input, chosen = false;
    for (let i = 0; i < args.length; i++) {
      const flag = args[i];
      if (flag === '--example' && !chosen) { input = sample; chosen = true; continue; }
      if (!['--input','--config','--records','--timeout-ms'].includes(flag) || !args[i + 1]) throw new JevError('invalid_arguments');
      const value = args[++i];
      if (flag === '--input') {
        if (chosen) throw new JevError('choose_one_input');
        input = JSON.parse(readFileSync(value === '-' ? 0 : value, 'utf8')); chosen = true;
      } else if (flag === '--config') options.config = value;
      else if (flag === '--records') options.recordRoot = value;
      else options.timeoutMs = Number(value);
    }
    if (!chosen) throw new JevError('missing_input');
    const controller = new AbortController();
    const cancel = () => controller.abort(); process.once('SIGINT', cancel); process.once('SIGTERM', cancel);
    try { console.log(JSON.stringify(await judgeWithJev(input, { ...options, signal: controller.signal }), null, 2)); }
    finally { process.removeListener('SIGINT', cancel); process.removeListener('SIGTERM', cancel); }
  }
} catch (error) {
  console.error(error instanceof JevError ? error.message : 'JEV: 本地输入或记录失败；未自动重试');
  process.exitCode = 1;
}
