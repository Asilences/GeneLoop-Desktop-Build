"""Find recurring motifs and witnessed parameter dependencies in normalized traces."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from ...trajectory import Trace
from .motif_miner import mine_motifs, normalize_repeated_tools


def mine_traces(traces: Iterable[Trace], *, min_trace_support: int = 2,
                min_len: int = 2, max_len: int = 8) -> list[dict[str, Any]]:
    """Find candidates observed in distinct traces, never crossing blocked calls."""
    if min_trace_support < 2:
        raise ValueError("at least two independent traces are required")
    rows = list(traces)
    if len({row.trace_id for row in rows}) != len(rows):
        raise ValueError("trace IDs must be unique")
    sequences = [normalize_repeated_tools(list(segment))
                 for row in rows for segment in row.segments if len(segment) >= min_len]
    if not sequences:
        return []
    candidates = mine_motifs(sequences, min_support=1 / len(sequences),
                             min_len=min_len, max_len=max_len)
    promoted = []
    for candidate in candidates:
        pattern = candidate["tools"]
        supporting_ids = sorted(row.trace_id for row in rows if any(
            any(normalize_repeated_tools(list(segment))[index:index + len(pattern)] == pattern
                for index in range(len(normalize_repeated_tools(list(segment))) - len(pattern) + 1))
            for segment in row.segments))
        if len(supporting_ids) < min_trace_support:
            continue
        promoted.append({**candidate, "source_trace_ids": supporting_ids,
                         "trace_count": len(supporting_ids),
                         "trace_support": len(supporting_ids) / len(rows)})
    return promoted


def mine_witnessed_parameter_edges(traces: Iterable[Trace], *,
                                   min_task_support: int = 2) -> list[dict[str, Any]]:
    """Propose local dependency edges even when calls were batched/interleaved.

    Each edge comes from trace evidence that ties a parameter value to an
    earlier successful tool result.
    """
    if min_task_support < 2:
        raise ValueError("edge candidates require at least two distinct tasks")
    rows = list(traces)
    if len({row.trace_id for row in rows}) != len(rows):
        raise ValueError("trace IDs must be unique")
    if any(not row.task_fingerprint for row in rows):
        raise ValueError("every trace needs a task fingerprint")
    witnesses: dict[tuple[str, str, str, str], Counter[str]] = defaultdict(Counter)
    tasks: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for trace in rows:
        for record in trace.records:
            if not record.eligible:
                continue
            for target_param, source in (record.parameter_sources or {}).items():
                edge = (source["from_tool"], source["from_field"],
                        record.name, target_param)
                witnesses[edge][trace.trace_id] += 1
                tasks[edge].add(trace.task_fingerprint)
    candidates = []
    for edge, counts in witnesses.items():
        if len(tasks[edge]) < min_task_support:
            continue
        candidates.append({
            "status": "candidate_only",
            "from_tool": edge[0], "from_field": edge[1],
            "to_tool": edge[2], "to_param": edge[3],
            "source_trace_ids": sorted(counts),
            "task_support": len(tasks[edge]),
            "observed_edges": sum(counts.values()),
        })
    return sorted(candidates, key=lambda row: (
        -row["task_support"], -row["observed_edges"],
        row["from_tool"], row["to_tool"], row["to_param"]))
