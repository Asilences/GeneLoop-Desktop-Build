"""Conservative local spending gate for Web, File and research calls.

Reserves a peak-price upper bound before *every* upstream request, including
requests issued internally by Distil. A successful response with complete
provider usage settles that reservation at the peak-price token estimate;
otherwise the full reservation remains charged against the cap. It never logs
prompt bodies or credentials. Reconcile the provider bill afterwards.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if __package__:
    from .request_fingerprint import RequestFingerprints
    from .model_usage import normalize_usage, cost_evidence, UpstreamEvidence
    from .model_transport import MODEL_REQUEST_MAX_BYTES, MODEL_REQUEST_TOO_LARGE
    from .model_api import model_api_root, model_chat_path, model_wire_id, model_upstream_headers, model_price_rates
else:  # Preserve direct CLI execution from a different working directory.
    from request_fingerprint import RequestFingerprints
    from model_usage import normalize_usage, cost_evidence, UpstreamEvidence
    from model_transport import MODEL_REQUEST_MAX_BYTES, MODEL_REQUEST_TOO_LARGE
    from model_api import model_api_root, model_chat_path, model_wire_id, model_upstream_headers, model_price_rates


PEAK_USD_PER_MILLION = {
    "deepseek-flash": (0.30, 1.20),
    "deepseek-v4-pro": (1.32, 3.96),
    **model_price_rates()[0],
}
CACHE_HIT_PEAK_USD_PER_MILLION = {
    "deepseek-flash": 0.006,
    "deepseek-v4-pro": 0.044,
    **model_price_rates()[1],
}
HOP_HEADERS = {"host", "connection", "content-length", "transfer-encoding",
               "accept-encoding", "keep-alive", "proxy-connection"}
FILE_PATH = re.compile(r"^/v1/files(?:/[A-Za-z0-9_-]+)?$")

# Provider-owned defaults/capacities, verified 2026-10-15. These values are used
# only to reserve money; they are never injected into an uncapped request.
# https://api-docs.deepseek.com/api/create-chat-completion/
DEEPSEEK_OUTPUT_DEFAULTS = {'disabled': 8192, 'enabled': 65536, 'max': 131072}
# Z.AI documents a maximum, but no omitted-parameter default for these models:
# https://docs.z.ai/api-reference/llm/chat-completion
GLM_OUTPUT_CAPACITIES = {'glm-4.6': 131072, 'glm-4.7': 131072, 'glm-5': 131072,
                         'glm-5.1': 131072, 'glm-5.2': 131072, 'glm-5.3': 131072}


def normalize_output_limit(value: int | None) -> int | None:
    """JSON null / CLI zero removes the application cap, not provider capacity."""
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError('output limit must be a non-negative integer or null')
    return value or None


def output_limit_argument(value: str) -> int | None:
    return normalize_output_limit(int(value))


def provider_output_reservation(model: str, request: dict) -> int:
    """Reserve omitted output using documented provider behavior, never zero."""
    if model in PEAK_USD_PER_MILLION:
        thinking = request.get('thinking')
        disabled = (isinstance(thinking, dict) and thinking.get('type') == 'disabled')
        disabled = disabled or request.get('reasoning_effort') == 'none'
        mode = 'disabled' if disabled else 'max' if request.get('reasoning_effort') == 'max' else 'enabled'
        return DEEPSEEK_OUTPUT_DEFAULTS[mode]
    if model in GLM_OUTPUT_CAPACITIES:
        return GLM_OUTPUT_CAPACITIES[model]
    raise ValueError('provider output capacity is unknown for omitted max_tokens')


def _image_count(value: Any, *, file_profile: bool = False) -> int:
    if isinstance(value, dict):
        kind = value.get("type")
        image = (file_profile or isinstance(kind, str)) and kind in {"image_url", "input_image", "file", "image"}
        return int(image) + sum(_image_count(item, file_profile=file_profile) for item in value.values())
    if isinstance(value, list):
        return sum(_image_count(item, file_profile=file_profile) for item in value)
    return 0


def reservation(body: bytes, *, max_output: int | None,
                rates: dict[str, tuple[float, float]] | None = None) -> tuple[str, float, int]:
    return _reservation(body, max_output=max_output, rates=rates, file_profile=False)


def file_reservation(body: bytes, *, max_output: int | None,
                     rates: dict[str, tuple[float, float]] | None = None) -> tuple[str, float, int]:
    """Reserve for the File SDK's max_tokens request format."""
    return _reservation(body, max_output=max_output, rates=rates, file_profile=True)


