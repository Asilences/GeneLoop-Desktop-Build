"""Changed dependencies invalidate current locks without changing historical evidence."""
import hashlib
from pathlib import Path

import pytest

from src.adapters import continuous_rsi
from src.adapters.experience_library import sources
from src.adapters.mcp_learning import ManagementOperations

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ('src/adapters/model_transport.py', 'config/geneloop-transport.json')
TRACE = 'src/adapters/geneloop_task_trace.ts'


@pytest.mark.parametrize('name', [*TRANSPORT, TRACE])
def test_new_dependency_changes_learner_evidence_digest(tmp_path, monkeypatch, name):
    assert name in continuous_rsi.LEARNER
    original = (ROOT / name).read_bytes()
    target = tmp_path / name
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    monkeypatch.setattr(continuous_rsi, 'ROOT', tmp_path)
    before = continuous_rsi.source_map([name])
    assert before[name] == hashlib.sha256(original).hexdigest()
    target.write_bytes(original + b'\n')
    assert continuous_rsi.source_map([name])[name] != before[name]


@pytest.mark.parametrize('name', TRANSPORT)
def test_file_public_runtime_lock_includes_imported_transport(tmp_path, monkeypatch, name):
    assert name in ManagementOperations().runtime_sources()
    current = sources()
    assert current[name] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    for source in ManagementOperations().runtime_sources():
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    monkeypatch.setattr(continuous_rsi, 'ROOT', tmp_path)
    assert sources() == current
    target = tmp_path / name
    target.write_bytes(target.read_bytes() + b'\n')
    changed = sources()
    assert {key for key in current if current[key] != changed[key]} == {name}


def test_task_mirror_is_wider_web_evidence_not_standalone_file_runtime():
    assert TRACE in continuous_rsi.LEARNER
    assert TRACE not in ManagementOperations().runtime_sources()

def test_reviewed_relocation_keeps_the_enrolled_source_binding(tmp_path, monkeypatch):
    from src.adapters.operation_runner import recovery_source_transition
    from src.motif_core.reuse.experience_registry import digest, durable

    name = 'src/adapters/scenario.py'
    before = {name: 'a' * 64}
    after = {name: 'b' * 64}
    pair = {'before_sha256': digest(before), 'after_sha256': digest(after)}
    durable(tmp_path / 'config/file-management-runtime-compatibility.json',
            {'schema_version': 1, 'enrollment_source_relocations': [pair]})
    origin = tmp_path / 'origin'
    durable(origin / 'source-code.json', before)
    durable(origin / 'enrollment.json', {'source_sha256': digest(before)})
    monkeypatch.setattr(continuous_rsi, 'ROOT', tmp_path)

    assert recovery_source_transition(origin, tmp_path, after) == {**pair, 'scope': 'reviewed_adapter_relocation'}
    assert continuous_rsi.reviewed_source_relocation(before, {**after, 'different.py': 'c' * 64}) is None
    durable(origin / 'enrollment.json', {'source_sha256': 'c' * 64})
    with pytest.raises(ValueError, match='original enrolled code changed'):
        recovery_source_transition(origin, tmp_path, after)


def test_archived_entry_plugin_rebinds_without_rewriting_yml_environment_tags(tmp_path, monkeypatch):
    import json
    from src.adapters import operation_runner

    monkeypatch.setattr(operation_runner, 'ROOT', tmp_path)
    old = {'id': 'sss-entry-motif', 'name': (tmp_path / 'src/adapters/file_entry_motif.ts').as_uri()}
    tag = '- id: worker\n  config:\n    path: !env "FM_JOB_FILE"\n'
    original = tmp_path / 'scene.patch.yml'
    value = tag + '- {"insert": [' + json.dumps(old) + ']}\n'
    original.write_text(value)
    result = Path(operation_runner.relocated_scene_patch(str(original), tmp_path)).read_text()
    assert original.read_text() == value
    assert result.startswith(tag)
    plugin = json.loads(result[len(tag) + 2:])['insert'][0]
    assert plugin == {'id': old['id'],
                      'name': (tmp_path / 'src/adapters/harness/motif/dsh_entry_motif.ts').as_uri(),
                      'config': {'durablePlan': True}}


def test_relocated_operation_binding_checks_original_and_preserves_other_fields(tmp_path, monkeypatch):
    from src.adapters import operation_runner
    from src.motif_core.reuse.experience_registry import durable, read, sha

    name = 'src/adapters/scenario.py'
    target = tmp_path / name
    target.parent.mkdir(parents=True)
    target.write_text('# relocated launcher\n')
    monkeypatch.setattr(operation_runner, 'ROOT', tmp_path)
    old = {name: 'a' * 64}
    original = tmp_path / 'operation-binding.json'
    payload = {'runtime_source': {**old, 'other.py': 'b' * 64},
               'task_sha256': 'c' * 64, 'registry_sha256': 'd' * 64}
    durable(original, payload)
    binding = read(operation_runner.relocated_operation_binding(original, tmp_path, old))
    assert read(original) == payload
    assert binding == {**payload, 'runtime_source': {**payload['runtime_source'], name: sha(target)}}
    with pytest.raises(ValueError, match='original operation launcher binding changed'):
        operation_runner.relocated_operation_binding(original, tmp_path, {name: 'e' * 64})
