"""Versioned custom MCP configuration; secrets remain environment references."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r'^[a-z][a-z0-9_]{0,31}$')
ENV_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def prepare_scenario(path: Path, *, case: str = '', session_workspace: str | None = None,
                     tool_presentation: str = 'native', entry_motif: bool = False,
                     web_deployment: bool = False, _file_profile: bool = False) -> dict:
    if type(web_deployment) is not bool:
        raise ValueError('web_deployment must be boolean')
    if type(entry_motif) is not bool or entry_motif and tool_presentation != 'native':
        raise ValueError('entry Motif requires native tool presentation')
    if tool_presentation not in ('native', 'ptc'):
        raise ValueError('invalid tool presentation')
    path = path.resolve(strict=True)
    scenario = json.loads(path.read_text(encoding='utf-8'))
    if set(scenario) - {'schema_version', 'name', 'prompt', 'servers', 'allowed_tools', 'completion_guard', 'acceptance_guard'}:
        raise ValueError('unknown scenario field')
    if scenario.get('schema_version') != 1 or not NAME.fullmatch(scenario.get('name', '')):
        raise ValueError('invalid scenario version/name')
    if case and not NAME.fullmatch(case):
        raise ValueError('invalid case name')
    substitutions = {'PROJECT_ROOT': str(ROOT), 'PYTHON': sys.executable, 'CASE': case}
    if session_workspace is not None:
        substitutions['SESSION_WORKSPACE'] = session_workspace
    def substitute(text):
        for name, replacement in substitutions.items():
            text = text.replace('${' + name + '}', replacement)
        return text

    references = {}
    required_env = []
    literal_fields = substitute(json.dumps(scenario, ensure_ascii=False))
    env_prefix = '__SSS_ENV_REFERENCE_'
    while env_prefix in literal_fields:
        env_prefix = '_' + env_prefix

    def value(item):
        if isinstance(item, dict) and set(item) == {'from_env'}:
            name = item['from_env']
            if not isinstance(name, str) or not ENV_NAME.fullmatch(name):
                raise ValueError('invalid environment reference')
            token = f'{env_prefix}{len(references)}__'
            references[token] = '!!js ' + json.dumps(f'process.env[{json.dumps(name)}]')
            required_env.append(name)
            return token
        if not isinstance(item, str):
            raise ValueError('configuration values must be strings or from_env references')
        item = substitute(item)
        if '${' in item:
            raise ValueError('unsupported placeholder; use from_env for secrets')
        return item

    servers = scenario.get('servers', [])
    if not isinstance(servers, list) or not servers:
        raise ValueError('scenario needs MCP servers')
    clients = []
    seen = set()
    for server in servers:
        name = server.get('server_name', '')
        if not NAME.fullmatch(name) or name in seen:
            raise ValueError('invalid or duplicate MCP server name')
        seen.add(name)
        transport = server.get('transport')
        common = {'server_name', 'transport', 'tool_call_timeout_ms'}
        extra = {'command', 'args', 'cwd', 'env'} if transport == 'stdio' else {'url', 'headers'}
        if transport not in {'stdio', 'streamable-http'} or set(server) - common - extra:
            raise ValueError('invalid MCP transport/configuration')
        config = {'serverName': name, 'transport': transport, 'failOnStartupError': True,
                  'toolCallTimeoutMs': server.get('tool_call_timeout_ms', 60000)}
        if type(config['toolCallTimeoutMs']) is not int or not 1 <= config['toolCallTimeoutMs'] <= 300000:
            raise ValueError('invalid MCP timeout')
        if transport == 'stdio':
            config.update(command=value(server['command']),
                          args=[value(x) for x in server.get('args', [])],
                          cwd=value(server.get('cwd', '${PROJECT_ROOT}')),
                          env={key: value(item) for key, item in server.get('env', {}).items()})
        else:
            config.update(url=value(server['url']),
                          headers={key: value(item) for key, item in server.get('headers', {}).items()})
        clients.append({'id': 'sss-mcp-' + name, 'name': '@deepseek-ai/dsh-mcp-client', 'config': config})
    allowed = scenario.get('allowed_tools', [])
    if not isinstance(allowed, list) or not allowed or any(
        not isinstance(tool, str) or len(tool) > 64 or
        not any(re.fullmatch('mcp__' + name + '__[a-zA-Z0-9_]+', tool) for name in seen)
        for tool in allowed) or len(set(allowed)) != len(allowed):
        raise ValueError('allowed_tools must explicitly name tools of the configured MCP servers')
    # Keep the profile's credential/provider plumbing; replace model-facing
    # native tools with a stable, ordered MCP surface and monotonic guard.
    profile = ROOT / ('scenarios/file-management' if _file_profile else 'config')
    base = (profile / 'semantic-sdk.patch.yml').read_text(encoding='utf-8')
    insert = {'insert': [*clients, {'id': 'sss-scenario-guard',
                  'name': (ROOT / 'src/adapters/harness/dsh_scenario_guard.mjs').as_uri()}]}
    agent_plugins = []
    if entry_motif:
        entry = {'id': 'sss-entry-motif',
                 'name': (ROOT / 'src/adapters/harness/motif/dsh_entry_motif.ts').as_uri()}
        if _file_profile:
            entry['config'] = {'durablePlan': True}
        insert['insert'].append(entry)
    policy = scenario.get('completion_guard')
    if policy is not None:
        if (not isinstance(policy, dict) or set(policy) != {'tool', 'statuses', 'max_continuations'}
                or policy['tool'] not in allowed or not isinstance(policy['statuses'], list)
                or not 1 <= len(policy['statuses']) <= 4
                or any(not isinstance(s, str) or re.fullmatch(r'[a-z_]{1,40}', s) is None for s in policy['statuses'])
                or type(policy['max_continuations']) is not int or not 0 <= policy['max_continuations'] <= 2):
            raise ValueError('invalid bounded completion guard')
        agent_plugins.append({'id': 'sss-completion-guard',
            'name': (ROOT / 'src/adapters/harness/dsh_completion_guard.ts').as_uri(),
            'config': {**policy, 'artifact_root': str(ROOT / '.local')}})
    acceptance = scenario.get('acceptance_guard')
    durable_job = False
    if acceptance is not None:
        if not isinstance(acceptance, dict):
            raise ValueError('invalid bounded file acceptance guard')
        durable_job = _file_profile and acceptance.get('durable_job') is True
        interruptible = durable_job and acceptance.get('interruptible') is True
        fields = {'kind', 'max_repairs'}
        if durable_job:
            fields.add('durable_job')
        if interruptible:
            fields.add('interruptible')
        repairs = acceptance.get('max_repairs')
        if (set(acceptance) != fields or acceptance.get('kind') != 'file_management'
                or not (durable_job and repairs is None or type(repairs) is int and 0 <= repairs <= 2)
                or tool_presentation != 'native' or 'mcp__file_management__submit_report' not in allowed):
            raise ValueError('invalid bounded file acceptance guard')
        verifier = 'src/adapters/file_acceptance_guard.ts'
        archive = Path(os.environ.get('HARLESS_MANAGEMENT_PRIVATE_ROOT', ROOT / '.local')) if _file_profile else ROOT / '.local'
        acceptance_config = {'kind': acceptance['kind'], 'max_repairs': repairs} if _file_profile else acceptance
        # The delivery verifier owns any continuation needed for a missing receipt.
        agent_plugins = [{'id': 'sss-acceptance-guard', 'name': (ROOT / verifier).as_uri(),
            'config': {**acceptance_config, 'project_root': str(ROOT), 'python': sys.executable,
                'task_file': value({'from_env': 'FM_TASK_FILE'}),
                'delivery_root': value({'from_env': 'FM_OUTPUT'}),
                'archive_root': str(archive / 'task-acceptance'),
                **({'job_file': value({'from_env': 'FM_JOB_FILE'})} if durable_job else {}),
                **({'interruptible': True} if interruptible else {})}}]
    insert['insert'].extend(agent_plugins)
    if tool_presentation == 'ptc':
        base += '\n- id: tools\n  config:\n    mode: ptc\n- id: code-runtime\n  disabled: true\n'
        insert['insert'].append({'id': 'sss-container-code-runtime',
            'name': (ROOT / 'src/adapters/harness/dsh_code_container.ts').as_uri()})
    base += '\n- id: system-prompt\n  config:\n    personaPrefix: You complete the requested task using the permitted MCP evidence.\n    personaSuffix: Cite source IDs and versions. Do not invent evidence or perform unapproved writes.\n'
    if web_deployment:
        from src.adapters.web.tasks.harless_product_prompt import product_system_prompt
        base += '\n- ' + json.dumps({'id': 'system-prompt', 'config': product_system_prompt()}, ensure_ascii=False) + '\n'
        if durable_job:
            # This host-authored addition cannot be requested in a scenario's
            # MCP allowlist. Todos only update the session, never managed files.
            allowed = [*allowed, 'todo_write']
            base += '\n- id: tool-todo\n  disabled: false\n  config:\n    allowParallelInProgress: true\n'
            # Retry only a failed model request. The native loop keeps completed
            # tool results; every HTTP attempt still passes the original gate.
            base += '\n- id: llm-retry\n  disabled: false\n'
            base += '\n- id: llm-deepseek\n  config:\n    retryPolicy:\n      mode: normal\n      maxRetries: 5\n      retryableCodes: [EMPTY_RESPONSE, RATE_LIMIT, SERVER, TIMEOUT, TRANSPORT]\n      backoff:\n        initialDelayMs: 500\n        maxDelayMs: 30000\n        jitterRatio: 0.2\n'
    # JSON is valid YAML; environment tags contain quoted JS expressions.
    plugin_patch = json.dumps(insert, ensure_ascii=False, indent=2).replace('\n', '\n  ')
    for token, expression in references.items():
        plugin_patch = plugin_patch.replace(json.dumps(token), expression)
    rendered = base + '\n- ' + plugin_patch + '\n'
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    target = ROOT / '.local/scenarios/patches' / (digest + '.patch.yml')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding='utf-8'); target.chmod(0o600)
    prompt_path = Path(value(scenario['prompt']))
    if not prompt_path.is_absolute():
        prompt_path = path.parent / prompt_path
    prompt_path = prompt_path.resolve(strict=True)
    prompt = prompt_path.read_text(encoding='utf-8')
    if not prompt.strip() or len(prompt) > 100000:
        raise ValueError('missing or unbounded task prompt')
    return {'name': scenario['name'], 'patch': str(target), 'patch_sha256': digest,
            'config_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'prompt': prompt, 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
            'tool_presentation': tool_presentation,
            'server_names': [client['config']['serverName'] for client in clients], 'allowed_tools': allowed,
            'mcp_rows': clients, 'agent_plugins': agent_plugins, 'environment_references': references,
            'required_env': sorted(set(required_env)), 'case': case, 'acceptance_guard': acceptance}


def prepare_file_scenario(path: Path, *, case: str = '', session_workspace: str | None = None,
                          tool_presentation: str = 'native', entry_motif: bool = False,
                          web_deployment: bool = False) -> dict:
    return prepare_scenario(path, case=case, session_workspace=session_workspace,
                            tool_presentation=tool_presentation, entry_motif=entry_motif,
                            web_deployment=web_deployment, _file_profile=True)
