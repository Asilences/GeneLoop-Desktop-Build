"""Discover exact application-object ID flow without promoting it to execution.

Opaque source handles and application IDs have different version semantics.
This miner records the latter from real tool results, but never treats a
repeated ID as permission to execute a successor or bypass the model.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from ...trajectory.model import ObservedCall, ObservedResult


OBJECT_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[A-Za-z0-9_]+$")


def _fields(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _fields(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _fields(child, f"{path}.{index}" if path else str(index))
    elif isinstance(value, str) and OBJECT_ID.fullmatch(value):
        yield path, value


def object_reference_witnesses(
    events: list[ObservedCall | ObservedResult], approved_tools: set[str],
) -> list[dict[str, str]]:
    """Require one earlier successful producer and one successful consumer."""
    calls: dict[str, ObservedCall] = {}
    producers: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    pending: dict[str, list[dict[str, str]]] = {}
    witnesses = []
    for event in events:
        call_id = event.call_id
        if isinstance(event, ObservedCall):
            name = event.name
            if name not in approved_tools:
                continue
            calls[call_id] = event
            for param, value in event.arguments.items():
                if not isinstance(value, str) or not OBJECT_ID.fullmatch(value):
                    continue
                source = producers.get(value, [])
                if len(source) != 1:
                    continue
                _, from_tool, from_field = source[0]
                if from_tool == name:
                    continue
                pending.setdefault(call_id, []).append({
                    "from_tool": from_tool, "from_field": from_field,
                    "to_tool": name, "to_param": param})
            continue

        call = calls.get(call_id)
        if call is None:
            continue
        value = event.observation
        if (value.get("object_id") is not None and
                call.arguments.get("object_id") is not None and
                value["object_id"] != call.arguments["object_id"]):
            continue
        witnesses.extend(pending.pop(call_id, []))
        for field, object_id in _fields(value):
            producers[object_id].append((call_id, call.name, field))
    return witnesses

def repeated_object_edge_candidates(traces: list[dict], approved_tools: set[str]
                                    ) -> list[dict]:
    """Require two independent source tasks and one distinct validation task."""
    if (len(traces) != 3 or len({row.get("trace_id") for row in traces}) != 3 or
            len({row.get("decision_id") for row in traces}) != 3 or
            any(not row.get("decision_id") or not isinstance(row.get("events"), list)
                for row in traces)):
        raise ValueError("two training tasks and one distinct validation task are required")
    counts = [Counter(tuple(witness[key] for key in
                      ("from_tool", "from_field", "to_tool", "to_param"))
                      for witness in object_reference_witnesses(row["events"], approved_tools))
              for row in traces]
    shared = sorted(set(counts[0]) & set(counts[1]) & set(counts[2]))
    return [{"status": "witnessed_not_executable",
             "from_tool": edge[0], "from_field": edge[1],
             "to_tool": edge[2], "to_param": edge[3],
             "supporting_trace_ids": [row["trace_id"] for row in traces[:2]],
             "validation_trace_id": traces[2]["trace_id"],
             "witness_counts": {row["trace_id"]: count[edge]
                                for row, count in zip(traces, counts)},
             "missing_guard": "cross-object version and authorization relation"}
            for edge in shared]
