/** Kouri SystemOne structured judgements; separate from chat completions.
 * No automatic retries, permission grants or RSI certification decisions.
 */
import { constants, closeSync, fstatSync, openSync, readFileSync, realpathSync,
  mkdirSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { parseEnv } from 'node:util';
import { randomUUID, createHash } from 'node:crypto';

export const JEV_ENDPOINT = 'https://api.kourichat.com/v1/systemone';
export type JevQuestion = { type: 'noul'; instructions: string } |
  { type: 'choice'; instructions: string; criteria: Record<string, string> };
export type JevRequest = { model?: 'jev'; state: string; questions: Record<string, JevQuestion> };
export class JevError extends Error {
  code: string; runDirectory?: string;
  constructor(code: string, runDirectory?: string) {
    super(`JEV: ${code}${runDirectory ? ` (记录: ${runDirectory})` : ''}`);
    this.name = 'JevError'; this.code = code; this.runDirectory = runDirectory;
  }
}
const object = (v: any): v is Record<string, any> => v !== null && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown) => typeof v === 'string' && v.trim().length > 0;
const number = (v: unknown) => typeof v === 'number' && Number.isFinite(v);

export function validateJevRequest(value: unknown): JevRequest & { model: 'jev' } {
  if (!object(value) || Object.keys(value).some(k => !['model','state','questions'].includes(k)) ||
      (value.model !== undefined && value.model !== 'jev') || !text(value.state) ||
      !object(value.questions) || !Object.keys(value.questions).length) throw new JevError('invalid_request');
  for (const [id, q] of Object.entries(value.questions)) {
    if (!text(id) || !object(q) || !text(q.instructions) || !['noul','choice'].includes(q.type) ||
        Object.keys(q).some(k => !['type','instructions','criteria'].includes(k))) throw new JevError('invalid_question');
    if (q.type === 'choice') {
      if (!object(q.criteria) || !Object.keys(q.criteria).length ||
          Object.entries(q.criteria).some(([k, v]) => !text(k) || !text(v))) throw new JevError('invalid_criteria');
    } else if (Object.hasOwn(q, 'criteria')) throw new JevError('invalid_criteria');
  }
  return JSON.parse(JSON.stringify({ ...value, model: 'jev' })) as JevRequest & { model: 'jev' };
}

/** Uses the same private credential file, without exporting its key to env/children. */
export function loadJevCredential(config = process.env.KOURI_JEV_CONFIG ?? process.env.SSS_FILE_PROVIDER_CONFIG): string {
  if (!config) throw new JevError('missing_private_config');
  const path = resolve(config);
  let fd: number | undefined;
  try {
    fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
    const info = fstatSync(fd);
    if (!info.isFile() || info.nlink !== 1 || (info.mode & 0o077) || realpathSync(path) !== path)
      throw new JevError('private_config_required');
    const values = parseEnv(readFileSync(fd, 'utf8'));
    // Do not follow configured origins to arbitrary services with this credential.
    if (!/^https:\/\/api\.kourichat\.com(?:\/v1)?\/?$/.test(values.KOURI_BASE_URL ?? ''))
      throw new JevError('invalid_kouri_origin');
    const key = values.KOURI_API_KEY;
    if (!key || /[\s\x00-\x1f\x7f]/.test(key) || key === 'sk-kouri-') throw new JevError('missing_credential');
    return key;
  } catch (error) {
    if (error instanceof JevError) throw error;
    throw new JevError('private_config_unreadable');
  } finally { if (fd !== undefined) closeSync(fd); }
}

