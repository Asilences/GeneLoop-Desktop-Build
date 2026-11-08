from src.adapters.ppt_workflow_learning import continuations, discover_workflows, collect_workflow_trace


CONTRACTS = {
    'export': {'read_only': False, 'observed_completion': {
        'success': ['mechanical_status'], 'success_value': 'passed',
        'empty_findings': ['findings'], 'collection': ['review_pages']}},
    'image': {'read_only': True, 'image_output_required': True},
}


def trace(identity):
    path = '/owned/' + identity + '.png'
    return {'task_id': identity, 'decision_id': identity, 'source_signature': 'source-' + identity,
            'question_sha256': 'question-' + identity, 'events_sha256': 'version-' + identity,
            'schemas': {'export': {'type': 'object'}, 'image': {'type': 'object'}},
            'records': [
                {'name': 'export', 'call_id': 'export-' + identity, 'error': False, 'arguments': {}, 'call_sequence': 0, 'result_sequence': 1,
                 'value': {'mechanical_status': 'passed', 'findings': [], 'review_pages': [{'path': path, 'sha256': 'a' * 64}]}},
                {'name': 'image', 'call_id': 'image-' + identity, 'error': False, 'arguments': {'file_path': path}, 'call_sequence': 2, 'result_sequence': 3,
                 'content': [{'type': 'image', 'attachment': {'attachmentId': 'sha256:' + 'a' * 64}}]},
            ]}


def test_workflow_order_and_current_value_binding_are_discovered_from_distinct_traces():
    library = discover_workflows([trace('a'), trace('b')], [trace('c')], CONTRACTS, 'environment')
    program = library['programs'][0]
    assert program['status'] == 'certified'
    assert program['certification']['independent_replay_decisions'] == 1
    assert program['ir']['steps'][0]['bindings'] == {'file_path': ['review_pages', 0, 'path']}
    assert '/owned/' not in str(program['ir'])
    assert CONTRACTS[program['ir']['anchor']['tool']]['read_only'] is False


def test_same_decision_or_source_and_training_reuse_do_not_create_independent_certification():
    for key in ('decision_id', 'source_signature', 'question_sha256'):
        a, b = trace('a'), trace('b')
        b[key] = a[key]
        assert not discover_workflows([a, b], [trace('c')], CONTRACTS, 'environment')['programs']
    candidate = discover_workflows([trace('a'), trace('b')], [trace('a')], CONTRACTS, 'environment')['programs'][0]
    assert candidate['status'] == 'candidate'


def test_unknown_calls_failures_and_ambiguous_binding_form_boundaries():
    for inserted in ({'name': 'unknown', 'error': False}, {'name': 'image', 'error': True}):
        sample = trace('a')
        sample['records'].insert(1, inserted)
        assert not list(continuations(sample, CONTRACTS))
    sample = trace('a')
    sample['records'][0]['value']['review_pages'][0]['alias'] = '/owned/a.png'
    assert not list(continuations(sample, CONTRACTS))


def test_failed_delivery_and_wrong_image_version_cannot_support_continuation():
    sample = trace('a')
    sample['records'][0]['value']['findings'] = [{'rule': 'overflow'}]
    assert not list(continuations(sample, CONTRACTS))
    sample = trace('a')
    sample['records'][1]['content'][0]['attachment']['attachmentId'] = 'sha256:' + 'b' * 64
    assert not list(continuations(sample, CONTRACTS))


def test_explicit_learning_holdout_is_rejected_before_opening_events():
    assert collect_workflow_trace({'request': {'learning_eligible': False}, 'state': {}}) is None


def test_parallel_completion_order_does_not_prove_sequential_continuation():
    sample = trace('parallel')
    sample['records'][1]['call_sequence'] = 0
    assert not list(continuations(sample, CONTRACTS))


def test_withdrawn_workflow_is_not_republished_by_background_learning(tmp_path):
    import json
    from src.adapters.ppt_workflow_learning import advance_workflow_learning
    for marker, body in [('selected.json', {'phase': 'disabled'}), ('suspended.json', {'reason': 'operator'})]:
        store = tmp_path / marker
        folder = store / 'workflows'
        folder.mkdir(parents=True)
        (folder / marker).write_text(json.dumps(body))
        advance_workflow_learning(tmp_path, store, {}, {}, {}, delivery=lambda *a, **k: None)
        assert json.loads((folder / 'status.json').read_text())['status'] == 'withdrawn_requires_explicit_recertification'
        assert json.loads((folder / marker).read_text()) == body


def test_incomplete_collection_and_missing_or_misbound_images_cannot_be_certified():
    sample = trace('a')
    sample['records'][0]['value']['review_pages'].append({'path': '/owned/second.png', 'sha256': 'b' * 64})
    assert not list(continuations(sample, CONTRACTS))
    sample['records'][1]['content'][0]['attachment']['attachmentId'] = 'sha256:' + 'b' * 64
    assert not list(continuations(sample, CONTRACTS)), 'An image for another row cannot witness the bound path'
    sample = trace('a')
    sample['records'][1]['content'] = [{'type': 'text', 'text': 'image unavailable'}]
    assert not list(continuations(sample, CONTRACTS))


def test_complete_sequential_collection_is_compiled_without_partial_prefixes():
    sample = trace('a')
    sample['records'][0]['value']['review_pages'].append({'path': '/owned/second.png', 'sha256': 'b' * 64})
    sample['records'].append({'name': 'image', 'call_id': 'second', 'error': False, 'call_sequence': 4, 'result_sequence': 5,
       'arguments': {'file_path': '/owned/second.png'},
       'content': [{'type': 'image', 'attachment': {'attachmentId': 'sha256:' + 'b' * 64}}]})
    rows = list(continuations(sample, CONTRACTS))
    assert len(rows) == 1 and len(rows[0][0]['steps']) == 2


def test_native_receipt_parser_accepts_a_separate_caption_and_rejects_ambiguous_receipts():
    from src.adapters.ppt_workflow_learning import tool_value
    content=[{'type':'text','text':'preview caption'},{'type':'text','text':'{"status":"passed"}'}]
    assert tool_value(content,[['status']])=={'status':'passed'}
    content.append({'type':'text','text':'{"status":"passed"}'})
    assert tool_value(content,[['status']]) is None


def test_native_replay_cache_changes_when_page_engine_dependency_changes(tmp_path, monkeypatch):
    import json
    from src.adapters import ppt_workflow_certification as certification
    dependency = tmp_path / 'native-skill.ts'
    dependency.write_text('old runtime')
    library = tmp_path / 'library.json'
    library.write_text(json.dumps({'code_locks': {'native-skill.ts': 'historical-version'}}))
    monkeypatch.setattr(certification, 'ROOT', tmp_path)
    before = certification.component_environment(library)
    dependency.write_text('new runtime')
    assert certification.component_environment(library) != before
    assert json.loads(library.read_text())['code_locks']['native-skill.ts'] == 'historical-version'
