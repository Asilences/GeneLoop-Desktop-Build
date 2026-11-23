from src.adapters.ppt.learning.ppt_workflow_learning import continuations, discover_workflows, collect_workflow_trace


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


def parallel_trace(identity, count):
    sample=trace(identity)
    anchor=sample['records'][0]
    anchor['value']['review_pages']=[{'path':f'/owned/{identity}-{n}.png','sha256':str(n % 10)*64} for n in range(count)]
    sample['records']=[anchor]+[
        {'name':'image','call_id':f'image-{identity}-{n}','error':False,
         'arguments':{'file_path':row['path']},'call_sequence':2+n,'result_sequence':2+count+n,
         'content':[{'type':'image','attachment':{'attachmentId':'sha256:'+row['sha256']}}]}
        for n,row in enumerate(anchor['value']['review_pages'])]
    return sample


def test_parallel_full_collection_read_induces_map_after_two_lengths_and_certifies_third():
    rows=[parallel_trace('a',4),parallel_trace('b',5),parallel_trace('c',6)]
    library=discover_workflows(rows[:2],rows[2:],CONTRACTS,'environment')
    program=next(p for p in library['programs'] if p['ir']['kind']=='observed_anchor_read_map')
    assert program['status']=='certified'
    assert program['ir']['step']['bindings']=={'file_path':['path']}
    assert {w['collection_length'] for w in program['provenance']}=={4,5}
    assert program['certification']['replay'][0]['collection_length']==6
    assert '/owned/' not in str(program['ir'])
    from src.adapters.ppt.learning.ppt_skill_opportunities import program_tools
    assert program_tools(program)=={'export','image'}


def test_map_requires_length_variation_and_unseen_independent_certification_length():
    for counts in [(4,4,6),(4,5,5)]:
        rows=[parallel_trace(key,n) for key,n in zip('abc',counts)]
        maps=[p for p in discover_workflows(rows[:2],rows[2:],CONTRACTS,'environment')['programs']
              if p['ir']['kind']=='observed_anchor_read_map']
        assert not maps or maps[0]['status']=='candidate'
    rows=[parallel_trace('a',4),parallel_trace('b',5),parallel_trace('c',6)]
    rows[2]['source_signature']=rows[0]['source_signature']
    assert not any(p['status']=='certified' for p in discover_workflows(rows[:2],rows[2:],CONTRACTS,'environment')['programs'])


def test_parallel_read_map_rejects_missing_pages_literals_wrong_bytes_and_intervening_writes():
    from src.adapters.ppt.learning.ppt_workflow_learning import mapped_continuations
    for defect in ('partial','literal','wrong_version','write','before_anchor'):
        row=parallel_trace('a',4)
        if defect=='partial':row['records'].pop()
        if defect=='literal':row['records'][1]['arguments']['extra']='not-bound'
        if defect=='wrong_version':row['records'][1]['content'][0]['attachment']['attachmentId']='sha256:'+'f'*64
        if defect=='write':row['records'][2]['name']='export'
        if defect=='before_anchor':row['records'][1]['call_sequence']=0
        assert not list(mapped_continuations(row,CONTRACTS)),defect


def test_workflow_order_and_current_value_binding_are_discovered_from_distinct_traces():
    library = discover_workflows([trace('a'), trace('b')], [trace('c')], CONTRACTS, 'environment')
    program = library['programs'][0]
    assert program['status'] == 'certified'
    assert program['certification']['independent_replay_decisions'] == 1
    assert program['ir']['steps'][0]['bindings'] == {'file_path': ['review_pages', 0, 'path']}
    assert '/owned/' not in str(program['ir'])
    assert CONTRACTS[program['ir']['anchor']['tool']]['read_only'] is False


def test_same_decision_or_source_and_training_reuse_do_not_create_independent_certification():
    for key in ('decision_id', 'source_signature'):
        a, b = trace('a'), trace('b')
        b[key] = a[key]
        assert not discover_workflows([a, b], [trace('c')], CONTRACTS, 'environment')['programs']
    candidate = discover_workflows([trace('a'), trace('b')], [trace('a')], CONTRACTS, 'environment')['programs'][0]
    assert candidate['status'] == 'candidate'


def test_same_natural_prompt_with_distinct_documents_and_sessions_is_independent():
    rows = [trace(identity) for identity in ('a', 'b', 'c')]
    for row in rows:
        row['question_sha256'] = 'same-user-request'
    program = discover_workflows(rows[:2], rows[2:], CONTRACTS, 'environment')['programs'][0]
    assert program['status'] == 'certified'
    assert program['certification']['independence_policy'] == 'ppt_distinct_source_decision_v2'
    assert program['provenance'][0]['question_sha256'] == program['certification']['replay'][0]['question_sha256']


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


