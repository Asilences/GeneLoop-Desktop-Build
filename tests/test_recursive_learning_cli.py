"""Public offline entry diagnostics; real Runtime witnesses, no model calls."""
import copy
import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from src.adapters.capability_contract import capability_ref
from src.adapters.capability_feedback import CapabilityFeedback, file_ref
from src.adapters.capability_motif_learning import learn_capability_motifs
from tests.test_capability_evolution_runtime import graph, native, put

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/learn-recursive-capabilities.py'
spec = importlib.util.spec_from_file_location('recursive_learning_cli', SCRIPT)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


@pytest.fixture(scope='module')
def corpus(tmp_path_factory):
    directory = tmp_path_factory.mktemp('recursive-cli-witnesses')
    snapshot = native({'action': 'seed', 'owner': 'rae-cli'})
    traces = [graph(directory, snapshot, 'cli-' + str(i), value) for i, value in enumerate((2, 5, 10))]
    refs = [put(directory / (trace['task_id'] + '.json'), trace) for trace in traces]
    manifest = {'snapshot': put(directory / 'snapshot.json', snapshot), 'training': refs[:2], 'heldout': refs[2:]}
    return snapshot, traces, manifest


def test_preview_checks_evidence_without_mining_and_freezes_actual_sources(tmp_path, corpus, monkeypatch):
    _, _, manifest = corpus
    monkeypatch.setattr(entry, 'learn_capability_motifs', lambda *a, **k: pytest.fail('preview called learner'))
    result = entry.run_manifest(manifest, tmp_path / 'preview', private_root=tmp_path)
    assert result['status'] == 'preview' and result['model_requests'] == 0 and result['candidates'] == []
    effective = json.loads(Path(result['effective']['path']).read_bytes())
    assert effective['execute'] is False and effective['owner'] == 'rae-cli'
    assert 'src/motif_core/offline/trace_compiler.py' in effective['code_sha256']
    assert not (tmp_path / 'preview' / 'learning.json').exists()
    with pytest.raises(FileExistsError):
        entry.run_manifest(manifest, tmp_path / 'preview', private_root=tmp_path)


def test_execute_exports_original_candidates_without_publication(tmp_path, corpus):
    _, _, manifest = corpus
    result = entry.run_manifest(manifest, tmp_path / 'run', execute=True, private_root=tmp_path)
    assert result['status'] == 'completed' and result['candidates'] and result['model_requests'] == 0
    assert result['publication_authorized'] is False and result['budget_credit'] is None
    for row in result['candidates']:
        compiled = json.loads(Path(row['compiled']['path']).read_bytes())
        proposal = json.loads(Path(row['proposal']['path']).read_bytes())
        assert proposal['format'] == 'capability_compose_proposal_v1'
        assert capability_ref(compiled['capability']) == row['capability']
        assert compiled['capability']['certification'] == 'candidate'
        assert compiled['capability']['lifecycle'] == 'build_only'
        assert Path(row['provenance']['path']).is_file() and Path(row['motif']['path']).is_file()
        candidate = json.loads(Path(row['candidate_ref']['path']).read_bytes())
        assert candidate['compiled'] == compiled and candidate['proposal'] == proposal
        assert candidate['provenance']['evidence']
    assert not (tmp_path / 'run' / 'store').exists()


def test_bad_source_and_overlapping_split_preserve_failure_records(tmp_path, corpus):
    _, _, manifest = corpus
    wrong = copy.deepcopy(manifest)
    wrong['training'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='evidence_changed'):
        entry.run_manifest(wrong, tmp_path / 'bad-source', execute=True, private_root=tmp_path)
    failure = json.loads((tmp_path / 'bad-source' / 'failure.json').read_bytes())
    assert failure['status'] == 'failed' and failure['model_requests'] == 0
    overlap = copy.deepcopy(manifest)
    overlap['heldout'] = [overlap['training'][0]]
    with pytest.raises(ValueError, match='independent_tasks_required'):
        entry.run_manifest(overlap, tmp_path / 'bad-split', private_root=tmp_path)
    assert (tmp_path / 'bad-split' / 'failure.json').exists()


def test_public_cli_rejects_output_outside_private_local(tmp_path, corpus):
    _, _, manifest = corpus
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    output = ROOT / ('rae-rejected-output-' + uuid.uuid4().hex)
    assert not output.exists()
    result = subprocess.run([sys.executable, str(SCRIPT), '--manifest', str(manifest_path),
                             '--output', str(output)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0 and 'private_output_required' in result.stderr
    assert not output.exists()


def test_evolution_cli_uses_same_feedback_and_changes_real_mined_boundary(tmp_path, corpus):
    snapshot, traces, manifest = corpus
    full = max(learn_capability_motifs(traces[:2], traces[2:], snapshot)['candidates'],
               key=lambda row: len(row['proposal']['steps']))
    ref = capability_ref(full['compiled']['capability'])
    feedback_root = tmp_path / 'existing-feedback'
    manager = CapabilityFeedback(feedback_root, snapshot['owner'])
    fact_id = manager.observe(stage='execution', subject=ref, scope='local-obligation', status='failed',
                              cost=None, evidence=[traces[0]['evidence'][-1]])
    proposal = {'subject': ref, 'scope': 'local-obligation', 'feedback_ids': [fact_id],
                'regions': {trace['task_id']: ['n0', 'n1'] for trace in traces}}
    manifest = {**copy.deepcopy(manifest), 'evolution': {
        'feedback_directory': str(feedback_root),
        'prior_candidate': put(tmp_path / 'prior.json', full['compiled']),
        'proposal': put(tmp_path / 'boundary.json', proposal)}}
    before = manager.path.read_bytes()
    preview = entry.run_manifest(manifest, tmp_path / 'evolution-preview', private_root=tmp_path)
    assert preview['status'] == 'preview' and manager.path.read_bytes() == before
    result = entry.run_manifest(manifest, tmp_path / 'evolution-run', execute=True, private_root=tmp_path)
    assert result['status'] == 'completed' and manager.path.read_bytes() == before
    for row in result['candidates']:
        compiled = json.loads(Path(row['compiled']['path']).read_bytes())
        assert len(compiled['capability']['implementation']['steps']) == 2
        assert row['capability'] != ref and 'evolution' in row
    assert (tmp_path / 'evolution-run' / 'evolution' / 'feedback.json').is_file()


def test_missing_feedback_preview_does_not_create_account(tmp_path, corpus):
    _, _, manifest = corpus
    missing = tmp_path / 'absent-account'
    manifest = {**copy.deepcopy(manifest), 'evolution': {
        'feedback_directory': str(missing),
        'prior_candidate': put(tmp_path / 'prior.json', {}),
        'proposal': put(tmp_path / 'proposal.json', {})}}
    with pytest.raises(ValueError, match='feedback_missing'):
        entry.run_manifest(manifest, tmp_path / 'rejected', private_root=tmp_path)
    assert not missing.exists()


def test_interrupted_learning_is_recorded_without_retry(tmp_path, corpus, monkeypatch):
    _, _, manifest = corpus
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt('diagnostic cancellation')
    monkeypatch.setattr(entry, 'learn_capability_motifs', interrupted)
    with pytest.raises(KeyboardInterrupt):
        entry.run_manifest(manifest, tmp_path / 'interrupted', execute=True, private_root=tmp_path)
    row = json.loads((tmp_path / 'interrupted' / 'failure.json').read_bytes())
    assert row['status'] == 'interrupted' and row['model_requests'] == 0
