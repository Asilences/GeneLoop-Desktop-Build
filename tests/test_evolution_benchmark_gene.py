"""Diagnostic trial/agent callbacks; real benchmark runs use BenchmarkHost."""
import json
from pathlib import Path

import pytest

from src.adapters.capability_contract import create_capability_snapshot
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.capability_investigation import Investigation
from src.adapters.evolution_benchmark import inspect_benchmark
from src.adapters.evolution_benchmark_gene import OWNER, run_gene_benchmark
from tests.test_capability_motif_learning import corpus


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


class Host:
    def __init__(self, directory, *, action='task_strategy', validation_pass=True, activated=True,
                 duplicate_sources=False, validation_reward=None):
        self.directory = directory
        self.action = action
        self.validation_pass = validation_pass
        self.activated = activated
        self.duplicate_sources = duplicate_sources
        self.validation_reward = validation_reward
        self.trials = []
        self.observations = []
        self.agent_calls = []
        self.submissions = []

    def trial(self, task_id, *, split='training', skill_directory=None, label='initial'):
        index = len(self.trials)
        value = {'task_id': task_id, 'split': split, 'skill_directory': skill_directory, 'label': label}
        self.trials.append(value)
        passed = self.validation_pass if label == 'gene-independent-validation' else True
        reward = self.validation_reward if label == 'gene-independent-validation' and self.validation_reward is not None else 1 if passed else 0
        result = {'status': 'evaluated', 'task_id': task_id, 'split': split,
                  'evaluation': {'status': 'evaluated', 'passed': passed, 'reward': reward},
                  'score': str(reward),
                  'skill_activated': self.activated if skill_directory else None,
                  'model': {'provider_requests': 1, 'observed_model_usd': None}}
        record = put(self.directory / str(index) / 'result.json', result)
        source = put(self.directory / str(index) / 'input.json', {'task': task_id, 'split': split})
        observation = put(self.directory / str(index) / 'experience.json', {
            'owner': OWNER, 'task_id': task_id + '-' + split,
            'source_identity': 'same-source' if self.duplicate_sources else task_id + '-' + split,
            'relation': 'benchmark-task-work', 'stage': 'execution',
            'status': 'passed' if passed else 'failed', 'quality': 'official_verifier',
            'counterexample': False, 'capabilities': [], 'steps': [],
            'model_decision_count': 1, 'observed_cost_usd': None,
            'cost_attribution': 'task_model_requests_only',
            'decision_context': {'objective': 'Complete ' + task_id,
                                 'state': {'task_id': task_id, 'split': split},
                                 'outcome': {'reward': 1 if passed else 0}},
            'evidence': [record, source], 'interaction_evidence': []})
        self.observations.append(observation)
        return {**result, 'record': record, 'observation': observation}

    def agent(self, request, dispatch):
        self.agent_calls.append(request)
        rows = dispatch('evolution_search', {'kind': 'experience'})['items']
        assert request['initial_context']['capabilities']['selectable'] == 0
        if self.action != 'no_change':
            identifiers = [row['id'] for row in rows[:2]]
            proposal = {'kind': self.action, 'burden': 'Repeated interface investigation',
                        'evidence_ids': identifiers, 'scope': 'skillsbench',
                        'expected_behavior': 'Inspect the current interface before choosing a transformation',
                        'verification': 'Independent original task verifier',
                        'failure_conditions': 'Retain the prior method when the interface differs',
                        'proposal': {'applicability': 'Tasks requiring data transformation',
                                     'decision_policy': 'Inspect current inputs and required outputs, then choose the transformation.',
                                     'capability_refs': [], 'parent': None}}
            self.submissions.append(dispatch('evolution_submit', {
                'candidate': proposal, 'observation_ids': identifiers}))
        dispatch('evolution_finish', {'reason': 'Finish diagnostic investigation'})
        return {'status': 'completed', 'diagnostic': True, 'model_requests': 0}


def run(tmp_path, host, **kwargs):
    return run_gene_benchmark(host, development_tasks=['dev-one', 'dev-two'],
        validation_tasks=['future-one'], test_tasks=['future-one'], output=tmp_path / 'generation', **kwargs)


