"""Deterministic worker admission diagnostics. No model or savings claims."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adapters import ppt_page_learning as page
from src.adapters import ppt_program_learning as program


@pytest.mark.parametrize('proof,scope', [
    ({'status': 'unknown', 'mechanical_status': 'passed'}, 'delivered_page_parameters_scientific_quality_not_certified'),
    ({'status': 'failed', 'model_failed_pages': [1], 'layout_status': 'passed'}, program.LAYOUT_ONLY_SCOPE),
    ({'status': 'failed', 'model_failed_pages': [1], 'layout_status': 'failed'}, None),
    ({'status': 'failed', 'model_failed_pages': [1]}, None),
])
def test_page_material_admission_is_scoped_to_verified_visual_structure(proof, scope):
    assert program.page_material_scope(proof) == scope


@pytest.mark.parametrize('changed', [
    'src/adapters/ppt_component_tool.ts', 'src/adapters/ppt_component_schema.ts',
    'src/adapters/ppt_component_render.py', 'scenarios/ppt_master/runtime-policy.md',
    'src/adapters/ppt_background_review.py', 'src/adapters/ppt_delivery_quality.py',
])
def test_execution_protocol_changes_create_a_fresh_certification_attempt(monkeypatch, changed):
    baseline = program.program_implementation_signature()
    original = program.sha
    monkeypatch.setattr(program, 'sha', lambda path: 'changed-version' if Path(path) == program.ROOT / changed else original(path))
    assert program.program_implementation_signature() != baseline


@pytest.fixture
def materials(tmp_path, monkeypatch):
    store = tmp_path / 'learning/ppt-owner'
    store.mkdir(parents=True)
    sources, eligible = [], []
    for n in (1, 2):
        svg = store / f'{n}.svg'
        svg.write_text(f'<svg><text>content {n}</text></svg>')
        receipt = tmp_path / f'receipt-{n}.json'
        program.save(receipt, {'mechanical_status': 'passed'})
        sources.append({'task_id': str(n), 'source_signature': str(n), 'compatibility': 'same', 'layout_fingerprint': 'layout',
                        'svg': str(svg), 'svg_sha256': program.sha(svg), 'events_sha256': 'events', 'call_id': 'call',
                        'delivered': {'receipt': str(receipt), 'receipt_sha256': program.sha(receipt)}})
        eligible.append(({'id': f'turn-{n}'}, {'task_id': str(n), 'locks': {}, 'task_dir': str(tmp_path),
                         'source_signature': str(n), 'decision_id': str(n), 'question_sha256': str(n)}))
    (store / 'component-opportunities').mkdir()
    program.save(store / 'component-opportunities/index.json', {'sources': {str(i): row for i, row in enumerate(sources)}})
    monkeypatch.setenv('GENELOOP_PPT_COMPONENT_LEARNING_POLICY', 'private-policy')
    calls = []
    def proposal(*args, **kwargs):
        calls.append(kwargs['independent']['task_id'])
        return {'heldout_parameters': {'title': 'independent'}}
    def prepare(witness, proposal, directory, heldout):
        directory.mkdir()
        program.save(directory / 'candidates.json', [])
    def certify(candidates, folder, resources):
        program.save(folder / 'library.json', {'digest': 'certified', 'programs': [{'id': 'page'}]})
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(page, 'propose_component', proposal)
    monkeypatch.setattr(page, 'prepare_candidate', prepare)
    monkeypatch.setattr(program, 'certify_programs', certify)
    return tmp_path, store, eligible, calls


def test_normal_independent_pages_publish_only_after_certification(materials):
    output, store, eligible, calls = materials
    assert page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    pointer = program.read(store / 'program-selected.json')
    assert pointer['phase'] == 'probation'
    assert pointer['origin'] == 'automatic_normal_page_parameterization_v1'
    assert pointer['support_turns'] == ['turn-1', 'turn-2']
    assert len(calls) == 1
    assert not page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert len(calls) == 1


def test_feedback_change_during_generation_cannot_publish(materials, monkeypatch):
    output, store, eligible, calls = materials
    original = page.propose_component
    def veto(*args, **kwargs):
        result = original(*args, **kwargs)
        program.save(store / 'feedback-version.json', {'version': 'withdrawn'})
        return result
    monkeypatch.setattr(page, 'propose_component', veto)
    assert not page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert not (store / 'program-selected.json').exists()
    assert 'feedback_changed' in program.read(store / 'page-learning-status.json')['reason']


def test_same_decision_or_source_never_buys_a_candidate(materials):
    output, store, eligible, calls = materials
    eligible[1][1]['decision_id'] = eligible[0][1]['decision_id']
    assert not page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert calls == []


def test_normal_output_reused_as_an_independent_input_is_an_opportunity_signal(materials):
    output, store, eligible, calls = materials
    path = store / 'component-opportunities/index.json'
    index = program.read(path)
    index['sources']['0']['delivered']['deck_sha256'] = 'reference-template'
    index['sources']['1'].update(layout_fingerprint='different', input_versions=['reference-template'])
    program.save(path, index)
    assert page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert len(calls) == 1


@pytest.mark.parametrize('json_mode,changed_prompt', [(False, False), (True, False), (True, True)])
def test_validator_revision_can_reuse_the_exact_metered_proposal_without_a_new_model_call(materials, json_mode, changed_prompt):
    output, store, eligible, calls = materials
    old = store / 'program-previous'
    (old / 'model-proposal').mkdir(parents=True)
    index = program.read(store / 'component-opportunities/index.json')
    program.save(old / 'learning-evidence.json', {'sources': list(index['sources'].values())})
    proposal = {'description': 'Current title', 'source': 'import sys,json\nprint(json.load(open(sys.argv[1])))',
                'parameters_schema': {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title']},
                'default_parameters': {'title': 'Training'}, 'heldout_parameters': {'title': 'Independent'}}
    program.save(old / 'model-proposal/proposal.json', proposal)
    import json
    cached_request = page.proposal_request({'parameter_policy': page.TEXT_CONTENT_POLICY}, independent={})
    if changed_prompt:
        cached_request['messages'][0]['content'] = 'Obsolete generation contract'
    if json_mode:
        answer = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal)}}]}
    else:
        cached_request.pop('response_format')
        answer = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': 'propose_ppt_component', 'arguments': json.dumps(proposal)}}]}}]}
    program.save(old / 'model-proposal/request.json', cached_request)
    program.save(old / 'model-proposal/response.json', answer)
    assert page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert calls == (['2'] if changed_prompt else [])
    status = program.read(store / 'page-learning-status.json')
    assert status['proposal_reused'] is not changed_prompt
    assert status['model_request_attempted'] is changed_prompt


def test_transient_certification_failure_reuses_the_saved_proposal(materials, monkeypatch):
    output, store, eligible, calls = materials
    original_proposal = page.propose_component
    import json
    def saved_proposal(*args, **kwargs):
        original_proposal(*args, **kwargs)
        folder = args[2]
        folder.mkdir()
        value = {'description': 'Current title', 'source': 'import sys,json\nprint(json.load(open(sys.argv[1])))',
                 'parameters_schema': {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title']},
                 'default_parameters': {'title': 'Training'}, 'heldout_parameters': {'title': 'Independent'}}
        program.save(folder / 'proposal.json', value)
        program.save(folder / 'request.json', page.proposal_request({'parameter_policy': page.TEXT_CONTENT_POLICY}, independent={}))
        program.save(folder / 'response.json', {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': 'propose_ppt_component', 'arguments': json.dumps(value)}}]}}]})
        return value
    original_certify = program.certify_programs
    attempts = []
    def temporary_failure(*args):
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError('Temporary transport failure')
        return original_certify(*args)
    monkeypatch.setattr(page, 'propose_component', saved_proposal)
    monkeypatch.setattr(program, 'certify_programs', temporary_failure)
    assert not page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert program.read(store / 'page-learning-status.json')['status'] == 'retryable'
    assert page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert len(calls) == 1 and len(attempts) == 2


@pytest.mark.parametrize('repair_succeeds', [True, False])
def test_certification_content_failure_has_one_metered_correction_then_stops(materials, monkeypatch, repair_succeeds):
    output, store, eligible, calls = materials
    original = program.certify_programs
    certifications = []
    original_propose = page.propose_component
    def propose(witness, policy, folder, **kwargs):
        value = original_propose(witness, policy, folder, **kwargs)
        folder.mkdir()
        for name in ('request.json', 'response.json', 'proposal.json'):
            program.save(folder / name, {'diagnostic': True})
        if folder.name == 'model-repair':
            assert witness['certification_findings']['rejected'][0]['reason'] == 'task_specific_content_not_parameterized'
            assert witness['rejected_proposal']['heldout_parameters'] == {'title': 'independent'}
        return value
    def certify(candidates, folder, resources):
        certifications.append(folder.name)
        if len(certifications) == 1 or not repair_succeeds:
            program.save(folder / 'library.json', {'programs': []})
            program.save(folder / 'report.json', {'rejected': [{'reason': 'task_specific_content_not_parameterized'}]})
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        return original(candidates, folder, resources)
    monkeypatch.setattr(page, 'propose_component', propose)
    monkeypatch.setattr(program, 'certify_programs', certify)
    assert page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible) is repair_succeeds
    assert len(calls) == 2 and certifications == ['candidate', 'candidate-repair']
    assert not page.advance_page_components(output, store, {'user': 'owner', 'scope': 'scope'}, eligible)
    assert len(calls) == 2
    if repair_succeeds:
        pointer = program.read(store / 'program-selected.json')
        assert any(name.endswith('model-repair/response.json') for name in pointer['evidence_locks'])


def test_recertification_prefers_the_saved_correction_over_the_original_rejection(materials):
    import json
    output, store, eligible, calls = materials
    sources = list(program.read(store / 'component-opportunities/index.json')['sources'].values())
    for name, phase in [('program-a-original', 'model-proposal'), ('program-z-corrected', 'model-repair')]:
        folder = store / name
        model = folder / phase
        model.mkdir(parents=True)
        program.save(folder / 'learning-evidence.json', {'sources': sources})
        witness = {'parameter_policy': page.TEXT_CONTENT_POLICY}
        if phase == 'model-repair':
            witness['certification_findings'] = True
        value = {'description': phase, 'source': 'import sys,json\nprint(json.load(open(sys.argv[1])))',
                 'parameters_schema': {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title']},
                 'default_parameters': {'title': 'Training'}, 'heldout_parameters': {'title': 'Independent'}}
        program.save(model / 'request.json', page.proposal_request(witness, independent={}))
        program.save(model / 'response.json', {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]})
        program.save(model / 'proposal.json', value)
    proposal, proof = page.cached_page_proposal(store, sources)
    assert proposal['description'] == 'model-repair'
    assert proof['request_sha256'] == program.sha(Path(proof['request']))
    assert calls == []
