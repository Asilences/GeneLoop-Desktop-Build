/** Web selection over DeepSeek's native, validated effort IDs. */
import { DeepSeekAdapter } from '@deepseek-ai/dsh-llm-deepseek';
import type { LlmResolvedModelInfo } from '@deepseek-ai/dsh-llm';

// Provider-native maximum, verified 2026-10-20 against the official API.
// Omitting max_tokens instead selects only 8K in Off mode, not this capacity.
// https://api-docs.deepseek.com/api/create-chat-completion/
export const WEB_DEEPSEEK_OUTPUT_CAPACITY = 393216;

export const WEB_REASONING_EFFORTS = ['off', 'low', 'high', 'max'] as const;
export type WebReasoningEffort = typeof WEB_REASONING_EFFORTS[number];
export const WEB_REASONING_LABELS: Record<WebReasoningEffort, string> = {off:'Off', low:'Low', high:'High', max:'Max'};
export type WebModelOption = { provider: string; model: string; label: string; available: boolean;
  context_window?: number; max_output_tokens?: number; input_modalities?: readonly ('text'|'image')[];
  supported_reasoning_efforts?: readonly WebReasoningEffort[];
  reasoning_unavailable?: Partial<Record<WebReasoningEffort, string>> };

/** Use explicit server metadata for Kouri ids outside the installed defaults. */
export function webDeepSeekModels<T extends {id: string; name?: string}>(native: readonly T[], configured: readonly WebModelOption[]): T[] {
  return configured.filter(row => row.available && row.provider === 'deepseek-official').map(row => {
    const model = native.find(item => item.id === row.model);
    if ((!model || !['deepseek-flash','deepseek-v4-pro'].includes(model.id)) &&
      (!Number.isSafeInteger(row.context_window) || row.context_window! < 1 ||
       !Number.isSafeInteger(row.max_output_tokens) || row.max_output_tokens! < 1 ||
       !row.input_modalities?.length || row.input_modalities.some(value => !['text','image'].includes(value))))
      throw new Error('Configured DeepSeek model is not supported by the installed provider without explicit capabilities');
    return {...model, id:row.model, name:row.label,
      ...(row.context_window === undefined ? {} : {contextWindow:row.context_window}),
      ...(row.max_output_tokens === undefined ? {} : {maxTokens:row.max_output_tokens}),
      ...(row.input_modalities === undefined ? {} : {inputModalities:[...row.input_modalities]})} as T;
  });
}

export function webReasoningAvailability(option: WebModelOption, value: unknown = 'off'): WebReasoningEffort | undefined {
  const effort = webReasoningEffort(option.provider, value);
  if (effort && option.supported_reasoning_efforts && !option.supported_reasoning_efforts.includes(effort))
    throw new Error('The configured model does not support the selected reasoning effort');
  const reason = effort && option.reasoning_unavailable?.[effort];
  if (reason) throw new Error(reason);
  return effort;
}

export function webReasoningEffort(provider: string, value: unknown = 'off'): WebReasoningEffort | undefined {
  if (provider === 'harless-glm') {
    if (value === undefined || value === 'off') return undefined;
    throw new Error('The configured GLM connection does not expose a reasoning toggle');
  }
  if (provider === 'deepseek-official' && WEB_REASONING_EFFORTS.includes(value as WebReasoningEffort)) return value as WebReasoningEffort;
  throw new Error('Unsupported reasoning mode');
}

function productModes(model: LlmResolvedModelInfo, configured: readonly WebModelOption[]): LlmResolvedModelInfo {
  const option = configured.find(row => row.provider === model.provider && row.model === model.id);
  const unavailable = option?.reasoning_unavailable;
  const descriptions: Record<WebReasoningEffort, string> = {off:'关闭思考，直接回答。', low:'较低思考强度，适合简单或重视响应速度的任务。',
    high:'较高思考强度，适合复杂任务。', max:'最高思考强度，可能增加响应时间与 token 用量。'};
  // An older catalog may only list IDs. In that case retain the installed
  // adapter's native capabilities instead of assuming new API levels exist.
  const efforts = model.reasoning?.efforts.filter(row => WEB_REASONING_EFFORTS.includes(row.id as WebReasoningEffort) &&
      (!option?.supported_reasoning_efforts || option.supported_reasoning_efforts.includes(row.id as WebReasoningEffort)))
    .map(row => ({ ...row, name: WEB_REASONING_LABELS[row.id as WebReasoningEffort] + (unavailable?.[row.id as WebReasoningEffort] ? '（当前预算不可用）' : ''),
      description: unavailable?.[row.id as WebReasoningEffort] ?? descriptions[row.id as WebReasoningEffort] }));
  if (!efforts?.some(row => row.id === 'off')) throw new Error('DeepSeek deployment must support reasoning Off');
  return { ...model, reasoning: { efforts, defaultEffort: efforts.find(row => row.id === 'off')!.id } };
}

/** Keep provider serialization in the installed adapter; customize discovery only. */
export class WebDeepSeekAdapter extends DeepSeekAdapter {
  private configuredModels: readonly WebModelOption[];
  private connectionOptions: ConstructorParameters<typeof DeepSeekAdapter>[0]['options'];
  constructor(config: ConstructorParameters<typeof DeepSeekAdapter>[0], models: readonly WebModelOption[] = []) {
    super(config); this.configuredModels = models; this.connectionOptions=config.options;
  }
  override async resolveModel(...args: Parameters<DeepSeekAdapter['resolveModel']>) {
    return productModes(await super.resolveModel(...args), this.configuredModels);
  }
  override async prepareCall(...args: Parameters<DeepSeekAdapter['prepareCall']>) {
    const prepared = await super.prepareCall(...args);
    return { ...prepared, model: productModes(prepared.model, this.configuredModels),
      stream:(request:Parameters<DeepSeekAdapter['stream']>[0])=>this.transportStream(this.withOutputCapacity(request),prepared.stream) };
  }
  private withOutputCapacity(request:Parameters<DeepSeekAdapter['stream']>[0]) {
    const connection=this.connectionOptions();
    const providerCapacity=connection.models.find(row=>row.id===request.model)?.maxTokens??WEB_DEEPSEEK_OUTPUT_CAPACITY;
    const applicationCapacity=connection.maxTokens??WEB_DEEPSEEK_OUTPUT_CAPACITY;
    return request.maxTokens!==undefined?request:{...request,maxTokens:Math.min(providerCapacity,applicationCapacity)};
  }
  private async *transportStream(request:Parameters<DeepSeekAdapter['stream']>[0],
    stream:(request:Parameters<DeepSeekAdapter['stream']>[0])=>ReturnType<DeepSeekAdapter['stream']>) {
    if(!request.signal){yield* stream(request);return;}
    // Node fetch captures a stack on an object passed as AbortSignal.reason.
    // The native agent's cause is an immutable JSON journal value; exposing
    // that same object makes turn/end fail lossless-JSON validation on cancel.
    // Forward cancellation synchronously with a fresh transport-only reason.
    const transport=new AbortController(),abort=()=>transport.abort(new DOMException('Request cancelled','AbortError'));
    request.signal.addEventListener('abort',abort,{once:true});
    if(request.signal.aborted)abort();
    try{yield* stream({...request,signal:transport.signal});}
    finally{request.signal.removeEventListener('abort',abort);}
  }
  override stream(request:Parameters<DeepSeekAdapter['stream']>[0]) {
    return this.transportStream(this.withOutputCapacity(request),q=>super.stream(q));
  }
}
