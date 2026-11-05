"""T1–T12 deterministic protocol regressions; these are not model results."""
import copy
import json

import pytest

from src.adapters.capability_feedback import file_ref
from src.adapters.capability_improvement import save
from src.adapters.capability_investigation import Investigation
from src.adapters.capability_evolution_investigation import run_investigation
from src.adapters.rsi_quality import compare_research_outcomes
from tests.test_capability_investigation import data, inspect, make, put
from tests.test_capability_evolution_investigation import candidate


def test_t1_shared_source_family_does_not_increase_independence(tmp_path, data):
    snapshot, entries, catalog = data
    first = json.loads(file_ref_value(entries[0]['evidence']))
    second = json.loads(file_ref_value(entries[1]['evidence']))
    second['source_identity'] = first['source_identity']
    entries[1]['evidence'] = put(tmp_path / 'derived.json', second)
    service = make(tmp_path, data)
    assert service.overview()['experiences']['observations'] == 3
    assert service.overview()['experiences']['independent_sources'] == 2


def file_ref_value(reference):
    from src.adapters.capability_feedback import verify
    return verify(reference)


def test_t2_tasks_and_repeats_remain_separate(tmp_path, data):
    row = json.loads(file_ref_value(data[1][0]['evidence']))
    row['task_id'] = 'another-objective-on-same-source'
    data[1].append({'split': 'training', 'scope': 'study',
                    'evidence': put(tmp_path / 'another-task.json', row)})
    service = make(tmp_path, data)
    assert service.overview()['experiences']['observations'] == 4
    assert service.overview()['experiences']['independent_sources'] == 3


def test_t3_steps_are_expandable_to_original_evidence(tmp_path, data):
    service = make(tmp_path, data)
    identifier = service.search('experience')['items'][0]['id']
    assert service.read('experience', identifier, 'steps')['items']
    references = service.read('experience', identifier, 'evidence')['items']
    assert all(service.read('evidence', ref['id'], 'content')['content'] for ref in references)


def test_t4_model_hypothesis_does_not_rewrite_observed_steps(tmp_path, data):
    service = make(tmp_path, data)
    identifier = service.search('experience')['items'][0]['id']
    before = copy.deepcopy(service.context([identifier])['observations'])
    service.note('Possible shared cause, not established', [identifier], ['Inspect counterexample'])
    assert service.context([identifier])['observations'] == before
    assert service.notes[-1]['authorship'] == 'model_interpretation'


def test_t5_certified_capability_is_not_automatic_quality(tmp_path, data):
    service = make(tmp_path, data)
    cards = service.search('experience')['items']
    assert all(card['quality'] == 'unreviewed' for card in cards)
    assert service.overview()['capabilities']['selectable'] > 0


def test_t6_single_source_requires_explicit_local_host(tmp_path, data):
    def agent(request, dispatch):
        identifier = dispatch('evolution_search', {'kind': 'experience'})['items'][0]['id']
        proposal = candidate([identifier])
        proposal.pop('scope')
        result = dispatch('evolution_submit', {'candidate': proposal, 'observation_ids': [identifier]})
        assert result['outcome']['admission_scope'] == 'local'
        dispatch('evolution_finish', {'reason': 'Local candidate awaits later evidence', 'decision': 'proposal'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': lambda value, context, path: {
            'status': 'pending', 'admission_scope': context['admission_scope']}},
        output=tmp_path / 'local', local_only=True)
    assert result['status'] == 'completed'
    assert result['production_enabled'] is False


@pytest.fixture
def policy(tmp_path):
    return put(tmp_path / 'frozen-policy.json', {'quality_tolerance': '0', 'cost_tolerance_usd': '0.001',
        'minimum_samples': 1, 'max_cost_increase_ratio': '0.25', 'min_quality_gain': '0.01',
        'minimum_quality': '0.8'})


def outcome(quality, cost):
    return {'quality': quality, 'cost_usd': cost, 'samples': 1}