def test_real_host_seams_connect_policy_admission_to_frozen_native_test(tmp_path):
    host = Host(tmp_path / 'trials')
    result = run(tmp_path, host)
    assert result['status'] == 'completed'
    assert len(host.agent_calls) == 1
    assert result['selection'] is not None
    assert [trial['label'] for trial in host.trials] == [
        'gene-development', 'gene-development', 'gene-independent-validation', 'gene-frozen-test']
    assert [trial['split'] for trial in host.trials] == ['training', 'training', 'training', 'test']
    assert host.trials[-1]['skill_directory'] is not None
    content = (Path(host.trials[-1]['skill_directory']) / 'SKILL.md').read_text()
    assert 'Inspect current inputs' in content
    sidecar = json.loads(verify(result['selection']['strategy']))
    exported = json.loads((Path(result['skill_directory']) / 'strategy.json').read_text())
    assert exported == sidecar
    assert result['actual_adoption']['strategy_read_trials'] == 1
    assert result['measured_net_benefit'] is None


def test_no_change_preserves_original_test_and_pending_mechanisms(tmp_path):
    host = Host(tmp_path / 'trials', action='no_change')
    result = run(tmp_path, host)
    assert result['investigation']['status'] == 'no_change'
    assert result['selection'] is None
    assert len(host.trials) == 3
    assert host.trials[-1]['skill_directory'] is None
    assert result['pending']['construction_strategy'] == 'real_builder_adapter_unavailable'


@pytest.mark.parametrize('validation_pass,activated', [(False, True), (True, False)])
def test_failed_quality_or_missing_activation_does_not_take_over(tmp_path, validation_pass, activated):
    host = Host(tmp_path / 'trials', validation_pass=validation_pass, activated=activated)
    result = run(tmp_path, host)
    assert result['selection'] is None
    assert host.trials[-1]['skill_directory'] is None
    assert host.submissions[0]['status'] == 'rejected'
    assert 'evaluation_failed' in host.submissions[0]['reason']
    assert result['validation'][0]['verdict']['passed'] is False


def test_construction_policy_is_pending_without_fake_builder_run(tmp_path):
    host = Host(tmp_path / 'trials', action='construction_strategy')
    result = run(tmp_path, host)
    assert host.submissions[0]['status'] == 'pending'
    assert result['validation'] == []
    assert result['selection'] is None
    assert len(host.trials) == 3


def test_positive_partial_reward_does_not_pass_full_quality_admission(tmp_path):
    host = Host(tmp_path / 'trials', validation_reward=0.5)
    result = run(tmp_path, host)
    assert result['selection'] is None
    quality = result['validation'][0]['runs'][0]['quality_assessment']
    assert quality['raw_reward'] == 0.5
    assert quality['quality_threshold'] == '1'
    assert quality['full_quality'] is False
    assert quality['paper_positive_reward_pass'] is True
    assert host.trials[-1]['skill_directory'] is None


def test_quality_threshold_is_explicit_and_recorded(tmp_path):
    result = run(tmp_path, Host(tmp_path / 'trials', validation_reward=0.75), quality_threshold='0.75')
    assert result['selection'] is not None
    assert result['quality_threshold'] == '0.75'
    assert json.loads(verify(result['continuation']))['quality_threshold'] == '0.75'


def test_verifier_reward_alone_does_not_qualify_failed_model_trial():
    from decimal import Decimal
    from src.adapters.evolution_benchmark_gene import _quality
    quality = _quality({'evaluation': {'status': 'evaluated', 'reward': 1},
                        'score': None, 'model': {'status': 'failed'}}, Decimal('1'))
    assert quality['verifier_succeeded'] is True
    assert quality['trial_scoreable'] is False
    assert quality['raw_reward'] == 1
    assert quality['full_quality'] is None


@pytest.mark.parametrize('threshold', [0, -1, True, 'NaN', 'Infinity', 'invalid'])
def test_invalid_quality_threshold_fails_before_trials(tmp_path, threshold):
    host = Host(tmp_path / 'trials')
    with pytest.raises(ValueError, match='quality_threshold_invalid'):
        run(tmp_path, host, quality_threshold=threshold)
    assert host.trials == []


def test_capability_candidate_is_pending_without_native_certifier(tmp_path):
    host = Host(tmp_path / 'trials', action='capability')
    result = run(tmp_path, host)
    assert host.submissions[0]['status'] == 'pending'
    assert result['pending']['capability'] == 'native_certification_adapter_unavailable'
    assert result['selection'] is None


