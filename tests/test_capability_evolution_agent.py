"""Protocol diagnostics, not autonomous model or efficiency evidence."""
import copy
import json

import pytest

from src.adapters.capability_contract import capability_digest
from src.adapters.capability_evolution_agent import packet, run, validate_candidate, model_view, restore_regions
from src.adapters.capability_feedback import file_ref
from tests.test_capability_feedback import fixture
from tests.test_capability_goal_proposal import FiniteDiagnosticGate
from tests.test_capability_proposal_loop import fake_harness
from tests.test_capability_motif_learning import corpus, publish


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


def inspect(ref, owner):
    from src.adapters.capability_feedback import verify
    return json.loads(verify(ref))


@pytest.fixture
def data(tmp_path):
    _, library, source, _ = fixture(tmp_path)
    snapshot = library['snapshot']; rows = []
    for i in range(3):
        row = {'task_id': 'task-' + str(i), 'source_identity': str(i), 'relation': 'same-binding',
               'stage': 'execution', 'status': 'passed' if i != 1 else 'failed',
               'counterexample': i == 1, 'quality': 'unreviewed', 'capabilities': snapshot['roots'],
               'steps': [{'call_id': 'first', 'capability': snapshot['roots'][0], 'status': 'succeeded'},
                         {'call_id': 'second', 'capability': snapshot['roots'][1], 'status': 'succeeded'}],
               'observed_cost_usd': None, 'evidence': [source]}
        ref = put(tmp_path / ('row-' + str(i) + '.json'), row)
        rows.append({'split': 'training', 'scope': 'study', 'evidence': ref})
    return snapshot, rows


def make(tmp_path, data, **kwargs):
    snapshot, rows = data
    result = packet(rows, snapshot, 'study', tmp_path / 'packet', inspector=inspect, **kwargs)
    context = json.loads(open(result['packet']['path']).read()) if result['packet'] else None
    return result, context


def candidate(context):
    return {'kind': 'boundary', 'burden': 'Repeated conversion',
            'evidence_ids': [r['id'] for r in context['observations']], 'scope': 'same input contract',
            'expected_behavior': 'Call a compiled stable conversion', 'verification': 'Host checks on new inputs',
            'failure_conditions': 'Keep original on failure', 'proposal': {'regions': {
                r['task_id']: ['first', 'second'] for r in context['observations']}}}


def model_candidate(value, context):
    result = copy.deepcopy(value)
    _, mappings = model_view(context)
    result['proposal']['regions'] = {task: ['call_0', 'call_1'] for task in mappings}
    return result


def test_packet_deduplicates_sources_and_retains_counterexample_inventory(tmp_path, data):
    snapshot, rows = data
    duplicate = copy.deepcopy(json.loads(open(rows[0]['evidence']['path']).read()))
    duplicate['task_id'] = 'renamed-retry'
    rows.append({'split': 'training', 'scope': 'study', 'evidence': put(tmp_path / 'retry.json', duplicate)})
    result, context = make(tmp_path, data, max_examples=2)
    assert context['independent_sources'] == 3
    assert context['inventory'] == {'observations': 4, 'failed': 1, 'counterexamples': 1, 'unknown_cost': 4}
    assert context['observations'][0]['counterexample'] is True
    assert context['omitted_observations'] == 2
    assert all('implementation' not in card for card in context['capabilities'])
    assert len(json.loads(open(result['index']['path']).read())['groups']) == 1


def test_single_task_retries_do_not_admit_model(tmp_path, data):
    snapshot, rows = data
    for entry in rows:
        row = json.loads(open(entry['evidence']['path']).read()); row['source_identity'] = 'same'
        entry['evidence'] = put(__import__('pathlib').Path(entry['evidence']['path']), row)
    result, context = make(tmp_path, data)
    assert result['status'] == 'insufficient_evidence' and context is None


def test_heldout_never_enters_packet(tmp_path, data):
    data[1][1]['split'] = 'heldout'
    with pytest.raises(ValueError, match='split_or_scope'):
        make(tmp_path, data)


