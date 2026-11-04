"""Budget-routing diagnostics, no model or external endpoint is called."""
import json
import pytest
from src.adapters.ppt_capability_budget import PptCapabilityBudget


@pytest.mark.parametrize('prefix', ['', 'abc12345'])
def test_public_proposal_uses_existing_account_policy_and_separate_learning_budget(tmp_path, monkeypatch, prefix):
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'endpoint': 'http://127.0.0.1:1/v1', 'control_endpoint': 'http://127.0.0.1:2',
        'control_token': 'diagnostic-only', 'budget_usd': None, 'budget_task_prefix': prefix}), encoding='utf-8')
    gate = PptCapabilityBudget(policy, tmp_path / 'existing-ledger')
    calls = []
    def control(route, value=None):
        calls.append((route, value))
        return {'usage_complete': True, 'upstream_requests': 1, 'observed_peak_cost_usd': .002,
                'global_upstream_requests': 101, 'global_estimated_cost_usd': .2}
    monkeypatch.setattr(gate, 'control', control)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic-only')
    output = tmp_path / 'attempt'
    gate.register_attempt(output, 'round/attempt');output.mkdir()
    session = gate.session_id(output)
    assert calls[0][0] == '/tasks/register' and calls[0][1]['budget_usd'] is None
    assert calls[0][1]['task_id'].startswith(prefix)
    assert session.startswith('session-' if prefix else 'turn-')
    environment = gate.environment()
    assert environment['DEEPSEEK_BASE_URL'] == 'http://127.0.0.1:1/v1'
    result = gate.costs(output)
    assert result['provider_requests'] == 1 and result['observed_model_usd'] == .002
    assert [route for route, value in calls] == (['/tasks/register', '/tasks/activate', '/bind', '/tasks/cancel', '/unbind']
         if prefix else ['/tasks/register', '/tasks/activate', '/tasks/cancel'])
    assert not (tmp_path / 'existing-ledger').exists()
    assert json.loads((output / 'budget-attribution.json').read_text())['included_in_B_O_execution'] is False


def test_public_budget_rejects_external_endpoint_before_reading_credentials(tmp_path):
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'endpoint': 'https://example.invalid/v1', 'control_endpoint': 'http://127.0.0.1:2'}))
    with pytest.raises(ValueError, match='private_budget_service'):
        PptCapabilityBudget(policy, tmp_path / 'ledger')