def test_continuation_exposes_post_test_evidence_and_original_policy_history(tmp_path):
    host = Host(tmp_path / 'trials')
    result = run(tmp_path, host)
    continuation = json.loads(verify(result['continuation']))
    assert len(continuation['entries']) == 4
    assert continuation['observed_canonical_tasks'] == ['future-one']
    assert continuation['selection'] == result['selection']
    inquiry = Investigation(continuation['snapshot'], continuation['entries'], 'skillsbench',
                            tmp_path / 'followup-inquiry', inspector=inspect_benchmark,
                            history=continuation['history'])
    assert inquiry.overview()['history_entries'] == 4
    found = inquiry.search('experience', 'future-one')['items']
    assert any(row['task_id'] for row in found)
    assert any(json.loads(verify(entry['evidence']))['decision_context']['state']['split'] == 'test'
               for entry in continuation['entries'])
    assert inquiry.search('history', 'Inspect current inputs')['total'] == 1


def test_next_generation_can_reuse_admitted_sidecar_and_feedback(tmp_path):
    first = run(tmp_path, Host(tmp_path / 'trials'))
    continuation = json.loads(verify(first['continuation']))
    host = Host(tmp_path / 'later-trials', action='no_change')
    later = run_gene_benchmark(host, development_tasks=['later-a', 'later-b'],
        validation_tasks=['later-validation'], test_tasks=['later-test'], output=tmp_path / 'later',
        prior_selection=continuation['selection'],
        prior_observations=[entry['evidence'] for entry in continuation['entries']],
        history=continuation['history'], feedback_directory=continuation['feedback_directory'])
    assert later['selection'] == first['selection']
    assert all(trial['skill_directory'] is not None for trial in host.trials)
    assert len(host.agent_calls) == 1
    assert host.agent_calls[0]['initial_context']['history_entries'] >= 3


@pytest.mark.parametrize('development,validation', [
    (['one'], ['heldout']), (['same', 'same'], ['heldout']), (['one', 'two'], ['two'])])
def test_invalid_partitions_fail_before_any_trial(tmp_path, development, validation):
    host = Host(tmp_path / 'trials')
    with pytest.raises(ValueError, match='partition_invalid|validation_overlap'):
        run_gene_benchmark(host, development_tasks=development, validation_tasks=validation,
                           test_tasks=['test'], output=tmp_path / 'invalid')
    assert host.trials == []


def test_duplicate_source_identity_cannot_start_cross_task_evolution(tmp_path):
    host = Host(tmp_path / 'trials', duplicate_sources=True)
    with pytest.raises(ValueError, match='independent_development_required'):
        run(tmp_path, host)
    assert host.agent_calls == []
    report = json.loads((tmp_path / 'generation/result.json').read_text())
    assert report['status'] == 'failed'
    assert len(report['development']) == 2


def test_unknown_cost_stays_unknown_in_original_feedback(tmp_path):
    result = run(tmp_path, Host(tmp_path / 'trials'))
    continuation = json.loads(verify(result['continuation']))
    from src.adapters.capability_feedback import CapabilityFeedback
    feedback = CapabilityFeedback(continuation['feedback_directory'], OWNER).read()
    assert all(fact['cost'] is None for fact in feedback['facts'].values())


def test_seen_canonical_task_cannot_be_relabelled_as_new_final_test(tmp_path):
    first = run(tmp_path, Host(tmp_path / 'trials', action='no_change'))
    continuation = json.loads(verify(first['continuation']))
    later = Host(tmp_path / 'later-trials')
    with pytest.raises(ValueError, match='final_test_already_observed'):
        run_gene_benchmark(later, development_tasks=['later-a', 'later-b'],
            validation_tasks=['later-validation'], test_tasks=['future-one'], output=tmp_path / 'later',
            prior_observations=[entry['evidence'] for entry in continuation['entries']])
    assert later.trials == []


def test_foreign_snapshot_owner_rejected_before_task_execution(tmp_path):
    host = Host(tmp_path / 'trials')
    with pytest.raises(ValueError, match='foreign_owner'):
        run(tmp_path, host, snapshot=create_capability_snapshot('other-owner', [], []))
    assert host.trials == []


