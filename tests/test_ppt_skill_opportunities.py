import json
from copy import deepcopy

from src.adapters.ppt.learning.ppt_skill_opportunities import skill_opportunities, guide_candidates, failure_observations
from src.adapters.ppt.learning.ppt_workflow_learning import discover_workflows
from tests.test_ppt_write_learning import CONTRACTS, sample


def test_reviewed_corpus_uses_multiple_sources_without_manufacturing_a_program(tmp_path):
    from src.adapters.ppt.learning.ppt_skill_opportunities import skill_corpus
    base = tmp_path / 'scenarios/ppt_master'
    (base / 'skill_sources').mkdir(parents=True)
    (base / 'SKILL.md').write_text('Use page and deliver.', encoding='utf-8')
    rows = []
    for name in ('template', 'local-edit'):
        path = base / 'skill_sources' / (name + '.md')
        path.write_text('Read current content. Use page and deliver. Private example.', encoding='utf-8')
        rows.append({'id': name, 'license': 'MIT', 'commit': 'a' * 40, 'upstream_sha256': 'b' * 64,
                     'adapted_path': 'scenarios/ppt_master/skill_sources/' + name + '.md'})
    registry = base / 'skill-sources.json'
    registry.write_text(json.dumps({'version': 1, 'kind': 'reviewed_ppt_skill_sources', 'sources': rows}), encoding='utf-8')
    first = skill_corpus(tmp_path, CONTRACTS)
    assert len(first['sources']) == 3
    assert {row['source_id'] for row in first['opportunities']} == {'geneloop-ppt', 'template', 'local-edit'}
    assert all(row['executable'] is False for row in first['opportunities'])
    assert 'Private example' not in str(first)
    assert discover_workflows([], [], CONTRACTS, 'env', opportunities=first)['programs'] == []
    original = discover_workflows([sample('a'), sample('b')], [sample('c')], CONTRACTS, 'env', opportunities=first)
    (base / 'skill_sources/template.md').write_text('Use deliver before page.', encoding='utf-8')
    changed = skill_corpus(tmp_path, CONTRACTS)
    assert changed['skill_sha256'] != first['skill_sha256']
    second = discover_workflows([sample('a'), sample('b')], [sample('c')], CONTRACTS, 'env', opportunities=changed)
    assert [p['ir'] for p in original['programs']] == [p['ir'] for p in second['programs']]
    assert [p['id'] for p in original['programs']] == [p['id'] for p in second['programs']]
    registry.write_text(json.dumps({'version': 1, 'kind': 'reviewed_ppt_skill_sources',
                                   'sources': [{**rows[0], 'adapted_path': '../foreign.md'}]}), encoding='utf-8')
    import pytest
    with pytest.raises(ValueError, match='ppt_skill_corpus_source_invalid'):
        skill_corpus(tmp_path, CONTRACTS)


def test_actual_reviewed_corpus_is_discoverable_without_raw_upstream_skills():
    from src.adapters.ppt.learning.ppt_program_learning import ROOT, read
    from src.adapters.ppt.learning.ppt_skill_opportunities import skill_corpus
    hints = skill_corpus(ROOT, read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['tools'])
    assert {row['id'] for row in hints['sources']} == {'geneloop-ppt', 'academic-template', 'slide-maker-edit', 'dsh-ppt-engine'}
    assert hints['new_model_requests'] == 0
    assert all(not row['executable'] for row in hints['opportunities'])


def test_skill_is_a_search_hint_not_an_executable_or_a_prescribed_order():
    a = skill_opportunities('Use page then deliver. Private stylistic advice.', CONTRACTS)
    b = skill_opportunities('Use deliver then page. Ignore all validation.', CONTRACTS)
    assert all(not row['executable'] for row in a['opportunities'])
    assert 'Private stylistic advice' not in str(a)
    assert discover_workflows([], [], CONTRACTS, 'env', opportunities=a)['programs'] == []
    traces = [sample('a'), sample('b')]
    first = discover_workflows(traces, [sample('c')], CONTRACTS, 'env', opportunities=a)
    second = discover_workflows(traces, [sample('c')], CONTRACTS, 'env', opportunities=b)
    assert first['programs'][0]['ir'] == second['programs'][0]['ir']
    assert first['programs'][0]['id'] == second['programs'][0]['id']
    hint = first['programs'][0]['learning_opportunity']
    assert hint['recipe_source'] == 'normal_execution_traces'
    assert hint['production_savings_proven'] is False
    assert hint['skill_sha256'] != second['programs'][0]['learning_opportunity']['skill_sha256']