export function validateJevResponse(value: unknown, request: JevRequest) {
  if (!object(value) || !text(value.model) || !object(value.answers) ||
      Object.keys(value.answers).length !== Object.keys(request.questions).length) throw new JevError('invalid_response');
  for (const [id, q] of Object.entries(request.questions)) {
    const a = Object.hasOwn(value.answers, id) ? value.answers[id] : undefined;
    if (!object(a) || a.type !== q.type) throw new JevError('invalid_answer');
    if (q.type === 'noul' && !number(a.noul)) throw new JevError('invalid_noul');
    if (q.type === 'choice') {
      if (typeof a.choice !== 'string' || !Object.hasOwn(q.criteria, a.choice)) throw new JevError('invalid_choice');
      if (a.confidence !== undefined && (!number(a.confidence) || a.confidence < 0 || a.confidence > 1))
        throw new JevError('invalid_confidence');
      if (a.probabilities !== undefined && (!object(a.probabilities) ||
          Object.entries(a.probabilities).some(([k, p]) => !Object.hasOwn(q.criteria,k) || !number(p) || p < 0 || p > 1)))
        throw new JevError('invalid_probabilities');
    }
  }
  return value;
}

export async function judgeWithJev(input: JevRequest, options: {
  config?: string; recordRoot?: string; timeoutMs?: number; signal?: AbortSignal;
} = {}) {
  const request = validateJevRequest(input), credential = loadJevCredential(options.config);
  const timeoutMs = options.timeoutMs ?? 120_000;
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0) throw new JevError('invalid_timeout');
  const root = resolve(options.recordRoot ?? '.local/jev/runs');
  mkdirSync(root, { recursive: true, mode: 0o700 });
  const directory = join(root, randomUUID());
  mkdirSync(directory, { mode: 0o700 });
  const save = (name: string, value: unknown) => writeFileSync(join(directory, name),
    JSON.stringify(value, null, 2) + '\n', { encoding: 'utf8', mode: 0o600, flag: 'wx' });
  const payload = JSON.stringify(request), started = Date.now();
  save('request.json', request);
  save('started.json', { format: 'kouri-jev-call-v1', endpoint: JEV_ENDPOINT, model: 'jev',
    started_at: new Date(started).toISOString(), request_sha256: createHash('sha256').update(payload).digest('hex'),
    automatic_retries: 0, timeout_ms: timeoutMs, quota: null });
  let status: number | null = null, attempts = 0;
  try {
    const timeout = AbortSignal.timeout(timeoutMs);
    const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
    signal.throwIfAborted();
    attempts = 1;
    const response = await fetch(JEV_ENDPOINT, { method: 'POST', redirect: 'error', signal,
      headers: { 'Authorization': `Bearer ${credential}`, 'Content-Type': 'application/json' }, body: payload });
    status = response.status;
    const raw = await response.text();
    writeFileSync(join(directory, 'response.txt'), raw, { mode: 0o600, flag: 'wx' });
    save('http.json', { status, request_id: response.headers.get('x-request-id') ?? response.headers.get('request-id'),
      content_type: response.headers.get('content-type') });
    if (!response.ok) throw new JevError(`http_${status}`);
    let parsed: unknown;
    try { parsed = JSON.parse(raw); } catch { throw new JevError('invalid_json'); }
    const result = validateJevResponse(parsed, request);
    const accounting = { upstream_attempts: attempts, reported_usage: result.usage ?? null,
      reported_cost: result.usage?.cost ?? null, currency: null, invoice_verified: false,
      cost_basis: result.usage?.cost === undefined ? 'not_reported' : 'provider_reported_unverified_currency' };
    save('completed.json', { status: 'completed', http_status: status, elapsed_ms: Date.now() - started, ...accounting });
    return { result, accounting, record_directory: directory };
  } catch (error) {
    const code = error instanceof JevError ? error.code : options.signal?.aborted ? 'cancelled' :
      (error as Error)?.name === 'TimeoutError' ? 'timeout' : 'transport_error';
    save('failed.json', { status: 'failed', code, http_status: status, elapsed_ms: Date.now() - started,
      upstream_attempts: attempts, charge_unknown: attempts > 0, automatic_retries: 0 });
    throw new JevError(code, directory);
  }
}