class NativePool:
    """Diagnostic acquisition injection; real experiments use native Script."""
    owner = OWNER
    def __init__(self):
        self.snapshot = create_capability_snapshot(OWNER, [], [])
        self.acquisitions = []
    def catalog(self):
        return {'snapshot': self.snapshot, 'catalog': []}
    def acquire(self, program, examples, source_evidence, opportunity):
        from src.adapters.capability_contract import capability_ref, create_capability
        from tests.test_capability_contract import leaf
        definition = leaf('diagnostic-native-helper', OWNER)
        definition = {key: definition[key] for key in ('owner', 'contract', 'implementation', 'dependencies')}
        definition['implementation']['legacy_ref']['backend'] = 'script_motif'
        capability = create_capability(definition, {'lifecycle': 'active', 'certification': 'certified'})
        self.snapshot = create_capability_snapshot(OWNER, [capability_ref(capability)], [capability])
        self.acquisitions.append({'program': program, 'examples': examples,
                                  'source_evidence': source_evidence, 'opportunity': opportunity})
        return {'status': 'registered', 'snapshot': self.snapshot, 'refs': self.snapshot['roots'],
                'scope': 'source_equivalence_not_semantic_quality', 'diagnostic': True}


class NativeHost(Host):
    def __init__(self, directory, *, bad_examples=False, propose_new_ref_strategy=False):
        super().__init__(directory)
        self.materials = NativePool()
        self.bad_examples = bad_examples
        self.propose_new_ref_strategy = propose_new_ref_strategy
        self.available_during_trials = []

    def trial(self, task_id, **kwargs):
        self.available_during_trials.append(len(self.materials.snapshot['roots']))
        result = super().trial(task_id, **kwargs)
        directory = Path(result['observation']['path']).parent
        artifact = put(directory / 'artifact-input.json', {'value': len(self.trials)})
        index = put(directory / 'artifact-index.json', {
            'format': 'skillsbench_artifact_index_v1', 'phase': 'pre_verification',
            'files': {'artifact-input.json': artifact}, 'origin': 'host_collection'})
        row = json.loads(verify(result['observation']))
        row['evidence'].extend([index, artifact])
        updated = put(directory / 'experience.json', row)
        self.observations[-1] = updated
        result['observation'] = updated
        return result

    def agent(self, request, dispatch):
        self.agent_calls.append(request)
        assert 'example_evidence_ids' in request['prompt']
        rows = dispatch('evolution_search', {'kind': 'experience'})['items'][:2]
        identifiers = [row['id'] for row in rows]
        examples = []
        target = 'result.json' if self.bad_examples else 'artifact-input.json'
        for row in rows:
            references = dispatch('evolution_read', {'kind': 'experience', 'id': row['id'],
                                                    'section': 'evidence', 'limit': 100})['items']
            examples.append(next(item['id'] for item in references if item['name'] == target))
        proposal = {'kind': 'capability', 'burden': 'Repeated data conversion', 'evidence_ids': identifiers,
                    'scope': 'skillsbench', 'expected_behavior': 'Reuse a certified current-data helper',
                    'verification': 'Original native sandbox and task checks', 'failure_conditions': 'Keep original',
                    'proposal': {'program': {'source': "def run(value):\n    return {'value': value['data']['value'] + 1}\n",
                        'description': 'Diagnostic current-data transform', 'mode': 'json', 'interface': 'function_v1'},
                        'example_evidence_ids': examples}}
        result = dispatch('evolution_submit', {'candidate': proposal, 'observation_ids': identifiers})
        self.submissions.append(result)
        if self.propose_new_ref_strategy and result['status'] == 'submitted':
            strategy = {**proposal, 'kind': 'task_strategy', 'proposal': {
                'applicability': 'Current-data conversion', 'decision_policy': 'Use a relevant certified helper',
                'capability_refs': result['outcome']['refs'], 'parent': None}}
            self.submissions.append(dispatch('evolution_submit', {'candidate': strategy, 'observation_ids': identifiers}))
        dispatch('evolution_finish', {'reason': 'Keep real outcome for the next task and generation'})
        return {'status': 'completed', 'diagnostic': True}


