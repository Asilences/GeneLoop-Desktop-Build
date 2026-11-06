"""Kouri connection contract; no network or paid model requests."""

import pytest
import json
import os
import subprocess
import sys
import textwrap

from src.adapters import model_api


def test_kouri_address_and_internal_model_mapping():
    assert model_api.model_api_base_url() == 'https://api.kourichat.com/v1'
    assert model_api.model_chat_url() == 'https://api.kourichat.com/v1/chat/completions'
    catalog = model_api.model_catalog_snapshot()
    assert [row['id'] for row in catalog['data']] == ['deepseek-flash']
    assert catalog['data'][0]['max_output_tokens'] == 393_216
    assert model_api.model_wire_id('deepseek-flash') == 'deepseek-v4.1-flash'


def test_kouri_model_mapping_keeps_other_provider_ids():
    assert model_api.model_wire_id('deepseek-v4-flash') == 'deepseek-v4.1-flash'
    assert model_api.model_wire_id('glm-4.6') == 'glm-4.6'


def test_second_configured_model_drives_catalog_route_and_price(monkeypatch):
    second = {'id': 'kouri-diagnostic', 'wire_id': 'provider-diagnostic',
              'label': 'Kouri diagnostic', 'context_window': 16_000,
              'max_output_tokens': 4_000, 'input_modalities': ('text',),
              'supported_reasoning_efforts': ('off',),
              'input_usd_per_million': 2.0, 'cache_hit_usd_per_million': 0.5,
              'output_usd_per_million': 8.0}
    monkeypatch.setattr(model_api, 'KOURI_MODELS', (*model_api.KOURI_MODELS, second))
    assert 'kouri-diagnostic' in model_api.model_ids()
    assert model_api.model_wire_id('kouri-diagnostic') == 'provider-diagnostic'
    assert model_api.model_catalog_snapshot()['data'][-1]['id'] == 'kouri-diagnostic'
    rates, cache_rates = model_api.model_price_rates()
    assert rates['kouri-diagnostic'] == (2.0, 8.0)
    assert cache_rates['kouri-diagnostic'] == 0.5


def test_one_file_model_addition_reaches_web_catalog_and_budget_gate():
    script = textwrap.dedent('''
        import json
        from src.adapters import model_api
        model_api.KOURI_MODELS += ({'id':'kouri-diagnostic','wire_id':'provider-diagnostic',
            'label':'Kouri diagnostic','context_window':16000,'max_output_tokens':4000,
            'input_modalities':('text',),'supported_reasoning_efforts':('off',),
            'input_usd_per_million':2.0,'cache_hit_usd_per_million':0.5,
            'output_usd_per_million':8.0},)
        from src.adapters.deepseek_cost_gate import PEAK_USD_PER_MILLION, reservation
        from src.adapters.harless_models import model_options
        options = model_options(model_api.model_catalog_snapshot(), budget_usd=None)
        assert [row['model'] for row in options] == ['deepseek-flash','kouri-diagnostic']
        assert options[1]['context_window'] == 16000
        assert options[1]['supported_reasoning_efforts'] == ['off']
        assert 'off' in model_options(model_api.model_catalog_snapshot(),budget_usd=.01)[1]['reasoning_unavailable']
        assert PEAK_USD_PER_MILLION['kouri-diagnostic'] == (2.0,8.0)
        body = json.dumps({'model':'kouri-diagnostic','max_tokens':4000,'messages':[]}).encode()
        assert reservation(body,max_output=None)[0] == 'kouri-diagnostic'
        assert model_api.model_wire_id('kouri-diagnostic') == 'provider-diagnostic'
    ''')
    subprocess.run([sys.executable, '-c', script], check=True)


def test_env_model_addition_reaches_catalog_route_and_budget_gate():
    extra = {'id': 'example-model', 'label': 'Example Model',
             'context_window': 16_000, 'max_output_tokens': 4_000,
             'input_usd_per_million': 2.0, 'output_usd_per_million': 8.0}
    env = {**os.environ, 'KOURI_EXTRA_MODELS_JSON': json.dumps([extra])}
    env.pop('KOURI_API_KEY', None)
    script = textwrap.dedent('''
        from src.adapters import model_api
        from src.adapters.deepseek_cost_gate import PEAK_USD_PER_MILLION
        from src.adapters.harless_models import model_options
        rows = model_api.model_catalog_snapshot()['data']
        assert [row['id'] for row in rows] == ['deepseek-flash', 'example-model']
        assert rows[1]['input_modalities'] == ['text']
        assert rows[1]['supported_reasoning_efforts'] == ['off']
        assert model_api.model_wire_id('example-model') == 'example-model'
        assert PEAK_USD_PER_MILLION['example-model'] == (2.0, 8.0)
        assert model_options(model_api.model_catalog_snapshot(), budget_usd=None)[1]['label'] == 'Example Model'
    ''')
    subprocess.run([sys.executable, '-c', script], env=env, check=True)


@pytest.mark.parametrize('value', [
    'not json', '{}', '[]',
    json.dumps([{'id': 'example-model'}]),
    json.dumps([{'id': 'deepseek-flash', 'context_window': 16000,
                 'max_output_tokens': 4000, 'input_usd_per_million': 1,
                 'output_usd_per_million': 2}]),
    json.dumps([{'id': 'example-model', 'context_window': 100,
                 'max_output_tokens': 200, 'input_usd_per_million': 1,
                 'output_usd_per_million': 2}]),
])
def test_invalid_env_models_fail_closed(monkeypatch, value):
    monkeypatch.setenv('KOURI_EXTRA_MODELS_JSON', value)
    with pytest.raises(ValueError):
        model_api.model_routes()


def test_only_kouri_credential_reaches_remote_gateway(monkeypatch):
    monkeypatch.delenv('KOURI_API_KEY', raising=False)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'old-provider-secret')
    incoming = {'Authorization': 'Bearer old-provider-secret', 'X-API-Key': 'old-provider-secret'}
    with pytest.raises(ValueError, match='KOURI_API_KEY'):
        model_api.model_upstream_headers(model_api.model_api_root(), incoming)
    monkeypatch.setenv('KOURI_API_KEY', 'kouri-test-token')
    assert model_api.model_sdk_key() != 'old-provider-secret'
    outgoing = model_api.model_upstream_headers(model_api.model_api_root(), incoming)
    assert outgoing['Authorization'] == 'Bearer kouri-test-token'
    assert 'X-API-Key' not in outgoing
    assert incoming['Authorization'] == 'Bearer old-provider-secret'
