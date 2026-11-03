"""Project a private native event journal into a bounded RSI structure sample."""

import argparse
import json
import stat
from pathlib import Path

from jsonschema import Draft202012Validator

from .dsh_event_projection import is_original_tool_result
from .dsh_trajectory import extract_dsh_trace, infer_dsh_provenance
from .tool_contract_loader import parse_tool_contracts

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
        nodes.append({"tool": record.name if record.name in contracts else None, "outcome": record.reason})
        for param in (record.parameter_sources or {}) if record.eligible else ():
            source = provenance[call_id][param]
            bindings.append({"from": calls[source["from_call_id"]], "to": index,
                             "field": source["from_field"], "parameter": param})
    sample = {"format": "geneloop.rsi-learning-trace/v1", "scene": scene, "status": status,
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
