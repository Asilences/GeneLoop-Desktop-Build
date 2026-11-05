"""Synthetic quality-feedback diagnostics, with no model or benefit claim."""
import json
from pathlib import Path

import pytest

from src.adapters.capability_decision_evidence import inspect_decision, record_web_decision
from src.adapters.capability_evolution_agent import model_view, packet
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.capability_investigation import Investigation
from src.adapters.rsi_quality import review_quality
from tests.test_capability_decision_evidence import context, put, source_refs, web_task
from tests.test_capability_feedback import fixture


@pytest.fixture
def reviewed(tmp_path):
    task = web_task(tmp_path)
    rubric = tmp_path / 'rubric.txt'
    rubric.write_text('Check whether the claim is supported, including negation.')
    source = tmp_path / 'source.txt'
    source.write_text('SYNTHETIC SOURCE. The stated result does not hold.')
    request = file_ref(task / 'task.json')
    artifact = file_ref(task / 'events.jsonl')
    seen = []

    def judge(prompt):
        seen.append(prompt)
        return {'checks': [{'id': 'support', 'status': 'failed',
                            'observation': 'Synthetic claim omits the negation.',
                            'evidence_ids': prompt['sources']}]}

    arguments = dict(task_id='task', task=request, artifact=artifact, rubric=file_ref(rubric),
                     sources=[file_ref(source)], required_checks=['support'], evidence_root=tmp_path,
                     evaluator='synthetic-diagnostic', call_judge=judge)
    review_quality(**arguments, directory=tmp_path / 'judge')
    binding = {'evaluation': file_ref(tmp_path / 'judge/quality.json'), 'rubric': file_ref(rubric),
               'artifact': artifact, 'required_checks': ['support'], 'evidence_root': str(tmp_path),
               'role': 'discovery'}
    approved = context(tmp_path / 'approved.json', source_refs(task))
    return task, approved, binding, arguments, seen


def record(tmp_path, reviewed):
    task, approved, binding, _, _ = reviewed
    return record_web_decision(task, 'owner', relation='claim-support', approved_context=approved,
                               output=tmp_path / 'decision.json', quality_review=binding)


def test_completed_execution_retains_failed_semantic_quality_and_original_source(tmp_path, reviewed):
    row = inspect_decision(record(tmp_path, reviewed), 'owner')
    assert row['status'] == 'passed'
    assert row['quality'] == 'failed'
    assert row['observed_cost_usd'] is None
    assert row['evaluation_role'] == 'discovery'
    assert row['quality_findings'][0]['id'] == 'support'
    assert any(Path(ref['path']).name == 'source.txt' for ref in row['evidence'])
    assert len(reviewed[-1]) == 1
    result = json.loads((tmp_path / 'judge/result.json').read_text())
    assert result == {'status': 'failed', 'certification_granted': False}


def test_evolution_queries_quality_and_reads_originals_only_on_demand(tmp_path, reviewed):
    reference = record(tmp_path, reviewed)
    snapshot = fixture(tmp_path)[1]['snapshot']
    entries = [{'split': 'training', 'scope': 'study', 'evidence': reference}]
    service = Investigation(snapshot, entries, 'study', tmp_path / 'investigation', inspector=inspect_decision)
    assert 'omits the negation' not in json.dumps(service.overview())
    cards = service.search('experience', quality='failed', status='passed')
    assert cards['total'] == 1
    row = service.read('experience', cards['items'][0]['id'], 'quality')
    assert row['quality'] == 'failed' and row['total'] == 1
    evidence_id = row['items'][0]['evidence'][0]['id']
    assert 'does not hold' in service.read('evidence', evidence_id, 'content')['content']
    assert str(tmp_path) not in json.dumps(row)
    assert service.search('experience', quality='passed')['total'] == 0


@pytest.mark.parametrize('field', ['task_id', 'task_sha256', 'artifact_sha256', 'rubric_sha256'])
def test_quality_cannot_be_borrowed_from_another_task_or_artifact(tmp_path, reviewed, field):
    binding = reviewed[2]
    value = json.loads(verify(binding['evaluation']))
    value['payload'][field] = 'other-task' if field == 'task_id' else 'a' * 64
    binding['evaluation'] = put(tmp_path / 'changed-quality.json', value)
    with pytest.raises(ValueError, match='quality_.*changed'):
        record(tmp_path, reviewed)


def test_review_evidence_changes_are_rechecked_before_discovery(tmp_path, reviewed):
    reference = record(tmp_path, reviewed)
    (tmp_path / 'source.txt').write_text('Changed after review.')
    with pytest.raises(ValueError, match='quality_evidence_changed'):
        inspect_decision(reference, 'owner')


def test_evaluation_only_quality_is_excluded_from_discovery(tmp_path, reviewed):
    reviewed[2]['role'] = 'evaluation'
    reference = record(tmp_path, reviewed)
    snapshot = fixture(tmp_path)[1]['snapshot']
    entries = [{'split': 'training', 'scope': 'study', 'evidence': reference}]
    with pytest.raises(ValueError, match='evaluation_source_excluded'):
        Investigation(snapshot, entries, 'study', tmp_path / 'investigation', inspector=inspect_decision)
    with pytest.raises(ValueError, match='evaluation_source_excluded'):
        packet(entries, snapshot, 'study', tmp_path / 'packet', inspector=inspect_decision)