def test_model_selected_real_file_ids_route_to_native_material_handler(tmp_path):
    host = NativeHost(tmp_path / 'trials')
    result = run(tmp_path, host)
    assert len(host.materials.acquisitions) == 1
    acquisition = host.materials.acquisitions[0]
    source = json.loads(verify(acquisition['source_evidence']))
    assert source['candidate']['proposal']['program'] == acquisition['program']
    assert source['origin'] == 'host_resolution_of_model_selected_file_ids'
    assert len({identity for item in source['example_provenance'] for identity in item['source_identities']}) == 2
    assert all(Path(ref['path']).name == 'artifact-input.json' for ref in acquisition['examples'])
    assert host.available_during_trials == [0, 0, 1]
    assert len(result['snapshot_before']['roots']) == 0
    assert len(result['snapshot_after']['roots']) == 1
    assert 'capability' not in result['pending']
    continuation = json.loads(verify(result['continuation']))
    assert continuation['snapshot'] == host.materials.snapshot
    assert result['recursive_learning']['status'] == 'pending'


def test_metadata_files_cannot_be_substituted_for_selected_artifact_inputs(tmp_path):
    host = NativeHost(tmp_path / 'trials', bad_examples=True)
    result = run(tmp_path, host)
    assert host.materials.acquisitions == []
    assert host.submissions[0]['status'] == 'rejected'
    assert 'selected_pre_verification_files' in host.submissions[0]['reason']
    assert result['snapshot_after']['roots'] == []


def test_new_capability_reference_keeps_original_strategy_snapshot_frozen(tmp_path):
    host = NativeHost(tmp_path / 'trials', propose_new_ref_strategy=True)
    result = run(tmp_path, host)
    assert host.submissions[0]['outcome']['status'] == 'registered'
    assert host.submissions[1]['outcome']['status'] == 'pending'
    assert host.submissions[1]['outcome']['reason'] == 'new_material_requires_next_generation_snapshot'
    assert result['selection'] is None
    assert result['validation'] == []


def test_original_miner_consumes_two_training_and_one_heldout_actual_runtime_trace(tmp_path, corpus):
    from src.adapters.evolution_benchmark_gene import _recursive_learning
    _, _, _, _, traces = corpus
    runs = [{'split': 'training' if index < 2 else 'test',
             'capability_trajectory': put(tmp_path / ('actual-trace-' + str(index) + '.json'), trace)}
            for index, trace in enumerate(traces)]
    result = _recursive_learning(runs, tmp_path)
    assert result['status'] == 'candidates'
    learned = json.loads(verify(result['result']))
    assert learned['candidates']
    assert result['publication'] == 'pending_independent_original_store_publication'


def test_only_the_first_two_native_certification_examples_establish_independence(tmp_path):
    from types import SimpleNamespace
    from src.adapters.evolution_benchmark_gene import _example_files
    first = put(tmp_path / 'first.json', {'value': 1})
    second = put(tmp_path / 'second.json', {'value': 2})
    third = put(tmp_path / 'third.json', {'value': 3})
    one = put(tmp_path / 'one-index.json', {'format': 'skillsbench_artifact_index_v1',
        'phase': 'pre_verification', 'files': {'first': first, 'second': second}})
    two = put(tmp_path / 'two-index.json', {'format': 'skillsbench_artifact_index_v1',
        'phase': 'pre_verification', 'files': {'third': third}})
    context = {'observations': [{'source_identity': 'task-one', 'evidence': [one, first, second]},
                                {'source_identity': 'task-two', 'evidence': [two, third]}]}
    ids = ['evidence_' + ref['sha256'] for ref in [first, second, third]]
    investigation = SimpleNamespace(evidence=dict(zip(ids, [first, second, third])))
    candidate = {'proposal': {'program': {}, 'example_evidence_ids': ids}}
    with pytest.raises(ValueError, match='independent_sources_required'):
        _example_files(candidate, context, investigation)
    candidate['proposal']['example_evidence_ids'] = [ids[0], ids[2], ids[1]]
    selected = _example_files(candidate, context, investigation)
    assert len(selected) == 3
    assert selected[0]['source_identities'] == ['task-one']
    assert selected[1]['source_identities'] == ['task-two']


