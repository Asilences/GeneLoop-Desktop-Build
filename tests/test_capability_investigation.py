"""Deterministic investigation diagnostics over synthetic source records."""
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.adapters.capability_contract import capability_digest
from src.adapters.capability_evolution_agent import restore_regions, validate_candidate
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.capability_investigation import Investigation
from tests.test_capability_feedback import fixture


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return file_ref(path)


def inspect(reference, owner):
    return json.loads(verify(reference))


@pytest.fixture
def data(tmp_path):
    _, library, source, _ = fixture(tmp_path)
    snapshot = library['snapshot']
    rows = []
    for index in range(3):
        row = {'task_id': 'task-' + str(index), 'source_identity': 'source-' + str(index),
               'relation': 'interface-' + str(index), 'stage': 'construction',
               'status': 'failed' if index == 1 else 'passed',
               'quality': 'unreviewed', 'counterexample': index == 1,
               'capabilities': snapshot['roots'],
               'steps': [{'call_id': 'prepare', 'capability': snapshot['roots'][0],
                          'status': 'succeeded', 'input_binding': {'kind': 'input', 'path': []}}],
               'decision_context': {'objective': 'Build a reusable relation checker',
                                    'state': 'Interface conversion required',
                                    'outcome': 'Still awaiting independent review'},
               'construction_outcomes': [{'error': 'binding_incompatible', 'verification_status': None}],
               'observed_cost_usd': None if index == 0 else str(index / 10),
               'cost_attribution': 'construction_requests_only',
               'evidence': [source]}
        rows.append({'split': 'training', 'scope': 'study',
                     'evidence': put(tmp_path / ('row-' + str(index) + '.json'), row)})
    catalog = {'source_catalog': {'catalog': [
        {'capability': snapshot['roots'][0], 'description': 'Prepare metadata records'},
        {'capability': snapshot['roots'][1], 'description': 'Join relation records'}]}}
    return snapshot, rows, catalog


def make(tmp_path, data, **kwargs):
    snapshot, rows, catalog = data
    return Investigation(snapshot, rows, 'study', tmp_path / 'investigation',
                         inspector=inspect, catalog=catalog, **kwargs)


def test_overview_is_compact_and_does_not_preselect_relation(tmp_path, data):
    service = make(tmp_path, data)
    overview = service.overview()
    assert overview['experiences']['observations'] == 3
    assert overview['experiences']['independent_sources'] == 3
    assert overview['costs']['unknown_observations'] == 1
    assert overview['costs']['minimum_known_observation_usd'] == '0.1'
    assert overview['costs']['maximum_known_observation_usd'] == '0.2'
    assert 'relation checker' not in json.dumps(overview)
    assert str(tmp_path) not in json.dumps(overview)
    assert len(service.search('experience')['items']) == 3


def test_single_unknown_quality_source_is_queryable(tmp_path, data):
    snapshot, rows, catalog = data
    service = Investigation(snapshot, rows[:1], 'study', tmp_path / 'one', inspector=inspect)
    result = service.search('experience')
    assert result['total'] == 1
    assert result['items'][0]['quality'] == 'unreviewed'
    assert result['items'][0]['observed_cost_usd'] is None
    assert result['items'][0]['cost_attribution'] == 'construction_requests_only'


def test_empty_history_can_be_investigated_without_paid_proposal(tmp_path, data):
    service = Investigation(data[0], [], 'study', tmp_path / 'empty', inspector=inspect)
    assert service.overview()['experiences']['observations'] == 0
    assert service.search('experience')['items'] == []


def test_continuation_keeps_capabilities_original_builder_inspector_notes_and_new_outcomes(tmp_path, data):
    service = make(tmp_path, data)
    service.note('A hypothesis about the witnessed interface', [next(iter(service.observations))], ['Check next actions'])
    new = {'task_id': 'successor-task', 'source_identity': 'successor-source', 'relation': 'later-execution',
           'stage': 'execution', 'status': 'passed', 'capabilities': [], 'evidence': [],
           'observed_cost_usd': None}
    ref = put(tmp_path / 'new-row.json', new)
    inspected = []
    def successor_inspector(reference, owner):
        inspected.append(reference)
        assert reference == ref and owner == data[0]['owner']
        return json.loads(verify(reference))
    next_view = service.continue_with(tmp_path / 'next',
        entries=[{'split': 'training', 'scope': 'study', 'evidence': ref}], inspector=successor_inspector)
    assert inspected == [ref]
    assert next_view.snapshot == service.snapshot
    assert next_view.capability_cards == service.capability_cards
    assert next_view.overview()['experiences']['stages'] == {'construction': 3, 'execution': 1}
    assert any(item['value']['format'] == 'capability_investigation_note_v1' for item in next_view.history.values())
    unchanged = next_view.continue_with(tmp_path / 'no-change-next')
    assert unchanged.snapshot == next_view.snapshot
    assert unchanged.overview()['experiences'] == next_view.overview()['experiences']