@pytest.mark.parametrize('before,after,effect,publication', [
    (outcome(1, '.10'), outcome(1, '.08'), 'positive', 'eligible_scoped'),
    (outcome('.8', '.10'), outcome(1, '.12'), 'mixed', 'eligible_scoped'),
    (outcome('.8', '.10'), outcome(1, '.14'), 'mixed', 'research_only'),
    (outcome(1, '.10'), outcome('.7', '.05'), 'mixed', 'research_only'),
    (outcome(1, '.10'), outcome(1, '.10'), 'neutral', 'retain_current'),
    (outcome(1, '.10'), outcome(1, '.12'), 'negative', 'research_only'),
    (outcome(1, '.10'), outcome(1, None), 'inconclusive', 'pending')])
def test_t7_independent_effect_and_publication_dimensions(policy, before, after, effect, publication):
    result = compare_research_outcomes(before, after, policy)
    assert (result['effect'], result['publication']) == (effect, publication)


def test_t8_receiver_exposure_is_not_semantic_adoption(tmp_path, data):
    def agent(request, dispatch):
        dispatch('evolution_finish', {'reason': 'No supported improvement', 'decision': 'no_change'})
        return {'status': 'completed'}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'run')
    assert result['actual_adoption'] is None and result['measured_net_benefit'] is None


def test_t9_sealed_raw_summary_and_statistics_cannot_be_indexed(tmp_path, data):
    protected = [put(tmp_path / (name + '.json'), {'sealed': name}) for name in ('answer', 'summary', 'statistics')]
    snapshot, entries, catalog = data
    service = Investigation(snapshot, entries, 'study', tmp_path / 'isolation',
                            inspector=inspect, catalog=catalog, sealed_evidence=protected)
    for ref in protected:
        with pytest.raises(ValueError, match='sealed_evidence_excluded'):
            service._index_evidence([ref])
    with pytest.raises(ValueError, match='sealed_evidence_excluded'):
        service._index_evidence([{'path': protected[0]['path'], 'sha256': 'f' * 64}])


def test_t9_development_exposure_does_not_unlock_sealed(tmp_path, data):
    dev = put(tmp_path / 'development.json', {'observed': 'development feedback'})
    sealed = put(tmp_path / 'sealed.json', {'private': 'sealed outcome'})
    snapshot, entries, catalog = data
    service = Investigation(snapshot, entries, 'study', tmp_path / 'roles', inspector=inspect,
        catalog=catalog, sealed_evidence=[sealed], development_evidence=[dev])
    with pytest.raises(ValueError, match='sealed_evidence_excluded'):
        service._index_evidence([dev])
    service.expose_development()
    assert service.read('evidence', 'evidence_' + dev['sha256'], 'content')['content']
    with pytest.raises(ValueError, match='sealed_evidence_excluded'):
        service._index_evidence([sealed])


def test_t10_research_comparison_never_changes_production(policy):
    result = compare_research_outcomes(outcome(1, '.10'), outcome(1, '.08'), policy)
    assert result['production_default_changed'] is False
    assert result['policy'] == policy


def test_t11_step_exhaustion_is_inconclusive(tmp_path, data):
    def agent(request, dispatch):
        dispatch('evolution_overview', {})
        assert dispatch('evolution_overview', {})['status'] == 'error'
        dispatch('evolution_finish', {'reason': 'Tool bound reached', 'decision': 'no_change'})
        return {'timed_out': False}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={},
                               output=tmp_path / 'bounded', max_tool_calls=1, timeout_seconds=60)
    assert result['status'] == 'inconclusive'