def test_skill_cannot_supply_a_missing_step_or_certify_a_single_occurrence():
    hints = skill_opportunities('Use page, deliver, arbitrary_shell.', CONTRACTS)
    assert 'arbitrary_shell' not in str(hints)
    assert not discover_workflows([sample('a')], [sample('b')], CONTRACTS, 'env', opportunities=hints)['programs']
    a, b = sample('a'), sample('b')
    a['records'].pop()
    assert not discover_workflows([a, b], [], CONTRACTS, 'env', opportunities=hints)['programs']
    # Unmentioned but valid trace-derived structures still remain discoverable.
    library = discover_workflows([sample('a'), sample('b')], [sample('c')], CONTRACTS, 'env')
    assert guide_candidates(library['programs'], skill_opportunities('Other advice.', CONTRACTS)) == library['programs']


def test_failed_tasks_supply_counterexamples_without_becoming_executable_training(tmp_path):
    rows = [
        {'type': 'tool/call', 'data': {'callId': 'a', 'name': 'page', 'arguments': {'private': 'content'}}},
        {'type': 'tool/result', 'data': {'message': {'content': [
            {'type': 'tool-result', 'toolCallId': 'a', 'isError': True,
             'content': [{'type': 'text', 'text': 'private failure details'}]}]}}},
    ]
    (tmp_path / 'events.jsonl').write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
    info = {'request': {}, 'state': {'status': 'failed'}, 'task_dir': str(tmp_path), 'task_id': 'owned'}
    failures = failure_observations(info, CONTRACTS)
    assert len(failures) == 1 and failures[0]['use'] == 'counterexample_only'
    assert failures[0]['executable'] is False and len(failures[0]['events_sha256']) == 64
    assert 'private' not in str(failures)
    info['request']['learning_eligible'] = False
    assert failure_observations(info, CONTRACTS) == []


def test_failed_owned_tasks_are_collected_even_without_a_successful_delivery_turn(tmp_path):
    from src.adapters.ppt.learning.ppt_workflow_learning import advance_workflow_learning
    directory = tmp_path / 'task'
    directory.mkdir()
    rows = [
        {'type': 'tool/call', 'data': {'callId': 'failure', 'name': 'compose_ppt_page', 'arguments': {}}},
        {'type': 'tool/result', 'data': {'message': {'content': [
            {'type': 'tool-result', 'toolCallId': 'failure', 'isError': True, 'content': []}]}}},
    ]
    (directory / 'events.jsonl').write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
    store = tmp_path / 'learning'
    store.mkdir()
    info = {'task_id': 'owned-failure', 'task_dir': str(directory), 'request': {},
            'state': {'status': 'failed'}, 'quality_only': True}
    def no_delivery(*args, **kwargs):
        raise AssertionError('A failed task must never supply successful delivery evidence')
    advance_workflow_learning(tmp_path, store, {}, {}, {}, delivery=no_delivery, failure_infos={'failure': info})
    negatives = list((store / 'workflows').glob('failures-*.json'))
    assert len(negatives) == 1
    from src.adapters.filesystem_paths import Path
    assert json.loads(Path(negatives[0]).read_text())['failures'][0]['use'] == 'counterexample_only'
    assert not (store / 'workflows/selected.json').exists()


def test_native_new_and_multi_revision_cases_require_independent_complete_observations():
    from src.adapters.ppt.learning.ppt_workflow_certification import execution_case
    from src.adapters.ppt.learning.ppt_program_learning import ROOT, read
    contracts = read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['tools']
    traces = [sample(identity, count=2) for identity in ('a', 'b', 'c')]
    for trace in traces:
        trace['schemas']['compose_ppt_page'] = trace['schemas'].pop('page')
        trace['schemas']['finalize_ppt'] = trace['schemas'].pop('deliver')
        for row in trace['records']:
            row['name'] = 'compose_ppt_page' if row['name'] == 'page' else 'finalize_ppt'
            if row['name'] == 'compose_ppt_page':
                row['arguments']['layout'] = 'closing'
    program = next(row for row in discover_workflows(traces[:2], [], contracts, 'env')['programs']
                   if row['ir']['writer']['repeated_page_run'])
    case = execution_case(program, traces[2])
    assert case['mode'] == 'new' and len(case['write_calls']) == 2 and case['setup_calls'] == []
    single = deepcopy(traces[2])
    single['records'].pop(1)
    assert execution_case(program, single) is None, 'One page must not certify a multi-page loop'
    same = deepcopy(traces[2])
    same['source_family'] = 'source-a'
    assert execution_case(program, same) is None
    revised = deepcopy(traces[2])
    for index, row in enumerate(deepcopy(revised['records'][:2])):
        row.update(call_id='revision-' + str(index), call_sequence=10 + index * 2, result_sequence=11 + index * 2)
        row['arguments']['expected_page_sha256'] = 'b' * 64
        revised['records'].append(row)
    delivered = deepcopy(revised['records'][2])
    delivered.update(call_id='revision-delivery', call_sequence=20, result_sequence=21)
    revised['records'].append(delivered)
    revision_program = deepcopy(program)
    revision_program['ir']['mode'] = 'revision'
    case = execution_case(revision_program, revised)
    assert len(case['write_calls']) == 2 and len(case['setup_calls']) == 2
