import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from jsonschema import ValidationError

from src.adapters.rsi_learning_trace import SCHEMA, project

PIN = "mcp__paper_checks__pin_document"
READ = "mcp__paper_checks__read_pinned_document"
HANDLE = "source-" + "a" * 32
INTENT_CASES = json.loads(
    (Path(__file__).parent / "fixtures/rsi_task_intent.json").read_text(encoding="utf-8")
)


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


def instruction(text, **extra):
    return {"type": "user/message", "data": {"source": {"kind": "user"}, "content": [
        {"type": "text", "text": text},
        {"type": "image", "name": "private-image.png", "data": "private-image-bytes"},
    ]}, **extra}


@pytest.mark.skipif(not os.environ.get("SSS_RSI_GITLEAKS"), reason="requires isolated local privacy tools")
@pytest.mark.parametrize("case", INTENT_CASES, ids=[f"{case['scene']}-{i}" for i, case in enumerate(INTENT_CASES)])
def test_bilingual_task_intent_removes_private_spans_and_keeps_learning_signals(case):
    context = instruction("private plugin context")
    context["data"]["source"] = {"kind": "plugin"}
    events = [context, instruction("private replaced text", surfaceOp="replace"), instruction(case["text"]),
              instruction("private later instruction")]
    sample = project(events, case["scene"], "completed", include_task_intent=True)
    assert sample["format"].endswith("/v3")
    intent = sample.pop("task_intent")
    assert [span for span in case["private"] if span in intent] == []
    assert [span for span in case["keep"] if span not in intent] == []
    assert "private" not in intent
    if not case["private"]:
        assert intent == unicodedata.normalize("NFKC", case["text"])
    assert {**sample, "format": "geneloop.rsi-learning-trace/v2"} == project(events, case["scene"], "completed")


@pytest.mark.parametrize("scanner", ["missing", "real"])
def test_semantic_cli_rejects_unavailable_scanner_or_credential_without_leaking(tmp_path, scanner):
    path = tmp_path / "events.jsonl"
    fake_token = "ghp_" + "6K8vZ0Er91Ac4Jw2mHnX3Tp7bQdY5LfGkS8r"
    path.write_text(json.dumps(instruction(f"Review the slides {fake_token} gitleaks:allow")) + "\n",
                    encoding="utf-8")
    env = dict(os.environ)
    if scanner == "missing":
        env["SSS_RSI_GITLEAKS"] = str(tmp_path / "missing-gitleaks")
    elif not env.get("SSS_RSI_GITLEAKS"):
        pytest.skip("requires isolated local Gitleaks")
    args = [sys.executable, "-m", "src.adapters.rsi_learning_trace", "--input", str(path),
            "--scene", "ppt", "--status", "completed", "--start", "0", "--authorized"]
    structural = subprocess.run(args, capture_output=True, check=True, env=env)
    assert b"task_intent" not in structural.stdout
    rejected = subprocess.run([*args, "--include-task-intent"], capture_output=True, check=False, env=env)
    assert rejected.returncode == 1 and not rejected.stdout
    assert rejected.stderr.strip() == b"rsi_learning_trace_rejected"


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


def test_non_default_read_and_unknown_interleaving_do_not_become_safe_witnesses():
    from src.adapters.rsi_learning_trace import compilation_trace, CONTRACTS, ROOT
    from src.adapters.tool_contract_loader import parse_tool_contracts
    from src.motif_core.offline.edge_compiler import count_safe_edge_witnesses

    contracts = parse_tool_contracts(json.loads(
        (ROOT / CONTRACTS["paper-proofreading"]).read_text(encoding="utf-8")))
    events = [call("pin", PIN, {"name": "private", "sha256": "private"}),
              result("pin", {"source_id": HANDLE}),
              call("private-call", "private-tool", {"secret": "private"}),
              call("page-two", READ, {"source_id": HANDLE, "page": 2}), result("page-two", {}),
              call("page-one", READ, {"source_id": HANDLE}), result("page-one", {})]
    sample = project(events, "paper-proofreading", "completed")
    assert sample["nodes"][2]["outcome"] == "invalid_arguments"
    assert [row["to"] for row in sample["bindings"]] == [3]
    legacy = {**sample, "format": "geneloop.rsi-learning-trace/v1"}
    with pytest.raises(ValueError, match="invalid_learning_projection"):
        compilation_trace(legacy, contracts, scene="paper-proofreading", trace_id="t", fingerprint="t")
    semantic = {**sample, "format": "geneloop.rsi-learning-trace/v3", "task_intent": "Check citations"}
    SCHEMA.validate(semantic)
    with pytest.raises(ValueError, match="invalid_learning_projection"):
        compilation_trace(semantic, contracts, scene="paper-proofreading", trace_id="t", fingerprint="t")
    trace = compilation_trace(sample, contracts, scene="paper-proofreading", trace_id="t", fingerprint="t")
    edge = {"status": "candidate_only", "from_tool": PIN, "to_tool": READ, "from_field": "source_id", "to_param": "source_id"}
    assert count_safe_edge_witnesses(edge, trace, contracts) == 0
    assert "private" not in json.dumps(sample)