def test_capacity_rejects_instead_of_silently_truncating(tmp_path, data):
    with pytest.raises(ValueError, match='capacity_exceeded'):
        make(tmp_path, data, context_bytes=1024)


@pytest.mark.parametrize('mutation,message', [
    ('extra', 'fields'), ('support', 'cross_task'), ('reorder', 'contiguous'), ('invent', 'not_observed')])
def test_model_cannot_invent_evidence_guards_or_graph_calls(tmp_path, data, mutation, message):
    _, context = make(tmp_path, data); value = candidate(context)
    if mutation == 'extra': value['certified'] = True
    if mutation == 'support': value['evidence_ids'] = [context['observations'][0]['id']]
    if mutation == 'reorder': value['proposal']['regions'][context['observations'][0]['task_id']] = ['second', 'first']
    if mutation == 'invent': value['proposal']['regions'][context['observations'][0]['task_id']] = ['fake']
    with pytest.raises(ValueError, match=message): validate_candidate(value, context)


def test_disabled_does_not_read_or_create(tmp_path):
    assert run(None, tmp_path / 'unused') == {'status': 'disabled', 'model_requests': 0}
    assert not (tmp_path / 'unused').exists()


def test_real_transport_seam_passes_model_candidate_to_host_not_certification(tmp_path, data, monkeypatch):
    result, context = make(tmp_path, data); value = candidate(context); seen = []
    fake_harness(monkeypatch, json.dumps({'candidates': [model_candidate(value, context)]}), notifications=True)
    def handler(proposal, packet, directory):
        seen.append(proposal)
        return {'status': 'deferred', 'reason': 'independent_quality_failure'}
    result = run(result['packet'], tmp_path / 'run', enabled=True, gate=FiniteDiagnosticGate(),
                 inspector=inspect, snapshot=data[0], handlers={'boundary': handler})
    assert seen == [value]
    assert result['decisions'][0]['outcome']['status'] == 'deferred'
    assert result['measured_net_benefit'] is None and result['proposal']['request_ids'] == [123]


def test_no_change_retains_request_cost_and_original_answer(tmp_path, data, monkeypatch):
    result, _ = make(tmp_path, data)
    fake_harness(monkeypatch, '{"candidates":[]}')
    output = run(result['packet'], tmp_path / 'run', enabled=True, gate=FiniteDiagnosticGate(),
                 inspector=inspect, snapshot=data[0])
    assert output['status'] == 'no_change' and output['proposal']['observed_model_usd'] is None
    assert (tmp_path / 'run/model/answer.txt').exists()


def test_tampered_packet_is_rebuilt_before_any_request(tmp_path, data, monkeypatch):
    result, context = make(tmp_path, data)
    context['inventory']['failed'] = 0
    ref = put(tmp_path / 'tampered.json', context)
    with pytest.raises(ValueError, match='packet_changed'):
        run(ref, tmp_path / 'run', enabled=True, gate=FiniteDiagnosticGate(), inspector=inspect, snapshot=data[0])


def test_unsupported_strategy_stays_pending_not_guidance_injected(tmp_path, data, monkeypatch):
    result, context = make(tmp_path, data); value = candidate(context)
    value.update(kind='construction_strategy', proposal={'procedure': 'change decomposition'})
    fake_harness(monkeypatch, json.dumps({'candidates': [value]}))
    output = run(result['packet'], tmp_path / 'run', enabled=True, gate=FiniteDiagnosticGate(),
                 inspector=inspect, snapshot=data[0])
    assert output['decisions'][0]['status'] == 'pending'


def test_request_ceiling_survives_reopening_journal(tmp_path):
    from scenarios.paper_proofreading.frontier.budget import FrontierGate
    journal = tmp_path / 'research.jsonl'
    journal.write_text('{"event":"request_booked"}\n', encoding='utf-8')
    gate = FrontierGate(tmp_path, journal, deadline=1234, max_requests=1)
    assert gate.max_requests == gate.booked_requests == 1
    with pytest.raises(ValueError, match='limit_invalid'):
        FrontierGate(tmp_path, journal, deadline=1234, max_requests=True)