def _reservation(body: bytes, *, max_output: int | None,
                 rates: dict[str, tuple[float, float]] | None, file_profile: bool) -> tuple[str, float, int]:
    request = json.loads(body)
    if not isinstance(request, dict):
        raise ValueError("request body must be an object")
    model = request.get("model")
    rates = PEAK_USD_PER_MILLION if rates is None else rates
    if model not in rates:
        raise ValueError("model is not in the approved peak-price table")
    if file_profile:
        output = request.get("max_tokens")
    else:
        output = request.get("max_tokens", request.get("max_completion_tokens"))
        if 'max_tokens' in request and 'max_completion_tokens' in request:
            raise ValueError('conflicting model output limit fields')
    max_output = normalize_output_limit(max_output)
    if output is None and max_output is None:
        output = provider_output_reservation(model, request)
    elif (type(output) is not int or output < 1 or
          (max_output is not None and output > max_output)):
        raise ValueError("max_tokens is missing or exceeds the per-request cap")
    # Every text token consumes at least one UTF-8 byte on the wire. Reserve an
    # additional 2,000 tokens for protocol/accounting differences and 1,024 for
    # each image reference; inline base64 is already covered by body bytes.
    input_ceiling = len(body) + 2_000 + 1_024 * _image_count(request, file_profile=file_profile)
    input_rate, output_rate = rates[model]
    dollars = (input_ceiling * input_rate + output * output_rate) / 1_000_000
    return model, dollars, input_ceiling


def response_usage(content_type: str, answer: bytes) -> dict[str, int]:
    """Extract only billable counters, including Distil's hidden requests."""
    payloads: list[dict[str, Any]] = []
    try:
        if "text/event-stream" in content_type:
            for line in answer.splitlines():
                if line.startswith(b"data:"):
                    data = line[5:].strip()
                    if data and data != b"[DONE]":
                        item = json.loads(data)
                        if isinstance(item, dict) and isinstance(item.get("usage"), dict):
                            payloads.append(item)
        else:
            item = json.loads(answer)
            if isinstance(item, dict) and isinstance(item.get("usage"), dict):
                payloads.append(item)
    except (ValueError, TypeError):
        return {}
    if not payloads:
        return {}
    return normalize_usage(payloads[-1]['usage'])


def observed_peak_cost(model: str, usage: dict[str, int], *,
                       rates: dict[str, tuple[float, float]] | None = None,
                       cache_rates: dict[str, float] | None = None) -> float:
    """Price a complete provider usage record without reading response content."""
    rates = PEAK_USD_PER_MILLION if rates is None else rates
    cache_rates = CACHE_HIT_PEAK_USD_PER_MILLION if cache_rates is None else cache_rates
    if model not in rates:
        raise ValueError("model is not in the approved peak-price table")
    required = ("prompt_tokens", "prompt_cache_hit_tokens",
                "prompt_cache_miss_tokens", "completion_tokens", "total_tokens")
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in required):
        raise ValueError("incomplete provider usage")
    if (usage["prompt_tokens"] != usage["prompt_cache_hit_tokens"]
            + usage["prompt_cache_miss_tokens"]
            or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
        raise ValueError("inconsistent provider usage")
    input_rate, output_rate = rates[model]
    return (usage["prompt_cache_miss_tokens"] * input_rate
            + usage["prompt_cache_hit_tokens"] * cache_rates.get(model, input_rate)
            + usage["completion_tokens"] * output_rate) / 1_000_000


def normalize_request_limit(value: int | None, name: str = 'request_limit') -> int | None:
    """None/JSON null and zero mean unlimited calls; dollar limits still apply."""
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a non-negative integer or null (0/null means unlimited)')
    return value or None


def request_limit_argument(value: str) -> int | None:
    """argparse converter: keep unlimited explicit in CLI configuration as 0."""
    return normalize_request_limit(int(value))


def validate_cost_cap(value: float | None) -> float | None:
    """Only null disables a State cost cap; a numeric zero still denies spending."""
    if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                              or not math.isfinite(value) or value < 0):
        raise ValueError('cost cap must be a finite non-negative number or null')
    return value