@pytest.mark.parametrize('status', ['published', 'pending', 'failed'])
def test_original_store_publication_receives_original_learning_sources(tmp_path, corpus, status):
    from src.adapters.evolution_benchmark_gene import _recursive_learning
    _, _, _, _, traces = corpus
    runs = [{'split': 'training' if index < 2 else 'test',
             'capability_trajectory': put(tmp_path / ('trace-' + str(index) + '.json'), trace)}
            for index, trace in enumerate(traces)]
    calls = []
    materials = object()
    def publish(candidate, trace_refs, *, materials, output):
        calls.append((candidate, trace_refs, materials, output))
        return {'status': status, 'followup': 'pending_independent_task_consumption'}
    result = _recursive_learning(runs, tmp_path, materials=materials, publish=publish)
    assert len(calls) == 1
    assert calls[0][1] == [run['capability_trajectory'] for run in runs]
    assert calls[0][2] is materials
    assert result['status'] == status
    assert result['publications'][0]['status'] == status
    assert result['followup'] == 'pending_actual_later_task_consumption'


@pytest.mark.parametrize('action', ['no_change', 'task_strategy', 'construction_strategy'])
def test_construction_feedback_inherits_submissions_no_change_and_original_cost_evidence(tmp_path, action):
    host = Host(tmp_path / 'trials', action=action, validation_pass=False)
    original_agent = host.agent
    def agent(request, dispatch):
        value = original_agent(request, dispatch)
        session = tmp_path / 'model-session'
        original = put(session / 'result.json', {'status': 'completed', 'observed_model_usd': '0.023'})
        put(session / 'request.json', {'actual': 'diagnostic model input'})
        return {**value, 'directory': str(session), 'observed_model_usd_decimal': '0.023',
                'provider_requests': 3, 'result_ref': original}
    host.agent = agent
    result = run(tmp_path, host)
    continuation = json.loads(verify(result['continuation']))
    manifest_ref = continuation['history'][-1]
    manifest = json.loads(verify(manifest_ref))
    assert manifest['model_cost']['observed_model_usd_decimal'] == '0.023'
    assert manifest['native_certification_cost_usd'] is None
    assert 'not per capability' in manifest['cost_scope']
    assert manifest['status'] == ('no_change' if action == 'no_change' else 'completed')
    assert len(manifest['submissions']) == (0 if action == 'no_change' else 1)
    inquiry = Investigation(continuation['snapshot'], continuation['entries'], 'skillsbench',
        tmp_path / 'followup', inspector=inspect_benchmark, history=continuation['history'])
    refs = manifest['sources']['model_session']
    cost_ref = next(ref for ref in refs if Path(ref['path']).name == 'result.json')
    assert '0.023' in inquiry.read('evidence', 'evidence_' + cost_ref['sha256'])['content']
    if action == 'task_strategy':
        assert manifest['sources']['validation']
        assert manifest['submissions'][0]['status'] == 'rejected'
        assert 'reason' in manifest['submissions'][0]
        assert result['selection'] is None
    elif action == 'construction_strategy':
        assert manifest['submissions'][0]['status'] == 'pending'


def test_native_failure_original_evidence_reaches_next_generation(tmp_path):
    host = NativeHost(tmp_path / 'trials')
    host.materials.directory = tmp_path / 'native-materials'
    def failed_acquire(program, examples, source_evidence, opportunity):
        folder = host.materials.directory / 'acquisitions' / 'failed-native'
        put(folder / 'request.json', {'program': program, 'source_evidence': source_evidence})
        put(folder / 'result.json', {'status': 'failed', 'error': 'actual_native_diagnostic_failure'})
        raise ValueError('actual_native_diagnostic_failure')
    host.materials.acquire = failed_acquire
    result = run(tmp_path, host)
    continuation = json.loads(verify(result['continuation']))
    manifest = json.loads(verify(continuation['history'][-1]))
    assert manifest['submissions'][0]['status'] == 'rejected'
    assert 'actual_native_diagnostic_failure' in manifest['submissions'][0]['reason']
    reference = next(ref for ref in manifest['sources']['native'] if Path(ref['path']).name == 'result.json')
    inquiry = Investigation(continuation['snapshot'], continuation['entries'], 'skillsbench',
        tmp_path / 'later-native-inquiry', inspector=inspect_benchmark, history=continuation['history'])
    assert 'actual_native_diagnostic_failure' in inquiry.read('evidence', 'evidence_' + reference['sha256'])['content']
