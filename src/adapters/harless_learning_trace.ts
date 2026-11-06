import {execFile} from 'node:child_process';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));

export async function projectPrivateLearningTrace(python: string, input: string, scene: string,
  status: string, start: number, options: {semantic?: boolean; share?: boolean} = {}): Promise<string> {
  const env = Object.fromEntries(['PATH', 'SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP', 'TMPDIR', 'SSS_RSI_GITLEAKS']
    .filter(name => process.env[name] !== undefined).map(name => [name, process.env[name]]));
  return new Promise((resolve, reject) => {
    execFile(python, ['-m', 'src.adapters.rsi_learning_trace', '--authorized', '--input', input,
      '--scene', scene, '--status', status, '--start', String(start),
      ...(options.semantic ? ['--include-task-intent'] : []), ...(options.share ? ['--share-object'] : [])],
    {cwd: root, env: {...env, PYTHONUTF8: '1'}, timeout: options.semantic ? 45000 : 15000, maxBuffer: 4 * 1024 * 1024},
    (error, stdout) => error ? reject(new Error('rsi_learning_trace_rejected')) : resolve(stdout));
  });
}

/** Isolated diagnostics only. Web and offline import run the same projector. */
export async function capturePrivateLearningTrace(config: {provider_mode?: string; learning_python?: string},
  output: string, scene: string, status: string, start: number | undefined) {
  if (config.provider_mode !== 'mock' || process.env.SSS_RSI_PRIVACY_DIAGNOSTIC !== '1' ||
      start === undefined || !['paper-proofreading', 'ppt'].includes(scene)) return;
  const python = process.env.SSS_PYTHON ?? config.learning_python;
  if (!python) return;
  const semantic = process.env.SSS_RSI_PRIVACY_SEMANTIC === '1';
  try {
    const sample = await projectPrivateLearningTrace(python, join(output, 'events.jsonl'), scene, status, start, {semantic});
    await writeFile(join(output, 'rsi-learning-trace.json'), sample, {mode: 0o600, flag: 'wx'});
  } catch {
    // A diagnostic failure cannot alter task settlement or expose raw errors.
    await writeFile(join(output, 'rsi-learning-trace-rejected'), '', {mode: 0o600, flag: 'wx'}).catch(() => {});
  }
}