def cost_cap_argument(value: str) -> float | None:
    """CLI cumulative-cap convention: an explicit 0 means unlimited, recorded as null."""
    return validate_cost_cap(float(value)) or None


class State:
    _use_file_reservation = False

    def __init__(self, *, cap_usd: float | None, output_cap: int | None, record: Path,
                 request_limit: int | None = None,
                 rates: dict[str, tuple[float, float]] | None = None,
                 cache_rates: dict[str, float] | None = None,
                 checkpoint: Path | None = None):
        self.request_limit = normalize_request_limit(request_limit)
        self.cap_usd = validate_cost_cap(cap_usd)
        self.output_cap = normalize_output_limit(output_cap)
        self.record = record
        self.rates = PEAK_USD_PER_MILLION if rates is None else rates
        self.cache_rates = CACHE_HIT_PEAK_USD_PER_MILLION if cache_rates is None else cache_rates
        self.reserved_usd = 0.0
        self.request_count = 0
        self.pending: dict[int, float] = {}
        self.lock = threading.Lock()
        self.checkpoint_path = checkpoint
        if checkpoint is not None:
            value = json.loads(checkpoint.read_text(encoding='utf-8'))
            count, cost = value.get('request_count'), value.get('reserved_usd')
            if (type(count) is not int or count < 0 or
                    not isinstance(cost, (int, float)) or isinstance(cost, bool) or
                    not math.isfinite(cost) or cost < 0):
                raise ValueError('invalid cumulative budget checkpoint')
            # Unknown/in-flight usage remains charged after a restart.
            self.request_count, self.reserved_usd = count, float(cost)

    def checkpoint_locked(self) -> None:
        """Persist reservations before upstream I/O; caller holds this State lock."""
        if self.checkpoint_path is None:
            return
        temporary = self.checkpoint_path.with_suffix('.pending')
        raw = json.dumps({'request_count': self.request_count, 'reserved_usd': self.reserved_usd})
        with temporary.open('w', encoding='utf-8') as stream:
            os.chmod(temporary, 0o600)
            stream.write(raw + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.checkpoint_path)

    def book(self, body: bytes) -> tuple[int, str, float, int] | None:
        price_request = file_reservation if self._use_file_reservation else reservation
        model, dollars, ceiling = price_request(body, max_output=self.output_cap, rates=self.rates)
        with self.lock:
            if ((self.cap_usd is not None and self.reserved_usd + dollars > self.cap_usd) or
                    (self.request_limit is not None and self.request_count >= self.request_limit)):
                return None
            self.reserved_usd += dollars
            self.request_count += 1
            self.pending[self.request_count] = dollars
            self.checkpoint_locked()
            return self.request_count, model, dollars, ceiling

    def settle(self, request_id: int, model: str, status: int,
               usage: dict[str, int]) -> tuple[float | None, float]:
        """Release unused reservation only after a complete successful usage record."""
        with self.lock:
            reserved = self.pending.pop(request_id)
            if status != 200:
                return None, 0.0
            try:
                observed = observed_peak_cost(model, usage, rates=self.rates, cache_rates=self.cache_rates)
            except ValueError:
                return None, 0.0
            if observed > reserved:
                # The input ceiling was insufficient; account for the excess
                # and refuse future requests until the budget allows them.
                self.reserved_usd += observed - reserved
                self.checkpoint_locked()
                return observed, 0.0
            released = reserved - observed
            self.reserved_usd -= released
            self.checkpoint_locked()
            return observed, released

    def log(self, row: dict[str, Any]) -> None:
        self.record.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            with self.record.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
            os.chmod(self.record, 0o600)


class FileState(State):
    """File budget with a bounded retry allowance for one original task."""

    _use_file_reservation = True

    def __init__(self, **options):
        super().__init__(**options)
        self.provider_retries = 0

    def claim_provider_retry(self) -> int | bool:
        with self.lock:
            if self.provider_retries >= 2:
                return False
            self.provider_retries += 1
            return self.provider_retries


