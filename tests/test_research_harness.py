"""Local MCP and injected-Harness diagnostics. No external/model API calls."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import anyio
import pytest

from src.adapters import research_harness as research


TOOLS = [{'name': 'read_skill', 'description': 'Read a selected skill resource.',
          'parameters': {'type': 'object', 'properties': {
              'node_id': {'type': 'string'}, 'resource': {'type': 'string'}},
              'required': ['node_id', 'resource'], 'additionalProperties': False}}]


def request(prompt='Diagnostic task'):
    return {'mode': 'iteration', 'prompt': prompt, 'tools': TOOLS,
            'available_skill_cards': [{'name': 'diagnostic-skill', 'description': 'Synthetic procedure',
                                       'path': '/diagnostic/skill'}],
            'initial_context': {'observations': 2}}


class Gate:
    def __init__(self, current):
        self.current = current
        self.directories = []
        self.provider_requests = 2

    def environment(self):
        return {'DEEPSEEK_API_KEY': 'diagnostic-no-external-provider'}

    def costs(self, directory):
        assert self.current == directory
        self.directories.append(directory)
        return {'provider_requests': self.provider_requests,
                'request_ids': [31, 32] if self.provider_requests else [],
                'observed_model_usd_decimal': None, 'billing_usd': None}


@pytest.fixture
def injected(monkeypatch, tmp_path):
    """Keep session logic real while injecting transport callbacks only."""
    stack = []
    observed = {'factories': [], 'prompts': [], 'actions': [], 'cancellations': [],
                'closed': [], 'cancelled': threading.Event()}

    class Callback:
        def __init__(self, tools, dispatch, output):
            self.tools = tools
            self.dispatch = dispatch
            self.output = output
            self.calls = []
            self.port = 12345

        def __enter__(self):
            stack.append(self)
            return self

        def __exit__(self, *_):
            assert stack.pop() is self

        def call(self, name, arguments):
            result = self.dispatch(name, arguments)
            self.calls.append({'name': name, 'arguments': arguments,
                               'status': 'completed', 'result': result})
            return result

    @contextmanager
    def create_harness(**kwargs):
        observed['factories'].append(kwargs)

        class Client:
            @property
            def client(self):
                return self

            def request(self, method, params, *, response_model, timeout_seconds):
                observed['cancellations'].append({'method': method, 'params': params,
                                                  'timeout_seconds': timeout_seconds})
                if observed.get('cancel_error'):
                    raise RuntimeError('diagnostic cancel transport failure')
                observed['cancelled'].set()
                return response_model(accepted=True)

            def close(self):
                observed['closed'].append(True)
                observed['cancelled'].set()

            def run(self, prompt, session_id, on_notification):
                observed['prompts'].append(prompt)
                on_notification(SimpleNamespace(method='session.event', payload={
                    'sessionId': 'other-session', 'event': {'type': 'step/start', 'data': {'wrong': True}}}))
                on_notification(SimpleNamespace(method='session.event', payload={
                    'sessionId': session_id, 'event': {'type': 'step/start', 'data': {'model': 'diagnostic'}}}))
                if observed['actions']:
                    observed['actions'].pop(0)(stack[-1])
                return SimpleNamespace(final_response='diagnostic response', finish_reason='completed')

        yield Client()

    monkeypatch.setattr(research, 'CallbackTools', Callback)
    monkeypatch.setattr(research, 'create_harness', create_harness)
    return observed


def test_actual_mcp_22_exposes_schema_dispatch_and_error_flag(tmp_path):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    def dispatch(name, arguments):
        if arguments['resource'] == 'fail':
            raise ValueError('diagnostic callback failure')
        return {'resource': arguments['resource'], 'content': 'synthetic skill'}

    async def check(endpoint):
        async with streamable_http_client(endpoint) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert len(tools.tools) == 1
                tool = tools.tools[0]
                assert tool.name == 'read_skill'
                assert tool.input_schema == TOOLS[0]['parameters']
                assert tool.model_dump(by_alias=True)['inputSchema'] == TOOLS[0]['parameters']
                good = await client.call_tool('read_skill', {'node_id': 'controller', 'resource': 'SKILL.md'})
                assert good.is_error is False
                assert json.loads(good.content[0].text)['content'] == 'synthetic skill'
                bad = await client.call_tool('read_skill', {'node_id': 'controller', 'resource': 'fail'})
                assert bad.is_error is True
                assert bad.model_dump(by_alias=True)['isError'] is True
                assert 'diagnostic callback failure' in bad.content[0].text

    with research.CallbackTools(TOOLS, dispatch, tmp_path) as callback:
        anyio.run(check, 'http://127.0.0.1:' + str(callback.port) + '/mcp')
        assert [row['status'] for row in callback.calls] == ['completed', 'failed']
    rows = [json.loads(line) for line in (tmp_path / 'tool-calls.jsonl').read_text().splitlines()]
    assert [row['phase'] for row in rows] == ['started', 'finished', 'started', 'finished']
    assert not callback.thread.is_alive()


@pytest.mark.parametrize('tools', [[], [TOOLS[0], TOOLS[0]]])
def test_duplicate_or_empty_mcp_tools_rejected(tmp_path, tools):
    with pytest.raises(ValueError, match='empty_or_duplicate'):
        research.CallbackTools(tools, lambda *_: {}, tmp_path)


def test_actual_prompt_tool_order_request_evidence_and_unlimited_defaults(tmp_path, injected):
    prior = tmp_path / 'prior'
    gate = Gate(prior)
    harness = research.ResearchHarness(gate, tmp_path / 'sessions')
    injected['actions'].append(lambda callback: callback.call('read_skill', {
        'node_id': 'controller', 'resource': 'SKILL.md'}))
    result = harness(request(), lambda *_: {'content': 'synthetic procedure'})
    directory = Path(result['directory'])
    effective = json.loads((directory / 'effective.json').read_text())
    assert effective['budget_usd'] is None and effective['max_requests'] is None
    assert effective['max_tokens'] == 393216
    assert effective['tool_order'] == ['read_skill']
    assert result['request_ids'] == [31, 32]
    assert result['observed_model_usd_decimal'] is None
    assert result['controller_activated'] is True
    assert gate.current == prior
    prompt = injected['prompts'][0]
    assert 'Initial overview' in prompt
    assert 'Synthetic procedure' not in prompt
    assert 'synthetic procedure' not in prompt
    arguments = injected['factories'][0]
    patch = Path(arguments['patches'][0]).read_text()
    assert '"id": "tool-skill", "disabled": false' in patch
    assert 'Synthetic procedure' in patch
    assert arguments['max_tokens'] == 393216
    assert json.loads(arguments['env']['SSS_SCENARIO_TOOLS']) == ['mcp__research__read_skill']
    assert arguments['env']['DSH_HOME'] == str(directory / 'dsh')
    assert arguments['cwd'] == str(directory)
    rows = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
    assert len(rows) == 1 and 'wrong' not in rows[0]['data']


def test_native_skill_load_receipt_counts_as_controller_activation(tmp_path, injected):
    gate = Gate(tmp_path / 'prior')
    harness = research.ResearchHarness(gate, tmp_path / 'sessions')
    def native_load(callback):
        (callback.output / 'skill-activations.jsonl').write_text(json.dumps({
            'name': 'diagnostic-skill', 'status': 'loaded', 'session_id': 'diagnostic-session',
            'source_sha256': 'a' * 64}) + '\n')
    injected['actions'].append(native_load)
    response = harness(request(), lambda *_: {})
    assert response['controller_activated'] is True
    assert response['activated_skill_names'] == ['diagnostic-skill']
    assert response['controller_activation_evidence']['sha256']


def test_task_timeout_is_forwarded_to_original_harness(tmp_path, injected):
    gate = Gate(tmp_path / 'prior')
    call = request()
    call['timeout_seconds'] = 45
    research.ResearchHarness(gate, tmp_path / 'sessions')(call, lambda *_: {})
    assert injected['factories'][0]['request_timeout_seconds'] == 45


@pytest.mark.parametrize('cancel_error', [False, True])
def test_total_deadline_cancels_public_session_and_preserves_costs(tmp_path, injected, cancel_error):
    prior = tmp_path / 'prior'
    gate = Gate(prior)
    injected['cancel_error'] = cancel_error
    def wait_for_cancel(_callback):
        assert injected['cancelled'].wait(timeout=2)
        if cancel_error:
            raise RuntimeError('diagnostic runtime closed')
    injected['actions'].append(wait_for_cancel)
    call = request()
    call['timeout_seconds'] = 0.05
    started = time.monotonic()
    result = research.ResearchHarness(gate, tmp_path / 'sessions')(call, lambda *_: {})
    assert time.monotonic() - started < 2
    assert result['status'] == 'timeout' and result['timed_out'] is True
    assert result['session_timeout_seconds'] == 0.05
    assert result['request_ids'] == [31, 32]
    assert result['observed_model_usd_decimal'] is None
    assert gate.current == prior
    evidence = json.loads(Path(result['cancel_evidence']['path']).read_text())
    assert evidence['method'] == 'session/cancel'
    assert evidence.get('accepted') is True if not cancel_error else evidence['runtime_closed'] is True
    cancellation = injected['cancellations'][0]
    assert cancellation['method'] == 'session/cancel'
    assert cancellation['params']['sessionId'].startswith('research-')
    assert cancellation['timeout_seconds'] == 10
    assert injected['factories'][0]['request_timeout_seconds'] == 0.05
    stored = json.loads((Path(result['directory']) / 'result.json').read_text())
    assert stored['status'] == 'timeout' and stored['provider_requests'] == 2


def test_completed_session_stops_deadline_before_next_session(tmp_path, injected):
    gate = Gate(tmp_path / 'prior')
    harness = research.ResearchHarness(gate, tmp_path / 'sessions')
    call = request()
    call['timeout_seconds'] = 0.05
    assert harness(call, lambda *_: {})['status'] == 'completed'
    time.sleep(0.08)
    assert not injected['cancellations']
    assert harness(request(), lambda *_: {})['status'] == 'completed'
    assert not injected['cancellations']


@pytest.mark.parametrize('timeout', [None, 0, -1, True, float('nan'), float('inf')])
def test_invalid_session_timeout_rejected_before_opening_session(tmp_path, injected, timeout):
    gate = Gate(tmp_path / 'prior')
    call = request()
    call['timeout_seconds'] = timeout
    with pytest.raises(ValueError, match='research_session_timeout_invalid'):
        research.ResearchHarness(gate, tmp_path / 'sessions')(call, lambda *_: {})
    assert not injected['factories'] and not gate.directories


@pytest.mark.parametrize('resource,result', [('references/workspace.md', {'content': 'references'}),
                                           ('SKILL.md', {'status': 'error', 'error': 'missing'})])
def test_reference_or_failed_resource_read_does_not_activate_controller(tmp_path, injected, resource, result):
    gate = Gate(tmp_path / 'prior')
    harness = research.ResearchHarness(gate, tmp_path / 'sessions')
    injected['actions'].append(lambda callback: callback.call('read_skill', {
        'node_id': 'controller', 'resource': resource}))
    response = harness(request(), lambda *_: result)
    assert response['controller_activated'] is False


def test_missing_provider_request_evidence_fails_real_session_claim(tmp_path, injected):
    gate = Gate(tmp_path / 'prior')
    gate.provider_requests = 0
    response = research.ResearchHarness(gate, tmp_path / 'sessions')(request(), lambda *_: {})
    assert response['status'] == 'failed'
    assert response['error'] == 'research_model_request_evidence_missing'


def test_nested_evaluation_sessions_restore_each_fee_owner(tmp_path, injected):
    prior = tmp_path / 'prior'
    gate = Gate(prior)
    harness = research.ResearchHarness(gate, tmp_path / 'sessions')
    owners = []

    def outer_action(callback):
        before = gate.current
        nested = harness(request('nested evaluation'), lambda *_: {})
        owners.append((before, gate.current, Path(nested['directory'])))

    injected['actions'].append(outer_action)
    response = harness(request('outer optimization'), lambda *_: {})
    assert gate.current == prior
    assert len(gate.directories) == 2
    before, restored, nested_directory = owners[0]
    assert before == restored == Path(response['directory'])
    assert nested_directory != restored
    assert gate.directories == [nested_directory, restored]


def test_fee_owner_restored_when_final_cost_read_fails(tmp_path, injected):
    prior = tmp_path / 'prior'
    gate = Gate(prior)
    def fail(_directory):
        raise RuntimeError('diagnostic cost read failure')
    gate.costs = fail
    with pytest.raises(RuntimeError, match='cost read failure'):
        research.ResearchHarness(gate, tmp_path / 'sessions')(request(), lambda *_: {})
    assert gate.current == prior


def test_fee_owner_restored_when_final_result_write_fails(tmp_path, injected, monkeypatch):
    prior = tmp_path / 'prior'
    gate = Gate(prior)
    original = research.save
    def fail_result(path, value):
        if Path(path).name == 'result.json':
            raise OSError('diagnostic result write failure')
        return original(path, value)
    monkeypatch.setattr(research, 'save', fail_result)
    with pytest.raises(OSError, match='result write failure'):
        research.ResearchHarness(gate, tmp_path / 'sessions')(request(), lambda *_: {})
    assert gate.current == prior


@pytest.mark.parametrize('timeout_seconds', [None, 3])
def test_original_harness_native_skill_and_callback_mcp_use_original_request_ledger(tmp_path, monkeypatch, timeout_seconds):
    """Full local SDK round trip with synthetic SSE responses and actual tools."""
    from src.adapters import capability_proposal as proposal

    provider_calls = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            provider_calls.append(body)
            if timeout_seconds:
                time.sleep(4)
            number = len(provider_calls)
            tool = None
            arguments = None
            if number == 1:
                tool, arguments = 'skill', {'name': 'diagnostic-skill'}
            elif number == 2:
                tool, arguments = 'mcp__research__read_skill', {'node_id': 'controller', 'resource': 'references/detail.md'}
            delta = {'role': 'assistant'}
            if tool:
                delta['tool_calls'] = [{'index': 0, 'id': 'diagnostic-' + str(number), 'type': 'function',
                                        'function': {'name': tool, 'arguments': json.dumps(arguments)}}]
            else:
                delta['content'] = 'Local protocol diagnostic complete.'
            base = {'id': 'local-' + str(number), 'created': 1, 'model': body['model'],
                    'object': 'chat.completion.chunk'}
            usage = {'prompt_tokens': 100, 'prompt_cache_hit_tokens': 50,
                     'prompt_cache_miss_tokens': 50, 'completion_tokens': 20, 'total_tokens': 120}
            chunks = [{**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                      {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls' if tool else 'stop'}]},
                      {**base, 'choices': [], 'usage': usage}]
            raw = (''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except BrokenPipeError:
                pass

    skill = tmp_path / 'skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: diagnostic-skill\ndescription: Synthetic diagnostic procedure\n---\n'
                                   'Read the referenced detail when necessary.\n')
    ledger = tmp_path / 'ledger'
    ledger.mkdir()
    (ledger / 'budget-checkpoint.json').write_text(json.dumps({'request_count': 5, 'reserved_usd': 0}))
    (ledger / 'cost-ledger.jsonl').write_text('')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic-local-provider-only')
    original_server = proposal.create_server
    with ThreadingHTTPServer(('127.0.0.1', 0), Provider) as provider:
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setattr(proposal, 'create_server', lambda host, port, _upstream, state:
            original_server(host, port, 'http://127.0.0.1:' + str(provider.server_port), state))
        try:
            with proposal.CumulativeProposalGate(ledger) as gate:
                call = request('Complete the diagnostic workflow.')
                call['available_skill_cards'] = [{'name': 'diagnostic-skill',
                    'description': 'Synthetic diagnostic procedure', 'path': str(skill)}]
                if timeout_seconds:
                    call['timeout_seconds'] = timeout_seconds
                observed = []
                def dispatch(name, arguments):
                    observed.append((name, arguments))
                    return {'content': 'Synthetic referenced detail'}
                result = research.ResearchHarness(gate, tmp_path / 'sessions')(call, dispatch)
                if timeout_seconds:
                    assert result['status'] == 'timeout' and result['timed_out'] is True
                    evidence = json.loads(Path(result['cancel_evidence']['path']).read_text())
                    assert evidence.get('accepted') is True or evidence.get('runtime_closed') is True
                    assert result['request_ids'] == [6] and result['provider_requests'] == 1
                    assert result['elapsed_seconds'] < 6
                    assert gate.current is None
                    assert gate.state.request_count == 6
                    return
                assert result['status'] == 'completed'
                assert result['controller_activated'] is True
                assert result['activated_skill_names'] == ['diagnostic-skill']
                assert result['request_ids'] == [6, 7, 8]
                assert result['provider_requests'] == 3
                assert gate.current is None
                assert gate.state.request_count == 8
                assert observed == [('read_skill', {'node_id': 'controller', 'resource': 'references/detail.md'})]
                names = {tool['function']['name'] for tool in provider_calls[0]['tools']}
                assert names == {'skill', 'mcp__research__read_skill'}
                first_prompt = json.dumps(provider_calls[0]['messages'])
                assert 'Synthetic diagnostic procedure' in first_prompt
                assert 'Read the referenced detail' not in first_prompt
                assert 'Read the referenced detail' in json.dumps(provider_calls[1]['messages'])
                assert all(body['max_tokens'] == 393216 for body in provider_calls)
                directory = Path(result['directory'])
                assert len(list(directory.glob('request-*.json'))) == 3
                assert (directory / 'requests.jsonl').is_file()
            rows = [json.loads(line) for line in (ledger / 'cost-ledger.jsonl').read_text().splitlines()]
            assert len(rows) == 3
        finally:
            provider.shutdown()
            thread.join(timeout=5)
