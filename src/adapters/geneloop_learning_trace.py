"""Scene-independent native task projection; private evidence is never rewritten."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import stat
from jsonschema import Draft202012Validator

from .dsh_event_projection import is_original_tool_result
from .geneloop_privacy import MAX_BYTES, PrivacyRejected, admit_publication, learning_view

SCENE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/-]{0,255}$")
MAX_EVENTS = 20_000


def private_json(path):
    path = Path(path)
    if not stat.S_ISREG(path.lstat().st_mode) or path.absolute() != path.resolve():
        raise PrivacyRejected()
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise PrivacyRejected()
    return raw


def _content(parts):
    if not isinstance(parts, list):
        raise PrivacyRejected()
    output = []
    for part in parts:
        if not isinstance(part, dict):
            raise PrivacyRejected()
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            text = part["text"]
            try:
                text = json.loads(text)
            except ValueError:
                pass
            output.append(text)
        elif part.get("type") not in ("tool-call", "tool-result"):
            output.append({"content_omitted": "binary_or_unsupported"})
    return output


def project(events, scene, status, allowed_tools, *, semantic=True):
    if (not SCENE.fullmatch(scene) or status not in ("completed", "failed", "cancelled", "interrupted", "budget_exhausted")
            or not isinstance(events, list) or len(events) > MAX_EVENTS
            or not isinstance(allowed_tools, list) or any(not isinstance(tool, str) or not TOOL.fullmatch(tool)
                                                       for tool in allowed_tools)):
        raise PrivacyRejected()
    approved, calls, results, material = set(allowed_tools), {}, {}, []
    for event in events:
        if not isinstance(event, dict) or event.get("ptc_analysis_source"):
            raise PrivacyRejected()
        data = event.get("data", {})
        if not isinstance(data, dict):
            raise PrivacyRejected()
        kind = event.get("type")
        if kind == "tool/call":
            call, name = data.get("callId"), data.get("name")
            if not isinstance(call, str) or not call or call in calls or not isinstance(name, str):
                raise PrivacyRejected()
            node = len(calls)
            calls[call] = (node, name if name in approved else None)
            if semantic:
                arguments = json.loads(data.get("arguments", "null"))
                material.append({"type": "tool/call", "node": node, "value": arguments})
        elif is_original_tool_result(event):
            message = data.get("message", {})
            call = message.get("source", {}).get("callId")
            if call not in calls or call in results:
                raise PrivacyRejected()
            parts = message.get("content", [])
            blocks = [part for part in parts if isinstance(part, dict) and part.get("type") == "tool-result"]
            if len(blocks) != 1 or blocks[0].get("toolCallId") != call:
                raise PrivacyRejected()
            results[call] = blocks[0].get("isError") is not True
            if semantic:
                material.append({"type": "tool/result", "node": calls[call][0],
                                 "value": _content(blocks[0].get("content", []))})
        elif semantic and kind in ("user/message", "assistant/message"):
            operation=event.get("surfaceOp")
            if not (operation in (None, "append") or isinstance(operation,dict) and operation.get('op')=='append'):
                continue
            message = data.get("message", data)
            source=message.get('source',data.get('source',{}))
            role='user' if source.get('kind')=='user' else 'model' if source.get('kind')=='model' else 'system'
            material.append({"type": kind, "node": None, "role":role, "value": _content(message.get("content", []))})
    nodes = [{"tool": name, "outcome": "unapproved_tool" if name is None else
              "observed_success" if results.get(call) else "missing_or_failed_result"}
             for call, (_, name) in calls.items()]
    result = {"format": "geneloop.rsi-learning-trace/v4", "scene": scene, "status": status,
              "nodes": nodes, "bindings": []}
    if semantic:
        # All content and field keys use one engine; names/paths are not left
        # untouched in assistant replies, nested tool arguments or observations.
        result["content"] = material
        return learning_view(result)
    return result


def sharing_object(sample, allowed_tools):
    fields = {"format", "scene", "status", "nodes", "bindings"}
    if (not isinstance(sample, dict) or set(sample) != fields
            or sample.get("format") != "geneloop.rsi-learning-trace/v4"
            or sample.get("status") != "completed" or not isinstance(sample.get('scene'),str)
            or not SCENE.fullmatch(sample["scene"]) or not isinstance(allowed_tools,list)
            or sample.get("bindings") != [] or not isinstance(sample.get("nodes"), list)
            or not 0 < len(sample["nodes"]) <= MAX_EVENTS):
        raise PrivacyRejected()
    for node in sample["nodes"]:
        if (not isinstance(node, dict) or set(node) != {"tool", "outcome"}
                or node["tool"] is not None and node["tool"] not in allowed_tools
                or node["outcome"] not in ("observed_success", "unapproved_tool", "missing_or_failed_result")
                or (node["tool"] is None) != (node["outcome"] == "unapproved_tool")):
            raise PrivacyRejected()
    # Custom scene/MCP identifiers can themselves disclose a person's name or
    # an internal service. Public topology uses sample-local IDs for every scene.
    aliases={}
    nodes=[]
    for node in sample['nodes']:
        tool=node['tool']
        if tool is not None:
            if tool not in aliases:aliases[tool]='tool-'+str(len(aliases))
            tool=aliases[tool]
        nodes.append({'tool':tool,'outcome':node['outcome']})
    public={**sample,'scene':'generic','nodes':nodes}
    value = {"format": "geneloop.rsi-shared-object/v1", "kind": "tool_flow", "trace": public}
    schema=Path(__file__).resolve().parents[2]/'schemas/rsi-shared-tool-flow.schema.json'
    Draft202012Validator(json.loads(schema.read_text(encoding='utf-8'))).validate(value)
    return admit_publication(value)


def import_trace(path, scene, status, start, allowed_tools, *, semantic=True):
    lines = private_json(path).splitlines()
    if type(start) is not int or not 0 <= start <= len(lines):
        raise PrivacyRejected()
    events = [json.loads(line) for line in lines[start:] if line.strip()]
    return project(events, scene, status, allowed_tools, semantic=semantic)


def capture_run(output, scene, status, allowed_tools, start=0):
    """Offline/SDK admission uses exactly the same projector as the Web hosts."""
    output = Path(output)
    try:
        view = import_trace(output / "agent-events.jsonl", scene, status, start, allowed_tools)
        target = output / "privacy-learning.json"
        with target.open("x", encoding="utf-8") as stream:
            target.chmod(0o600)
            json.dump(view, stream, ensure_ascii=False, allow_nan=False)
        return True
    except Exception:
        marker = output / "privacy-learning-rejected"
        with marker.open("a"):
            marker.chmod(0o600)
        return False


def capture_native_events(output, events, *, session_id, status):
    """SDK observer admission. The private source index grants no execution authority."""
    import hashlib
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    try:
        tools = list(dict.fromkeys(event['data']['name'] for event in events
                                  if event.get('type') == 'tool/call'))
        view = project(events, 'sdk', status, tools)
        (output/'privacy-learning.json').write_text(json.dumps(view,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        (output/'privacy-learning.json').chmod(0o600)
        source = {'session_id':session_id,'events_sha256':hashlib.sha256(
            json.dumps(events,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'scope':'native_invocation','execution_witness':False}
        (output/'source-private.json').write_text(json.dumps(source),encoding='utf-8')
        (output/'source-private.json').chmod(0o600)
        return True
    except Exception:
        (output/'privacy-learning-rejected').touch(mode=0o600)
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized", action="store_true", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--share-object", action="store_true")
    args = parser.parse_args()
    try:
        catalog = json.loads(private_json(args.catalog))
        allowed = list(dict.fromkeys([*catalog.get("allowed_tools", []),
            *[tool["name"] for tool in catalog.get("tools", []) if isinstance(tool, dict) and "name" in tool]]))
        result = import_trace(args.input, args.scene, args.status, args.start, allowed,
                              semantic=not args.share_object)
        if args.share_object:
            # A failed semantic/credential check closes the source as well;
            # structure sharing is not a fallback around failed admission.
            import_trace(args.input, args.scene, args.status, args.start, allowed, semantic=True)
            result = sharing_object(result, allowed)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    except Exception:
        parser.exit(1, "geneloop_privacy_rejected\n")


if __name__ == "__main__":
    main()
