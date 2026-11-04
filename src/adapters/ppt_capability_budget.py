"""Delegate public construction to the running account budget service."""
import json
import os
from pathlib import Path
import re
import urllib.request
from urllib.parse import urlsplit
from uuid import uuid4


class PptCapabilityBudget:
    def __init__(self, policy, ledger_root):
        self.policy = json.loads(Path(policy).read_text(encoding='utf-8'))
        for name in ('endpoint', 'control_endpoint'):
            endpoint = urlsplit(self.policy[name])
            if endpoint.scheme != 'http' or endpoint.hostname not in ('127.0.0.1', 'localhost'):
                raise ValueError('ppt_capability_private_budget_service_required')
        self.root = Path(ledger_root)
        self.current = None
        self.sessions = {}

    def register_attempt(self, output, identity):
        if not identity or Path(output).exists():
            raise ValueError('ppt_capability_fresh_attempt_required')

    def control(self, route, value=None):
        request = urllib.request.Request(self.policy['control_endpoint'].rstrip('/') + route,
            data=None if value is None else json.dumps(value).encode(),
            headers={'Content-Type': 'application/json', 'X-SSS-Control-Token': self.policy['control_token']})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def session_id(self, output):
        prefix = self.policy.get('budget_task_prefix', '')
        if not re.fullmatch(r'(?:[a-f0-9]{8})?', prefix):
            raise ValueError('ppt_capability_account_prefix_invalid')
        task_id = prefix + uuid4().hex[len(prefix):]
        budget_session = 'turn-' + task_id
        model_session = 'session-' + str(uuid4()) if prefix else budget_session
        binding = {'session_id': model_session, 'budget_session_id': budget_session}
        self.control('/tasks/register', {'task_id': task_id, 'session_id': budget_session,
                     'budget_usd': self.policy.get('budget_usd'), 'model': 'deepseek-flash'})
        self.sessions[str(output)] = {'task_id': task_id, **binding, 'bound': False}
        self.control('/tasks/activate', {'session_id': budget_session})
        if prefix:
            self.control('/bind', binding)
            self.sessions[str(output)]['bound'] = True
        Path(output, 'budget-attribution.json').write_text(json.dumps({'phase': 'ppt_public_capability_construction',
            'task_id': task_id, **binding, 'included_in_B_O_execution': False, 'cumulative_ledger_reset': False}), encoding='utf-8')
        return model_session

    def environment(self):
        if not os.environ.get('DEEPSEEK_API_KEY'):
            raise ValueError('ppt_capability_private_credential_required')
        return {'DEEPSEEK_API_KEY': os.environ['DEEPSEEK_API_KEY'], 'DEEPSEEK_BASE_URL': self.policy['endpoint'],
                'SSS_BUDGET_GATE_ACTIVE': '1', 'SSS_BUDGET_CAP_USD': '0'}

    def costs(self, output):
        row = self.sessions.get(str(output))
        if row is None:
            return {'provider_requests': 0, 'request_ids': [], 'observed_model_usd': None, 'billing_usd': None}
        stats = self.control('/tasks/cancel', {'session_id': row['budget_session_id']})
        if row['bound']:
            self.control('/unbind', {'session_id': row['session_id'], 'budget_session_id': row['budget_session_id']})
        Path(output, 'budget-terminal.json').write_text(json.dumps(stats), encoding='utf-8')
        complete = stats.get('usage_complete') is True
        return {'provider_requests': stats.get('upstream_requests', 0), 'request_ids': [],
                'request_ids_unavailable_from_stats': True,
                'observed_model_usd': stats.get('observed_peak_cost_usd') if complete else None,
                'billing_usd': None, 'budget_task_id': row['task_id'],
                'cost_scope': 'existing_account_budget_proxy_learning_task', 'usage': stats,
                'cumulative_requests': stats.get('global_upstream_requests'),
                'cumulative_accounted_usd': stats.get('global_estimated_cost_usd')}