def test_t12_no_change_revisit_and_new_evidence(tmp_path, data):
    def agent(request, dispatch):
        dispatch('evolution_finish', {'reason': 'Completed current investigation', 'decision': 'no_change'})
        return {}
    first = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'first')
    prior = file_ref(tmp_path / 'first/result.json')
    second_service = Investigation(data[0], data[1], 'study', tmp_path / 'again', inspector=inspect, catalog=data[2])
    second = run_investigation(second_service, call_agent=lambda *_: pytest.fail('must skip model'),
                               handlers={}, output=tmp_path / 'second', prior_results=[prior])
    assert second['status'] == 'revisit_skipped'
    changed_service = Investigation(data[0], data[1], 'study', tmp_path / 'changed', inspector=inspect,
                                    catalog=data[2], objective='New evidence-backed objective')
    third = run_investigation(changed_service, call_agent=agent, handlers={}, output=tmp_path / 'third', prior_results=[prior])
    assert third['investigation_identity'] != first['investigation_identity']


def test_t12_incomplete_investigation_cannot_be_no_change(tmp_path, data):
    def agent(request, dispatch):
        rejected = dispatch('evolution_finish', {'reason': 'Not enough evidence', 'decision': 'no_change'})
        assert rejected['status'] == 'error'
        dispatch('evolution_finish', {'reason': 'Original evidence not yet investigated', 'decision': 'inconclusive'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={},
                               output=tmp_path / 'unfinished', require_no_change_evidence=True)
    assert result['status'] == 'inconclusive'


def test_t12_completed_no_change_has_original_read_and_note(tmp_path, data):
    def agent(request, dispatch):
        observation = dispatch('evolution_search', {'kind': 'experience'})['items'][0]
        evidence = dispatch('evolution_read', {'kind': 'experience', 'id': observation['id'], 'section': 'evidence'})['items'][0]
        dispatch('evolution_read', {'kind': 'evidence', 'id': evidence['id'], 'section': 'content'})
        dispatch('evolution_note', {'hypothesis': 'No supported change for the current evidence',
                                   'evidence_ids': [observation['id']], 'next_questions': []})
        dispatch('evolution_finish', {'reason': 'Completed evidence investigation', 'decision': 'no_change'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={},
                               output=tmp_path / 'completed', require_no_change_evidence=True)
    assert result['status'] == 'no_change'


def test_t9_shared_development_and_sealed_bytes_remain_sealed(tmp_path, data):
    shared = put(tmp_path / 'shared.json', {'same': 'derived bytes'})
    snapshot, entries, catalog = data
    service = Investigation(snapshot, entries, 'study', tmp_path / 'shared-roles', inspector=inspect,
        catalog=catalog, sealed_evidence=[shared], development_evidence=[shared])
    service.expose_development()
    with pytest.raises(ValueError, match='sealed_evidence_excluded'):
        service._index_evidence([shared])


def test_t12_default_evidence_read_and_evaluated_hypothesis_allow_no_change(tmp_path, data):
    def agent(request, dispatch):
        rows = dispatch('evolution_search', {'kind': 'experience'})['items']
        identifiers = [row['id'] for row in rows[:2]]
        evidence = dispatch('evolution_read', {'kind': 'experience', 'id': identifiers[0],
                                             'section': 'evidence'})['items'][0]
        read = dispatch('evolution_read', {'kind': 'evidence', 'id': evidence['id']})
        assert read['content']
        dispatch('evolution_note', {'hypothesis': 'Tested method has no measured advantage',
                                   'evidence_ids': identifiers, 'next_questions': []})
        submitted = dispatch('evolution_submit', {'candidate': candidate(identifiers),
                                                 'observation_ids': identifiers})
        assert submitted['status'] == 'submitted'
        finished = dispatch('evolution_finish', {'reason': 'Neutral independent result, retain current method',
                                                'decision': 'no_change'})
        assert finished['status'] == 'finished'
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': lambda *_: {'status': 'evaluated', 'effect': 'neutral'}},
        output=tmp_path / 'default-read', require_no_change_evidence=True)
    assert result['status'] == 'no_change'
    assert len(result['submissions']) == 1
    assert result['actual_adoption'] is None


def test_t12_relocated_reference_does_not_repeat_completed_investigation(tmp_path, data):
    original = json.loads(file_ref_value(data[1][0]['evidence']))
    material = put(tmp_path / 'material.json', {'original': 'same bytes'})
    original['projection_reference'] = material
    data[1][0]['evidence'] = put(tmp_path / 'projection-one.json', original)
    def agent(request, dispatch):
        dispatch('evolution_finish', {'reason': 'No further supported change', 'decision': 'no_change'})
        return {}
    first = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'first')
    relocated = put(tmp_path / 'relocated.json', {'original': 'same bytes'})
    original['projection_reference'] = relocated
    data[1][0]['evidence'] = put(tmp_path / 'projection-two.json', original)
    service = Investigation(data[0], data[1], 'study', tmp_path / 'again', inspector=inspect, catalog=data[2])
    second = run_investigation(service, call_agent=lambda *_: pytest.fail('must reuse completed decision'),
        handlers={}, output=tmp_path / 'second', prior_results=[file_ref(tmp_path / 'first/result.json')])
    assert first['investigation_identity'] == second['investigation_identity']
    assert second['status'] == 'revisit_skipped'


