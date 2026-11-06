"""Original Harness tool sessions for isolated evolution and benchmark trials.

Tool callbacks are exposed through the existing MCP client plugin. Model
requests continue through the original cumulative ledger and provider adapter.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import socket
import threading
import time
from uuid import uuid4

from pydantic import BaseModel

from .capability_feedback import file_ref
from .capability_improvement import save
from .capability_proposal import (
    MAX_TOKENS, MODEL, ROOT, append, create_harness,
)


class SessionCancelResult(BaseModel):
    accepted: bool


class CallbackTools:
    """One loopback MCP endpoint backed by the caller's existing operations."""

    def __init__(self, tools, dispatch, output):
        import anyio
        from mcp.server import MCPServer
        from mcp.types import CallToolResult, TextContent, Tool
        import uvicorn

        self.output = Path(output)
        self.calls = []
        self.lock = threading.Lock()
        names = [tool['name'] for tool in tools]
        if len(set(names)) != len(names) or not names:
            raise ValueError('research_tools_empty_or_duplicate')
        self.names = names
        host = self

        class Server(MCPServer):
            async def list_tools(self):
                return [Tool(name=tool['name'], description=tool['description'],
                             input_schema=tool['parameters']) for tool in tools]

            async def call_tool(self, name, arguments, context=None):
                def execute():
                    with host.lock:
                        row = {'sequence': len(host.calls), 'name': name,
                               'arguments': arguments, 'started_at': time.time()}
                        host.calls.append(row)
                        append(host.output / 'tool-calls.jsonl', {**row, 'phase': 'started'})
                        try:
                            if name not in host.names:
                                raise ValueError('research_tool_unknown')
                            result = dispatch(name, arguments)
                            text = json.dumps(result, ensure_ascii=False, allow_nan=False)
                            row.update(status='completed', result=result)
                            return CallToolResult(content=[TextContent(type='text', text=text)])
                        except Exception as error:
                            row.update(status='failed', error=type(error).__name__ + ':' + str(error))
                            return CallToolResult(content=[TextContent(type='text', text=json.dumps(
                                {'error': row['error']}))], is_error=True)
                        finally:
                            row['elapsed_seconds'] = time.time() - row['started_at']
                            append(host.output / 'tool-calls.jsonl', {**row, 'phase': 'finished'})
                return await anyio.to_thread.run_sync(execute)

        server = Server('GeneLoop research tools')
        self.socket = socket.socket()
        self.socket.bind(('127.0.0.1', 0))
        self.port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(
            server.streamable_http_app(json_response=True, stateless_http=True),
            host='127.0.0.1', port=self.port, log_level='error', access_log=False))
        self.thread = threading.Thread(target=self.server.run,
                                       kwargs={'sockets': [self.socket]}, daemon=True)

    def __enter__(self):
        self.thread.start()
        started = time.monotonic()
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() - started > 15:
                self.__exit__(None, None, None)
                raise RuntimeError('research_mcp_startup_failed')
            time.sleep(0.02)
        return self

    def __exit__(self, *_):
        self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(timeout=10)
        self.socket.close()


def callback_patch(output, endpoint, tools, *, persona, skills=()):
    """Reuse the pinned SDK profile and original scenario restriction plugin."""
    output = Path(output)
    allowed = ['mcp__research__' + tool['name'] for tool in tools]
    additions = [
        {'id': 'skill', 'disabled': False},
        {'id': 'tool-skill', 'disabled': False},
        {'id': 'system-prompt', 'config': {'personaPrefix': persona,
                                         'personaSuffix': 'Use the available tools to complete the requested work.'}},
        {'insert': [
            {'id': 'research-mcp', 'name': '@deepseek-ai/dsh-mcp-client', 'config': {
                'serverName': 'research', 'transport': 'streamable-http',
                'url': endpoint, 'failOnStartupError': True, 'toolCallTimeoutMs': 28800000}},
            {'id': 'research-tool-scope',
             'name': (ROOT / 'src/adapters/dsh_research_scope.mjs').as_uri(),
             'config': {'allowedTools': allowed, 'skills': list(skills),
                        'activationRecord': str(output / 'skill-activations.jsonl')}},
        ]},
    ]
    base = (ROOT / 'config/semantic-sdk.patch.yml').read_text(encoding='utf-8')
    path = output / 'harness.patch.yml'
    path.write_text(base + '\n' + '\n'.join('- ' + json.dumps(row, ensure_ascii=False)
                                           for row in additions) + '\n', encoding='utf-8')
    path.chmod(0o600)
    return path, allowed