def test_one_turn_projection_also_retains_findings_without_local_paths(tmp_path, reviewed):
    row = inspect_decision(record(tmp_path, reviewed), 'owner')
    row['id'] = 'observation'
    content = {'format': 'diagnostic', 'stage': 'execution', 'independent_sources': 1,
               'inventory': {}, 'max_candidates': 2, 'omitted_observations': 0,
               'cost_claim': 'unknown', 'capabilities': [], 'observations': [row]}
    projected, _ = model_view(content)
    assert projected['observations'][0]['quality_findings'][0]['status'] == 'failed'
    assert str(tmp_path) not in json.dumps(projected)


@pytest.mark.parametrize('status', ['passed', 'unknown'])
def test_judge_retains_correct_controls_and_insufficient_evidence(tmp_path, reviewed, status):
    arguments = reviewed[3].copy()
    arguments['call_judge'] = lambda prompt: json.dumps({'checks': [
        {'id': 'support', 'status': status, 'observation': 'Synthetic control.',
         'evidence_ids': prompt['sources'] if status == 'passed' else []}]})
    actual = review_quality(**arguments, directory=tmp_path / status)
    assert actual['payload']['checks'][0]['status'] == status


def test_fabricated_judge_evidence_retains_failure_and_no_quality_receipt(tmp_path, reviewed):
    arguments = reviewed[3].copy()
    arguments['call_judge'] = lambda prompt: {'checks': [
        {'id': 'support', 'status': 'passed', 'observation': 'Invalid citation.',
         'evidence_ids': ['not-in-host-sources']}]}
    with pytest.raises(ValueError, match='quality_judge_evidence_invalid'):
        review_quality(**arguments, directory=tmp_path / 'invalid')
    assert (tmp_path / 'invalid/response.json').is_file()
    assert not (tmp_path / 'invalid/quality.json').exists()
    assert json.loads((tmp_path / 'invalid/result.json').read_text())['quality'] == 'unknown'


def test_source_mutation_during_judging_is_not_accepted(tmp_path, reviewed):
    arguments = reviewed[3].copy()

    def judge(prompt):
        (tmp_path / 'source.txt').write_text('Changed during model call.')
        return {'checks': [{'id': 'support', 'status': 'passed', 'observation': 'Synthetic.',
                            'evidence_ids': prompt['sources']}]}

    arguments['call_judge'] = judge
    with pytest.raises(ValueError, match='evidence_changed'):
        review_quality(**arguments, directory=tmp_path / 'mutation')
    assert not (tmp_path / 'mutation/quality.json').exists()


def test_missing_required_check_retains_original_response(tmp_path, reviewed):
    arguments = reviewed[3].copy()
    arguments['call_judge'] = lambda prompt: {'checks': []}
    with pytest.raises(ValueError, match='required_checks_missing'):
        review_quality(**arguments, directory=tmp_path / 'missing')
    assert (tmp_path / 'missing/response.json').is_file()
    assert not (tmp_path / 'missing/quality.json').exists()


def test_invalid_task_identity_is_rejected_before_model_callback(tmp_path, reviewed):
    arguments = reviewed[3].copy()
    arguments['task_id'] = ''
    before = len(reviewed[-1])
    with pytest.raises(ValueError, match='identifier_invalid'):
        review_quality(**arguments, directory=tmp_path / 'invalid-task')
    assert len(reviewed[-1]) == before


def test_existing_strategy_cli_preview_consumes_quality_without_provider_calls(tmp_path, reviewed):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('quality_strategy_cli', root / 'scripts/run-strategy-evolution.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.ROOT = tmp_path
    code = tmp_path / 'src/adapters/capability_evolution_agent.py'
    code.parent.mkdir(parents=True)
    code.write_bytes((root / 'src/adapters/capability_evolution_agent.py').read_bytes())
    entries = [{'split': 'training', 'scope': 'paper', 'evidence': record(tmp_path, reviewed)}]
    second = web_task(tmp_path, identity='second', source='independent-second')
    arguments = {**reviewed[3], 'task_id': 'second', 'task': file_ref(second / 'task.json'),
                 'artifact': file_ref(second / 'events.jsonl')}
    review_quality(**arguments, directory=tmp_path / 'second-review')
    binding = {**reviewed[2], 'evaluation': file_ref(tmp_path / 'second-review/quality.json'),
               'artifact': arguments['artifact']}
    approved = context(tmp_path / 'second-approved.json', source_refs(second))
    reference = record_web_decision(second, 'owner', relation='claim-support', approved_context=approved,
        output=tmp_path / 'second-decision.json', quality_review=binding)
    entries.append({'split': 'training', 'scope': 'paper', 'evidence': reference})
    snapshot = put(tmp_path / 'snapshot.json', fixture(tmp_path)[1]['snapshot'])
    host = tmp_path / 'host.py'
    host.write_text('raise RuntimeError("Preview must not evaluate candidates")')
    manifest = put(tmp_path / 'manifest.json', {'snapshot': snapshot, 'observations': entries,
        'scope': 'paper', 'target': 'task', 'feedback_directory': str(tmp_path / 'feedback'),
        'ledger_root': str(tmp_path / 'ledger'), 'host_adapter': file_ref(host)})
    output = tmp_path / '.local/preview'
    result = cli.execute(manifest, output, budget_usd='0')
    assert result['status'] == 'preview' and result['model_requests'] == 0
    visible = json.loads((output / 'external-context.json').read_text())
    assert visible['independent_sources'] == 2
    assert all(row['quality'] == 'failed' for row in visible['observations'])
    assert all(row['quality_findings'][0]['id'] == 'support' for row in visible['observations'])
    assert 'PRIVATE' not in json.dumps(visible)
    assert not (tmp_path / 'ledger').exists()
