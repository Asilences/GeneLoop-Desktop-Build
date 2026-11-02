"""Real TS byte-consumption checks; fake scene renders are protocol diagnostics only."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.adapters.source_program_bridge import FrozenSourceLibrary, ROOT
from src.adapters.script_motif_compiler import digest


def library(path, suffix='old'):
    identity = {'format': 'parameterized_source_program_v1', 'language': 'tsx',
                'template': 'const p=__GENELOOP_PARAMETERS__; // '+suffix,
                'parameters_schema': {'type': 'object', 'properties': {'value': {'type': 'integer'}},
                                      'required': ['value'], 'additionalProperties': False}}
    key = digest(identity)
    program = {**identity, 'id': 'source_'+key[:24], 'description': 'Synthetic source fixture',
               'default_parameters': {'value': 1}, 'status': 'certified',
               'certification': {'source_equivalent': True, 'program_identity': key}}
    body = {'format': 'source_program_library_v1', 'programs': [program]}
    raw = json.dumps({**body, 'digest': digest(body)}).encode()
    path.write_bytes(raw)
    return program, hashlib.sha256(raw).hexdigest()


def bridge(request):
    return subprocess.run(['node', '--experimental-strip-types', str(ROOT/'scripts/materialize-source-program.mjs')],
                          input=json.dumps(request), text=True, capture_output=True, cwd=ROOT, timeout=15)


def test_task_consumes_captured_bytes_after_path_replacement(tmp_path):
    path = tmp_path/'library.json'; original, sha = library(path)
    task = FrozenSourceLibrary(path, expected_sha256=sha, include_source=True)
    expected = task.catalog()['program_versions'][0]
    replacement, _ = library(path, 'replacement')
    out = task.materialize(original['id'], {'value': 9})
    assert out['source'].endswith('// old') and '"value":9' in out['source']
    assert out['source_program_version'] == expected
    assert expected['library_sha256'] == sha
    assert expected['program_sha256'] == original['certification']['program_identity']
    assert expected['certificate_sha256'] == digest(original['certification'])
    assert out['phase'] == 'materialized' and 'native_receipt' not in out
    with pytest.raises(ValueError, match='unknown'): task.materialize(replacement['id'], {'value': 1})
    with pytest.raises(ValueError, match='bytes_changed'): FrozenSourceLibrary(path, expected_sha256=sha)
    assert task.catalog()['programs'][0]['id'] == original['id']


def test_persisted_task_copy_is_exact_and_replacement_fails_closed(tmp_path):
    path = tmp_path/'library.json'; program, sha = library(path)
    task = FrozenSourceLibrary(path); pinned = tmp_path/'frozen.json'; task.save_bytes(pinned)
    assert pinned.read_bytes() == path.read_bytes()
    task.save_bytes(pinned)  # Preview then run can reuse exactly the same snapshot.
    library(pinned, 'changed')
    with pytest.raises(ValueError, match='task_copy_changed'): task.save_bytes(pinned)
    with pytest.raises(ValueError, match='bytes_changed'): FrozenSourceLibrary(pinned, expected_sha256=sha)
    assert task.materialize(program['id'], {'value': 2})['source'].endswith('// old')


def test_pins_library_digest_and_actual_object_certificate(tmp_path):
    path = tmp_path/'library.json'; program, sha = library(path); task = FrozenSourceLibrary(path)
    request = {'library': str(path), 'operation': 'materialize', 'program_id': program['id'],
               'parameters': {'value': 2}, 'expected_library_sha256': sha,
               'expected_program_version': task.catalog()['program_versions'][0]}
    assert bridge(request).returncode == 0
    for key in ('library_sha256', 'library_digest', 'program_sha256', 'certificate_sha256'):
        changed = copy.deepcopy(request); changed['expected_program_version'][key] = 'f'*64
        result = bridge(changed)
        assert result.returncode != 0 and 'source_program_version_changed' in result.stderr
    with pytest.raises(ValueError, match='digest_changed'): FrozenSourceLibrary(path, expected_digest='f'*64)
    changed = copy.deepcopy(request); changed['expected_library_sha256'] = 'f'*64
    assert 'source_library_bytes_changed' in bridge(changed).stderr


def test_legacy_path_protocol_and_default_binding_remain_compatible(tmp_path):
    path = tmp_path/'library.json'; program, _ = library(path)
    catalog = bridge({'operation': 'catalog', 'library': str(path)})
    assert catalog.returncode == 0
    assert json.loads(catalog.stdout)['programs'][0]['id'] == program['id']
    result = bridge({'operation': 'materialize', 'library': str(path), 'program_id': program['id'],
                     'parameters': {}, 'parameter_binding': 'defaults'})
    assert result.returncode == 0 and json.loads(result.stdout)['parameters'] == {'value': 1}
    task = FrozenSourceLibrary(path); exposed = task.catalog(); exposed['program_versions'][0]['certificate_sha256'] = 'f'*64
    assert task.materialize(program['id'], {}, 'defaults')['parameters'] == {'value': 1}


def test_failure_stdio_does_not_echo_private_parameter_text(tmp_path):
    path = tmp_path/'library.json'; program, _ = library(path)
    result = bridge({'library': str(path), 'program_id': program['id'], 'parameters': {'value': 'private-secret-text'}})
    assert result.returncode != 0 and not result.stdout
    assert 'private-secret-text' not in result.stderr
    assert 'source_program_parameters_invalid' in result.stderr


def load_scene_diagnostic(tmp_path, monkeypatch, *, render_fails=False, write_drift=False, receipt_drift=False, late_drift=False):
    path = tmp_path/'library.json'; program, sha = library(path)
    monkeypatch.setenv('REMOTION_SOURCE_LIBRARY', str(path))
    monkeypatch.setenv('REMOTION_SOURCE_LIBRARY_SHA256', sha)
    monkeypatch.delenv('REMOTION_SOURCE_LIBRARY_DIGEST', raising=False)
    work = tmp_path/'task'; work.mkdir()
    state = {'source': None, 'render_calls': 0}
    def current(): return hashlib.sha256(state['source'].encode()).hexdigest()
    def write(text):
        state['source'] = text+' drift' if write_drift else text
        return {'source_version': current()}
    def render(version):
        state['render_calls'] += 1
        if render_fails: raise RuntimeError('private-source-and-parameters must not escape')
        if late_drift: state['source'] += ' changed during render'
        return {'source_version': 'f'*64 if receipt_drift else version, 'video_sha256': hashlib.sha256(b'synthetic-video-receipt').hexdigest(), 'video_path': 'out/video.mp4'}
    scene = SimpleNamespace(WORK=work, LOCK=threading.RLock(), write_source=write,
                            current_source_version=current, render_composition=render)
    spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
    source = ROOT/'scenarios/remotion_edit/structured/program_server.py'
    namespace = {'__file__': str(source), '__name__': 'program_scene_diagnostic'}
    original_spec, original_module = importlib.util.spec_from_file_location, importlib.util.module_from_spec
    def chosen_spec(name, *args, **kwargs):
        return spec if name == 'remotion_structured' else original_spec(name, *args, **kwargs)
    def chosen_module(value):
        return scene if value is spec else original_module(value)
    with patch('importlib.util.spec_from_file_location', side_effect=chosen_spec), patch('importlib.util.module_from_spec', side_effect=chosen_module):
        exec(compile(source.read_text(), str(source), 'exec'), namespace)
    return namespace, path, program, state


def test_scene_receipt_binds_materialized_version_after_path_replacement(tmp_path, monkeypatch):
    scene, path, program, state = load_scene_diagnostic(tmp_path, monkeypatch)
    frozen = scene['list_programs']()['program_versions'][0]; library(path, 'new')
    result = scene['render_program'](program['id'], {'value': 7})
    assert state['source'].endswith('// old') and state['render_calls'] == 1
    receipt = result['native_receipt']
    assert receipt['source_program_version'] == frozen
    assert receipt['phase'] == 'rendered' and receipt['status'] == 'succeeded'
    assert receipt['source_sha256'] == result['source_version']
    assert receipt['video_sha256'] == result['video_sha256']


@pytest.mark.parametrize('write_drift', [False, True])
def test_scene_failure_never_emits_success_receipt(tmp_path, monkeypatch, write_drift):
    scene, _, program, state = load_scene_diagnostic(tmp_path, monkeypatch, render_fails=True, write_drift=write_drift)
    with pytest.raises(Exception, match='source_program_render_failed') as error:
        scene['render_program'](program['id'], {'value': 7})
    assert 'private-source-and-parameters' not in str(error.value)
    rows = [json.loads(line) for line in (tmp_path/'source-program-audit.jsonl').read_text().splitlines()]
    assert [r['kind'] for r in rows] == ['source_program_selected', 'source_program_failed']
    assert all('native_receipt' not in row for row in rows)
    assert state['render_calls'] == (0 if write_drift else 1)


@pytest.mark.parametrize('drift', ['receipt_drift', 'late_drift'])
def test_scene_changed_render_binding_has_no_success_receipt(tmp_path, monkeypatch, drift):
    scene, _, program, state = load_scene_diagnostic(tmp_path, monkeypatch, **{drift: True})
    with pytest.raises(Exception, match='source_program_render_failed'):
        scene['render_program'](program['id'], {'value': 8})
    rows = [json.loads(line) for line in (tmp_path/'source-program-audit.jsonl').read_text().splitlines()]
    assert [r['kind'] for r in rows] == ['source_program_selected', 'source_program_failed']
    assert state['render_calls'] == 1