def test_external_projection_omits_private_values_and_maps_graph_identity(tmp_path, data):
    _, context = make(tmp_path, data)
    context['capabilities'][0]['description'] = 'PRIVATE_DESCRIPTION'
    context['capabilities'][0]['contract']['input_schema']['examples'] = ['PRIVATE_EXAMPLE']
    context['observations'][0]['task_id'] = 'PRIVATE_TASK'
    context['observations'][0]['steps'][0]['input_binding'] = {'kind': 'literal', 'value': 'PRIVATE_VALUE'}
    visible, mappings = model_view(context); encoded = json.dumps(visible)
    assert 'PRIVATE_' not in encoded and str(tmp_path) not in encoded
    assert 'value_withheld' in encoded
    value = candidate(context)
    assert restore_regions(model_candidate(value, context), mappings) == value


def test_request_limit_denies_second_request_before_native_booking(tmp_path, monkeypatch):
    import time
    from types import SimpleNamespace
    from scenarios.paper_proofreading.frontier.budget import FrontierGate
    from src.adapters.capability_proposal import CumulativeProposalGate
    booked = []
    def enter(gate):
        def book(body):
            booked.append(body)
            return (len(booked), 'diagnostic', 0.01)
        gate.state = SimpleNamespace(book=book, log=lambda row: None, output_cap=393216,
                                     rates={'deepseek-flash': (1, 1)})
        return gate
    monkeypatch.setattr(CumulativeProposalGate, '__enter__', enter)
    gate = FrontierGate(tmp_path, tmp_path / 'journal.jsonl', deadline=time.time() + 60, max_requests=1)
    gate.activate('one', '3'); gate.__enter__()
    attempt = tmp_path / 'attempt'; attempt.mkdir()
    gate.register_attempt(attempt, 'one'); gate.current = attempt
    body = json.dumps({'model': 'deepseek-flash', 'max_tokens': 393216,
                       'messages': [{'role': 'user', 'content': 'diagnostic'}]}).encode()
    assert gate.state.book(body) is not None
    assert gate.state.book(body) is None and len(booked) == 1
    assert json.loads(gate.journal.read_text().splitlines()[-1])['reason'] == 'research_request_limit'