def test_continuation_preserves_sealed_material_until_explicit_role_transition(tmp_path, data):
    sealed = put(tmp_path / 'sealed-answer.json', {'answer': 'hidden'})
    service = make(tmp_path, data, sealed_evidence=[sealed], development_evidence=[sealed])
    service.expose_development()  # A shared sealed hash must remain sealed.
    next_view = service.continue_with(tmp_path / 'still-sealed')
    assert 'evidence_' + sealed['sha256'] not in next_view.evidence
    exposed = next_view.continue_with(tmp_path / 'exposed', expose_evaluation=True)
    assert exposed.read('evidence', 'evidence_' + sealed['sha256'])['content']
    transition = json.loads((tmp_path / 'exposed/transition.json').read_text())
    assert transition['evaluation_exposed'] is True
    assert transition['next_independent_evaluation'] == 'fresh_material_required'
    third = exposed.continue_with(tmp_path / 'third-generation')
    assert third.read('evidence', 'evidence_' + sealed['sha256'])['content']


def test_continuation_cannot_silently_drop_capability_refs_used_by_earlier_experience(tmp_path, data):
    from src.adapters.capability_contract import create_capability_snapshot
    service = make(tmp_path, data)
    with pytest.raises(ValueError, match='capability_not_visible'):
        service.continue_with(tmp_path / 'lost-C',
            snapshot=create_capability_snapshot(data[0]['owner'], [], []))


def test_search_pages_and_filters_return_stable_cards(tmp_path, data):
    service = make(tmp_path, data)
    first = service.search('experience', 'conversion', limit=1)
    second = service.search('experience', 'conversion', offset=first['next_offset'], limit=1)
    assert first['total'] == second['total'] == 3
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert service.search('experience', status='failed')['total'] == 1
    assert service.search('experience', stage='execution')['total'] == 0
    assert service.search('experience', capability=data[0]['roots'][0]['id'])['total'] == 3
    caps = service.search('capability', 'metadata')
    assert caps['total'] == 1
    assert caps['items'][0]['description'] == 'Prepare metadata records'
    assert 'implementation' not in caps['items'][0]


@pytest.mark.parametrize('offset,limit', [(-1, 10), (True, 10), (0, False), (0, 0), (0, 101)])
def test_invalid_page_is_rejected(tmp_path, data, offset, limit):
    with pytest.raises(ValueError, match='page_invalid'):
        make(tmp_path, data).search('experience', offset=offset, limit=limit)


def test_duplicate_retries_preserve_source_identity(tmp_path, data):
    snapshot, rows, catalog = data
    duplicate = json.loads(verify(rows[0]['evidence']))
    duplicate['task_id'] = 'renamed-retry'
    rows.append({'split': 'training', 'scope': 'study',
                 'evidence': put(tmp_path / 'retry.json', duplicate)})
    rows.append(copy.deepcopy(rows[0]))
    service = make(tmp_path, data)
    overview = service.overview()
    assert overview['experiences']['observations'] == 4
    assert overview['experiences']['independent_sources'] == 3


def test_local_evidence_keeps_diagnostics_and_cost_scope(tmp_path, data):
    service = make(tmp_path, data)
    identifier = service.search('experience')['items'][0]['id']
    diagnostics = service.read('experience', identifier, 'diagnostics')
    assert diagnostics['items'][0]['error'] == 'binding_incompatible'
    context = service.read('experience', identifier, 'context')
    assert context['cost_attribution'] == 'construction_requests_only'
    assert context['decision_context']['state'] == 'Interface conversion required'
    assert service.read('experience', identifier, 'steps')['items'][0]['call_id'] == 'prepare'
    evidence = service.read('experience', identifier, 'evidence')['items']
    assert all('name' in item and 'suffix' in item for item in evidence)


