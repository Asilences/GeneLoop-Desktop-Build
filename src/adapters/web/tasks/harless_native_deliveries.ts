import { basename, join } from "node:path";
import { pptFinalDeliveryFiles } from "../../ppt/delivery/ppt_task_completion.ts";
import { captureComparisonDeliveries, comparisonArtifacts } from "./harless_comparison_artifacts.ts";
import { publicTaskJson } from "./harless_public_output.ts";
import { TaskError, terminal, type Task } from "./harless_task.ts";

export function supportsNativeDelivery(task: Task) {
  return task.scene.adapter === "workspace" || task.scene.adapter === "video" ||
    (task.scene.adapter === "ppt" && task.scene.ppt_execution_strategy === "ppt_master");
}

type TaskAccess = {
  tasks: ReadonlyMap<string, Task>;
  ensureOwned(session: string): Promise<unknown>;
  getTask(id: string): Task;
  isComparisonLane(session: string): boolean | undefined;
};

export function createNativeTaskDeliveries(config: {output: string; command_resources?: any}) {
  function capture(task: Task) {
    const store = comparisonArtifacts(config.output);
    const turn = 'native-' + task.request.task_id;
    const ppt = task.scene.adapter === 'ppt';
    if (ppt && task.status === 'completed') {
      const files = pptFinalDeliveryFiles(task, config.command_resources);
      if (files.size) {
        const approved = new Set(files.keys());
        return store.snapshot(turn, 'baseline', 0, task.workspace, approved, false, approved, undefined, files, 'ppt-delivery-v1');
      }
    }
    const verification = task.scene.adapter === 'video' ? 'video-delivery-v1' : 'code-output-v1';
    return captureComparisonDeliveries(store, {
      turn, lane: 'baseline', attempt: 0,
      workspace: task.workspace, adapter: task.scene.adapter, status: task.status, answer: task.answer,
      eventsPath: join(task.output, 'events.jsonl'), startedAt: task.started_at, finishedAt: task.finished_at,
    }).filter((row: any) => row.verification === verification || (ppt && row.verification === 'ppt-delivery-v1'));
  }

  function mount(ctx: any, {tasks, ensureOwned, getTask, isComparisonLane}: TaskAccess) {
    ctx.effect(() => ctx.connection.fetch.register({ path: '/api/harless/deliveries', methods: ['GET'], requestBody: 'buffered',
      async fetch(request: Request) {
        const rejected = ctx.connection.requestRejection(request); if (rejected) return new Response('Unauthorized', { status: rejected });
        try {
          const url = new URL(request.url), session = url.searchParams.get('session_id')!;
          await ensureOwned(session);
          if (isComparisonLane(session)) throw new TaskError('artifact_not_found', '请在原对话查看结果。', 404);
          const id = url.searchParams.get('id'), turn = Number(url.searchParams.get('turn'));
          const task = id ? getTask(id.replace(/^native-/, '')) : [...tasks.values()].find(task =>
            task.request.session_id === session && task.native_turn === turn && supportsNativeDelivery(task));
          if (!task || task.request.session_id !== session || !supportsNativeDelivery(task))
            throw new TaskError('artifact_not_found', '找不到本轮交付文件。', 404);
          if (!terminal.has(task.status)) return Response.json({ pending: true }, { status: 202, headers: {'Cache-Control':'no-store'} });
          if (task.status !== 'completed') throw new TaskError('artifact_not_found', '本轮没有已完成的文件。', 404);
          const rows = capture(task).filter((row: any) => task.scene.adapter !== 'ppt' || row.verification === 'ppt-delivery-v1');
          const file = url.searchParams.get('file');
          if (file) {
            const row = rows.find((row: any) => row.id === file);
            if (url.searchParams.get('lane') !== 'baseline' || !row) throw new TaskError('artifact_not_found', '找不到本轮交付文件。', 404);
            return new Response(comparisonArtifacts(config.output).read('native-' + task.request.task_id, 'baseline', row), { headers: {
              'Content-Type': 'application/octet-stream', 'Content-Disposition': "attachment; filename*=UTF-8''" + encodeURIComponent(basename(row.name)),
              'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
          }
          return publicTaskJson({ id: 'native-' + task.request.task_id, session_id: session, turn: task.native_turn,
            presentation: 'single', status: task.status, lanes: { baseline: { status: task.status, artifacts: rows } } },
            { headers: { 'Cache-Control': 'no-store' } });
        } catch (error) {
          return Response.json({ error: { code: 'delivery_unavailable', message: '文件不可用，请刷新后重试。' } },
            { status: error instanceof TaskError ? error.status : 409 });
        }
      },
    }), 'harless-native-deliveries');
  }

  return {capture, mount};
}
