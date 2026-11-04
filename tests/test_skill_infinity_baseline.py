"""Deterministic baseline protocol diagnostics, with no paid model requests."""
import json
from pathlib import Path

import pytest

from src.adapters.capability_feedback import file_ref
from src.adapters.skill_infinity_baseline import (
    SkillInfinityRun, create_seed_meta_skill, create_seed_task_skill,
    optimize_task_skill, refine_meta_skill,
)


PROPOSAL = {'observation': 'Repeated training failure', 'change': 'Add a reusable procedure',
            'predicted_effect': 'Correct outputs', 'falsifying_outcome': 'Same check fails'}


@pytest.fixture
def skills(tmp_path):
    task = create_seed_task_skill(tmp_path / 'task', 'task-procedure', 'Solve the supplied task class')
    meta = create_seed_meta_skill(tmp_path / 'meta')
    return task, meta


def evaluate(request):
    content = (Path(request['skill_directory']) / 'SKILL.md').read_text()
    return {'score': '1' if 'improved-task' in content else '0',
            'skill_activated': True, 'observed_model_usd_decimal': None,
            'evidence': {'diagnostic': request['split']}}


def review(request):
    assert request['mode'] == 'review'
    assert request['fresh_context'] is True
    assert 'history' not in request and 'messages' not in request
    return {'accepted': True, 'reason': 'Supported by rollout and validation'}


def actor(request, dispatch):
    assert 'SKILL.md' not in request['prompt']
    assert 'content' not in request['available_skill_cards'][0]
    dispatch('read_skill', {'node_id': 'controller', 'resource': 'SKILL.md'})
    current = dispatch('read_skill', {'node_id': request['parent'], 'resource': 'SKILL.md'})
    dispatch('rollout', {'node_id': request['parent']})
    candidate = dispatch('create_candidate', {'parent_id': request['parent'],
        'files': {'SKILL.md': current['content'] + '\nimproved-task\n'}, 'proposal': PROPOSAL})
    node_id = candidate['node_id']
    dispatch('evaluate_candidate', {'node_id': node_id})
    dispatch('review_candidate', {'node_id': node_id})
    dispatch('select_parent', {'selected_node_id': node_id, 'action': 'stop', 'reason': 'Validated change'})
    return {'model_requests': 0, 'diagnostic': True}


def make_run(tmp_path, skills, **kwargs):
    task, meta = skills
    return SkillInfinityRun(task, tmp_path / 'run', optimization_target='task_skill',
        context={'task_id': 'one'}, call_agent=actor, evaluate=evaluate, review=review,
        meta_skill=meta, **kwargs)


def test_native_discovery_archive_and_independent_review(tmp_path, skills):
    task, meta = skills
    result = optimize_task_skill(task, tmp_path / 'run', call_agent=actor, evaluate=evaluate,
                                 review=review, meta_skill=meta)
    assert result['status'] == 'completed'
    assert result['selected_node'] == 'i000-c1'
    assert result['score'] == '1'
    assert result['observed_model_usd_decimal'] is None
    assert result['archive']['nodes'][1]['status'] == 'accepted'
    assert result['controller_activation_observations'][0]['activated'] is True
    request = json.loads((tmp_path / 'run/request-000.json').read_text())
    assert request['available_skill_cards'][0]['name'] == 'skill-self-evolver'
    assert 'instructions' not in request
    assert len(list((tmp_path / 'run/tool-calls').glob('*.json'))) == 7
    assert (tmp_path / 'run/seed/evaluation/result.json').is_file()


def test_unactivated_candidate_is_preserved_and_ineligible(tmp_path, skills):
    run = make_run(tmp_path, skills)
    run.evaluate = lambda request: {**evaluate(request), 'skill_activated': None}
    run._evaluate('seed', 'validation')
    node = run.dispatch('create_candidate', {'parent_id': 'seed', 'files': {'extra.txt': 'helper'},
                                           'proposal': PROPOSAL})
    run.dispatch('evaluate_candidate', {'node_id': node['node_id']})
    result = run.dispatch('review_candidate', {'node_id': node['node_id']})
    assert result['accepted'] is False
    assert result['host_rejection'] == 'activation_unconfirmed'
    decision = run.dispatch('select_parent', {'selected_node_id': node['node_id'], 'action': 'stop', 'reason': 'Try'})
    assert decision['status'] == 'error'
    assert run.nodes[node['node_id']]['status'] == 'rejected'