def test_action_cards_are_deterministic_paged_and_searchable(tmp_path, data):
    row = json.loads(verify(data[1][0]['evidence']))
    row['action_overview'] = [{'index': index, 'name': 'execute',
        'command_first_line': 'node process-' + str(index) + '.js', 'returncode': 0}
        for index in range(86)]
    row['action_scope'] = 'original_host_actions'
    data[1][0]['evidence'] = put(tmp_path / 'row-0.json', row)
    service = make(tmp_path, data)
    assert 'process-' not in json.dumps(service.overview())
    found = service.search('experience', 'process-75')['items']
    assert len(found) == 1 and found[0]['observed_actions'] == 86
    page = service.read('experience', found[0]['id'], 'actions', offset=74, limit=3)
    assert page['total'] == 86 and page['next_offset'] == 77
    assert [item['index'] for item in page['items']] == [74, 75, 76]


def test_raw_evidence_uses_indexed_ids_and_explicit_windows(tmp_path, data):
    snapshot, rows, _ = data
    row = json.loads(verify(rows[0]['evidence']))
    raw = tmp_path / 'long.json'
    payload = json.dumps({'text': '雪' * 1200}, ensure_ascii=False)
    raw.write_text(payload, encoding='utf-8')
    row['evidence'].append(file_ref(raw))
    rows[0]['evidence'] = put(tmp_path / 'row-0.json', row)
    service = make(tmp_path, data)
    identifier = 'evidence_' + file_ref(raw)['sha256']
    first = service.read('evidence', identifier, 'content', limit=1)
    second = service.read('evidence', identifier, 'content', offset=first['next_offset'], limit=1)
    third = service.read('evidence', identifier, 'content', offset=second['next_offset'], limit=1)
    assert first['content'] + second['content'] + third['content'] == payload
    assert third['next_offset'] is None
    with pytest.raises(ValueError, match='read_unavailable'):
        service.read('evidence', str(raw), 'content')