def test_boundary_proposal_enters_original_miner_store_and_followup(tmp_path, corpus, monkeypatch):
    from src.adapters.capability_contract import capability_ref
    from src.adapters.capability_evolution_agent import boundary_handler
    from src.adapters.capability_feedback import CapabilityFeedback
    _, snapshot, c_ref, _, traces = corpus
    refs = [put(tmp_path / ('trace-' + str(i) + '.json'), trace) for i, trace in enumerate(traces)]
    def arithmetic_inspector(reference, owner):
        # This diagnostic host has pure integer inputs and no files. The Paper
        # inspector deliberately requires actual file-version witnesses.
        from src.adapters.capability_feedback import verify
        from src.adapters.capability_motif_learning import _checked
        trace = _checked(json.loads(verify(reference)), owner)
        return {'task_id': trace['task_id'], 'source_identity': capability_digest(trace['task_input']),
                'relation': 'diagnostic-integer-transform', 'stage': 'execution', 'status': 'passed',
                'counterexample': False, 'quality': 'unreviewed', 'observed_cost_usd': None,
                'capabilities': [s['capability'] for s in trace['steps']], 'steps': trace['steps'],
                'evidence': [reference, *trace['evidence']]}
    prior = put(tmp_path / 'prior.json', {'capability': next(c for c in snapshot['capabilities'] if capability_ref(c) == c_ref)})
    result = packet([{'split': 'training', 'scope': 'study', 'evidence': ref} for ref in refs[:2]],
                    snapshot, 'study', tmp_path / 'evidence', inspector=arithmetic_inspector)
    context = json.loads(open(result['packet']['path']).read()); view, _ = model_view(context)
    value = candidate(context)
    value['verification'] = ['Independent value check', 'Followup call']
    value['proposal']['regions'] = {r['task_id']: [s['call_id'] for s in r['steps']] for r in view['observations']}
    fake_harness(monkeypatch, json.dumps({'candidates': [value]}))
    feedback = CapabilityFeedback(tmp_path / 'feedback', snapshot['owner'])
    feedback.observe(stage='attempt', subject=c_ref, scope='study', status='passed', cost=None, evidence=refs[:2])
    accepted = []
    def accept(row, directory):
        outcome = publish(directory, snapshot, row['compiled'], 'evolved', 'p0_value', lambda x: 2 * (x + 1))
        accepted.append(outcome)
        return {'followup_passed': outcome['result']['followup_passed']}
    handler = boundary_handler(training=traces[:2], heldout=traces[2:], snapshot=snapshot,
        feedback=feedback, prior_candidate=prior, scope='study',
        heldout_regions={traces[2]['task_id']: [s['call_id'] for s in traces[2]['steps']]}, accept=accept)
    output = run(result['packet'], tmp_path / 'run', enabled=True, gate=FiniteDiagnosticGate(),
                 snapshot=snapshot, handlers={'boundary': handler}, inspector=arithmetic_inspector)
    assert output['decisions'][0]['status'] == 'submitted', output['decisions']
    assert accepted and accepted[0]['result']['followup_passed'] is True
    assert output['decisions'][0]['outcome']['candidates'][0]['compiled']['capability']['certification'] == 'candidate'
    assert output['measured_net_benefit'] is None


def test_host_admitted_capability_uses_existing_construction_queue(tmp_path):
    from tests.test_capability_improvement import plan_at, Adapter
    from src.adapters.capability_evolution_agent import construction_handler
    plan, snapshot, proposal = plan_at(tmp_path)
    adapter = Adapter(snapshot, proposal)
    adapter.configure_jobs = lambda jobs: None
    job = copy.deepcopy(plan['jobs'][0]); job['execution_scope'] = 'study'
    reviewed = put(tmp_path / 'review.json', {'diagnostic': True, 'checker': 'unchanged_host_checker'})
    value = {'kind': 'capability', 'expected_behavior': 'diagnostic new behavior'}
    def admit(candidate, context):
        task = json.loads(open(job['task']['path']).read())
        task['instruction'] = candidate['expected_behavior']
        job['task'] = put(tmp_path / 'admitted-task.json', task)
        return {'decision': 'accepted', 'evidence': reviewed, 'job': job}
    seen = []; original = adapter.construct
    def construct(task, *args):
        seen.append(task['instruction'])
        return original(task, *args)
    adapter.construct = construct
    handle = construction_handler(plan=plan, adapter=adapter, admit=admit)
    outcome = handle(value, {'owner': 'owner', 'scope': 'study', 'snapshot_sha256': snapshot['digest']}, tmp_path / 'candidate')
    assert seen == ['diagnostic new behavior']
    assert outcome['outcomes'][0]['status'] == 'published'


def test_exact_external_prompt_has_final_capacity_gate(tmp_path):
    from src.adapters.capability_goal_proposal import propose_json
    gate = FiniteDiagnosticGate()
    with pytest.raises(ValueError, match='context_capacity_exceeded'):
        propose_json({'owner': 'owner', 'trigger_id': 'bounded'}, tmp_path / 'model', gate,
                     system='x' * 200, prompt_request={}, max_prompt_bytes=100)
    assert gate.current is None
    assert not (tmp_path / 'model/requests.jsonl').exists()