def test_followup_trace_does_not_attribute_inherited_operations_to_this_turn(tmp_path):
    import json
    rows=[]
    for name in ('inherited', 'current'):
        rows.extend([{'type':'tool/call','data':{'name':name,'callId':name,'arguments':{}}},
                     {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result',
                         'toolCallId':name,'content':[],'isError':False}]}}}])
    (tmp_path/'events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    info={'request':{},'state':{'status':'completed'},'task_dir':str(tmp_path),
          'effective':{'trace_start_index':2},'task_id':'current','decision_id':'current',
          'source_signature':'different-material','question_sha256':'same-prompt','schemas':[]}
    result=collect_workflow_trace(info)
    assert [r['name'] for r in result['records']]==['current']
    assert result['records'][0]['call_sequence']==2


def test_two_sources_record_candidates_without_publishing_or_needing_a_third_to_discover(tmp_path, monkeypatch):
    import json
    from src.adapters.ppt.learning import ppt_workflow_learning as learning
    from src.adapters.ppt.learning import ppt_skill_opportunities as hints
    package=tmp_path/'scenarios/ppt_master';package.mkdir(parents=True)
    (package/'SKILL.md').write_text('design reference')
    (package/'workflow-contracts.json').write_text(json.dumps({'tools':CONTRACTS}))
    monkeypatch.setattr(learning,'ROOT',tmp_path)
    monkeypatch.setattr(learning,'workflow_environment',lambda:'environment')
    monkeypatch.setattr(learning,'collect_workflow_trace',lambda info:{**trace(info['task_id']),'source_family':info['task_id']})
    monkeypatch.setattr(hints,'failure_observations',lambda *a:[])
    monkeypatch.setattr(hints,'skill_corpus',lambda *a:{'skill_sha256':'reference','opportunities':[]})
    store=tmp_path/'learning';store.mkdir()
    infos={key:{'task_id':key,'locks':{}} for key in ('a','b')}
    turns={key:{'id':key,'learning_lane':'baseline','lanes':{'baseline':{'task_id':key}}} for key in infos}
    learning.advance_workflow_learning(tmp_path,store,{},infos,turns,delivery=lambda *a,**k:{'mechanical_status':'passed'})
    status=json.loads((store/'workflows/status.json').read_text())
    assert status['discovered_candidates']==1 and status['certified_programs']==0
    assert not (store/'workflows/selected.json').exists()
    observed,=(store/'workflows').glob('discovered-*.json')
    assert json.loads(observed.read_text())['programs'][0]['status']=='candidate'


def test_independent_observed_writes_are_available_for_trial_without_an_extra_native_gate(tmp_path, monkeypatch):
    import json
    from tests.test_ppt_write_learning import sample, CONTRACTS as writes
    from src.adapters.ppt.learning import ppt_workflow_learning as learning
    from src.adapters.ppt.learning import ppt_skill_opportunities as hints
    package=tmp_path/'scenarios/ppt_master';package.mkdir(parents=True)
    (package/'SKILL.md').write_text('design reference')
    (package/'workflow-contracts.json').write_text(json.dumps({'tools':writes}))
    monkeypatch.setattr(learning,'ROOT',tmp_path)
    monkeypatch.setattr(learning,'workflow_environment',lambda:'environment')
    monkeypatch.setattr(learning,'collect_workflow_trace',lambda info:{**sample(info['task_id'],count=1),'source_family':info['task_id']})
    monkeypatch.setattr(hints,'failure_observations',lambda *a:[])
    monkeypatch.setattr(hints,'skill_corpus',lambda *a:{'skill_sha256':'reference','opportunities':[]})
    store=tmp_path/'learning';store.mkdir()
    infos={key:{'task_id':key,'locks':{}} for key in ('a','b','c')}
    turns={key:{'id':key,'learning_lane':'baseline','lanes':{'baseline':{'task_id':key}}} for key in infos}
    learning.advance_workflow_learning(tmp_path,store,{'user':'diagnostic','scope':'scope'},infos,turns,
                                      delivery=lambda *a,**k:{'mechanical_status':'passed'})
    pointer=json.loads((store/'workflows/selected.json').read_text())
    library=json.loads((store/'workflows'/pointer['library']).read_text())
    program=library['programs'][0]
    assert pointer['phase']=='probation' and program['ir']['kind']=='observed_page_write_delivery'
    assert program['certification']['scope']=='independent_observed_write_binding_replay'
    assert program['certification']['quality_deferred'] and program['certification']['runtime_followup_required']


def test_parallel_completion_order_does_not_prove_sequential_continuation():
    sample = trace('parallel')
    sample['records'][1]['call_sequence'] = 0
    assert not list(continuations(sample, CONTRACTS))


