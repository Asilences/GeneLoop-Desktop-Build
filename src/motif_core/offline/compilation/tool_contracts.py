"""Read tool contracts and bind descriptive MCP schemas during compilation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from src.motif_core.trajectory.model import ToolContract
from .continuation_policy import policy_digest, validate_policy


def _pairs(spec: dict[str, Any], field: str) -> tuple[tuple[str, Any], ...]:
    raw = spec.get(field, [])
    if (not isinstance(raw, list)
            or any(not isinstance(row, list) or len(row) != 2
                   or not isinstance(row[0], str) or not row[0]
                   for row in raw)
            or len({row[0] for row in raw}) != len(raw)):
        raise ValueError(f"invalid {field} in approved tool contract")
    return tuple((row[0], row[1]) for row in raw)


def parse_tool_contracts(rows: dict[str, Any]) -> dict[str, ToolContract]:
    if not isinstance(rows, dict) or not rows:
        raise ValueError("manifest needs approved tool contracts")
    result = {}
    for name, spec in rows.items():
        if (not isinstance(name, str) or not name
                or not isinstance(spec, dict)
                or not isinstance(spec.get("required_params"), list)
                or not isinstance(spec.get("output_fields", []), list)
                or not isinstance(spec.get("provenance_params", []), list)
                or not isinstance(spec.get("collection_params", []), list)
                or not isinstance(spec.get("witness_default_only", []), list)
                or not isinstance(spec.get("description", ""), str)
                or type(spec.get("replay_stable")) is not bool
                or type(spec.get("observed_anchor", False)) is not bool
                or (spec.get("observed_anchor", False) and spec["replay_stable"])):
            raise ValueError("invalid approved tool contract")
        shapes = _pairs(spec, "parameter_shapes")
        defaults = _pairs(spec, "default_params")
        default_only = spec.get("witness_default_only", [])
        if (any(value not in {"string_list_allow_empty", "measure_list", "time_window_list"}
                for _, value in shapes)
                or not {key for key, _ in shapes} <= set(spec["required_params"])
                or not {key for key, _ in defaults}.isdisjoint(spec["required_params"])
                or any(not isinstance(key, str) or not key for key in default_only)
                or len(set(default_only)) != len(default_only)
                or not set(default_only) <= {key for key, _ in defaults}):
            raise ValueError("invalid parameter shape or default in approved tool contract")
        policy = spec.get("continuation_policy")
        if policy is not None:
            validate_policy(policy)
            step = next((s for s in policy['steps'] if s['tool'] == name), None)
            if (step is None or spec.get('read_only') is not True or not spec['replay_stable']
                    or spec['required_params'] != [step['param']] or defaults or shapes
                    or step['receipt_field'] not in spec.get('output_fields', [])):
                raise ValueError('continuation policy conflicts with tool contract')
        result[name] = ToolContract(
            tuple(spec["required_params"]), spec.get("read_only") is True,
            tuple(spec.get("output_fields", [])),
            tuple(spec.get("collection_params", [])),
            spec.get("description", ""),
            tuple(spec.get("provenance_params", [])), shapes, defaults,
            tuple(default_only), spec["replay_stable"],
            spec.get("observed_anchor", False), policy)
    return result


def bind_mcp_descriptions(
    contracts: Mapping[str, ToolContract], tools_result: Any,
) -> dict[str, ToolContract]:
    rows = tools_result.get("tools") if isinstance(tools_result, dict) else tools_result
    if not isinstance(rows, list):
        raise ValueError("MCP tool schema must contain a tools list")
    by_name: dict[str, dict] = {}
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name or name in by_name:
            raise ValueError("MCP tool names are missing or repeated")
        by_name[name] = row
    updated = {}
    for name, contract in contracts.items():
        schema = by_name.get(name)
        if schema is None:
            raise ValueError(f"approved tool missing from MCP schema: {name}")
        description = schema.get("description")
        parameters = schema.get("inputSchema")
        if (not isinstance(description, str)
                or not 1 <= len(description.strip()) <= 160
                or not isinstance(parameters, dict)
                or parameters.get("type") != "object"
                or not isinstance(parameters.get("properties"), dict)
                or not isinstance(parameters.get("required", []), list)
                or any(not isinstance(key, str) for key in parameters.get("required", []))
                or set(parameters.get("required", [])) != set(contract.required_params)
                or not set(contract.required_params) <= set(parameters["properties"])):
            raise ValueError(f"MCP schema does not match approved tool: {name}")
        if contract.continuation_policy:
            step = next(s for s in contract.continuation_policy['steps'] if s['tool'] == name)
            if policy_digest(parameters) != step['input_schema_sha256']:
                raise ValueError(f'continuation schema changed: {name}')
        updated[name] = replace(contract, description=description.strip())
    return updated