def test_semantic_pressure_groups_different_graphs_and_exposes_only_approved_context(tmp_path, data):
    snapshot, rows = data
    for index, entry in enumerate(rows):
        row = json.loads(open(entry['evidence']['path']).read())
        row['capabilities'] = [snapshot['roots'][index % 2]]
        row['decision_context'] = {'objective': 'Prepare a verified result',
            'state': 'Some inputs need an interface decision',
            'remaining_judgments': ['Choose whether existing interfaces suffice'],
            'interactions': [], 'outcome': 'Host review remains unknown'}
        entry['evidence'] = put(__import__('pathlib').Path(entry['evidence']['path']), row)
    result, context = make(tmp_path, data)
    assert result['status'] == 'ready' and context['independent_sources'] == 3
    visible, _ = model_view(context)
    assert visible['observations'][0]['decision_context']['remaining_judgments']
    assert str(tmp_path) not in json.dumps(visible)
    assert len(json.loads(open(result['index']['path']).read())['groups']) == 1


def test_evolved_policy_is_independently_admitted_then_enters_actual_builder_prompt(tmp_path, data):
    from pathlib import Path
    from src.adapters.capability_evolution_agent import strategy_handler
    from src.adapters.capability_feedback import CapabilityFeedback
    from src.adapters.capability_proposal import prepare_attempt
    from src.adapters.capability_strategy import strategy_context
    snapshot, _ = data
    _, context = make(tmp_path, data)
    feedback = CapabilityFeedback(tmp_path / 'policy-feedback', snapshot['owner'])
    training = put(tmp_path / 'policy-training.json', {'input': 'first independent input'})
    heldout = put(tmp_path / 'policy-heldout.json', {'input': 'second independent input'})
    value = candidate(context)
    value['kind'] = 'construction_strategy'
    value['proposal'] = {'applicability': 'When an existing certified interface is relevant',
        'decision_policy': 'Check the certified input and output contracts before generating glue.',
        'capability_refs': [snapshot['roots'][0]], 'parent': None}
    validate_candidate(value, context)
    evaluated = []
    def evaluate(strategy):
        evaluated.append(strategy['id'])
        return {'passed': True, 'checks': [{'id': 'diagnostic-independent-host-check', 'status': 'passed'}],
                'training_sources': [training], 'heldout_sources': [heldout], 'evidence': [heldout]}
    outcome = strategy_handler(snapshot=snapshot, feedback=feedback, target='construction',
        scope='study', evaluate=evaluate)(value, context, tmp_path / 'policy-result')
    selection = outcome['selection']
    loaded = strategy_context(selection, snapshot, target='construction', scope='study', feedback=feedback)
    assert loaded['decision_policy'] == value['proposal']['decision_policy']
    catalog = {'source_catalog': {'inherited_strategy': {'enabled': True, 'selection': selection,
        'scope': 'study', 'feedback_directory': str(feedback.directory.parent)}}}
    effective, prompt = prepare_attempt(task={'id': 'later-task', 'instruction': 'Construct an independently checked result'},
        catalog=catalog, snapshot=snapshot, output=tmp_path / 'later-builder')
    assert value['proposal']['decision_policy'] in prompt
    assert selection['strategy']['sha256'] in json.dumps(effective)
    assert evaluated and outcome['actual_adoption'] is None
    child = copy.deepcopy(value)
    child['proposal']['decision_policy'] += ' Retain independently observed counterexamples.'
    child_outcome = strategy_handler(snapshot=snapshot, feedback=feedback, target='construction',
        scope='study', evaluate=evaluate, parent_selection=selection)(child, context, tmp_path / 'child-policy')
    child_value = json.loads(Path(child_outcome['selection']['strategy']['path']).read_text())
    assert child_value['parent'] == selection['strategy']
    assert child_value['id'] != loaded['strategy']['id']
    foreign = copy.deepcopy(context)
    foreign['owner'] = 'another-owner'
    with pytest.raises(ValueError, match='strategy_context_changed'):
        strategy_handler(snapshot=snapshot, feedback=feedback, target='construction', scope='study',
            evaluate=evaluate)(value, foreign, tmp_path / 'foreign-policy')