class StreamUsage:
    """Retain only one bounded SSE event and the final usage, never the whole answer."""
    def __init__(self, evidence=None):
        self.evidence = evidence
        self.pending = b''
        self.data: list[bytes] = []
        self.size = 0
        self.invalid = False
        self.usage: dict[str, int] = {}
        self.models: set[str] = set()

    def line(self, line: bytes) -> None:
        line = line.rstrip(b'\r')
        if not line:
            if self.data:
                raw = b'\n'.join(self.data)
                if raw != b'[DONE]':
                    try:
                        value = json.loads(raw)
                        if isinstance(value, dict):
                            model = value.get('model')
                            if isinstance(model, str) and re.fullmatch(r'[A-Za-z0-9._:/-]{1,200}', model) and len(self.models) < 8:
                                self.models.add(model)
                            if self.evidence is not None:
                                self.evidence.packet(value)
                            if value.get('usage') is not None:
                                self.usage = response_usage('application/json', raw)
                    except (ValueError, TypeError):
                        self.invalid = True
            self.data, self.size = [], 0
        elif line.startswith(b'data:'):
            data = line[5:]
            if data.startswith(b' '): data = data[1:]
            self.size += len(data)
            if self.size <= 1024 * 1024: self.data.append(data)
            else: self.invalid = True; self.data = []

    def feed(self, chunk: bytes) -> None:
        self.pending += chunk
        while b'\n' in self.pending:
            line, self.pending = self.pending.split(b'\n', 1)
            self.line(line)
        if len(self.pending) > 1024 * 1024:
            self.pending = b''
            self.invalid = True

    def finish(self) -> dict[str, int]:
        if self.pending: self.line(self.pending)
        self.line(b'')
        if self.evidence is not None:
            self.evidence.value['usage_parse_valid'] = not self.invalid
        return {} if self.invalid else self.usage


def create_server(host: str, port: int, upstream: str, state: State, *,
                  state_selector=None, allowed_models: set[str] | None = None,
                  chat_path: str | None = None, allow_files: bool = True,
                  gate_token: str | None = None,
                  omit_sdk_output_limit: bool = False, allow_search: bool = False,
                  allow_vision: bool = False) -> ThreadingHTTPServer:
    return _create_server(host, port, upstream, state, state_selector=state_selector,
                          allowed_models=allowed_models, chat_path=chat_path, allow_files=allow_files,
                          gate_token=gate_token, omit_sdk_output_limit=omit_sdk_output_limit,
                          allow_search=allow_search, allow_vision=allow_vision)


def create_file_server(host: str, port: int, upstream: str, state: FileState, *,
                       forward_headers=None, forward_model_alias: bool = True,
                       **options) -> ThreadingHTTPServer:
    """Use File SDK accounting and durable task settlement on the shared gateway."""
    return _create_server(host, port, upstream, state, file_profile=True, forward_headers=forward_headers,
                          forward_model_alias=forward_model_alias, **options)


