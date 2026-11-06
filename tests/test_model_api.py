"""Kouri connection contract; no network or paid model requests."""

import pytest

from src.adapters import model_api


def test_kouri_address_and_internal_model_mapping():
    assert model_api.model_api_base_url() == 'https://api.kourichat.com/v1'
    assert model_api.model_chat_url() == 'https://api.kourichat.com/v1/chat/completions'
    assert model_api.model_catalog_snapshot()['data'] == [{'id': 'deepseek-flash'}]
    assert model_api.model_wire_id('deepseek-flash') == 'deepseek-v4.1-flash'


def test_kouri_model_mapping_keeps_other_provider_ids():
    assert model_api.model_wire_id('deepseek-v4-flash') == 'deepseek-v4.1-flash'
    assert model_api.model_wire_id('glm-4.6') == 'glm-4.6'


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
