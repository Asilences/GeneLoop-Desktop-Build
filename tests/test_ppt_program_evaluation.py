"""Lifecycle regressions using synthetic receipts, without model or savings claims."""
import json
from pathlib import Path
import pytest

from src.adapters import ppt_program_evaluation as evaluation
from src.adapters import ppt_program_learning as program


def fixture(tmp_path):
    store = tmp_path / 'learning/ppt-owner'
    store.mkdir(parents=True)
    folder = store / 'program-first'
    folder.mkdir()
    library = {'programs': [{'id': 'p1', 'component': {'version': 1}}], 'code_locks': {}, 'digest': 'first'}
    program.save(folder / 'library.json', library)
    support = {key: [] for key in ('decision_id', 'source_signature', 'question_sha256')}
    pointer = {'user': 'owner', 'scope': 'scope', 'phase': 'probation', 'library': 'program-first/library.json',
               'library_sha256': program.sha(folder / 'library.json'), 'library_digest': 'first',
               'implementation_signature': program.program_implementation_signature(), 'added_program_ids': ['p1'],
               'support_turns': [], 'support': support, 'evidence_locks': {}}
    program.save(store / 'program-selected.json', pointer)
    return store, pointer


def use(tmp_path, pointer, n, *, used=True, single=True, program_id='p1'):
    task_id = str(n)
    directory = tmp_path / 'tasks' / task_id
    directory.mkdir(parents=True)
    program.save(directory / 'ppt-program-snapshot.json', pointer)
    (directory / 'artifact-motif-audit.jsonl').write_text(
        json.dumps({'kind': 'component_used_in_delivery', 'program_id': program_id}) + '\n' if used else '', encoding='utf-8')
    lane = 'baseline' if single else 'motif'
    turn = {'id': 'turn-' + task_id, 'status': 'completed', 'presentation': 'single' if single else 'paired',
            'learning_lane': lane, 'lanes': {lane: {'task_id': task_id}}}
    info = {'task_id': task_id, 'task_dir': str(directory), 'effective': {'mode': 'execute'},
            'state': {'status': 'completed'}, 'decision_id': 'decision-' + task_id,
            'source_signature': 'source-' + task_id, 'question_sha256': 'question-' + task_id,
            'locks': {}, 'compatibility': 'same'}
    return turn, info


def run(tmp_path, store, pointer, turns, infos, positive=lambda *args: True):
    def delivery(*args, **kwargs):
        return {'status': 'unknown', 'mechanical_status': 'passed'}
    def costs(*args):
        raise AssertionError('Single-lane use cannot claim matched cost advantage')
    return evaluation.evaluate_generation(tmp_path, store, {'user': 'owner', 'scope': 'scope'}, pointer,
        infos, turns, {}, delivery=delivery, positive=positive, costs=costs)


def test_unused_failed_comparison_does_not_suspend_a_program(tmp_path):
    store, pointer = fixture(tmp_path)
    turn, info = use(tmp_path, pointer, 1, used=False, single=False)
    turn['status'] = 'failed'
    result = run(tmp_path, store, pointer, {turn['id']: turn}, {})
    assert result['phase'] == 'probation'
    assert result['groups'][0]['blocked'] == []


def test_independent_single_lane_uses_are_retained_without_claiming_cost_advantage(tmp_path):
    store, pointer = fixture(tmp_path)
    rows = [use(tmp_path, pointer, n) for n in (1, 2)]
    result = run(tmp_path, store, pointer, {t['id']: t for t, i in rows}, {i['task_id']: i for t, i in rows})
    assert result['groups'][0]['phase'] == 'retained'
    assert result['quality_cost_promoted'] is False
    assert result['phase'] == 'probation'
    assert len(result['groups'][0]['uses']) == 2


def test_new_certified_generation_merges_while_previous_candidate_is_on_probation(tmp_path):
    store, pointer = fixture(tmp_path)
    folder = store / 'program-second'
    folder.mkdir()
    library = {'programs': [{'id': 'p2', 'component': {'version': 1}}], 'code_locks': {}, 'digest': 'second'}
    assert evaluation.publish_generation(tmp_path, store, {'user': 'owner', 'scope': 'scope'}, folder, library,
        {}, [], pointer['support'], 'normal_page_learning')
    current = program.read(store / 'program-selected.json')
    assert len(current['groups']) == 2
    assert {p['id'] for p in program.read(store / current['library'])['programs']} == {'p1', 'p2'}
    turn, info = use(tmp_path, current, 1)
    result = run(tmp_path, store, current, {turn['id']: turn}, {info['task_id']: info}, positive=lambda *args: False)
    assert result['phase'] == 'probation'
    assert {p['id'] for p in program.read(store / result['library'])['programs']} == {'p2'}
    assert program.read(store / 'program-retired.json')[0]['program_ids'] == ['p1']