def test_unchanged_candidate_cannot_be_accepted(tmp_path, skills):
    run = make_run(tmp_path, skills)
    run._evaluate('seed', 'validation')
    node = run._create('seed', {}, PROPOSAL)
    run._evaluate(node['node_id'], 'validation')
    assert run._review(node['node_id'])['host_rejection'] == 'unchanged_package'


def test_candidate_count_includes_failed_draft(tmp_path, skills):
    run = make_run(tmp_path, skills, candidate_budget=1)
    bad = run.dispatch('create_candidate', {'parent_id': 'seed', 'files': {'../escaped': 'bad'},
                                          'proposal': PROPOSAL})
    assert bad['status'] == 'error'
    assert run.created == 1
    assert run.nodes['i000-c1']['status'] == 'draft_failed'
    assert (tmp_path / 'run/i000-c1/failure.json').is_file()
    assert run.dispatch('create_candidate', {'parent_id': 'seed', 'files': {},
                                           'proposal': PROPOSAL})['status'] == 'error'


def test_evaluation_freezes_candidate_package(tmp_path, skills):
    run = make_run(tmp_path, skills)
    node = run._create('seed', {'extra.txt': 'helper'}, PROPOSAL)
    run._evaluate(node['node_id'], 'validation')
    (Path(node['skill_directory']) / 'extra.txt').write_text('changed')
    with pytest.raises(ValueError, match='evaluated_package_changed'):
        run._review(node['node_id'])


def test_missing_agent_decision_is_explicit_failure(tmp_path, skills):
    run = make_run(tmp_path, skills)
    run.call_agent = lambda request, dispatch: {'diagnostic': True}
    result = run.run()
    assert result['status'] == 'failed'
    assert 'decision_missing' in result['error']
    assert (tmp_path / 'run/result.json').is_file()


def test_review_is_required_before_selection(tmp_path, skills):
    run = make_run(tmp_path, skills)
    run._evaluate('seed', 'validation')
    node = run._create('seed', {'extra.txt': 'helper'}, PROPOSAL)
    run._evaluate(node['node_id'], 'validation')
    with pytest.raises(ValueError, match='reviews_pending'):
        run._select('seed', 'stop', 'Retain seed')


def test_evaluation_failure_and_unknown_cost_remain_in_archive(tmp_path, skills):
    run = make_run(tmp_path, skills)
    def failing(request):
        raise RuntimeError('diagnostic_verifier_failure')
    run.evaluate = failing
    result = run.run()
    assert result['status'] == 'failed'
    assert result['observed_model_usd_decimal'] is None
    assert result['archive']['nodes'][0]['status'] == 'evaluation_failed'
    assert 'diagnostic_verifier_failure' in result['error']
    assert (tmp_path / 'run/seed/evaluation/failure.json').is_file()


@pytest.mark.parametrize('score', [None, True, 'NaN', 'Infinity', 'bad'])
def test_invalid_scores_are_not_zero_or_success(tmp_path, skills, score):
    run = make_run(tmp_path, skills)
    run.evaluate = lambda request: {'score': score, 'skill_activated': True}
    assert run.run()['status'] == 'failed'


def test_reusing_workspace_preserves_previous_run(tmp_path, skills):
    run = make_run(tmp_path, skills)
    before = (tmp_path / 'run/context.json').read_bytes()
    with pytest.raises(FileExistsError):
        make_run(tmp_path, skills)
    assert before == (tmp_path / 'run/context.json').read_bytes()


