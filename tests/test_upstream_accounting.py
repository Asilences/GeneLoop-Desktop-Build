"""Local HTTP and saved-counter diagnostics only; no provider/model requests."""
import http.client
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.adapters import deepseek_cost_gate
from src.adapters.web.web_task_budget import FileTaskBudgetRegistry, TaskBudgetRegistry
from src.adapters.model_usage import UpstreamEvidence, accounting_breakdown, summarize_receipts


USAGE = {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15,
         'prompt_tokens_details': {'cached_tokens': 8}, 'cost': '0.000082314'}


@contextmanager
def local_gateway(tmp_path, file_profile, mode, monkeypatch):
    received = []

    class Upstream(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_args):
            pass

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            if mode == 'transport_error':
                self.close_connection = True
                return
            usage = {**USAGE, 'total_tokens': 74} if mode == 'anomaly' else USAGE
            packet = {'id': 'chatcmpl-fixture', 'model': 'provider-declared-model', 'system_fingerprint': 'fp-fixture',
                      'choices': [{'message': {'content': 'PRIVATE ANSWER'}}], 'usage': usage}
            if mode == 'reset' and len(received) == 2:
                packet = {'choices': [{'message': {'content': 'SECOND PRIVATE ANSWER'}}]}
            sse = mode in ('sse', 'truncated', 'deferred')
            if sse:
                first = {key: value for key, value in packet.items() if key != 'usage'}
                raw = b'data: ' + json.dumps(first).encode() + b'\n\n'
                raw += b'data: ' + json.dumps({'usage': usage}).encode() + b'\n\ndata: [DONE]\n\n'
            else:
                raw = json.dumps(packet).encode()
            self.send_response(503 if mode in ('error', 'truncated_error') else 200)
            self.send_header('Content-Type', 'text/event-stream' if sse else 'application/json')
            if len(received) == 1:
                self.send_header('X-Request-ID', 'request-fixture-001')
            self.send_header('Set-Cookie', 'PRIVATE COOKIE')
            self.send_header('Authorization', 'Bearer PRIVATE RESPONSE AUTH')
            self.send_header('Content-Length', str(len(raw) + (1 if mode in ('truncated', 'truncated_error') else 0)))
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()
            if mode in ('truncated', 'truncated_error'):
                self.close_connection = True

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    origin = f'http://127.0.0.1:{upstream.server_port}'
    # Verify recording follows the actual wire alias, not just the SDK alias.
    monkeypatch.setattr(deepseek_cost_gate, 'model_api_root', lambda: origin)
    monkeypatch.setattr(deepseek_cost_gate, 'model_wire_id', lambda _model: 'requested-wire-model')
    state_type = deepseek_cost_gate.FileState if file_profile else deepseek_cost_gate.State
    create_server = deepseek_cost_gate.create_file_server if file_profile else deepseek_cost_gate.create_server
    state = state_type(cap_usd=None, output_cap=100, record=tmp_path / 'ledger.jsonl')
    if mode == 'deferred':
        state.path = tmp_path / 'original-durable-job'
    gate = create_server('127.0.0.1', 0, origin, state)
    servers = [upstream, gate]
    threads = [threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    client = http.client.HTTPConnection('127.0.0.1', gate.server_port, timeout=3)
    try:
        yield state, client, received
    finally:
        client.close()
        for server in reversed(servers):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


def call(client):
    client.request('POST', '/v1/chat/completions', json.dumps({'model': 'deepseek-flash', 'max_tokens': 100,
                   'stream': True, 'messages': [{'role': 'user', 'content': 'PRIVATE INPUT'}]}),
                   {'Content-Type': 'application/json', 'Authorization': 'Bearer PRIVATE KEY'})
    return client.getresponse()


@pytest.mark.parametrize('file_profile', [False, True], ids=['web', 'file-sdk'])
@pytest.mark.parametrize('mode', ['json', 'sse', 'anomaly', 'error', 'truncated'])
def test_gateway_records_actual_wire_model_and_separate_upstream_cost_without_changing_guard(tmp_path, monkeypatch, file_profile, mode):
    with local_gateway(tmp_path, file_profile, mode, monkeypatch) as (state, client, received):
        response = call(client)
        assert response.status == (503 if mode == 'error' else 200)
        if mode == 'truncated':
            with pytest.raises(http.client.IncompleteRead):
                response.read()
        else:
            answer = response.read()
            assert b'PRIVATE ANSWER' in answer
        # Server commits the receipt before finishing a normal stream, but JSON
        # replies are also read only after the receipt was committed.
        rows = [json.loads(line) for line in state.record.read_text().splitlines()]
        assert len(received) == len(rows) == state.request_count == 1
        row = rows[0]
        assert row['request_started_utc_epoch'] <= row['request_utc_epoch']
        upstream = row['upstream_response']
        assert received[0]['model'] == upstream['requested_model'] == 'requested-wire-model'
        assert upstream['response_model'] == 'provider-declared-model'
        assert upstream['response_id'] == 'chatcmpl-fixture'
        assert upstream['system_fingerprint'] == 'fp-fixture'
        assert upstream['request_ids'] == {'x-request-id': 'request-fixture-001'}
        assert upstream['raw_usage']['prompt_tokens_details'] == {'cached_tokens': 8}
        assert upstream['raw_usage']['cost'] == '0.000082314'
        assert upstream['reported_cost']['amount'] == '0.000082314'
        assert upstream['reported_cost']['currency'] == upstream['reported_cost']['unit'] == 'unknown'
        assert upstream['response_complete'] == (mode != 'truncated')
        if mode == 'truncated':
            assert upstream['http_status'] == 200 and row['response_status'] == 502
            assert upstream['outcome'] == 'transport_error'
            assert upstream['transport_error_type'] in ('EOFError', 'IncompleteRead')
        if mode in ('anomaly', 'error', 'truncated'):
            assert row['observed_peak_usd'] is None
            assert state.reserved_usd == pytest.approx(row['reserved_upper_usd'], abs=1e-8)
        else:
            assert row['observed_peak_usd'] is not None
        raw = state.record.read_text()
        assert all(private not in raw for private in ('PRIVATE', 'choices', 'Set-Cookie', 'Bearer'))
        summary = summarize_receipts(rows, state.rates, state.cache_rates)
        separated = accounting_breakdown(state.reserved_usd, summary)
        assert separated['budget_reservation']['amount'] == state.reserved_usd
        assert separated['configured_estimate']['amount'] == summary['reported_component_proxy_usd']
        assert separated['upstream_reported']['unit_unknown_requests'] == 1
        assert separated['upstream_reported']['totals_by_currency_and_unit'] == []
        assert separated['invoice_usd'] is None


def test_file_durable_stream_keeps_upstream_metadata_before_returning_answer(tmp_path, monkeypatch):
    with local_gateway(tmp_path, True, 'deferred', monkeypatch) as (state, client, _):
        response = call(client)
        assert b'PRIVATE ANSWER' in response.read()
        row = json.loads(state.record.read_text())
        assert row['upstream_response']['response_complete']
        assert row['upstream_response']['raw_usage']['cost'] == USAGE['cost']
        assert row['observed_peak_usd'] is not None


@pytest.mark.parametrize('file_profile', [False, True], ids=['web', 'file-sdk'])
def test_transport_error_is_distinguished_from_provider_http_error_without_logging_error_text(tmp_path, monkeypatch, file_profile):
    with local_gateway(tmp_path, file_profile, 'transport_error', monkeypatch) as (state, client, received):
        response = call(client)
        assert response.status == 502
        assert json.loads(response.read()) == {'error': 'upstream unavailable'}
        row = json.loads(state.record.read_text())
        assert len(received) == 1
        assert row['upstream_response']['outcome'] == 'transport_error'
        assert row['upstream_response']['http_status'] is None
        assert row['upstream_response']['transport_error_type'] == 'RemoteDisconnected'
        assert row['upstream_response']['reported_cost']['amount'] is None
        assert row['observed_peak_usd'] is None


@pytest.mark.parametrize('file_profile', [False, True], ids=['web', 'file-sdk'])
def test_truncated_http_error_retains_partial_metadata_but_not_settlement(tmp_path, monkeypatch, file_profile):
    with local_gateway(tmp_path, file_profile, 'truncated_error', monkeypatch) as (state, client, _):
        response = call(client)
        assert response.status == 502
        response.read()
        row = json.loads(state.record.read_text())
        assert row['upstream_response']['http_status'] == 503
        assert row['upstream_response']['outcome'] == 'transport_error'
        assert not row['upstream_response']['response_complete']
        assert row['upstream_response']['raw_usage']['cost'] == USAGE['cost']
        assert row['observed_peak_usd'] is None


@pytest.mark.parametrize('file_profile', [False, True], ids=['web', 'file-sdk'])
def test_keepalive_second_response_does_not_inherit_previous_identity_or_cost(tmp_path, monkeypatch, file_profile):
    with local_gateway(tmp_path, file_profile, 'reset', monkeypatch) as (state, client, _):
        call(client).read()
        call(client).read()
        rows = [json.loads(line) for line in state.record.read_text().splitlines()]
        second = rows[1]['upstream_response']
        assert second['response_model'] is second['response_id'] is second['raw_usage'] is None
        assert second['request_ids'] == {}
        assert second['reported_cost']['amount'] is None
        summary = summarize_receipts(rows, state.rates, state.cache_rates)
        assert summary['upstream_reported_costs']['reported_cost_requests'] == 1
        assert summary['upstream_reported_costs']['missing_cost_requests'] == 1


def test_projection_is_bounded_and_preserves_original_anomalous_usage_not_arbitrary_text():
    evidence = UpstreamEvidence(b'{"model":"requested"}', 'https://user:PRIVATE@example.test/v1/chat/completions?key=PRIVATE')
    evidence.headers(200, {'x-request-id': 'bad\nPRIVATE'})
    evidence.packet({'model': 'declared', 'id': 'fixture', 'usage': {**USAGE, 'total_tokens': 74,
                    'prompt_tokens_details': {'cached_tokens': 8, 'private': 'PRIVATE'},
                    'authorization': 'PRIVATE', 'cost_details': {f'k_{i}': i for i in range(1000)}}})
    raw = evidence.value['raw_usage']
    assert raw['total_tokens'] == 74 and raw['cost'] == USAGE['cost']
    assert evidence.value['raw_usage_status'] == 'filtered'
    assert evidence.value['omitted_usage_fields'] > 0
    assert len(json.dumps(evidence.value)) < 8192
    assert 'PRIVATE' not in json.dumps(evidence.value)


def test_only_explicit_equal_currency_and_unit_can_be_summed_and_never_becomes_invoice():
    rows = []
    for cost in ({'amount': '0.1', 'currency': 'USD', 'unit': 'currency'},
                 {'amount': '0.2', 'currency': 'USD', 'unit': 'currency'},
                 {'amount': 1, 'currency': 'USD', 'unit': 'credits'}, '0.3'):
        evidence = UpstreamEvidence(b'{}', 'https://example.test/v1/chat/completions')
        evidence.packet({'usage': {'cost': cost}})
        evidence.value['response_complete'] = True
        rows.append({'upstream_response': evidence.value, 'response_status': 502})
    summary = summarize_receipts(rows, {}, {})['upstream_reported_costs']
    assert summary['unit_unknown_requests'] == 1
    assert summary['totals_by_currency_and_unit'] == [
        {'currency': 'USD', 'unit': 'credits', 'amount': '1', 'requests': 1},
        {'currency': 'USD', 'unit': 'currency', 'amount': '0.3', 'requests': 2}]
    assert summary['invoice_usd'] is None


def test_legacy_records_and_zero_amount_are_not_confused_with_unknown_cost():
    evidence = UpstreamEvidence(b'{}', 'https://example.test/v1/chat/completions')
    evidence.packet({'usage': {'cost': 0}})
    summary = summarize_receipts([{}, {'upstream_response': evidence.value}], {}, {})['upstream_reported_costs']
    assert summary['missing_cost_requests'] == summary['reported_cost_requests'] == 1
    assert evidence.value['reported_cost']['amount'] == 0
    assert summary['invoice_usd'] is None


def test_invalid_currency_and_unit_never_authorize_cost_aggregation():
    evidence = UpstreamEvidence(b'{}', 'https://example.test/v1/chat/completions')
    evidence.packet({'usage': {'cost': 2, 'currency': 3, 'unit': 4, 'total_tokens': 10**500}})
    assert evidence.value['reported_cost']['currency'] == evidence.value['reported_cost']['unit'] == 'unknown'
    assert evidence.value['raw_usage_status'] == 'filtered'


@pytest.mark.parametrize('state_type,registry_type', [
    pytest.param(deepseek_cost_gate.State, TaskBudgetRegistry, id='web'),
    pytest.param(deepseek_cost_gate.FileState, FileTaskBudgetRegistry, id='file-sdk'),
])
def test_task_stats_keep_three_accounting_domains_separate_and_preserve_legacy_alias(tmp_path, state_type, registry_type):
    root = tmp_path / '.local'
    state = state_type(cap_usd=None, output_cap=100, record=root / 'run.jsonl')
    registry = registry_type(run_state=state, tasks_root=root / 'tasks', task_request_limit=None)
    registry.register('a'*32, 'owned', None)
    registry.activate('owned')
    route = registry.state_for({'x-deepseek-harness-session-id': 'owned'})
    body = b'{"model":"deepseek-flash","max_tokens":100,"messages":[]}'
    booked = route.book(body)
    usage = deepseek_cost_gate.response_usage('application/json', json.dumps({'usage': USAGE}).encode())
    observed, _ = route.settle(booked[0], booked[1], 200, usage)
    evidence = UpstreamEvidence(body, 'https://example.test/v1/chat/completions')
    evidence.packet({'usage': USAGE})
    evidence.value['response_complete'] = True
    route.log({'request_id': booked[0], 'model': booked[1], 'response_status': 200,
               'response_usage': usage, 'observed_peak_usd': observed, 'upstream_response': evidence.value})
    stats = registry.stats('owned')
    accounting = stats['cost_accounting']
    assert stats['estimated_cost_usd'] == stats['budget_reserved_usd'] == accounting['budget_reservation']['amount']
    assert stats['estimated_cost_usd_semantics'].endswith('_not_spend')
    assert accounting['configured_estimate']['amount'] == pytest.approx(observed)
    assert accounting['upstream_reported']['unit_unknown_requests'] == 1
    assert accounting['upstream_reported']['totals_by_currency_and_unit'] == []
    assert accounting['invoice_usd'] is None
