// PR #161 / 225d7b557b640a7e66610077b9694c781da8cf37 src/adapters/motif_evidence_projection.ts
// 桌面只读协议投影的兼容副本；不改后台共享模块、执行器或认证规则。随上游协议升级同步。
/** Display adapter only: importing evidence never registers executable tools. */
type Row = Record<string, any>;
export function usd(value: number | null): string {
  return value === null ? '未知' : `USD ${value.toFixed(6)}`;
}

export function evidenceView(input: unknown, check: (value: unknown) => boolean) {
  if (!check(input)) throw new Error('Coding evidence contract mismatch');
  const data = input as Row;
  const runtime=data.format==='geneloop-motif-evidence-v2';
  const capabilities = new Map<string, Row>(data.capabilities.map((c: Row) => [c.id, c]));
  const runs = new Map<string, Row>(data.runs.map((r: Row) => [r.id, r]));
  const evidence = new Set(data.evidence.map((e: Row) => e.id));
  if(runtime&&!data.source.revisions.every((row:Row)=>evidence.has(row.evidence_ref)))throw new Error('Unknown version evidence');
  if (capabilities.size !== data.capabilities.length || runs.size !== data.runs.length || evidence.size !== data.evidence.length)
    throw new Error('Duplicate evidence identity');
  if (new Set(data.events.map((e: Row) => e.id)).size !== data.events.length)
    throw new Error('Duplicate event identity');
  let certifiedCount = 0;
  for (const row of [...data.capabilities, ...data.runs, ...data.events])
    if (!row.evidence_refs.every((id: string) => evidence.has(id))) throw new Error('Unknown evidence reference');
  for (const c of capabilities.values()) {
    const certified = c.status === 'certified';
    if (c.certification.status !== c.status || certified !== c.in_frozen_library ||
        (!runtime&&certified !== (c.version.certificate_digest !== null)) || runtime&&certified&&!c.version.certificate_digest) throw new Error('Inconsistent certification');
    if (certified) certifiedCount++;
  }
  if (certifiedCount !== data.library.certified_count) throw new Error('Incorrect library count');
  for (const e of data.events)
    if (!capabilities.has(e.capability_id) || !runs.has(e.run_id)) throw new Error('Unknown execution reference');
    else if(e.kind !== 'invoke' && e.actual_execution) throw new Error('Inconsistent actual execution');
  return {
    raw: data,
    summary: {
      certified: data.library.certified_count,
      pending: data.capabilities.filter((c: Row) => c.status === 'pending_certification').length,
      invalid: data.capabilities.filter((c: Row) => c.status === 'invalid').length,
      registered: data.capabilities.filter((c: Row) => c.status === 'registered').length,
      applied: data.events.filter((e: Row) => e.kind === 'invoke' && e.status === 'applied' && e.actual_execution).length,
      fallbacks: data.events.filter((e: Row) => e.kind === 'fallback').length,
      savings: null,
    },
    displayOnly: true,
    libraryVersion: data.library.generation,
    capabilities: [...capabilities.values()].map(c => ({
      id: c.id, name: c.name, status: c.status, version: c.version,
      certification: c.certification, contract: c.contract, dependencies: c.dependencies,
      cost: usd(c.cost.amount_usd), evidenceRefs: c.evidence_refs,
      events: data.events.filter((e: Row) => e.capability_id === c.id),
      tools:c.tools,toolFlow:c.tool_flow,sourceTaskCount:c.source_task_count,
    })),
    runs: [...runs.values()].map(r => ({...r, costLabel: usd(r.cost.cost_usd),
      elapsedLabel: r.end_to_end_elapsed_seconds === null ? '未知' : `${r.end_to_end_elapsed_seconds} 秒`})),
  };
}
