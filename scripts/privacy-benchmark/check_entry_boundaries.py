"""Supplemental real privacy-tool checks at research and export boundaries.

Uses existing synthetic fixtures. Paid model calls and artifact assembly are
test doubles; the privacy kernel and JSON/Presidio/Gitleaks calls stay real.
This is entry wiring evidence, separate from the frozen detection benchmarks.
"""
import argparse
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    code = args.code_root.resolve()
    sys.path.insert(0, str(code))
    out = args.output.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    from src.adapters.geneloop_privacy import PrivacyRejected
    from src.adapters.harness.capability import capability_proposal as builder
    from src.adapters.harness.capability import capability_goal_proposal as goals
    from src.rsi.learning import capability_construction_history as history
    from src.rsi.evolution.capability_evolution_investigation import run_investigation
    from tests.test_capability_proposal_loop import inputs, fake_harness
    from tests.test_capability_goal_proposal import FiniteDiagnosticGate
    from tests.test_capability_construction_history import put
    from tests.test_capability_investigation import data, make
    import pytest

    prose = 'Compute RMSE, keep n=128 and 24 fps; email owner@example.com.'
    secret = json.dumps({'password': 'diagnostic-only-not-a-real-credential'})
    rows = []

    def rejects(fn):
        try:
            fn()
        except PrivacyRejected:
            return
        raise AssertionError('expected_privacy_rejection')

    def check(name, fn, doubles):
        started = time.perf_counter()
        try:
            fn()
            rows.append({'id': name, 'passed': True, 'test_doubles': doubles,
                         'seconds': time.perf_counter() - started})
        except Exception as error:
            rows.append({'id': name, 'passed': False, 'error_type': type(error).__name__,
                         'test_doubles': doubles, 'seconds': time.perf_counter() - started})

    def construction(reject):
        task, catalog, snapshot, _ = inputs()
        task['instruction'] = secret if reject else prose
        original = copy.deepcopy(task)
        target = out / ('builder-secret' if reject else 'builder-semantic')
        invoke = lambda: builder.prepare_attempt(task=task, catalog=catalog, snapshot=snapshot, output=target)
        if reject:
            rejects(invoke)
            assert not (target / 'prompt.md').exists()
        else:
            _, prompt = invoke()
            assert 'owner@example.com' not in prompt and 'RMSE' in prompt and 'n=128' in prompt
        assert task == original

    for reject in (False, True):
        check('builder-' + ('reject' if reject else 'semantic'), lambda r=reject: construction(r), [])

    def goal(reject):
        request = {'owner': 'diagnostic-owner', 'trigger_id': 'frozen', 'text': secret if reject else prose}
        original = copy.deepcopy(request)
        with pytest.MonkeyPatch.context() as mp:
            observed = fake_harness(mp, json.dumps({'goals': []}), notifications=True)
            invoke = lambda: goals.propose(request, out / ('goals-secret' if reject else 'goals-semantic'), FiniteDiagnosticGate())
            if reject:
                rejects(invoke)
                assert 'prompt' not in observed
            else:
                invoke()
                assert 'owner@example.com' not in observed['prompt'] and 'RMSE' in observed['prompt']
        assert request == original

    for reject in (False, True):
        check('goal-' + ('reject' if reject else 'semantic'), lambda r=reject: goal(r), ['model Provider', 'budget gate'])

    def construction_history():
        task, catalog, snapshot, _ = inputs()
        task['instruction'] = prose
        task_path = out / 'history-task.json'
        task_ref = put(task_path, task)
        ref = put(out / 'history-view.json', history.build_history([], task_ref))
        library = history.feedback_library({'snapshot': snapshot, 'source_catalog': catalog}, ref,
                                          trigger='construction', budget={'limit_usd': '0', 'email': 'owner@example.com'})
        before = task_path.read_bytes()
        visible = history.model_context(library['source_catalog'], task, snapshot)
        assert 'owner@example.com' not in json.dumps(visible)
        assert task_path.read_bytes() == before
    check('construction-history', construction_history, [])

    def investigation():
        directory = out / 'investigation'; directory.mkdir()
        service = make(directory, data.__wrapped__(directory), objective=prose)
        seen = []
        def agent(request, dispatch):
            seen.append(request)
            assert 'owner@example.com' not in json.dumps(request) and 'RMSE' in json.dumps(request)
            visible = dispatch('evolution_overview', {})
            assert 'owner@example.com' not in json.dumps(visible)
            dispatch('evolution_finish', {'reason': 'diagnostic completed', 'decision': 'inconclusive'})
            return {'diagnostic': True, 'model_requests': 0}
        run_investigation(service, call_agent=agent, handlers={}, output=directory / 'run')
        assert len(seen) == 1 and service.objective == prose
    check('evolution-request-and-tool-result', investigation, ['model callback'])

    spec = importlib.util.spec_from_file_location('diagnostic_export_manifest', code / 'scripts/export-online-motif-manifest.py')
    manifest = importlib.util.module_from_spec(spec); spec.loader.exec_module(manifest)
    spec = importlib.util.spec_from_file_location('diagnostic_export_registry', code / 'scripts/export-efficiency-rsi-registry.py')
    registry = importlib.util.module_from_spec(spec); spec.loader.exec_module(registry)
    empty = out / 'empty.json'; empty.write_text('{}')

    def export_manifest():
        target = out / 'public-manifest.json'
        with patch.object(manifest, 'export_manifest', return_value={'email': 'owner@example.com'}), patch.object(sys, 'argv',
                ['export', '--library', str(empty), '--contracts', str(empty), '--output', str(target), '--public']):
            rejects(manifest.main)
        assert not target.exists()
    check('online-manifest-public-gate', export_manifest, ['certified artifact assembly'])

    def export_registry():
        class PreparedRegistry:
            def __init__(self, *args): pass
            def export(self, refs): return {'password': 'diagnostic-only-not-a-real-credential'}
        stream = io.StringIO()
        with patch.object(registry, 'StudyRequestRegistry', PreparedRegistry), patch.object(sys, 'argv',
                ['export', '--study', str(empty), '--journal', str(empty), '--provider-request-refs', str(empty), '--public']), redirect_stdout(stream):
            rejects(registry.main)
        assert stream.getvalue() == ''
    check('efficiency-registry-public-gate', export_registry, ['prepared registry assembly'])

    def export_operations():
        spec = importlib.util.spec_from_file_location('diagnostic_export_operations', code / 'scripts/export-operation-library.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        workspace = out / 'operation-fixture'; state = workspace / '.local/state'
        registry_path = state / 'registry'; registry_path.mkdir(parents=True)
        (registry_path / 'current.json').write_text(json.dumps({'file': 'view.json'}))
        (registry_path / 'view.json').write_text(json.dumps({'generation': 0, 'entries': [
            {'kind': 'operation_graph', 'state': 'active', 'runtime_source': {}, 'payload': 'policy.json'}]}))
        raw = json.dumps({'email': 'owner@example.com'}).encode()
        (registry_path / 'policy.json').write_bytes(raw)
        target = workspace / 'examples/motif-library/diagnostic'
        with patch.object(module, 'ROOT', workspace):
            rejects(lambda: module.export(state, target))
        assert not target.exists() and (registry_path / 'policy.json').read_bytes() == raw
    check('operation-library-export-before-write', export_operations, ['synthetic registry and workspace root'])

    receipt = {'total': len(rows), 'passed': sum(row['passed'] for row in rows), 'rows': rows,
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'scope': 'supplemental entry wiring; real privacy kernel; synthetic inputs and declared test doubles',
               'benchmark_records_added': 0, 'cloud_requests': 0, 'production_service_touched': False}
    (out / 'summary.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps({'total': receipt['total'], 'passed': receipt['passed']}))
    if receipt['passed'] != receipt['total']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
