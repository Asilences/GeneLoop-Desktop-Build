import json
import subprocess
import sys

import pytest
from jsonschema import ValidationError

from src.adapters.rsi_learning_trace import SCHEMA, project

PIN = "mcp__paper_checks__pin_document"
READ = "mcp__paper_checks__read_pinned_document"
HANDLE = "source-" + "a" * 32


def call(identity, name, args):
    return {"type": "tool/call", "data": {"callId": identity, "name": name,
                                          "arguments": json.dumps(args)}}


def result(identity, value):
    return {"type": "tool/result", "data": {"message": {
        "source": {"kind": "tool", "callId": identity}, "content": [{
            "type": "tool-result", "isError": False, "content": [
                {"type": "text", "text": json.dumps(value)}
            ],
        }],
    }}}


def test_unknown_binding_and_context_replacement_are_not_evidence():
    replacement = result("pin", {"source_id": HANDLE})
    replacement["surfaceOp"] = "replace"
    events = [call("pin", PIN, {"name": "private", "sha256": "private"}),
              result("pin", {"source_id": "source-" + "b" * 32}), replacement,
              call("read", READ, {"source_id": HANDLE}), result("read", {})]
    sample = project(events, "paper-proofreading", "completed")
    assert sample["bindings"] == []
    assert sample["nodes"][1]["outcome"] == "missing_parameter_provenance"
    sample["nodes"][0]["arguments"] = {"name": "private"}
    with pytest.raises(ValidationError):
        SCHEMA.validate(sample)


def test_duplicate_results_fail_closed():
    events = [call("pin", PIN, {}), result("pin", {}), result("pin", {})]
    with pytest.raises(ValueError, match="invalid_tool_result"):
        project(events, "paper-proofreading", "completed")


def test_offline_import_requires_authorization_and_redacts_errors(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('private-marker-invalid-json\n', encoding="utf-8")
    args = [sys.executable, "-m", "src.adapters.rsi_learning_trace", "--input", str(path),
            "--scene", "paper-proofreading", "--status", "completed", "--start", "0"]
    unauthorized = subprocess.run(args, capture_output=True, check=False)
    assert unauthorized.returncode != 0 and not unauthorized.stdout
    rejected = subprocess.run([*args, "--authorized"], capture_output=True, check=False)
    assert rejected.returncode == 1 and not rejected.stdout
    assert rejected.stderr.strip() == b"rsi_learning_trace_rejected"
