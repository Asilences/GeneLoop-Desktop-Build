"""Records and contracts for normalized tool-call trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolContract:
    required_params: tuple[str, ...]
    read_only: bool
    output_fields: tuple[str, ...] = ()
    collection_params: tuple[str, ...] = ()
    description: str = ""
    provenance_params: tuple[str, ...] = ()
    parameter_shapes: tuple[tuple[str, str], ...] = ()
    default_params: tuple[tuple[str, Any], ...] = ()
    witness_default_only: tuple[str, ...] = ()
    replay_stable: bool = True
    observed_anchor: bool = False
    continuation_policy: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolRecord:
    name: str
    arguments: dict[str, Any] | None
    observation_sha256: str | None
    eligible: bool
    reason: str
    event_seq: int
    observation: dict[str, Any] | None = None
    parameter_sources: dict[str, dict[str, str]] | None = None


@dataclass(frozen=True)
class Trace:
    trace_id: str
    records: tuple[ToolRecord, ...]
    segments: tuple[tuple[str, ...], ...]
    task_fingerprint: str | None = None



@dataclass(frozen=True)
class ObservedCall:
    """A tool invocation with decoded arguments."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ObservedResult:
    """The successful original observation for an invocation."""

    call_id: str
    observation: dict[str, Any]