def test_rejected_only_attempt_does_not_finish_as_proposal(tmp_path, data):
    def agent(request, dispatch):
        identifiers = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        proposed = candidate(identifiers)
        proposed.pop('burden')
        rejected = dispatch('evolution_submit', {'candidate': proposed, 'observation_ids': identifiers})
        assert rejected['status'] == 'rejected'
        rejected_finish = dispatch('evolution_finish', {'reason': 'Invalid attempted candidate', 'decision': 'proposal'})
        assert 'proposal_requires_valid_candidate' in rejected_finish['error']
        dispatch('evolution_finish', {'reason': 'No valid proposal after the failed attempt'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'invalid-only')
    assert result['status'] == 'inconclusive'
    assert result['investigation_decision'] == 'inconclusive'
    assert result['candidate_counts']['attempted'] == 1
    assert result['candidate_counts']['schema_and_evidence_valid'] == 0
    assert result['candidate_counts']['host_evaluations_started'] == 0


def test_investigation_completion_keeps_failed_independent_admission(tmp_path, data):
    def handler(*_):
        raise ValueError('independent_quality_failed')
    def agent(request, dispatch):
        identifiers = [row['id'] for row in dispatch('evolution_search', {'kind': 'experience'})['items'][:2]]
        rejected = dispatch('evolution_submit', {'candidate': candidate(identifiers), 'observation_ids': identifiers})
        assert rejected['status'] == 'rejected'
        dispatch('evolution_finish', {'reason': 'Valid hypothesis failed independent admission', 'decision': 'proposal'})
        return {}
    result = run_investigation(make(tmp_path, data), call_agent=agent,
        handlers={'construction_strategy': handler}, output=tmp_path / 'admission-failed')
    assert result['status'] == 'completed'
    assert result['completion_scope'] == 'investigation_only'
    assert result['candidate_counts']['schema_and_evidence_valid'] == 1
    assert result['candidate_counts']['host_evaluations_started'] == 1
    assert result['candidate_counts']['rejected'] == 1
    assert result['actual_adoption'] is None
    assert result['measured_net_benefit'] is None


@pytest.mark.parametrize('local_only,requirement', [(True, 'at least one source'), (False, 'at least two independent sources')])
def test_source_requirement_matches_actual_local_scope(tmp_path, data, local_only, requirement):
    def agent(request, dispatch):
        submit = next(tool for tool in request['tools'] if tool['name'] == 'evolution_submit')
        description = submit['parameters']['properties']['observation_ids']['description']
        assert requirement in description
        assert 'acquires its next' in request['prompt']
        assert 'successful and failed experiences' in request['prompt']
        assert 'Builder experience' in request['prompt']
        assert 'Model-issued commands' in request['prompt']
        dispatch('evolution_finish', {'reason': 'Scope and research objective checked', 'decision': 'inconclusive'})
        return {}
    run_investigation(make(tmp_path, data), call_agent=agent, handlers={}, output=tmp_path / 'scope-check',
                      local_only=local_only)