@pytest.mark.parametrize('failed_page,phase', [(1, 'disabled'), (2, 'probation')])
def test_model_review_failure_is_attributed_only_to_an_adopted_page(tmp_path, failed_page, phase):
    store, pointer = fixture(tmp_path)
    turn, info = use(tmp_path, pointer, 1)
    audit = tmp_path / 'tasks/1/artifact-motif-audit.jsonl'
    audit.write_text(json.dumps({'kind': 'component_used_in_delivery', 'program_id': 'p1', 'page': 1}) + '\n')
    result = evaluation.evaluate_generation(tmp_path, store, {'user': 'owner', 'scope': 'scope'}, pointer,
        {'1': info}, {turn['id']: turn}, {},
        delivery=lambda *args, **kwargs: {'status': 'failed', 'model_failed_pages': [failed_page], 'layout_status': 'passed'},
        positive=lambda *args: True, costs=lambda *args: pytest.fail('A failed delivery cannot prove lower qualified cost'))
    assert result['phase'] == phase


@pytest.mark.parametrize('layout_status,phase', [('passed', 'probation'), ('failed', 'disabled')])
def test_layout_only_support_preserves_its_scope_and_later_visual_failure_revokes_it(tmp_path, layout_status, phase):
    store, pointer = fixture(tmp_path)
    turn, info = use(tmp_path, pointer, 1, used=False)
    pointer['groups'] = evaluation.generation_groups(pointer)
    pointer['groups'][0]['support_turns'] = [turn['id']]
    pointer['groups'][0]['support_scopes'] = {turn['id']: program.LAYOUT_ONLY_SCOPE}
    result = evaluation.evaluate_generation(tmp_path, store, {'user': 'owner', 'scope': 'scope'}, pointer,
        {'1': info}, {turn['id']: turn}, {}, positive=lambda *args: True,
        delivery=lambda *args, **kwargs: {'status': 'failed', 'model_failed_pages': [1], 'layout_status': layout_status},
        costs=lambda *args: pytest.fail('Supporting source quality cannot prove future cost savings'))
    assert result['phase'] == phase
    assert result.get('quality_cost_promoted') is not True


def test_layout_only_source_cannot_authorize_general_programs(tmp_path):
    store, pointer = fixture(tmp_path)
    folder = store / 'not-a-page'
    folder.mkdir()
    library = {'programs': [{'id': 'general-program'}], 'code_locks': {}, 'digest': 'general'}
    with pytest.raises(ValueError, match='parameterized page components'):
        evaluation.publish_generation(tmp_path, store, {'user': 'owner', 'scope': 'scope'}, folder, library,
            {}, ['support'], pointer['support'], 'normal_page_learning',
            support_scopes={'support': program.LAYOUT_ONLY_SCOPE})


@pytest.mark.parametrize('layout_status,phase', [('passed', 'probation'), ('failed', 'disabled')])
def test_later_semantic_failure_never_promotes_a_layout_only_component(tmp_path, layout_status, phase):
    store,pointer=fixture(tmp_path)
    pointer['groups']=evaluation.generation_groups(pointer)
    pointer['groups'][0]['support_scopes']={'original-layout':program.LAYOUT_ONLY_SCOPE}
    turn,info=use(tmp_path,pointer,1)
    audit=tmp_path/'tasks/1/artifact-motif-audit.jsonl'
    audit.write_text(json.dumps({'kind':'component_used_in_delivery','program_id':'p1','page':1})+'\n')
    result=evaluation.evaluate_generation(tmp_path,store,{'user':'owner','scope':'scope'},pointer,
        {'1':info},{turn['id']:turn},{},positive=lambda *a:True,
        delivery=lambda *a,**kw:{'status':'failed','model_failed_pages':[1],'layout_status':layout_status},
        costs=lambda *a:pytest.fail('A semantic failure cannot prove qualified savings'))
    assert result['phase']==phase
    if layout_status=='passed':
        assert result['groups'][0]['uses']==[] and result['groups'][0]['pairs']==[]
        assert result['groups'][0]['pending'][0]['reason']=='semantic_quality_failed_layout_scope_retained'
        assert result['quality_cost_promoted'] is False
