"""Verify the File-only transport integrates with the shared model gateway."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from src.adapters import file_provider
from src.adapters.model_api import model_api_root


def test_file_provider_wraps_only_the_shared_live_gateway(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts/file-provider-web.py'
    spec = importlib.util.spec_from_file_location('file_web_entry_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    provider = {'credential': 'test-private-file-key', 'provider_binding': file_provider.binding()}
    monkeypatch.setattr(file_provider, 'configured', lambda: provider)
    gateway = object()
    wrapped = []

    def attach(server, config, *, selective):
        wrapped.append((server, config, selective))

    monkeypatch.setattr(file_provider, 'attach', attach)
    host = SimpleNamespace(create_server=lambda *a, **k: gateway)
    module.configure(host)
    assert host.create_server('127.0.0.1', 0, 'http://127.0.0.1:5000', object()) is gateway
    assert wrapped == []
    assert host.create_server('127.0.0.1', 0, model_api_root(), object()) is gateway
    assert wrapped == [(gateway, provider, True)]