def test_meta_self_improvement_reuses_the_same_agent_led_loop(tmp_path, skills):
    task, meta = skills
    seen_controllers = []
    def recursive_actor(request, dispatch):
        controller = dispatch('read_skill', {'node_id': 'controller', 'resource': 'SKILL.md'})
        seen_controllers.append(controller['content'])
        if request['optimization_target'] == 'task_skill' and 'improved-meta' not in controller['content']:
            dispatch('select_parent', {'selected_node_id': 'seed', 'action': 'stop',
                                      'reason': 'Diagnostic seed retained'})
            return {'diagnostic': True}
        current = dispatch('read_skill', {'node_id': request['parent'], 'resource': 'SKILL.md'})
        marker = 'improved-meta' if request['optimization_target'] == 'meta_skill' else 'improved-task'
        candidate = dispatch('create_candidate', {'parent_id': request['parent'],
            'files': {'SKILL.md': current['content'] + '\n' + marker + '\n'}, 'proposal': PROPOSAL})
        node_id = candidate['node_id']
        dispatch('evaluate_candidate', {'node_id': node_id})
        dispatch('review_candidate', {'node_id': node_id})
        dispatch('select_parent', {'selected_node_id': node_id, 'action': 'stop', 'reason': 'Observed gain'})
        return {'diagnostic': True}
    result = refine_meta_skill(meta, [{'id': 'q1', 'seed_skill': task, 'context': {'task_id': 'one'}}],
        tmp_path / 'outer', call_agent=recursive_actor, evaluate=evaluate, review=review)
    assert result['status'] == 'completed'
    assert result['self_improvement'] == 'completed'
    assert result['meta_refinement_outcome'] == 'changed'
    assert result['score'] == '1'
    assert any('improved-meta' in value for value in seen_controllers)
    outer_node = result['archive']['nodes'][1]
    assert outer_node['evaluation']['skill_activated'] is True
    assert outer_node['evaluation']['optimization_results'][0]['gain'] == '1'
    persisted = json.loads((tmp_path / 'outer/result.json').read_text())
    assert persisted['self_improvement'] == 'completed'


def test_zero_outer_candidates_is_labelled_seed_only(tmp_path, skills):
    task, meta = skills
    def stop(request, dispatch):
        dispatch('read_skill', {'node_id': 'controller', 'resource': 'SKILL.md'})
        dispatch('select_parent', {'selected_node_id': 'seed', 'action': 'stop', 'reason': 'Seed'})
        return {'diagnostic': True}
    result = refine_meta_skill(meta, [{'id': 'q', 'seed_skill': task}], tmp_path / 'outer',
        call_agent=stop, evaluate=evaluate, review=review, outer_candidate_budget=0)
    assert result['self_improvement'] == 'seed_only'
    assert result['meta_refinement_outcome'] == 'retained_seed'


def test_folded_skill_description_is_discoverable(tmp_path, skills):
    task, meta = skills
    document = Path(meta) / 'SKILL.md'
    document.write_text(document.read_text().replace(
        'description: Optimize task skills or this optimization skill using execution evidence, candidate evaluation, independent review, and parent selection.',
        'description: >-\n  Optimize task skills\n  and this optimization skill.'))
    result = optimize_task_skill(task, tmp_path / 'run', call_agent=actor, evaluate=evaluate,
                                review=review, meta_skill=meta)
    assert result['status'] == 'completed'
    request = json.loads((tmp_path / 'run/request-000.json').read_text())
    assert request['available_skill_cards'][0]['description'] == 'Optimize task skills and this optimization skill.'


def test_host_evidence_is_readable_in_pages_with_original_hash(tmp_path, skills):
    record = tmp_path / 'verifier.stdout.txt'
    record.write_text('Original failure\n' + 'x' * 40)
    reference = file_ref(record)
    run = make_run(tmp_path, skills)
    run.evaluate = lambda request: {**evaluate(request), 'evidence_refs': [reference]}
    result = run._evaluate('seed', 'validation')
    assert result['evidence_refs'] == [reference]
    assert 'read_evidence' in [tool['name'] for tool in run.tools()]
    page = run.dispatch('read_evidence', {'evidence_id': reference['sha256'], 'limit': 16})
    assert page['content'] == 'Original failure'
    assert page['evidence'] == reference
    assert page['next_offset'] == 16
    remainder = run.dispatch('read_evidence', {'evidence_id': reference['sha256'], 'offset': 16})
    assert page['content'] + remainder['content'] == record.read_text()
    assert remainder['next_offset'] is None