def test_changed_original_invalidates_later_read(tmp_path, data):
    service = make(tmp_path, data)
    identifier = next(row['id'] for row in service.search('experience')['items']
                      if row['source_identity'] == 'source-0')
    Path(data[1][0]['evidence']['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence_changed'):
        service.read('experience', identifier)


@pytest.mark.parametrize('field,value', [('split', 'heldout'), ('scope', 'other')])
def test_host_selected_training_scope_is_preserved(tmp_path, data, field, value):
    data[1][0][field] = value
    with pytest.raises(ValueError, match='split_or_scope'):
        make(tmp_path, data)


def test_hidden_capability_reference_is_rejected(tmp_path, data):
    row = json.loads(verify(data[1][0]['evidence']))
    row['capabilities'][0]['sha256'] = 'f' * 64
    data[1][0]['evidence'] = put(tmp_path / 'row-0.json', row)
    with pytest.raises(ValueError, match='not_visible'):
        make(tmp_path, data)


def test_history_is_queryable_by_evidence_without_a_new_store(tmp_path, data):
    history = put(tmp_path / 'past.json', {'owner': 'owner', 'format': 'evolution_result',
                                         'status': 'no_change', 'reason': 'No net gain observed'})
    service = make(tmp_path, data, history=[history])
    found = service.search('history', 'net gain')['items']
    assert len(found) == 1
    assert json.loads(service.read('history', found[0]['id'], 'content')['content'])['status'] == 'no_change'
    assert service.overview()['history_entries'] == 1


def test_history_summary_is_compact_and_original_content_is_paged(tmp_path, data):
    value = {'owner': 'owner', 'format': 'evolution_result', 'status': 'no_change', 'kind': 'investigation',
             'tool_calls': [{'result': {'payload': '真实调查' * 1000}} for _ in range(53)]}
    reference = put(tmp_path / 'large-history.json', value)
    original = verify(reference).decode('utf-8')
    service = make(tmp_path, data, history=[reference])
    identifier = service.search('history')['items'][0]['id']
    card = service.read('history', identifier)
    assert card['entry_counts'] == {'tool_calls': 53}
    assert card['evidence_id'] == 'evidence_' + reference['sha256']
    assert card['reference'] == reference
    assert len(json.dumps(card, ensure_ascii=False)) < 1000
    assert 'payload' not in json.dumps(card)
    first = service.read('history', identifier, 'content', limit=1)
    assert first['content'] == original[:512]
    assert first['total_characters'] == len(original) and first['next_offset'] == 1
    assert first['evidence_id'] == card['evidence_id']
    assert service.read('evidence', card['evidence_id'], 'content', limit=1)['content'] == first['content']
    assert verify(reference).decode('utf-8') == original


@pytest.mark.parametrize('kind', ['history', 'evidence'])
def test_json_subtree_selection_paginates_only_selected_content(tmp_path, data, kind):
    value = {'owner': 'owner', 'tool_calls': [{'result': {'payload': '字段' * 800}}, {'result': 'unselected'}]}
    reference = put(tmp_path / 'selected-history.json', value)
    service = make(tmp_path, data, history=[reference])
    identifier = ('history_' if kind == 'history' else 'evidence_') + reference['sha256']
    selected_path = ['tool_calls', 0, 'result']
    expected = json.dumps(value['tool_calls'][0]['result'], ensure_ascii=False)
    chunks = []
    offset = 0
    while offset is not None:
        page = service.dispatch('evolution_read', {'kind': kind, 'id': identifier, 'section': 'content',
            'json_path': selected_path, 'offset': offset, 'limit': 1})
        assert page['json_path'] == selected_path
        assert page['total_characters'] == len(expected)
        assert page['content_encoding'] == 'json'
        chunks.append(page['content'])
        offset = page['next_offset']
    assert ''.join(chunks) == expected
    assert 'unselected' not in ''.join(chunks)
    assert json.loads(verify(reference)) == value


@pytest.mark.parametrize('selector', ['tool_calls', [True], [-1], [None], [{}]])
def test_invalid_json_selectors_are_rejected(tmp_path, data, selector):
    reference = put(tmp_path / 'history.json', {'owner': 'owner', 'tool_calls': []})
    service = make(tmp_path, data, history=[reference])
    with pytest.raises(ValueError, match='json_path_invalid'):
        service.read('evidence', 'evidence_' + reference['sha256'], 'content', json_path=selector)


@pytest.mark.parametrize('selector', [['missing'], ['tool_calls', 1], ['tool_calls', '0']])
def test_missing_json_fields_or_array_indices_remain_explicit_failures(tmp_path, data, selector):
    reference = put(tmp_path / 'history.json', {'owner': 'owner', 'tool_calls': [{}]})
    service = make(tmp_path, data, history=[reference])
    with pytest.raises(ValueError, match='json_path_missing'):
        service.read('history', 'history_' + reference['sha256'], 'content', json_path=selector)


def test_json_selector_does_not_expand_evidence_or_bypass_version_checks(tmp_path, data):
    reference = put(tmp_path / 'history.json', {'owner': 'owner', 'tool_calls': [{'result': 1}]})
    service = make(tmp_path, data, history=[reference])
    with pytest.raises(ValueError, match='read_unavailable'):
        service.read('evidence', str(reference['path']), 'content', json_path=[])
    Path(reference['path']).write_text('{}')
    with pytest.raises(ValueError, match='evidence_changed'):
        service.read('history', 'history_' + reference['sha256'], 'content', json_path=['tool_calls'])


def test_json_selector_requires_json_while_plain_evidence_remains_unchanged(tmp_path, data):
    raw = tmp_path / 'original.txt'
    raw.write_text('原始纯文本证据')
    reference = file_ref(raw)
    row = json.loads(verify(data[1][0]['evidence']))
    row['evidence'].append(reference)
    data[1][0]['evidence'] = put(tmp_path / 'row-0.json', row)
    service = make(tmp_path, data)
    identifier = 'evidence_' + reference['sha256']
    assert service.read('evidence', identifier, 'content')['content'] == raw.read_text()
    with pytest.raises(ValueError, match='json_content_required'):
        service.read('evidence', identifier, 'content', json_path=[])


def test_read_tool_schema_documents_and_accepts_local_json_selection(tmp_path, data):
    tool = next(tool for tool in make(tmp_path, data).tools() if tool['name'] == 'evolution_read')
    validator = Draft202012Validator(tool['parameters'])
    validator.validate({'kind': 'history', 'id': 'history-id', 'section': 'content',
                        'json_path': ['tool_calls', 0, 'result'], 'offset': 1, 'limit': 2})
    assert 'compact card' in tool['description'] and '512-character' in tool['description']
    assert 'json_path' in tool['description'] and 'next_offset' in tool['description']


def test_notes_are_model_interpretations_with_source_refs(tmp_path, data):
    service = make(tmp_path, data)
    identifiers = [item['id'] for item in service.search('experience')['items'][:2]]
    note = service.dispatch('evolution_note', {'hypothesis': 'Try a shared result representation',
                            'evidence_ids': identifiers, 'next_questions': ['Find a counterexample']})
    assert note['authorship'] == 'model_interpretation'
    latest = service.overview()['latest_note']
    assert str(tmp_path) not in json.dumps(latest)
    assert json.loads(service.read('evidence', latest['id'], 'content')['content']) == note
    with pytest.raises(ValueError, match='unavailable'):
        service.note('Unknown support', ['invented'], [])
    assert json.loads((service.directory / 'tool-0.json').read_text())['status'] == 'succeeded'


def test_selected_observations_reuse_original_candidate_validation(tmp_path, data):
    service = make(tmp_path, data)
    identifiers = [item['id'] for item in service.search('experience')['items'][:2]]
    context = service.context(identifiers)
    assert context['inventory']['unknown_cost'] in (0, 1)
    assert context['observations'][0]['cost_attribution'] == 'construction_requests_only'
    mapping = service.reference_map(identifiers)
    candidate = {'kind': 'boundary', 'burden': 'Repeated conversion', 'evidence_ids': identifiers,
                 'scope': 'study', 'expected_behavior': 'Reuse stable conversion',
                 'verification': 'Independent original checks', 'failure_conditions': 'Retain old version',
                 'proposal': {'regions': {task: ['prepare'] for task in mapping}}}
    restored = restore_regions(candidate, mapping)
    assert validate_candidate(restored, context) == restored
    assert set(restored['proposal']['regions']) == {row['task_id'] for row in context['observations']}


def test_single_source_view_does_not_manufacture_cross_task_support(tmp_path, data):
    snapshot, rows, _ = data
    service = Investigation(snapshot, rows[:1], 'study', tmp_path / 'one', inspector=inspect)
    identifiers = [service.search('experience')['items'][0]['id']]
    context = service.context(identifiers)
    proposal = {'kind': 'capability', 'burden': 'Example', 'evidence_ids': identifiers, 'scope': 'study',
                'expected_behavior': 'Example', 'verification': 'Check', 'failure_conditions': 'Fallback',
                'proposal': {}}
    with pytest.raises(ValueError, match='cross_task_support_required'):
        validate_candidate(proposal, context)


def test_tool_schemas_and_failure_journal(tmp_path, data):
    service = make(tmp_path, data)
    for tool in service.tools():
        Draft202012Validator.check_schema(tool['parameters'])
    result = service.dispatch('evolution_search', {'kind': 'capability', 'query': 'metadata'})
    assert result['total'] == 1
    with pytest.raises(ValueError, match='read_unavailable'):
        service.dispatch('evolution_read', {'kind': 'capability', 'id': 'invented'})
    record = json.loads((service.directory / 'tool-1.json').read_text())
    assert record['status'] == 'failed'
    assert service.dispatch('evolution_overview', {})['scope'] == 'study'


@pytest.mark.parametrize('value', [-1, True, 'NaN', 'Infinity'])
def test_invalid_cost_is_rejected(tmp_path, data, value):
    row = json.loads(verify(data[1][0]['evidence']))
    row['observed_cost_usd'] = value
    data[1][0]['evidence'] = put(tmp_path / 'row-0.json', row)
    with pytest.raises(ValueError, match='cost_invalid'):
        make(tmp_path, data)


def test_host_manifest_indexes_only_declared_existing_sources(tmp_path, data):
    original = put(tmp_path / 'native-failure.json', {'error': 'actual_native_failure'})
    secret = put(tmp_path / 'unselected.json', {'private': 'outside_selected_sources'})
    manifest = put(tmp_path / 'construction.json', {
        'format': 'gene_benchmark_construction_feedback_v1', 'owner': 'owner', 'scope': 'study',
        'origin': 'trusted_benchmark_host', 'status': 'no_change',
        'sources': {'native': [original]}, 'candidate': {'forged_ref': secret}})
    service = make(tmp_path, data, history=[manifest])
    assert 'actual_native_failure' in service.read('evidence', 'evidence_' + original['sha256'])['content']
    with pytest.raises(ValueError, match='read_unavailable'):
        service.read('evidence', 'evidence_' + secret['sha256'])


def test_host_manifest_corrupt_source_is_not_silently_ignored(tmp_path, data):
    original = put(tmp_path / 'native.json', {'status': 'failed'})
    manifest = put(tmp_path / 'construction.json', {
        'format': 'gene_benchmark_construction_feedback_v1', 'owner': 'owner', 'scope': 'study',
        'origin': 'trusted_benchmark_host', 'sources': {'native': [original]}})
    Path(original['path']).write_text('{}')
    with pytest.raises(ValueError, match='evidence_changed'):
        make(tmp_path, data, history=[manifest])


def test_host_manifest_scope_cannot_expand_selected_history(tmp_path, data):
    manifest = put(tmp_path / 'construction.json', {
        'format': 'gene_benchmark_construction_feedback_v1', 'owner': 'owner', 'scope': 'different',
        'origin': 'trusted_benchmark_host', 'sources': {}})
    with pytest.raises(ValueError, match='scope_changed'):
        make(tmp_path, data, history=[manifest])
