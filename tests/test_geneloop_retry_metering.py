"""Local HTTP diagnostics: every retry remains separately metered and attributed."""
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from src.adapters import deepseek_cost_gate
from src.adapters.web.web_task_budget import FileTaskBudgetRegistry, TaskBudgetRegistry


@pytest.fixture(params=[
    pytest.param((deepseek_cost_gate.State, deepseek_cost_gate.create_server, TaskBudgetRegistry), id='web'),
    pytest.param((deepseek_cost_gate.FileState, deepseek_cost_gate.create_file_server, FileTaskBudgetRegistry), id='file-sdk'),
])
def gateway(request):
    return request.param


def test_transient_attempts_keep_task_identity_unknown_usage_and_retry_after(tmp_path, gateway):
    state_type, create_server, registry_type = gateway
    calls = []
    statuses = [429, 503, 200]
    usage = {'prompt_tokens': 10, 'prompt_cache_hit_tokens': 0,
             'prompt_cache_miss_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers['Content-Length'])))
            status = statuses.pop(0)
            raw = json.dumps({'usage': usage} if status == 200 else {'error': {'message': 'transient provider failure'}}).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            if status != 200: self.send_header('Retry-After', '7')
            self.end_headers(); self.wfile.write(raw)

    run = state_type(cap_usd=None, output_cap=None, request_limit=None, record=tmp_path/'run.jsonl')
    registry = registry_type(run_state=run, tasks_root=tmp_path/'.local'/'tasks')
    registry.register('a'*32, 'retry-session', None)
    registry.activate('retry-session')
    # Use the public registry API, so each attempt must still belong to the
    # same active admitted task. No gate-internal generic retry is introduced.
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    proxy = create_server('127.0.0.1', 0, f'http://127.0.0.1:{upstream.server_port}', run,
                              state_selector=registry.state_for)
    threads = [threading.Thread(target=s.serve_forever, kwargs={'poll_interval': .01}, daemon=True) for s in (upstream, proxy)]
    for thread in threads: thread.start()
    body = json.dumps({'model':'deepseek-flash','max_tokens':20,'messages':[],'stream':True}).encode()
    try:
        for expected in [429, 503, 200]:
            request = urllib.request.Request(f'http://127.0.0.1:{proxy.server_port}/v1/chat/completions', data=body,
                headers={'Content-Type':'application/json', 'x-deepseek-harness-session-id':'retry-session'})
            try: response = urllib.request.urlopen(request, timeout=3)
            except urllib.error.HTTPError as error: response = error
            with response:
                assert response.status == expected
                assert response.headers.get('Retry-After') == ('7' if expected != 200 else None)
                response.read()
        rows = [json.loads(line) for line in run.record.read_text().splitlines()]
        assert run.request_count == len(calls) == 3
        assert registry.stats('retry-session')['upstream_requests'] == 3
        assert registry.stats('retry-session')['unknown_usage_requests'] == 2
        assert all(row['task_id'] == 'a'*32 and row['session_id'] == 'retry-session' for row in rows)
        assert [row['response_status'] for row in rows] == [429, 503, 200]
        assert all(row['observed_peak_usd'] is None and row['response_usage'] == {} and row['reservation_released_usd'] == 0 for row in rows[:2])
        assert run.reserved_usd >= sum(row['reserved_upper_usd'] for row in rows[:2])
        assert len(set(calls)) == 1
        assert rows[2]['response_usage'] == usage
        registry.cancel('retry-session')
        with pytest.raises(urllib.error.HTTPError) as cancelled:
            urllib.request.urlopen(request, timeout=3)
        with cancelled.value as response:
            assert response.code == 403
            response.read()
        assert run.request_count == len(calls) == 3
    finally:
        for server in (proxy, upstream): server.shutdown(); server.server_close()
        for thread in threads: thread.join(timeout=2)


def test_actual_budget_denial_is_structured_quota_without_dispatch(tmp_path, gateway):
    state_type, create_server, _ = gateway
    state = state_type(cap_usd=0, output_cap=None, record=tmp_path/'run.jsonl')
    proxy = create_server('127.0.0.1', 0, 'http://127.0.0.1:1', state)
    thread = threading.Thread(target=proxy.serve_forever, kwargs={'poll_interval':.01}, daemon=True); thread.start()
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{proxy.server_port}/v1/chat/completions',
            data=b'{"model":"deepseek-flash","max_tokens":20,"messages":[]}', headers={'Content-Type':'application/json'})
        with pytest.raises(urllib.error.HTTPError) as caught: urllib.request.urlopen(request, timeout=3)
        with caught.value as response:
            assert response.code == 429
            error = json.load(response)['error']
            assert error['code'] == 'GENELOOP_BUDGET_EXHAUSTED' and error['type'] == 'quota_exceeded'
        assert state.request_count == 0
    finally:
        proxy.shutdown(); proxy.server_close(); thread.join(timeout=2)
