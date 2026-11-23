import type { Scene, Selection } from "../account/harless_settings.ts";
import type { SceneOptions } from "../attachments/harless_task_scope.ts";
import type { createPaperRecovery } from "../scenes/harless_paper_recovery.ts";
import type { createPptRecovery } from "../scenes/harless_ppt_recovery.ts";
import type { NormalizedWebTask, PromptPart } from "../web_task_request.ts";
import type { createPptMasterRecovery } from "../../ppt/delivery/ppt_master_recovery.ts";
import type { WebModelOption, WebReasoningEffort } from "./harless_reasoning.ts";
import type { createTaskProgress } from "./harless_task_progress.ts";
import type { FrozenTaskStrategy } from "./harless_task_strategy.ts";

export type Task = {
  request: NormalizedWebTask; delivery: PromptPart[]; confirmation_digest: string;
  native_turn?: number;
  research_strategy?: FrozenTaskStrategy;
  strategy_disposers?: (() => void)[];
  strategy_exposure?: 'prepared_only' | 'prompt_submitted';
  status: string; created_at: string; started_at?: string; finished_at?: string;
  failure: string | null; fallback_reason: string | null; answer: string;
  output: string; stats: Record<string, any>; interceptor?: any;
  humans: Map<string, string>; current_humans: Set<string>;
  sources: { resource_id: string; version: string; sha256: string }[];
  scene: Scene; selection: Selection; tools: any[]; manifest_sha256: string | null; binding_sha256: string | null;
  trace_start_index?: number;
  paper_flow_shadow_sha256?: string | null;
  closing?: Promise<void>; entrypoint: 'workbench' | 'native_chat';
  model_option: WebModelOption; reasoning_effort?: WebReasoningEffort; workspace: string; scene_options: SceneOptions; scene_inputs: any[]; source_pending?: boolean; scope_sha256: string | null;
  budget_session_id: string;
  input_abort?: AbortController;
  context_input_files?: string[];
  inherited_context?: string;
  inherited_evidence?: string[];
  inherited_images?: any[];
  native_image_sources?: any[];
  evidence_cache_directory?: string;
  source_task_id?: string;
  ppt_recovery?: ReturnType<typeof createPptRecovery>;
  ppt_master_recovery?: ReturnType<typeof createPptMasterRecovery>;
  ppt_initial_sources?: Record<string,string>;
  paper_recovery?: ReturnType<typeof createPaperRecovery>;
  bound_binding_sha256?: string | null;
  video_program_seen?: Set<string>;
};
export class TaskError extends Error {
  code: string; status: number;
  constructor(code: string, message: string, status = 400) { super(message); this.code = code; this.status = status; }
}

export const terminal = new Set(['completed', 'failed', 'cancelled', 'budget_exhausted']);

type TaskProgressSnapshot = ReturnType<ReturnType<typeof createTaskProgress>["snapshot"]>;

export function taskView(task: Task, principal: string, providerMode: 'mock' | 'real', live: TaskProgressSnapshot | undefined, detail = false) {
  const request = task.request;
  return { task_id: request.task_id, session_id: request.session_id, request_id: request.request_id,
    capability_profile: request.capability_profile, scene: task.scene.id, scene_sha256: task.scene.config_sha256,
    user_id: principal, selected_mode: task.selection.mode, rsi: task.selection.rsi, mode: request.mode, budget_usd: request.budget_usd,
    strategy_exposure: task.strategy_exposure,
    native_turn: task.native_turn, entrypoint: task.entrypoint, source_task_id: task.source_task_id, status: task.status, failure: task.failure, fallback_reason: task.fallback_reason,
    created_at: task.created_at, started_at: task.started_at, finished_at: task.finished_at,
    duration_ms:task.started_at?Math.max(0,Date.parse(task.finished_at??new Date().toISOString())-Date.parse(task.started_at)):0,
    input_summary: request.summary, prompt_sha256: request.prompt_sha256,
    request_sha256: request.request_sha256, confirmation_digest: task.confirmation_digest,
    provider_mode: providerMode, provider: task.model_option.provider, model: task.model_option.model,
    reasoning_effort: task.reasoning_effort ?? null,
    learning_version:task.scene.learning_version??null,learning_phase:task.scene.learning_phase??null,motif_library:task.scene.runtime_kind??null,library_sha256:task.scene.runtime_library_sha256??null,
    paid_calls_enabled: providerMode === 'real',
    scene_options: task.scene_options, scene_inputs: task.scene_inputs, source_pending: task.source_pending ?? false,
    effects: 'Configured scene tools, public web search/reading, and Session-isolated commands and background jobs.',
    stats: task.stats, sources: task.sources,
    ...(live?{progress:live.progress,activity:live.activity,messages:live.messages,trace:live.trace,todos:live.todos}:{}),
    ...(detail ? { answer: task.answer, input_preview: task.delivery.filter(part => part.type === 'text').map(part => (part as any).text).join('\n').slice(0, 4096), artifacts: ['task.json', 'effective-config.json', 'events.jsonl',
      'ledger.jsonl', 'motif-audit.jsonl', ...(task.answer ? ['answer.md'] : [])] } : {}) };
}