class ResearchHarness:
    """A callable session adapter, with no extra agent control loop."""

    def __init__(self, gate, output, *, model=MODEL):
        self.gate = gate
        self.output = Path(output)
        self.output.mkdir(parents=True, mode=0o700, exist_ok=True)
        if model != MODEL:
            raise ValueError('research_model_requires_original_ledger_configuration')
        self.model = model

    def __call__(self, request, dispatch):
        from deepseek_harness.api import final_response, finish_reason
        from .native_budget import NativeBudgetGuard

        timeout = request.get('timeout_seconds', 28800)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('research_session_timeout_invalid')
        directory = self.output / ('session-' + uuid4().hex)
        directory.mkdir(mode=0o700)
        source_directory = directory / 'source-snapshot'
        source_directory.mkdir()
        source_files = []
        for path in (Path(__file__), ROOT / 'src/adapters/dsh_research_scope.mjs'):
            target = source_directory / path.name
            target.write_bytes(path.read_bytes())
            source_files.append(file_ref(target))
        tools = request['tools']
        public = {key: value for key, value in request.items() if not callable(value)}
        save(directory / 'request.json', public)
        cards = request.get('available_skill_cards', [])
        prompt = request['prompt']
        if request.get('initial_context') is not None:
            prompt += '\nInitial overview:\n' + json.dumps(request['initial_context'], ensure_ascii=False)
        save(directory / 'effective.json', {
            'model': self.model, 'reasoning_effort': 'off', 'max_tokens': MAX_TOKENS,
            'budget_usd': None, 'max_requests': None, 'cumulative_ledger_reset': False,
            'mode': request.get('mode'), 'tool_order': [tool['name'] for tool in tools],
            'session_timeout_seconds': timeout,
            'native_skill_enabled': bool(cards),
            'available_skill_cards': cards,
            'provider_tool_names': [*(['skill'] if cards else []),
                                    *['mcp__research__' + tool['name'] for tool in tools]],
            'code': source_files,
            'code_manifest': file_ref(ROOT / '.research-code-snapshot.json')
                if (ROOT / '.research-code-snapshot.json').is_file() else None,
        })
        guard = NativeBudgetGuard(max_model_requests=None, max_observed_input_tokens=None)
        session = 'research-' + uuid4().hex

        def observe(notification):
            if notification.method == 'session.event' and notification.payload.get('sessionId') == session:
                event = notification.payload.get('event')
                if isinstance(event, dict):
                    append(directory / 'events.jsonl', event)
                    guard.observe_event(event)

        previous = self.gate.current
        self.gate.current = directory
        started = time.monotonic()
        result = {'status': 'failed', 'directory': str(directory), 'controller_activated': None,
                  'timed_out': False, 'session_timeout_seconds': timeout, 'cancel_evidence': None}
        deadline_lock = threading.Lock()
        finished = False
        try:
            with CallbackTools(tools, dispatch, directory) as callback:
                patch, allowed = callback_patch(directory, f'http://127.0.0.1:{callback.port}/mcp', tools,
                    persona=request.get('system', 'You investigate and improve agent work using actual evidence.'),
                    skills=cards)
                env = {**self.gate.environment(), 'SSS_SCENARIO_TOOLS': json.dumps(allowed),
                       'SSS_SCENARIO_PRESENTATION': 'native', 'DSH_HOME': str(directory / 'dsh'),
                       'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': ''}
                with create_harness(root=ROOT, patches=(str(patch),), env=env,
                        provider='deepseek-official', model=self.model, max_tokens=MAX_TOKENS,
                        cwd=str(directory), runtime_cwd=str(directory),
                        request_timeout_seconds=timeout) as client:
                    def cancel_session():
                        with deadline_lock:
                            if finished:
                                return
                            result.update(timed_out=True, status='timeout')
                        evidence = {'method': 'session/cancel', 'session_id': session,
                                    'timeout_seconds': timeout, 'requested_at': time.time()}
                        try:
                            cancelled = client.client.request('session/cancel', {'sessionId': session},
                                response_model=SessionCancelResult, timeout_seconds=10)
                            evidence['accepted'] = cancelled.accepted
                        except Exception as error:
                            evidence['error'] = type(error).__name__ + ':' + str(error)
                        if not evidence.get('accepted'):
                            try:
                                client.close()
                                evidence['runtime_closed'] = True
                            except Exception as error:
                                evidence['close_error'] = type(error).__name__ + ':' + str(error)
                        save(directory / 'cancel-evidence.json', evidence)
                        result['cancel_evidence'] = file_ref(directory / 'cancel-evidence.json')

                    remaining = timeout - (time.monotonic() - started)
                    response = None
                    if remaining <= 0:
                        result.update(timed_out=True, status='timeout',
                                      error='research_session_startup_deadline_exceeded')
                    else:
                        timer = threading.Timer(remaining, cancel_session)
                        timer.daemon = True
                        timer.start()
                        try:
                            response = client.run(prompt, session_id=session, on_notification=observe)
                        except Exception as error:
                            if not result['timed_out']:
                                raise
                            result['error'] = type(error).__name__ + ':' + str(error)
                        finally:
                            with deadline_lock:
                                finished = True
                            timer.cancel()
                            timer.join()
                answer = (response.final_response if response else None) or final_response(guard.events)
                finish = (response.finish_reason if response else None) or finish_reason(guard.events)
                (directory / 'answer.txt').write_text(answer, encoding='utf-8')
                activation_path = directory / 'skill-activations.jsonl'
                activations = [json.loads(line) for line in activation_path.read_text().splitlines()
                               if line] if activation_path.exists() else []
                controller_read = any(row['name'] == 'read_skill'
                    and row['arguments'].get('node_id') == 'controller'
                    and row['arguments'].get('resource') == 'SKILL.md'
                    and row.get('status') == 'completed'
                    and row.get('result', {}).get('status') != 'error'
                    for row in callback.calls)
                result.update(status='timeout' if result['timed_out'] else
                                  'completed' if finish == 'completed' else 'incomplete',
                              text=answer, finish_reason=finish, tools=callback.calls,
                              controller_activated=bool(activations) or controller_read,
                              activated_skill_names=[row['name'] for row in activations],
                              controller_activation_evidence=file_ref(activation_path)
                                  if activation_path.exists() else None)
        except BaseException as error:
            result['error'] = type(error).__name__ + ':' + str(error)
            raise
        finally:
            try:
                result.update(self.gate.costs(directory), elapsed_seconds=time.monotonic() - started)
                if result.get('status') == 'completed' and not result.get('provider_requests'):
                    result.update(status='failed', error='research_model_request_evidence_missing')
                save(directory / 'result.json', result)
            finally:
                self.gate.current = previous
        return result
