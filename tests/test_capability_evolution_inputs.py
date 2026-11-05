"""Input-boundary diagnostics; fixture evidence is not a research trajectory."""
import json
from pathlib import Path

import pytest

from src.adapters.capability_construction_history import capture
from src.adapters.capability_contract import capability_ref, create_capability_snapshot
from src.adapters.capability_decision_evidence import CONTEXT_FORMAT, record_construction_decision
from src.adapters.capability_evolution_inputs import load_builder_input_manifest
from src.adapters.capability_feedback import file_ref
from tests.test_capability_builder import setup


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


def valid_fixture(tmp_path):
    original, _ = setup()
    caps = [{**cap, 'certification': 'certified', 'lifecycle': 'active'}
            for cap in original['capabilities']]
    snapshot = create_capability_snapshot('owner', original['roots'], caps)
    focus = capability_ref(caps[0])
    refs = []
    for index in range(2):
        task = put(tmp_path / f'task-{index}.json', {'id': f'task-{index}', 'instruction': 'Build a checker'})
        attempt = tmp_path / f'attempt-{index}'
        attempt.mkdir()
        put(attempt / 'result.json', {'status': 'failed', 'model_called': False,
             'provider_requests': 0, 'request_ids': [], 'error': 'interface_incompatible'})
        record = capture({'id': f'goal-{index}', 'task': task}, attempt, snapshot,
                         output=tmp_path / f'construction-{index}.json')
        sources = [task, record, file_ref(attempt / 'result.json')]
        approved = put(tmp_path / f'approved-{index}.json', {
            'format': CONTEXT_FORMAT, 'owner': 'owner', 'source_evidence': sources,
            'objective': 'Build a reusable checker', 'state': 'The attempt failed at an interface boundary',
            'remaining_judgments': ['Inspect whether existing abstractions were usable'],
            'interactions': [], 'outcome': 'Construction failed; no quality claim.'})
        refs.append(record_construction_decision([record], task, 'owner', relation='checker-construction',
            approved_context=approved, output=tmp_path / f'decision-{index}.json', capabilities=[focus]))
    manifest = put(tmp_path / 'manifest.json', {
        'format': 'capability_evolution_builder_inputs_v1', 'owner': 'owner', 'scope': 'paper-research',
        'exposure': 'historically_exposed', 'snapshot': put(tmp_path / 'snapshot.json', snapshot),
        'focus_capability': focus, 'construction_observations': refs})
    return manifest, snapshot, focus, refs


def test_manifest_connects_certified_capability_and_independent_builder_evidence(tmp_path):
    manifest, snapshot, focus, refs = valid_fixture(tmp_path)
    loaded = load_builder_input_manifest(manifest, expected_owner='owner', expected_scope='paper-research')
    assert loaded['snapshot']['digest'] == snapshot['digest']
    assert loaded['focus_capability'] == focus
    assert loaded['independent_builder_sources'] == 2
    assert [row['evidence'] for row in loaded['entries']] == refs
    assert all(row['split'] == 'training' and row['scope'] == 'paper-research' for row in loaded['entries'])


@pytest.mark.parametrize('change, error', [
    ('owner', 'identity_or_role_invalid'),
    ('scope', 'identity_or_role_invalid'),
    ('role', 'identity_or_role_invalid'),
    ('one_source', 'independent_builder_observations_required'),
    ('duplicate_source', 'sources_not_independent'),
    ('foreign_owner', 'decision_evidence_owner_changed'),
    ('missing_capability', 'builder_capability_not_available'),
])
def test_manifest_rejects_mismatched_or_insufficient_inputs(tmp_path, change, error):
    manifest, snapshot, focus, refs = valid_fixture(tmp_path)
    value = json.loads(Path(manifest['path']).read_text(encoding='utf-8'))
    if change == 'owner': value['owner'] = 'other'
    elif change == 'scope': value['scope'] = 'other'
    elif change == 'role': value['exposure'] = 'sealed_evaluation'
    elif change == 'one_source': value['construction_observations'] = refs[:1]
    elif change == 'duplicate_source': value['construction_observations'] = [refs[0], refs[0]]
    elif change == 'foreign_owner':
        row = json.loads(Path(refs[0]['path']).read_text(encoding='utf-8')); row['owner'] = 'other'
        foreign = put(tmp_path / 'foreign.json', row)
        value['construction_observations'] = [foreign, refs[1]]
    elif change == 'missing_capability':
        row = json.loads(Path(refs[0]['path']).read_text(encoding='utf-8')); row['capabilities'] = []
        missing = put(tmp_path / 'missing.json', row)
        value['construction_observations'] = [missing, refs[1]]
    changed = put(tmp_path / f'{change}.json', value)
    with pytest.raises(ValueError, match=error):
        load_builder_input_manifest(changed, expected_owner='owner', expected_scope='paper-research')


def test_manifest_rejects_uncertified_focus_capability(tmp_path):
    manifest, snapshot, focus, _ = valid_fixture(tmp_path)
    caps = [{**cap, 'certification': 'candidate'} if cap['id'] == focus['id'] else cap
            for cap in snapshot['capabilities']]
    invalid_snapshot = create_capability_snapshot('owner', snapshot['roots'], caps)
    value = json.loads(Path(manifest['path']).read_text(encoding='utf-8'))
    value['snapshot'] = put(tmp_path / 'uncertified-snapshot.json', invalid_snapshot)
    changed = put(tmp_path / 'uncertified-manifest.json', value)
    with pytest.raises(ValueError, match='focus_capability_not_certified_active'):
        load_builder_input_manifest(changed, expected_owner='owner', expected_scope='paper-research')
