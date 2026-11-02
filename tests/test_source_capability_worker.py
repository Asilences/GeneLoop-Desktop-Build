"""Native-worker lifecycle diagnostics; no model calls or Docker startup."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capability_worker_test', ROOT/'scenarios/remotion_edit/structured/capability_worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_cleanup_removes_only_verified_immutable_container_id(monkeypatch):
    calls = []
    nonce = 'a'*32
    def run(args, **kwargs):
        calls.append(args)
        if args[1] == 'inspect':
            return SimpleNamespace(returncode=0, stdout=json.dumps([{'Id': 'immutable-owned-id',
                'Config': {'Labels': {'geneloop.capability_nonce': nonce}}}]), stderr='')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(worker.subprocess, 'run', run)
    result = worker.cleanup_owned_container('geneloop-cap-'+nonce, nonce)
    assert result['status'] == 'removed'
    assert calls[1] == ['docker', 'rm', '-f', 'immutable-owned-id']


def test_cleanup_never_removes_another_nonce_or_claims_daemon_error_is_absence(monkeypatch):
    nonce = 'a'*32
    calls = []
    def wrong(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps([{'Id': 'foreign-id',
            'Config': {'Labels': {'geneloop.capability_nonce': 'b'*32}}}]), stderr='')
    monkeypatch.setattr(worker.subprocess, 'run', wrong)
    with pytest.raises(RuntimeError, match='owner_mismatch'):
        worker.cleanup_owned_container('geneloop-cap-'+nonce, nonce)
    assert len(calls) == 1
    monkeypatch.setattr(worker.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='daemon unavailable'))
    with pytest.raises(RuntimeError, match='inspection_failed'):
        worker.cleanup_owned_container('geneloop-cap-'+nonce, nonce)


@pytest.mark.parametrize('scoped', [False, True])
def test_native_scene_preserves_legacy_launch_and_accepts_explicit_nonce_scope(tmp_path, monkeypatch, scoped):
    import atexit
    work = tmp_path/'work'; work.mkdir()
    monkeypatch.setenv('REMOTION_WORK', str(work)); monkeypatch.setenv('REMOTION_RUNTIME', str(tmp_path))
    monkeypatch.setenv('REMOTION_IMAGE', 'diagnostic-not-launched'); monkeypatch.delenv('REMOTION_MEDIA_TOOLS', raising=False)
    nonce = 'c'*32
    for key, value in [('REMOTION_CONTAINER_NAME', 'geneloop-cap-'+nonce), ('REMOTION_CONTAINER_NONCE', nonce)]:
        if scoped: monkeypatch.setenv(key, value)
        else: monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(atexit, 'register', lambda *args: None)
    monkeypatch.setattr(os, 'getuid', lambda: 1234, raising=False)
    monkeypatch.setattr(os, 'getgid', lambda: 1234, raising=False)
    scene_spec = importlib.util.spec_from_file_location('source_scene_launch_test', ROOT/'scenarios/remotion_edit/server.py')
    scene = importlib.util.module_from_spec(scene_spec); scene_spec.loader.exec_module(scene)
    launches = []
    monkeypatch.setattr(scene.subprocess, 'check_output', lambda args, **kwargs: launches.append(args) or 'test-container-id')
    monkeypatch.setattr(scene.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='', stderr=''))
    scene.run_command('true')
    assert ('--name' in launches[0]) is scoped
    assert ('geneloop.capability_nonce='+nonce in launches[0]) is scoped
    assert ('geneloop.experiment=remotion-motivation-20261027-v1' in launches[0]) is not scoped
    assert '--network' in launches[0] and '--read-only' in launches[0]
