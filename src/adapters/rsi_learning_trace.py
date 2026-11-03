"""Project a private native event journal into a bounded RSI structure sample."""

import argparse
import hashlib
import json
import stat
from pathlib import Path

from jsonschema import Draft202012Validator

from .dsh_event_projection import is_original_tool_result
from .dsh_trajectory import DshTrace, ToolRecord, extract_dsh_trace, infer_dsh_provenance
from src.motif_core.offline.edge_compiler import argument_shape
from .tool_contract_loader import parse_tool_contracts
from .task_identity import load_trace_identity

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = {
    "paper-proofreading": "scenarios/paper_proofreading/document-read-contracts.json",
    "ppt": "scenarios/ppt_master/contracts.json",
}
SCHEMA = Draft202012Validator(json.loads(
    (ROOT / "docs/schemas/rsi-learning-trace.schema.json").read_text(encoding="utf-8")
))
MAX_EVENTS = 20_000
MAX_BYTES = 32 * 1024 * 1024


def project(events, scene, status):
    contracts = parse_tool_contracts(json.loads((ROOT / CONTRACTS[scene]).read_text(encoding="utf-8")))
    calls, results = {}, set()
    ordered = []
    for index, event in enumerate(events):
        if event.get("ptc_analysis_source"):
            raise ValueError("derived_tool_event")
        if event.get("type") == "tool/call":
            data = event.get("data")
            if not isinstance(data, dict):
                raise ValueError("invalid_tool_call")
            call_id, name = data.get("callId"), data.get("name")
            if not isinstance(call_id, str) or not call_id or call_id in calls or not isinstance(name, str) or not name:
                raise ValueError("invalid_tool_call")
            calls[call_id] = len(calls)
        elif is_original_tool_result(event):
            data = event.get("data")
            message = data.get("message") if isinstance(data, dict) else None
            source = message.get("source") if isinstance(message, dict) else None
            call_id = source.get("callId") if isinstance(source, dict) else None
            if not isinstance(call_id, str) or call_id not in calls or call_id in results:
                raise ValueError("invalid_tool_result")
            results.add(call_id)
        # Use local ordering and discard original sequence identifiers.
        ordered.append({**event, "seq": index})
    provenance = infer_dsh_provenance(ordered, contracts)
    trace = extract_dsh_trace(ordered, contracts, trace_id="private-input", provenance_by_call_id=provenance)
    nodes, bindings = [], []
    for (call_id, index), record in zip(calls.items(), trace.records, strict=True):
        outcome = record.reason
        sources = provenance.get(call_id, {}) if record.eligible else {}
        if record.eligible and not argument_shape(record.arguments, contracts[record.name]):
            outcome = "invalid_arguments"
        if record.eligible and any(nodes[calls[ref["from_call_id"]]]["outcome"] != "eligible_read"
                                   for ref in sources.values()):
            outcome = "invalid_parameter_provenance"
        nodes.append({"tool": record.name if record.name in contracts else None, "outcome": outcome})
        if outcome == "eligible_read":
            for param, ref in sources.items():
                bindings.append({"from": calls[ref["from_call_id"]], "to": index,
                                 "field": ref["from_field"], "parameter": param})
    sample = {"format": "geneloop.rsi-learning-trace/v2", "scene": scene, "status": status,
              "nodes": nodes, "bindings": bindings}
    SCHEMA.validate(sample)
    return sample


def import_trace(path, scene, status, start):
    if not stat.S_ISREG(path.lstat().st_mode) or path.resolve() != path.absolute():
        raise ValueError("regular_private_input_required")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input_too_large")
    lines = raw.splitlines()
    if not 0 <= start <= len(lines) or len(lines) - start > MAX_EVENTS:
        raise ValueError("invalid_trace_range")
    events = [json.loads(line) for line in lines[start:] if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("invalid_event")
    return project(events, scene, status)


def export_projected_identity(out, sample, *, task_id, decision_id, question, local_root, write):
    """Freeze a private compilation input and keep raw text outside the round."""
    normalized = " ".join(question.split()).casefold()
    if not normalized:
        raise ValueError("missing_projected_question_evidence")
    trace = out / "learning-trace.json"
    manifest = out / "manifest.json"
    identity = out / "task-identity.json"
    write(trace, sample)
    write(manifest, {"task_id": task_id,
                     "question_sha256": hashlib.sha256(normalized.encode()).hexdigest()})
    write(identity, {"schema_version": 1, "research_decision_id": decision_id,
                     "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                     "events_sha256": hashlib.sha256(trace.read_bytes()).hexdigest()})
    return load_trace_identity(identity, trace, local_root, projected=True)


def compilation_trace(sample, contracts, *, scene, trace_id, fingerprint):
    """Adapt a validated projection to the existing witnessed compiler.

    Synthetic values only encode already witnessed bindings. Unbound fields
    carry no values from the task, and blocked calls stay barriers.
    """
    if not SCHEMA.is_valid(sample) or sample["scene"] != scene or sample["status"] != "completed":
        raise ValueError("invalid_learning_projection")
    rows = sample["nodes"]
    args, observations, sources = [], [], []
    for row in rows:
        tool = row["tool"]
        contract = contracts.get(tool)
        if tool is not None and (contract is None or not contract.read_only or contract.continuation_policy):
            raise ValueError("invalid_projected_tool")
        args.append({name: None for name in contract.required_params} if contract else {})
        observations.append({})
        sources.append({})
    for edge in sample["bindings"]:
        start, end, field, param = (edge[k] for k in ("from", "to", "field", "parameter"))
        if not 0 <= start < end < len(rows):
            raise ValueError("invalid_projected_binding")
        producer, consumer = rows[start]["tool"], rows[end]["tool"]
        if (any(rows[i]["outcome"] != "eligible_read" for i in (start, end))
                or producer not in contracts or consumer not in contracts
                or field not in contracts[producer].output_fields
                or param not in contracts[consumer].provenance_params or param in sources[end]):
            raise ValueError("invalid_projected_binding")
        handle = f"local:{start}:{field}"
        observations[start][field] = handle
        args[end][param] = handle
        sources[end][param] = {"from_tool": producer, "from_field": field}
    records = []
    for i, row in enumerate(rows):
        tool, outcome = row["tool"], row["outcome"]
        eligible = outcome == "eligible_read"
        if eligible and (tool not in contracts or set(sources[i]) != set(contracts[tool].provenance_params)):
            raise ValueError("missing_projected_binding")
        records.append(ToolRecord(tool or "", args[i] if eligible else None, None, eligible,
                                  outcome, i, observations[i], sources[i]))
    return DshTrace(trace_id, tuple(records), (), fingerprint)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized", action="store_true", required=True,
                        help="confirm authorization to process this specific private journal")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--scene", choices=CONTRACTS, required=True)
    parser.add_argument("--status", choices=("completed", "failed", "cancelled"), required=True)
    parser.add_argument("--start", type=int, required=True, help="zero-based line offset of the task")
    args = parser.parse_args()
    try:
        sample = import_trace(args.input, args.scene, args.status, args.start)
    except Exception:
        # Validation and parser exceptions can contain raw values and paths.
        parser.exit(1, "rsi_learning_trace_rejected\n")
    print(json.dumps(sample, separators=(",", ":")))


if __name__ == "__main__":
    main()