def test_disjoint_learning_batches_keep_older_certified_coverage(tmp_path, monkeypatch):
    import json
    from src.adapters.ppt.learning import ppt_skill_opportunities as hints
    from src.adapters.ppt.learning import ppt_workflow_learning as learning

    package = tmp_path / 'scenarios/ppt_master'
    package.mkdir(parents=True)
    (package / 'SKILL.md').write_text('design reference')
    contracts = {**CONTRACTS, 'patch': CONTRACTS['export']}
    (package / 'workflow-contracts.json').write_text(json.dumps({'tools': contracts}))
    monkeypatch.setattr(learning, 'ROOT', tmp_path)
    monkeypatch.setattr(learning, 'workflow_environment', lambda: 'environment')
    monkeypatch.setattr(learning, 'collect_workflow_trace', lambda info: info['trace'])
    monkeypatch.setattr(hints, 'skill_corpus', lambda *a: {'skill_sha256': 'reference', 'opportunities': []})
    monkeypatch.setattr(hints, 'failure_observations', lambda *a: [])
    store = tmp_path / 'learning'
    store.mkdir()
    folder = store / 'workflows'
    request = {'user': 'owner', 'scope': 'scope'}

    def learn(rows):
        infos = {}
        for row in rows:
            identity = row['task_id']
            evidence = tmp_path / identity
            evidence.write_text(identity)
            infos[identity] = {'task_id': identity, 'trace': {**row, 'source_family': identity},
                               'locks': {identity: learning.sha(evidence)}}
        turns = {key: {'lanes': {'baseline': {'task_id': key}}} for key in infos}
        learning.advance_workflow_learning(tmp_path, store, request, infos, turns,
                                          delivery=lambda *a, **k: {'mechanical_status': 'passed'})
        pointer = learning.read(folder / 'selected.json')
        return pointer, learning.read(folder / pointer['library'])

    old_pointer, old_library = learn([parallel_trace(key, count) for key, count in zip('abc', (4, 5, 6))])
    assert len(old_library['programs']) == 1
    patches = [trace(key) for key in 'def']
    for row in patches:
        row['records'][0]['name'] = 'patch'
        row['schemas']['patch'] = row['schemas']['export']
    pointer, merged = learn(patches)
    assert [row['ir']['anchor']['tool'] for row in merged['programs']] == ['export', 'patch']
    assert merged['programs'][0] == old_library['programs'][0]
    assert all(pointer['evidence_locks'][key] == value for key, value in old_pointer['evidence_locks'].items())
    assert set(pointer['evidence_locks']) == set('abcdef')
    assert learning.read(folder / old_pointer['library']) == old_library
    assert learning.retained_workflows(tmp_path, folder, pointer, request, 'other-environment', None) == ({}, {})
    assert learning.retained_workflows(tmp_path, folder, pointer, request, 'environment', 'new-feedback') == ({}, {})
    (tmp_path / 'a').write_text('tampered')
    assert learning.retained_workflows(tmp_path, folder, pointer, request, 'environment', None) == ({}, {})


def test_withdrawn_workflow_is_not_republished_by_background_learning(tmp_path):
    import json
    from src.adapters.ppt.learning.ppt_workflow_learning import advance_workflow_learning
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
    from src.adapters.ppt.learning.ppt_workflow_learning import tool_value
    content=[{'type':'text','text':'preview caption'},{'type':'text','text':'{"status":"passed"}'}]
    assert tool_value(content,[['status']])=={'status':'passed'}
    content.append({'type':'text','text':'{"status":"passed"}'})
    assert tool_value(content,[['status']]) is None


def test_native_replay_cache_changes_when_page_engine_dependency_changes(tmp_path, monkeypatch):
    import json
    from src.adapters.ppt.learning import ppt_workflow_certification as certification
    dependency = tmp_path / 'native-skill.ts'
    dependency.write_text('old runtime')
    library = tmp_path / 'library.json'
    library.write_text(json.dumps({'code_locks': {'native-skill.ts': 'historical-version'}}))
    monkeypatch.setattr(certification, 'ROOT', tmp_path)
    before = certification.component_environment(library)
    dependency.write_text('new runtime')
    assert certification.component_environment(library) != before
    assert json.loads(library.read_text())['code_locks']['native-skill.ts'] == 'historical-version'


def test_one_invalid_material_does_not_abort_learning_from_other_owned_deliveries(tmp_path, monkeypatch):
    import json
    from src.adapters.ppt.learning import ppt_workflow_learning as learning
    store = tmp_path / 'store'
    store.mkdir()
    infos = {name: {'task_id': name, 'locks': {}} for name in ('bad', 'good')}
    turns = {name: {'lanes': {'baseline': {'task_id': name}}} for name in infos}
    monkeypatch.setattr(learning, 'collect_workflow_trace', lambda info: {**trace(info['task_id']), 'source_family': info['task_id']})
    def delivery(output, turn, lane, locks, **kwargs):
        if turn['lanes'][lane]['task_id'] == 'bad':
            raise ValueError('invalid artifact bytes')
        return {'mechanical_status': 'passed'}
    learning.advance_workflow_learning(tmp_path, store, {}, infos, turns, delivery=delivery, failure_infos={})
    report = json.loads((store / 'workflows/material-admission.json').read_text())
    assert report['accepted_task_ids'] == ['good']
    assert report['excluded'] == [{'task_id': 'bad', 'reason': 'invalid artifact bytes'}]
    assert json.loads((store / 'workflows/status.json').read_text())['eligible_source_families'] == 1