def test_only_trusted_host_index_can_authorize_nested_records(tmp_path, skills):
    calls = tmp_path / 'tool-calls.jsonl'
    calls.write_text('{"command":"inspect inputs","stdout":"real tool result"}\n')
    verifier = tmp_path / 'verifier.stdout.txt'
    verifier.write_text('1 failed, 3 passed')
    nested = tmp_path / 'trajectory-index.json'
    nested.write_text(json.dumps({'evidence_refs': [file_ref(calls), file_ref(verifier)]}))
    index = tmp_path / 'host-index.json'
    index.write_text(json.dumps({'evidence_indexes': [file_ref(nested)]}))
    run = make_run(tmp_path, skills)
    run.evaluate = lambda request: {**evaluate(request), 'evidence_indexes': [file_ref(index)]}
    run._evaluate('seed', 'validation')
    assert run.dispatch('read_evidence', {'evidence_id': file_ref(calls)['sha256']})['status'] == 'error'
    first = run.dispatch('read_evidence', {'evidence_id': file_ref(index)['sha256']})
    assert first['discovered_evidence_refs'] == [file_ref(nested)]
    run.dispatch('read_evidence', {'evidence_id': file_ref(nested)['sha256']})
    assert run.dispatch('read_evidence', {'evidence_id': file_ref(calls)['sha256']})['content'] == calls.read_text()
    assert run.dispatch('read_evidence', {'evidence_id': file_ref(verifier)['sha256']})['content'] == verifier.read_text()


def test_model_authored_reference_cannot_authorize_oracle_or_arbitrary_path(tmp_path, skills):
    oracle = tmp_path / 'reference-solution.txt'
    oracle.write_text('private reference answer')
    model = tmp_path / 'model-result.json'
    model.write_text(json.dumps({'text': 'model claims access', 'evidence_refs': [file_ref(oracle)]}))
    run = make_run(tmp_path, skills)
    run.evaluate = lambda request: {**evaluate(request), 'evidence_refs': [file_ref(model)]}
    run._evaluate('seed', 'validation')
    run.dispatch('read_evidence', {'evidence_id': file_ref(model)['sha256']})
    denied = run.dispatch('read_evidence', {'evidence_id': file_ref(oracle)['sha256']})
    assert 'skill_evidence_not_authorized' in denied['error']
    assert run.dispatch('read_evidence', {'evidence_id': str(oracle)})['status'] == 'error'


def test_evidence_mutation_and_invalid_page_are_retained_failures(tmp_path, skills):
    record = tmp_path / 'record.txt'
    record.write_text('original')
    reference = file_ref(record)
    run = make_run(tmp_path, skills)
    run.evaluate = lambda request: {**evaluate(request), 'evidence_refs': [reference]}
    run._evaluate('seed', 'validation')
    for arguments in [{'offset': -1}, {'limit': 24001}, {'offset': True}, {'limit': 0}]:
        result = run.dispatch('read_evidence', {'evidence_id': reference['sha256'], **arguments})
        assert 'skill_evidence_page_invalid' in result['error']
    record.write_text('modified')
    result = run.dispatch('read_evidence', {'evidence_id': reference['sha256']})
    assert 'feedback_evidence_changed' in result['error']
    receipts = [json.loads(path.read_text()) for path in (tmp_path / 'run/tool-calls').glob('*.json')]
    assert all(receipt['status'] == 'failed' for receipt in receipts)


def test_meta_evaluation_inherits_original_inner_host_evidence(tmp_path, skills):
    task, meta = skills
    original = tmp_path / 'original-verifier.txt'
    original.write_text('original independent verifier diagnostics')
    reference = file_ref(original)
    result = refine_meta_skill(meta, [{'id': 'q', 'seed_skill': task}], tmp_path / 'outer',
        call_agent=actor,
        evaluate=lambda request: {**evaluate(request), 'evidence_refs': [reference]},
        review=review, outer_candidate_budget=0, inner_candidate_budget=0)
    assert result['status'] == 'completed'
    assert reference in result['archive']['nodes'][0]['evaluation']['evidence_refs']
    assert reference in result['archive']['evidence_refs']
    assert any(item['path'].endswith('inner-0/result.json') for item in result['archive']['evidence_refs'])
