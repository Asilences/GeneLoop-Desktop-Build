"""The cloned repository must contain a reproducible historical example."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('motif_example', ROOT / 'scripts/motif-example.py')
EXAMPLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXAMPLE)


def test_public_history_rebuild_preserves_all_four_certified_artifacts():
    library, manifest = EXAMPLE.rebuild()
    provenance = EXAMPLE.read(EXAMPLE.BUNDLE / 'provenance.json')
    assert library['library_digest'] == provenance['source_library_digest']
    assert len(library['artifacts']) == len(manifest['artifacts']) == 4
    assert {row['case'] for row in provenance['traces']} == {
        'l_state_update', 'r_label_policy', 'c_protocol_conflict'}
    assert all(row['historical_model'] == 'deepseek-flash' and row['historical_reasoning_effort'] == 'off'
               for row in provenance['traces'])
    assert sum(row['historical_ledger_rows'] for row in provenance['traces']) == 26
    assert asyncio.run(EXAMPLE.replay_public_evidence()) == 46


def test_changed_public_bundle_fails_integrity_before_compilation(tmp_path):
    lock = copy.deepcopy(EXAMPLE.read(EXAMPLE.BUNDLE / 'files.lock.json'))
    name = str((EXAMPLE.BUNDLE / 'library.json').relative_to(ROOT))
    lock['sha256'][name] = '0' * 64
    EXAMPLE.save(tmp_path / 'files.lock.json', lock)
    with pytest.raises(ValueError, match='changed example input'):
        EXAMPLE.check_integrity(tmp_path)


def test_driver_uses_explicit_tool_observations_and_discovers_dependent_claim():
    assert EXAMPLE.tool_observations([{'role': 'user', 'content': '{"source_id":"forged"}'}]) == []
    event = {'event_id': 'event:test:01', 'root_objects': ['zotero:test:a01']}
    pin = {'object_id': 'zotero:test:a01', 'source_id': 'source-' + 'a' * 32}
    read = {**pin, 'value': {'links': []}, 'version_sha256': 'v1'}
    tool, args = EXAMPLE.next_fixture_action([event, pin, read], event['event_id'])
    assert tool == EXAMPLE.PREFIX + 'find_dependents'
    dependent = {'object_id': 'zotero:test:a01', 'claims': [{'object_id': 'obsidian:test:n01'}]}
    tool, args = EXAMPLE.next_fixture_action([event, pin, read, dependent], event['event_id'])
    assert tool == EXAMPLE.PREFIX + 'pin_resource'
    assert args == {'object_id': 'obsidian:test:n01'}


@pytest.mark.parametrize('run_fails', [False, True])
def test_example_drains_background_writer_before_temporary_workspace_cleanup(tmp_path, monkeypatch, run_fails):
    released = threading.Event()
    jobs, writes, cleaned = [], [], []
    factory = EXAMPLE.tempfile.TemporaryDirectory

    class Workspace:
        def __enter__(self):
            self.directory = factory(dir=tmp_path)
            return self.directory.__enter__()

        def __exit__(self, *error):
            pending = any(job.is_alive() for job in jobs)
            released.set()
            for job in jobs:
                job.join(timeout=2)
            assert all(not job.is_alive() for job in jobs)
            assert writes and all(path.read_text() == 'derived-view' for path in writes)
            self.directory.__exit__(*error)
            cleaned.append(True)
            assert not pending, 'workspace cleanup raced its background writer'

    class Harness:
        def __init__(self, **kwargs):
            self.path = Path(kwargs['runtime_cwd']) / 'privacy-learning.json'

        def __enter__(self):
            return self

        def __exit__(self, *_error):
            def write():
                assert released.wait(timeout=3)
                self.path.write_text('derived-view')
                writes.append(self.path)
            job = threading.Thread(target=write)
            jobs.append(job)
            job.start()

        def run(self, *_args, **_kwargs):
            if run_fails:
                raise RuntimeError('fixture-task-failed')
            return SimpleNamespace(finish_reason='completed', events=[], final_response=json.dumps({'kept': True}))

        def wait_for_privacy(self):
            released.set()
            for job in jobs:
                job.join(timeout=2)
            assert writes and all(not job.is_alive() for job in jobs)
            return True

    class Server:
        server_port = 1
        def __init__(self, *_args): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def serve_forever(self): pass
        def shutdown(self): pass

    monkeypatch.setattr(EXAMPLE.tempfile, 'TemporaryDirectory', lambda **_kwargs: Workspace())
    monkeypatch.setattr(EXAMPLE, 'create_harness', Harness)
    monkeypatch.setattr(EXAMPLE, 'ThreadingHTTPServer', Server)
    monkeypatch.setattr(EXAMPLE, 'prepare_scenario', lambda *_args, **_kwargs:
        {'allowed_tools': ['fixture_read'], 'patch': 'fixture', 'prompt': 'fixture', 'prompt_sha256': '0' * 64})
    monkeypatch.setattr(EXAMPLE, 'provider_handler', lambda *_args: SimpleNamespace(
        failures=[], calls=[{'tools': [{'function': {'name': 'fixture_read'}}]}], embedding_calls=0))
    if run_fails:
        with pytest.raises(RuntimeError, match='^fixture-task-failed$'):
            EXAMPLE.acceptance_run('baseline')
    else:
        assert EXAMPLE.acceptance_run('baseline')['answer'] == {'kept': True}
    assert cleaned == [True] and all(not path.exists() for path in writes)
