"""Convert DSH's paired tool events into conservative motif-mining traces.

Only explicitly approved, read-only, successful calls enter contiguous mining
segments. Every other call is a barrier, so a motif cannot jump across an
unknown or failed action. Arguments remain in memory for later parameter-flow
compilation; callers must keep any persisted raw trace under ignored .local/.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from src.motif_core.offline.mining.trace_mining import (
    mine_traces as mine_dsh_traces,
    mine_witnessed_parameter_edges,
)
from src.motif_core.trajectory import ToolContract, ToolRecord
from src.motif_core.trajectory import Trace as DshTrace

from .dsh_event_projection import is_original_tool_result


HANDLE_PATTERN = re.compile(r"^(?:source|dataset|result|match)-[0-9a-f]{32}$")
OBJECT_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[A-Za-z0-9_]+$")
GMAIL_MESSAGE_ID_PATTERN = re.compile(r"^[0-9a-f]{16,32}$")
GMAIL_SEARCH = "mcp__scoped_gmail_request__search_emails"
GMAIL_READ = "mcp__scoped_gmail_request__read_email"
GMAIL_METADATA_MARKER = "SSS_STRUCTURED_METADATA_V1 "


def _field_value(value: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def infer_dsh_provenance(events: Iterable[Mapping[str, Any]],
                         approved_tools: Mapping[str, ToolContract]
                         ) -> dict[str, dict[str, dict[str, str]]]:
    """Witness exact opaque-handle flow from earlier successful tool results.

    Only prior result events may supply a parameter. A value returned by more
    than one call is ambiguous and is not inferred. Arbitrary equal text is not
    evidence of a dependency; only unpredictable handle-shaped IDs count.
    """
    call_names: dict[str, str] = {}
    producers: dict[str, tuple[str, str] | None] = {}
    inferred: dict[str, dict[str, dict[str, str]]] = {}
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event.get("type") == "tool/call":
            call_id, name = data.get("callId"), data.get("name")
            if not isinstance(call_id, str) or not isinstance(name, str):
                continue
            call_names[call_id] = name
            contract = approved_tools.get(name)
            if contract is None or not contract.provenance_params:
                continue
            try:
                arguments = json.loads(data.get("arguments", ""))
            except (TypeError, ValueError):
                continue
            if not isinstance(arguments, dict):
                continue
            for param in contract.provenance_params:
                value = arguments.get(param)
                if not isinstance(value, str) or not (
                    HANDLE_PATTERN.fullmatch(value) or
                    (param == "object_id" and OBJECT_ID_PATTERN.fullmatch(value)) or
                    (name == GMAIL_READ and param == "messageId" and
                     GMAIL_MESSAGE_ID_PATTERN.fullmatch(value))
                ):
                    continue
                producer = producers.get(value)
                if producer is not None:
                    inferred.setdefault(call_id, {})[param] = {
                        "from_call_id": producer[0], "from_field": producer[1]}
        elif is_original_tool_result(event):
            message = data.get("message")
            source = message.get("source") if isinstance(message, dict) else None
            call_id = source.get("callId") if isinstance(source, dict) else None
            name = call_names.get(call_id, "")
            contract = approved_tools.get(name)
            success, _, observation = _observation_digest(event, name)
            if not success or not isinstance(observation, dict) or contract is None:
                continue
            for field in contract.output_fields:
                value = _field_value(observation, field)
                if not isinstance(value, str) or not (
                    HANDLE_PATTERN.fullmatch(value) or OBJECT_ID_PATTERN.fullmatch(value) or
                    (name == GMAIL_SEARCH and field == "selected_message_id" and
                     observation.get("count") == 1 and
                     observation.get("message_ids") == [value] and
                     GMAIL_MESSAGE_ID_PATTERN.fullmatch(value))
                ):
                    continue
                if value in producers:
                    producers[value] = None
                else:
                    producers[value] = (call_id, field)
    return inferred

def _observation_digest(result: Mapping[str, Any], tool_name: str = ""
                        ) -> tuple[bool, str | None, dict[str, Any] | None]:
    data = result.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
        return False, None, None
    blocks = data["message"].get("content")
    if not isinstance(blocks, list) or not blocks:
        return False, None, None
    if result.get("data", {}).get("error"):
        return False, None, None
    if any(not isinstance(block, dict) or block.get("type") != "tool-result"
           or block.get("isError") is True for block in blocks):
        return False, None, None
    payload = json.dumps(blocks, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    observation = None
    if len(blocks) == 1:
        content = blocks[0].get("content")
        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
            item = content[0]
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                try:
                    text = item["text"]
                    if tool_name in (GMAIL_SEARCH, GMAIL_READ) and text.startswith(
                            GMAIL_METADATA_MARKER):
                        header, separator, original = text.partition("\n")
                        if (not separator or not original.startswith(
                                "<untrusted-tool-output>\n") or not original.rstrip().endswith(
                                "</untrusted-tool-output>")):
                            raise ValueError("invalid Gmail metadata envelope")
                        text = header[len(GMAIL_METADATA_MARKER):]
                    parsed = json.loads(text)
                    observation = parsed if isinstance(parsed, dict) else None
                except ValueError:
                    pass
    return True, hashlib.sha256(payload.encode()).hexdigest(), observation


def extract_dsh_trace(events: Iterable[Mapping[str, Any]],
                      approved_tools: Mapping[str, ToolContract], *, trace_id: str,
                      task_fingerprint: str | None = None,
                      provenance_by_call_id: Mapping[str, Mapping[str, Mapping[str, str]]]
                      | None = None) -> DshTrace:
    if not trace_id:
        raise ValueError("trace_id is required for motif provenance")
    calls: list[tuple[int, str, dict[str, Any]]] = []
    results: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for offset, event in enumerate(events):
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event.get("type") == "tool/call":
            call_id = data.get("callId")
            name = data.get("name")
            if isinstance(call_id, str) and call_id and isinstance(name, str) and name:
                raw_seq = event.get("seq", offset)
                seq = raw_seq if isinstance(raw_seq, int) else offset
                calls.append((seq, name, data))
        elif is_original_tool_result(event):
            message = data.get("message")
            source = message.get("source") if isinstance(message, dict) else None
            call_id = source.get("callId") if isinstance(source, dict) else None
            if isinstance(call_id, str) and call_id:
                raw_seq = event.get("seq", offset)
                seq = raw_seq if isinstance(raw_seq, int) else offset
                # A later context projection may have the same callId but is
                # not a new external observation. Keep the original result.
                results.setdefault(call_id, (seq, event))

    records: list[ToolRecord] = []
    eligible_by_call_id: dict[str, ToolRecord] = {}
    segments: list[tuple[str, ...]] = []
    current: list[str] = []
    for seq, name, call in calls:
        contract = approved_tools.get(name)
        arguments = None
        try:
            parsed = json.loads(call.get("arguments", ""))
            if isinstance(parsed, dict):
                arguments = parsed
        except (TypeError, ValueError):
            pass
        result_pair = results.get(call["callId"])
        result = result_pair[1] if result_pair is not None else None
        success, digest, observation = (_observation_digest(result, name)
                                        if result is not None else (False, None, None))
        if contract is None:
            reason = "unapproved_tool"
        elif not contract.read_only:
            reason = "effectful_tool"
        elif arguments is None:
            reason = "invalid_arguments"
        elif any((key not in arguments or
                  (arguments[key] in (None, "", []) and
                   not (dict(contract.parameter_shapes).get(key) == "string_list_allow_empty"
                        and arguments[key] == [])))
                 for key in contract.required_params):
            reason = "missing_required_parameter"
        elif not success:
            reason = "missing_or_failed_result"
        else:
            reason = "eligible_read"
        parameter_sources: dict[str, dict[str, str]] = {}
        declared = (provenance_by_call_id or {}).get(call["callId"], {})
        if not isinstance(declared, Mapping):
            reason = "invalid_parameter_provenance"
        elif reason == "eligible_read" and any(
                param not in declared for param in contract.provenance_params):
            reason = "missing_parameter_provenance"
        if declared and reason == "eligible_read":
            for param, source_ref in declared.items():
                if not isinstance(source_ref, Mapping):
                    reason = "invalid_parameter_provenance"
                    break
                source = eligible_by_call_id.get(source_ref.get("from_call_id", ""))
                field = source_ref.get("from_field", "")
                value: Any = source.observation if source else None
                if (source is None or not isinstance(param, str)
                        or param not in (arguments or {})
                        or not isinstance(field, str)
                        or field not in approved_tools[source.name].output_fields
                        or results.get(source_ref.get("from_call_id", ""), (seq,))[0] >= seq):
                    reason = "invalid_parameter_provenance"
                    break
                value = _field_value(value, field)
                target = arguments[param]
                matches = (type(value) is type(target) and value == target)
                if isinstance(value, list) and not matches:
                    matches = any(type(item) is type(target) and item == target
                                  for item in value)
                if not matches:
                    reason = "invalid_parameter_provenance"
                    break
                parameter_sources[param] = {"from_tool": source.name,
                                            "from_field": field}
        eligible = reason == "eligible_read"
        record = ToolRecord(name, arguments, digest, eligible, reason, seq,
                            observation if eligible else None,
                            parameter_sources if eligible and parameter_sources else None)
        records.append(record)
        if eligible:
            eligible_by_call_id[call["callId"]] = record
        if eligible:
            current.append(name)
        elif current:
            segments.append(tuple(current))
            current = []
    if current:
        segments.append(tuple(current))
    return DshTrace(trace_id, tuple(records), tuple(segments), task_fingerprint)