def _create_server(host: str, port: int, upstream: str, state: State, *,
                   state_selector=None, allowed_models: set[str] | None = None,
                   chat_path: str | None = None, allow_files: bool = True,
                   gate_token: str | None = None, omit_sdk_output_limit: bool = False,
                   allow_search: bool = False, allow_vision: bool = False,
                   file_profile: bool = False, forward_headers=None,
                   forward_model_alias: bool = True) -> ThreadingHTTPServer:
    if omit_sdk_output_limit and state.output_cap is not None:
        raise ValueError('SDK output defaults can only be omitted with an uncapped output policy')
    chat_path = model_chat_path() if chat_path is None else chat_path
    # macOS can supply system proxies even with no *_PROXY environment variables.
    # Never send a local mock/loopback upstream through an external proxy.
    opener = (urllib.request.build_opener(urllib.request.ProxyHandler({}))
              if urlparse(upstream).hostname in {"127.0.0.1", "localhost", "::1"}
              else urllib.request.build_opener())
    fingerprints = None if file_profile else RequestFingerprints()
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            pass

        def _state(self):
            # Dynamic Web tasks route by the adapter's server-owned session header.
            # Legacy SDK/frozen callers keep their original single State.
            match = re.fullmatch(r'/v1/search/((?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32}))/messages', self.path) if allow_search else None
            if not match and allow_vision:
                match = re.fullmatch(r'/v1/vision/((?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32}))/chat/completions', self.path)
            headers = dict(self.headers)
            if match:
                headers = {k: v for k, v in headers.items() if k.lower() != 'x-deepseek-harness-session-id'}
                headers['x-deepseek-harness-session-id'] = match[1]
            return state_selector(headers) if state_selector else state

        def _reply(self, code: int, message: str, *, error_code: str | None = None) -> None:
            # Distinguish local quota denial from upstream rate limiting.
            error = {"code": error_code, "type": "invalid_request_error" if code == 413 else "quota_exceeded", "message": message} if error_code else message
            if code == 413 and error_code == MODEL_REQUEST_TOO_LARGE:
                error['max_bytes'] = MODEL_REQUEST_MAX_BYTES
            raw = json.dumps({"error": error}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            if code == 413:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/budget/health":
                self._reply(200, "ok")
            elif allow_files and FILE_PATH.match(self.path):
                self._forward_file(None, "GET")
            else:
                self._reply(403, "budget gate only forwards model requests")

        def do_DELETE(self) -> None:  # noqa: N802
            if allow_files and FILE_PATH.match(self.path):
                self._forward_file(None, "DELETE")
            else:
                self._reply(403, "unmetered endpoint refused")

        def _stream_upstream(self, response, content_type: str) -> bytes:
            # File jobs release the raw SSE body after durable settlement. Other
            # callers receive chunks as they arrive and settle before the terminator.
            deferred = self.defer_durable
            chunks: list[bytes] = []
            self.stream_started = not deferred
            self.stream_complete = False
            self.stream_bytes = 0
            self.stream_disconnected = False
            usage = StreamUsage(self.upstream_evidence)
            if self.stream_started:
                try:
                    self.send_response(response.status)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Accel-Buffering', 'no')
                    self.send_header('Transfer-Encoding', 'chunked')
                    self.end_headers()
                    self.wfile.flush()
                except OSError:
                    self.stream_disconnected = self.close_connection = True
            try:
                while True:
                    # read1() yields available bytes, including partial SSE events.
                    chunk = response.read1(16 * 1024)
                    if not chunk:
                        if response.length not in (None, 0):
                            raise EOFError('upstream stream ended before Content-Length')
                        break
                    self.stream_bytes += len(chunk)
                    usage.feed(chunk)
                    if deferred:
                        chunks.append(chunk)
                    elif not self.stream_disconnected:
                        try:
                            frame = f'{len(chunk):X}\r\n'.encode() + chunk + b'\r\n'
                            self.wfile.write(frame)
                            self.wfile.flush()
                        except OSError:
                            # Drain an already-billed call so usage can settle.
                            self.stream_disconnected = self.close_connection = True
            except Exception:
                if self.stream_started:
                    self.close_connection = True
                raise
            self.stream_complete = True
            if deferred:
                self.deferred_answer = b''.join(chunks)
                self.deferred_content_type = content_type
            metadata = {'usage': usage.finish()}
            if not file_profile:
                metadata['_response_models'] = sorted(usage.models)
            return json.dumps(metadata).encode()

        def _call_upstream(self, body: bytes | None, method: str, *, stream: bool = False) -> tuple[int, str, bytes]:
            self.provider_retry_after = None
            content_type = 'application/json'
            target_path = ('/anthropic/v1/messages' if allow_search and self.path.startswith('/v1/search/') else
                           chat_path if self.path == '/v1/chat/completions' or (allow_vision and self.path.startswith('/v1/vision/')) else self.path)
            self.upstream_evidence = UpstreamEvidence(body, upstream.rstrip('/') + target_path) if method == 'POST' and not FILE_PATH.match(self.path) else None
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in HOP_HEADERS | {'x-sss-model-gate-token'}
                       and not (stream and key.lower() == 'accept-encoding')}
            if stream:
                headers['Accept-Encoding'] = 'identity'
            if forward_headers is not None:
                headers = forward_headers(headers)
            try:
                headers = model_upstream_headers(upstream, headers)
            except ValueError:
                if self.upstream_evidence is not None:
                    self.upstream_evidence.value['outcome'] = 'credential_unavailable'
                return 503, 'application/json', b'{"error":"Kouri credential unavailable"}'
            request = urllib.request.Request(upstream.rstrip('/') + target_path, data=body,
                                             headers=headers, method=method)
            try:
                with opener.open(request, timeout=900) as response:
                    content_type = response.headers.get('Content-Type', 'application/json')
                    if self.upstream_evidence is not None:
                        self.upstream_evidence.headers(response.status, response.headers)
                    if stream and content_type.split(';', 1)[0].strip().lower() == 'text/event-stream':
                        answer = self._stream_upstream(response, content_type)
                        self.upstream_evidence.value['response_complete'] = True
                        return response.status, 'application/json', answer
                    answer = response.read()
                    if self.upstream_evidence is not None:
                        self.upstream_evidence.body(content_type, answer)
                        self.upstream_evidence.value['response_complete'] = True
                    return response.status, content_type, answer
            except urllib.error.HTTPError as exc:
                self.provider_retry_after = exc.headers.get('Retry-After')
                content_type = exc.headers.get('Content-Type', 'application/json')
                if self.upstream_evidence is not None:
                    self.upstream_evidence.headers(exc.code, exc.headers)
                try:
                    answer = exc.read()
                except Exception as error:
                    if self.upstream_evidence is not None:
                        self.upstream_evidence.transport_error(error, content_type)
                    return 502, 'application/json', b'{"error":"upstream unavailable"}'
                if self.upstream_evidence is not None:
                    self.upstream_evidence.body(content_type, answer)
                    self.upstream_evidence.value['response_complete'] = True
                return exc.code, content_type, answer
            except Exception as error:
                if self.upstream_evidence is not None:
                    self.upstream_evidence.transport_error(error, content_type)
                return 502, "application/json", b'{"error":"upstream unavailable"}'

        def _send_upstream(self, status: int, content_type: str, answer: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(answer)))
            retry_after = getattr(self, 'provider_retry_after', None)
            if isinstance(retry_after, str) and len(retry_after) <= 128 and not any(c in retry_after for c in '\r\n'):
                self.send_header('Retry-After', retry_after)
            self.end_headers()
            self.wfile.write(answer)

        def _forward_file(self, body: bytes | None, method: str) -> None:
            # DeepSeek's Files API is free; image tokens are reserved when the
            # resulting file_id is used in a model request.
            try:
                request_state = self._state()
            except (ValueError, PermissionError):
                self._reply(403, "model session is not approved")
                return
            started = time.monotonic()
            status, content_type, answer = self._call_upstream(body, method)
            request_state.log({"kind": "files_api", "method": method, "path": self.path,
                       "request_bytes": len(body or b""), "response_status": status,
                       "response_bytes": len(answer),
                       "elapsed_seconds": round(time.monotonic() - started, 3)})
            self._send_upstream(status, content_type, answer)

        def do_POST(self) -> None:  # noqa: N802
            file_upload = allow_files and self.path == "/v1/files"
            vision = allow_vision and (self.path == '/v1/vision/chat/completions' or
                re.fullmatch(r'/v1/vision/(?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32})/chat/completions',self.path) is not None)
            search = allow_search and (self.path == '/v1/search/messages' or
                re.fullmatch(r'/v1/search/(?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32})/messages', self.path) is not None)
            if self.path != "/v1/chat/completions" and not file_upload and not search and not vision:
                self._reply(403, "unmetered endpoint refused")
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._reply(400, "invalid request length")
                return
            maximum = 64 * 1024 * 1024 if file_upload else MODEL_REQUEST_MAX_BYTES
            if not 0 < length <= maximum:
                self._reply(413, "request body exceeds HTTP transport capacity",
                            error_code=None if file_upload else MODEL_REQUEST_TOO_LARGE)
                return
            body = self.rfile.read(length)
            if file_upload:
                self._forward_file(body, "POST")
                return
            try:
                if gate_token is not None and self.headers.get('X-SSS-Model-Gate-Token') != gate_token:
                    raise PermissionError('model gate token is invalid')
                request_state = self._state()
            except (ValueError, PermissionError):
                self._reply(403, "model session is not approved")
                return
            try:
                if vision:
                    payload = json.loads(body)
                    if (not isinstance(payload, dict) or set(payload) != {'model', 'messages', 'stream', 'thinking','response_format'} or
                            payload['model'] != 'deepseek-flash' or payload['stream'] is not False or
                            payload['response_format'] != {'type':'json_object'} or
                            payload['thinking'] != {'type': 'disabled'} or
                            not isinstance(payload['messages'], list) or len(payload['messages']) != 1 or
                            not isinstance(payload['messages'][0], dict) or
                            set(payload['messages'][0]) != {'role', 'content'} or payload['messages'][0]['role'] != 'user'):
                        raise ValueError('invalid PDF vision request')
                    parts = payload['messages'][0]['content']
                    if not isinstance(parts, list) or not parts or not all(isinstance(p, dict) for p in parts) or not any(p.get('type') == 'image_url' for p in parts):
                        raise ValueError('PDF vision requires page pixels')
                    for part in parts:
                        if not isinstance(part, dict): raise ValueError('invalid vision content')
                        if part.get('type') == 'text' and set(part) == {'type', 'text'} and isinstance(part['text'], str): continue
                        if (part.get('type') == 'image_url' and set(part) == {'type', 'image_url'} and
                                isinstance(part['image_url'], dict) and set(part['image_url']) == {'url'} and
                                isinstance(part['image_url']['url'], str) and
                                re.fullmatch(r'data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}', part['image_url']['url'])): continue
                        raise ValueError('only inline PDF page pixels allowed')
                if search:
                    payload = json.loads(body)
                    def search_text(content):
                        # Native provider versions use either a string or
                        # Anthropic text blocks for the same search query.
                        return isinstance(content, str) or (isinstance(content, list) and bool(content) and all(
                            isinstance(part, dict) and set(part) == {'type', 'text'} and
                            part['type'] == 'text' and isinstance(part['text'], str) for part in content))
                    if (not isinstance(payload, dict) or set(payload) != {'model', 'max_tokens', 'messages', 'tools'} or
                            not isinstance(payload['messages'], list) or len(payload['messages']) != 1 or
                            not isinstance(payload['messages'][0], dict) or
                            payload['messages'][0].get('role') != 'user' or
                            not search_text(payload['messages'][0].get('content')) or
                            not isinstance(payload['tools'], list) or len(payload['tools']) != 1 or
                            payload['tools'][0] != {'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': 3}):
                        raise ValueError('invalid native search request')
                if omit_sdk_output_limit:
                    # pi-ai supplies a model-capacity max_tokens even when the
                    # admitted call omits it. Let this provider choose its own
                    # default, and reserve against that exact outgoing request.
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError('request body must be an object')
                    payload.pop('max_tokens', None)
                    payload.pop('max_completion_tokens', None)
                    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                if allowed_models is not None and json.loads(body).get('model') not in allowed_models:
                    raise ValueError('model is outside this provider gate')
                booked = request_state.book_vision(body) if vision and hasattr(request_state, 'book_vision') else request_state.book(body)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                if file_profile and self._durable_job(request_state):
                    request_state.log({'kind': 'budget_denied', 'reason': 'invalid_model_request',
                                       'error_type': type(error).__name__, 'detail': str(error)[:300]})
                self._reply(400, "unpriced or unbounded model request refused")
                return
            if booked is None:
                request_state.log({'kind': 'budget_denied', 'reason': 'budget_or_request_limit'})
                self._reply(429, "approved research budget exhausted", error_code='GENELOOP_BUDGET_EXHAUSTED')
                return
            request_id, model, dollars, ceiling = booked
            # Retries reserve the admitted SDK model before its provider wire rewrite.
            admitted_body = body
            upstream_uses_wire_alias = upstream.rstrip('/') == model_api_root()
            if search or (forward_model_alias and upstream_uses_wire_alias):
                payload = json.loads(body) if not search else payload
                if upstream_uses_wire_alias:
                    payload['model'] = model_wire_id(model)
                elif forward_model_alias:
                    payload['model'] = 'deepseek-v4-flash' if model == 'deepseek-flash' else model
                body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            fingerprint = self._fingerprint(body)
            self.defer_durable = file_profile and self._durable_job(request_state)
            self.deferred_answer = None
            retry = 0
            while True:
                self.stream_started = False
                started = time.monotonic()
                request_started_utc_epoch = time.time()
                status, content_type, answer = self._call_upstream(body, "POST", stream=not search and not vision)
                usage = response_usage(content_type, answer)
                details = ({'provider_retry': retry, 'retry_scope': 'original_task_max_two'} if file_profile
                           else {'request_fingerprint': fingerprint, 'response_models': self._response_models(answer)})
                observed, released = request_state.settle(request_id, model, status, usage)
                accounting = getattr(request_state, 'state', request_state)
                request_state.log({
                    "request_id": request_id, "model": model,
                    **({'kind': 'web_search', 'search_pricing': 'model_tokens_only_service_fee_not_estimated'} if search else {}),
                    **({'kind': 'pdf_vision'} if vision else {}),
                    "reserved_upper_usd": round(dollars, 8),
                    "observed_peak_usd": round(observed, 8) if observed is not None else None,
                    "reservation_released_usd": round(released, 8),
                    "input_token_ceiling": ceiling, "response_status": status,
                    "response_bytes": self.stream_bytes if self.stream_started else len(answer),
                    "streamed": self.stream_started,
                    "downstream_disconnected": self.stream_disconnected if self.stream_started else False,
                    "response_usage": usage, "upstream_response": self.upstream_evidence.value,
                    "cost_evidence": cost_evidence(model, usage, accounting.rates, accounting.cache_rates),
                    "request_utc_epoch": round(time.time(), 3),
                    "request_started_utc_epoch": round(request_started_utc_epoch, 3),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    **details,
                })
                if (not file_profile or search or vision or self.stream_started or status not in (502, 503)
                        or (not self.defer_durable and json.loads(body).get('stream'))):
                    break
                retry = request_state.claim_provider_retry()
                if not retry:
                    break
                time.sleep(retry)
                booked = request_state.book(admitted_body)
                if booked is None:
                    request_state.log({'kind': 'budget_denied', 'reason': 'provider_retry_within_original_cap'})
                    self._reply(429, 'approved research budget exhausted', error_code='GENELOOP_BUDGET_EXHAUSTED')
                    return
                request_id, model, dollars, ceiling = booked
            if self.stream_started:
                if self.stream_complete and not self.stream_disconnected:
                    try:
                        self.wfile.write(b'0\r\n\r\n')
                        self.wfile.flush()
                    except OSError:
                        self.close_connection = True
            elif self.deferred_answer is not None:
                self._send_upstream(status, self.deferred_content_type, self.deferred_answer)
            else:
                self._send_upstream(status, content_type, answer)

        @staticmethod
        def _durable_job(request_state) -> bool:
            return bool(getattr(request_state, 'job_file', None) or getattr(request_state, 'path', None)
                        or getattr(request_state, 'job', None))

        def _fingerprint(self, body: bytes):
            if fingerprints is None:
                return None
            # Observe outbound bytes in the matching caller session.
            try:
                return fingerprints.observe(body, self.headers.get('x-deepseek-harness-session-id', ''))
            except Exception as error:
                return {'schema_version': 1, 'status': 'unavailable', 'error_type': type(error).__name__}

        def _response_models(self, answer: bytes) -> list[str]:
            try:
                metadata = json.loads(answer)
                models = metadata.get('_response_models', []) if self.stream_started else [metadata.get('model')]
                return [model for model in models if isinstance(model, str)
                        and re.fullmatch(r'[A-Za-z0-9._:/-]{1,200}', model)]
            except (ValueError, TypeError, AttributeError):
                return []

    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str, port: int, upstream: str, state: State, *, file_profile: bool = False) -> None:
    create = create_file_server if file_profile else create_server
    server = create(host, port, upstream, state)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=('general', 'file'), default='general')
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--upstream", default=model_api_root())
    parser.add_argument("--cap-usd", type=cost_cap_argument, required=True,
                        help="cumulative cost cap; 0 means unlimited with accounting retained")
    parser.add_argument("--max-output", type=output_limit_argument, default=None,
                        help="application output cap; 0/default omits it, provider capacity still applies")
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    if args.cap_usd is not None and args.cap_usd > 100:
        parser.error("invalid research budget")
    root = Path(__file__).resolve().parents[2]
    record = args.record.resolve()
    if not record.is_relative_to(root / ".local"):
        parser.error("private request ledger must be under .local")
    file_profile = args.profile == 'file'
    state_type = FileState if file_profile else State
    serve("127.0.0.1", args.port, args.upstream.rstrip("/"),
          state_type(cap_usd=args.cap_usd, output_cap=args.max_output, record=record),
          file_profile=file_profile)


if __name__ == "__main__":
    main()
