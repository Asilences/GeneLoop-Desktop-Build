"""Shared benchmark host diagnostics using fake Docker and model transports."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adapters import evolution_benchmark as benchmark
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.skill_infinity_baseline import create_seed_task_skill, create_seed_meta_skill, optimize_task_skill
from src.adapters.skillsbench_trial import SkillsBenchTrial
from tests.test_skillsbench_trial import DockerDiagnostic, source, assertion_report


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    train = source(tmp_path, 'training/task-one')
    test = source(tmp_path, 'canonical/task-one')
    (test / 'instruction.md').write_text('Independent canonical instruction.\n')
    trials = []
    requests = []
    agent_options = {'reward': '1', 'raise': None, 'verifier_code': 0, 'model_status': 'completed'}

    def trial_factory(directory, output, **kwargs):
        adapter = SkillsBenchTrial(directory, output, run_command=DockerDiagnostic(
            reward=agent_options['reward'], verifier_code=agent_options['verifier_code'],
            ctrf=agent_options.get('ctrf')), **kwargs)
        trials.append(adapter)
        return adapter

    class Agent:
        def __init__(self, gate, output):
            self.output = Path(output)

        def __call__(self, request, dispatch):
            requests.append(request)
            directory = self.output / ('session-' + str(len(requests)))
            directory.mkdir(parents=True)
            (directory / 'events.jsonl').write_text(json.dumps({'type': 'step/start', 'data': {}}) + '\n')
            (directory / 'requests.jsonl').write_text(json.dumps({'phase': 'booked', 'request_id': len(requests),
                'diagnostic': True}) + '\n')
            (directory / 'request-000001.json').write_text(json.dumps({'model': 'diagnostic', 'messages': []}))
            if agent_options['raise']:
                raise RuntimeError(agent_options['raise'])
            if request['mode'] == 'benchmark_task':
                result = dispatch('execute', {'command': 'printf diagnostic-output'})
                assert result['returncode'] == 0
            model = {'status': agent_options['model_status'], 'text': 'diagnostic', 'directory': str(directory),
                     'finish_reason': 'completed', 'provider_requests': 1,
                     'request_ids': [len(requests)], 'observed_model_usd': None,
                     'observed_model_usd_decimal': None, 'billing_usd': None,
                     'activated_skill_names': [card['name'] for card in request.get('available_skill_cards', [])]}
            (directory / 'result.json').write_text(json.dumps(model))
            return model

    monkeypatch.setattr(benchmark, 'SkillsBenchTrial', trial_factory)
    monkeypatch.setattr(benchmark, 'ResearchHarness', Agent)
    gate = SimpleNamespace(current=None)
    host = benchmark.BenchmarkHost(train.parent, test.parent, tmp_path / 'host',
                                   source_version='fixed-dataset-commit', gate=gate)
    return SimpleNamespace(root=tmp_path, train=train, test=test, host=host, trials=trials,
                           requests=requests, options=agent_options)


def seed(fixture):
    return create_seed_task_skill(fixture.root / 'candidate-skill', 'task-procedure', 'Synthetic task procedure')


def test_two_arms_use_same_source_and_original_tool_schema(fixture):
    package = seed(fixture)
    first = fixture.host.trial('task-one', skill_directory=package, label='skill-infinity')
    second = fixture.host.trial('task-one', skill_directory=package, label='geneloop')
    assert first['status'] == second['status'] == 'evaluated'
    one, two = fixture.trials
    assert one.manifest()['instruction'] == two.manifest()['instruction']
    assert one.manifest()['source_files'] == two.manifest()['source_files']
    assert fixture.requests[0]['tools'] == fixture.requests[1]['tools']
    assert fixture.requests[0]['prompt'] == fixture.requests[1]['prompt']
    assert len(fixture.requests[0]['tools']) == 1
    assert fixture.requests[0]['tools'][0]['name'] == 'execute'
    assert len(fixture.host.observations) == 2


def test_native_skill_copy_has_container_resource_base(fixture):
    package = seed(fixture)
    helper = Path(package) / 'helper.py'
    helper.write_text('print("diagnostic")\n')
    result = fixture.host.trial('task-one', skill_directory=package)
    card = fixture.requests[0]['available_skill_cards'][0]
    assert card['path'] != package
    assert (Path(card['path']) / 'helper.py').read_bytes() == helper.read_bytes()
    assert card['resource_base'] == '/root/.agents/skills/task-procedure'
    assert result['skill_activated'] is True
    assert (fixture.train / 'environment/skills/curated/SKILL.md').read_text() == 'Original skill'
    assert 'Synthetic task procedure' not in fixture.requests[0]['prompt']


def test_optimization_validation_uses_fresh_training_variant_and_labels_difference(fixture):
    result = fixture.host.evaluate_skill({'context': {'task_id': 'task-one'},
        'skill_directory': seed(fixture), 'split': 'validation'})
    assert fixture.trials[0].source == fixture.train
    assert fixture.trials[0].split == 'training'
    assert result['validation_scope'] == 'fresh_run_of_training_variant'
    trial_record = json.loads(verify(result['record']))
    assert trial_record['label'] == 'validation'
    assert result['observed_model_usd_decimal'] is None
    assert json.loads(verify(result['observation']))['source_identity'] == fixture.trials[0].manifest()['source_identity']


def test_canonical_validation_mapping_does_not_change_training_rollouts(fixture):
    fixture.host.validation_splits = {'task-one': 'test'}
    (fixture.test / 'environment/input.txt').write_text('Separate canonical input')
    package = seed(fixture)
    train = fixture.host.evaluate_skill({'context': {'task_id': 'task-one'},
        'skill_directory': package, 'split': 'training'})
    validation = fixture.host.evaluate_skill({'context': {'task_id': 'task-one'},
        'skill_directory': package, 'split': 'validation'})
    assert [trial.split for trial in fixture.trials] == ['training', 'test']
    assert train['evaluation_role'] == 'development'
    assert validation['evaluation_role'] == 'validation'
    assert validation['validation_scope'] == 'canonical_validation_input'
    one, two = [json.loads(verify(row['observation'])) for row in (train, validation)]
    assert one['source_identity'] == two['source_identity']
    assert one['input_fingerprint'] != two['input_fingerprint']
    assert two['decision_context']['state']['dataset_split'] == 'test'
    assert two['decision_context']['state']['evaluation_role'] == 'validation'


def test_legacy_input_identity_comes_from_verified_manifest(fixture):
    result = fixture.host.trial('task-one')
    row = json.loads(verify(result['observation']))
    expected = row.pop('input_fingerprint')
    assert benchmark.observation_input_fingerprint(row) == expected
    row['input_fingerprint'] = 'changed'
    with pytest.raises(ValueError, match='input_fingerprint_changed'):
        benchmark.observation_input_fingerprint(row)


def _independence_context(fixture, trials):
    from src.adapters.capability_contract import create_capability_snapshot
    from src.adapters.capability_investigation import Investigation
    owner = json.loads(verify(trials[0]['observation']))['owner']
    entries = [{'split': 'training', 'scope': 'diagnostic', 'evidence': trial['observation']}
               for trial in trials]
    investigation = Investigation(create_capability_snapshot(owner, [], []), entries,
        'diagnostic', fixture.root / 'independence-inquiry', inspector=benchmark.inspect_benchmark)
    context = investigation.context(list(investigation.observations))
    candidate = {'kind': 'task_strategy', 'scope': 'diagnostic',
        'burden': 'Repeated processing of separate input instances',
        'expected_behavior': 'Reuse the witnessed stable processing',
        'verification': 'Independent original task checks',
        'failure_conditions': 'Keep the existing method if checks reject the candidate',
        'evidence_ids': [row['id'] for row in context['observations']],
        'proposal': {'applicability': 'The inspected task family',
            'decision_policy': 'Check inputs before choosing processing',
            'capability_refs': [], 'parent': None}}
    return context, candidate


def test_distinct_inputs_in_one_family_support_the_existing_investigation(fixture):
    from src.adapters.capability_evolution_agent import validate_candidate
    (fixture.test / 'environment/input.txt').write_text('Separate original input')
    trials = [fixture.host.trial('task-one', label='prior-development'),
              fixture.host.trial('task-one', split='test', label='prior-observed-instance')]
    original_bytes = {Path(trial[key]['path']): verify(trial[key])
                      for trial in trials for key in ('record', 'observation', 'manifest')}
    raw = [json.loads(verify(trial['observation'])) for trial in trials]
    assert raw[0]['source_identity'] == raw[1]['source_identity']
    context, candidate = _independence_context(fixture, trials)
    assert context['independent_sources'] == 2
    assert validate_candidate(candidate, context) == candidate
    for row in context['observations']:
        state = row['decision_context']['state']
        assert state['task_family_identity'] == raw[0]['source_identity']
        assert state['source_independence_basis'] == 'verified_input_fingerprint'
        assert benchmark.observation_input_fingerprint(row) == row['input_fingerprint']
    assert original_bytes == {path: path.read_bytes() for path in original_bytes}


@pytest.mark.parametrize('second_kind', ['renamed-task', 'retry', 'continuation'])
def test_same_input_does_not_gain_support_through_names_retries_or_continuations(fixture, second_kind):
    from src.adapters.capability_evolution_agent import validate_candidate
    first = fixture.host.trial('task-one')
    task = 'task-one'
    if second_kind == 'renamed-task':
        source(fixture.root, 'training/task-two')
        task = 'task-two'
    second = fixture.host.trial(task, label=second_kind)
    context, candidate = _independence_context(fixture, [first, second])
    assert context['independent_sources'] == 1
    with pytest.raises(ValueError, match='cross_task_support_required'):
        validate_candidate(candidate, context)


@pytest.mark.parametrize('claimed_fingerprint', [None, 'unwitnessed-claim'])
def test_unwitnessed_legacy_records_keep_the_conservative_family_identity(fixture, claimed_fingerprint):
    result = fixture.host.trial('task-one')
    raw = json.loads(verify(result['observation']))
    raw['evidence'] = [ref for ref in raw['evidence'] if Path(ref['path']).name != 'manifest.json']
    raw['input_fingerprint'] = claimed_fingerprint
    path = Path(result['observation']['path']).with_name('legacy-experience.json')
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    projected = benchmark.inspect_benchmark(file_ref(path), raw['owner'])
    assert projected['source_identity'] == raw['source_identity']
    assert projected['decision_context']['state']['source_independence_basis'] == 'legacy_family_identity'
    assert benchmark.observation_input_fingerprint(projected, require_manifest=True) is None
    assert path.read_bytes() == before


def test_projected_fingerprint_still_checks_original_manifest_and_family(fixture):
    result = fixture.host.trial('task-one')
    raw = json.loads(verify(result['observation']))
    projected = benchmark.inspect_benchmark(result['observation'], raw['owner'])
    assert benchmark.observation_input_fingerprint(projected) == raw['input_fingerprint']
    projected['input_fingerprint'] = 'changed'
    with pytest.raises(ValueError, match='input_fingerprint_changed'):
        benchmark.observation_input_fingerprint(projected)
    projected = benchmark.inspect_benchmark(result['observation'], raw['owner'])
    projected['decision_context']['state']['task_family_identity'] = 'changed-family'
    with pytest.raises(ValueError, match='input_source_identity_changed'):
        benchmark.observation_input_fingerprint(projected)
    projected = benchmark.inspect_benchmark(result['observation'], raw['owner'])
    projected['evidence'] = [ref for ref in projected['evidence'] if Path(ref['path']).name != 'manifest.json']
    with pytest.raises(ValueError, match='input_manifest_required'):
        benchmark.observation_input_fingerprint(projected)


@pytest.mark.parametrize('record,expected', [
    ({'split': 'test', 'label': 'validation'}, 'validation'),
    ({'split': 'test', 'evaluation_role': 'development'}, 'development'),
    ({'split': 'test', 'label': 'final'}, 'final'),
    ({'decision_context': {'state': {'split': 'test', 'label': 'gene-independent-validation'}}}, 'validation'),
    ({'split': 'training'}, 'development'),
])
def test_evaluation_role_is_independent_of_dataset_split_and_legacy_labels(record, expected):
    assert benchmark.benchmark_evaluation_role(record) == expected


def test_final_canonical_trial_keeps_source_and_verifier_bytes_frozen(fixture):
    before = {str(p.relative_to(fixture.test)): p.read_bytes() for p in fixture.test.rglob('*') if p.is_file()}
    result = fixture.host.trial('task-one', split='test', skill_directory=seed(fixture), label='final')
    assert fixture.trials[0].source == fixture.test
    assert fixture.requests[0]['prompt'] == 'Independent canonical instruction.\n'
    assert result['split'] == 'test'
    assert before == {str(p.relative_to(fixture.test)): p.read_bytes() for p in fixture.test.rglob('*') if p.is_file()}
    assert fixture.trials[0].evaluated is True
    assert fixture.trials[0].started is False


def test_failed_trial_retains_failure_and_cleanup(fixture):
    fixture.options['raise'] = 'diagnostic model transport failure'
    result = fixture.host.trial('task-one', skill_directory=seed(fixture))
    assert result['status'] == 'failed'
    assert 'model transport failure' in result['error']
    record = json.loads(verify(result['record']))
    assert record['cleanup']['returncode'] == 0
    observation = json.loads(verify(result['observation']))
    assert observation['status'] == 'failed'
    assert observation['quality'] == 'unreviewed'
    assert observation['observed_cost_usd'] is None


def test_missing_reward_is_explicit_and_preserves_original_trial(fixture):
    fixture.options['reward'] = None
    with pytest.raises(ValueError, match='unscored'):
        fixture.host.evaluate_skill({'context': {'task_id': 'task-one'},
            'skill_directory': seed(fixture), 'split': 'validation'})
    assert len(fixture.host.observations) == 1
    record = json.loads(verify(fixture.host.observations[0]))
    assert record['quality'] == 'unreviewed'
    assert record['decision_context']['outcome']['reward'] is None


def test_completed_quality_rejection_reaches_skill_optimizer_with_zero_score(fixture):
    fixture.options.update(reward='0', verifier_code=1, ctrf=assertion_report())
    package = seed(fixture)
    calls = []
    def optimizer(request, dispatch):
        calls.append(request)
        archive = dispatch('inspect_archive', {})
        assert archive['nodes'][0]['evaluation']['score'] == '0.0'
        dispatch('select_parent', {'selected_node_id': 'seed', 'action': 'stop',
                                  'reason': 'Diagnostic retained completed quality failure for later improvement'})
        return {'diagnostic': True}
    result = optimize_task_skill(package, fixture.root / 'optimization',
        call_agent=optimizer, evaluate=fixture.host.evaluate_skill, review=lambda request: {},
        task_context={'task_id': 'task-one'}, meta_skill=create_seed_meta_skill(fixture.root / 'meta'))
    assert result['status'] == 'completed' and result['score'] == '0.0'
    assert len(calls) == 1
    observation = json.loads(verify(fixture.host.observations[0]))
    assert observation['status'] == 'failed' and observation['quality'] == 'official_verifier'
    trial_record = json.loads(verify(observation['evidence'][0]))
    assert trial_record['evaluation']['verifier_outcome'] == 'quality_rejected'
    operation = json.loads(verify(trial_record['evaluation']['verification']))
    assert operation['returncode'] == 1


def test_partial_reward_from_failed_verifier_is_preserved_but_unscored(fixture):
    fixture.options['verifier_code'] = 1
    result = fixture.host.trial('task-one', skill_directory=seed(fixture))
    assert result['evaluation']['status'] == 'verifier_failed'
    assert result['evaluation']['reward'] == 1
    assert result['score'] is None
    assert json.loads(verify(result['observation']))['status'] == 'failed'


def test_failed_model_session_is_retained_and_not_scored_as_valid_execution(fixture):
    fixture.options['model_status'] = 'failed'
    result = fixture.host.trial('task-one', skill_directory=seed(fixture))
    assert result['model']['status'] == 'failed'
    assert result['score'] is None
    assert json.loads(verify(result['record']))['model']['status'] == 'failed'


def test_dependency_setup_precedes_model_and_keeps_original_verifier(fixture, monkeypatch):
    from src.adapters import benchmark_dependency_profile
    monkeypatch.setattr(benchmark_dependency_profile, 'dependency_profile', lambda source: {
        'id': 'synthetic-public-dependency-diagnostic', 'environment_keys': ['UV_DOWNLOAD_URL'],
        'steps': [{'id': 'versions', 'command': 'python --version', 'timeout_seconds': 20}]})
    fixture.host.prewarm_dependencies = True
    fixture.host.verifier_environment = {'UV_DOWNLOAD_URL': 'https://example.test/release'}
    original = (fixture.train / 'tests/test.sh').read_bytes()
    result = fixture.host.trial('task-one')
    preparation = json.loads(verify(result['dependency_preparation']))
    operation = json.loads(verify(preparation['operations'][0]['operation']))
    assert preparation['status'] == 'prepared' and preparation['model_requests'] == 0
    assert 'UV_DOWNLOAD_URL=https://example.test/release' in operation['argv'][-1]
    assert 'python --version' in operation['argv'][-1]
    assert fixture.trials[0]._run_command.calls[2] == operation['argv']
    assert (fixture.train / 'tests/test.sh').read_bytes() == original
    assert result['score'] == '1.0'


def test_failed_dependency_setup_preserves_record_without_model_call(fixture, monkeypatch):
    from src.adapters import benchmark_dependency_profile
    monkeypatch.setattr(benchmark_dependency_profile, 'dependency_profile', lambda source: {
        'id': 'synthetic-failure', 'environment_keys': [],
        'steps': [{'id': 'download', 'command': 'fetch-public-dependency', 'timeout_seconds': 20}]})
    original_execute = SkillsBenchTrial.execute

    def failed(adapter, *args, **kwargs):
        result = original_execute(adapter, *args, **kwargs)
        return {**result, 'returncode': 1}

    monkeypatch.setattr(SkillsBenchTrial, 'execute', failed)
    fixture.host.prewarm_dependencies = True
    result = fixture.host.trial('task-one')
    assert result['status'] == 'failed' and not fixture.requests
    assert 'benchmark_dependency_preparation_failed:download' in result['error']
    assert json.loads(verify(result['dependency_preparation']))['status'] == 'failed'


@pytest.mark.parametrize('requests,cancellation,expected', [(1, True, True), (0, True, False),
                                                          (1, False, False), (True, True, False)])
def test_timeout_trial_is_scored_only_with_provider_and_public_cancel_evidence(fixture, requests, cancellation, expected):
    def agent(request, dispatch):
        dispatch('execute', {'command': 'printf diagnostic-output'})
        directory = fixture.host.output / 'timeout-session'
        directory.mkdir()
        cancel = directory / 'cancel.json'
        cancel.write_text('{"operation":"session.cancel","accepted":true,"diagnostic":true}')
        return {'status': 'timeout', 'timed_out': True, 'provider_requests': requests,
                'directory': str(directory), 'finish_reason': 'timeout',
                'cancel_evidence': file_ref(cancel) if cancellation else None,
                'activated_skill_names': []}
    fixture.host.agent = agent
    result = fixture.host.trial('task-one')
    assert result['model_scoreable'] is expected
    assert (result['score'] is not None) is expected


def test_experience_retains_original_request_and_cost_evidence(fixture):
    result = fixture.host.trial('task-one', skill_directory=seed(fixture))
    observation = json.loads(verify(result['observation']))
    sources = {Path(ref['path']).name for ref in observation['evidence']}
    assert 'requests.jsonl' in sources
    model_directory = Path(result['model']['directory'])
    assert file_ref(model_directory / 'result.json') in observation['evidence']
    assert file_ref(model_directory / 'requests.jsonl') in observation['evidence']


def test_experience_inspection_checks_original_hashes_and_owner(fixture):
    result = fixture.host.trial('task-one')
    assert benchmark.inspect_benchmark(result['observation'], 'overnight-research')['task_id'] == 'task-one-training'
    with pytest.raises(ValueError, match='owner_changed'):
        benchmark.inspect_benchmark(result['observation'], 'someone-else')
    fixture.train.joinpath('instruction.md').write_text('Changed source')
    with pytest.raises(ValueError, match='evidence_changed'):
        benchmark.inspect_benchmark(result['observation'], 'overnight-research')


def test_artifacts_are_frozen_before_verifier_can_create_gold(fixture, monkeypatch):
    original_collect = SkillsBenchTrial.collect_artifacts
    original_evaluate = SkillsBenchTrial.evaluate
    order = []
    gold_created = []
    def collect(trial):
        order.append('collect')
        collected = original_collect(trial)
        assert not gold_created
        return collected
    def evaluate(trial):
        order.append('evaluate')
        gold_created.append(True)
        gold = trial.output / 'verifier-only-gold.json'
        gold.write_text('{"expected":"private verifier output"}')
        outcome = original_evaluate(trial)
        outcome['post_verification_artifact'] = file_ref(gold)
        return outcome
    monkeypatch.setattr(SkillsBenchTrial, 'collect_artifacts', collect)
    monkeypatch.setattr(SkillsBenchTrial, 'evaluate', evaluate)
    result = fixture.host.trial('task-one')
    assert order == ['collect', 'evaluate']
    assert result['artifacts']['phase'] == 'pre_verification'
    index = json.loads(verify(result['artifacts']['index']))
    assert index['phase'] == 'pre_verification'
    observation = benchmark.inspect_benchmark(result['observation'], 'overnight-research')
    assert 'verifier-only-gold' not in json.dumps(observation['evidence'])


def test_missing_artifact_phase_keeps_result_but_excludes_source_files(fixture):
    result = fixture.host.trial('task-one')
    record = json.loads(verify(result['record']))
    record['artifacts'].pop('phase')
    directory = fixture.host.output / 'legacy-projection'
    directory.mkdir()
    (directory / 'result.json').write_text(json.dumps(record))
    observed = fixture.host._observation(fixture.trials[0], record, directory)
    row = json.loads(verify(observed))
    assert file_ref(directory / 'result.json') in row['evidence']
    assert result['artifacts']['index'] not in row['evidence']
    original_files = json.loads(verify(result['artifacts']['index']))['files']
    assert all(reference not in row['evidence'] for reference in original_files.values())


def test_old_post_verification_artifact_index_is_not_evolution_input(fixture):
    result = fixture.host.trial('task-one')
    row = json.loads(verify(result['observation']))
    index = fixture.host.output / 'old-artifact-index.json'
    index.write_text(json.dumps({'format': 'skillsbench_artifact_index_v1',
                                'files': {}, 'phase': 'post_verification'}))
    row['evidence'].append(file_ref(index))
    old = fixture.host.output / 'old-experience.json'
    old.write_text(json.dumps(row))
    with pytest.raises(ValueError, match='pre_verification_required'):
        benchmark.inspect_benchmark(file_ref(old), 'overnight-research')


def test_host_exposes_native_task_tools_and_original_capture(fixture):
    from src.adapters.capability_contract import capability_ref
    from tests.test_capability_motif_learning import run_driver
    snapshot = run_driver({'action': 'seed', 'owner': 'overnight-research'})
    class Materials:
        owner = snapshot['owner']
        def catalog(self):
            return {'snapshot': snapshot, 'catalog': [{'capability': ref, 'description': 'Diagnostic native computation'}
                                                     for ref in snapshot['roots']]}
        def execute(self, ref, value, directory, task_id):
            arguments = {'value': value}
            execution = run_driver({'action': 'run', 'snapshot': snapshot, 'root': ref,
                                    'input': arguments, 'task_id': task_id})['execution']
            directory.mkdir()
            (directory / 'trace.json').write_text(json.dumps(execution))
            return {'trace': execution, 'execution_ref': file_ref(directory / 'trace.json'),
                    'snapshot': snapshot, 'arguments': arguments}
    fixture.host.materials = Materials()
    def agent(request, dispatch):
        assert {tool['name'] for tool in request['tools']} == {'execute', 'capability_list', 'capability_call'}
        overview = request['initial_context']['reusable_capabilities']
        assert overview['count'] == len(snapshot['roots'])
        assert all(set(item) == {'capability_id', 'description'} for item in overview['items'])
        assert all(item['description'] == 'Diagnostic native computation' for item in overview['items'])
        assert 'schema' not in json.dumps(overview) and 'implementation' not in json.dumps(overview)
        listed = dispatch('capability_list', {})
        ref = listed['capabilities'][0]['capability']
        result = dispatch('capability_call', {'capability_id': ref['id'], 'value': 3})
        assert result['status'] == 'succeeded'
        directory = fixture.host.output / 'native-session'
        directory.mkdir()
        return {'status': 'completed', 'directory': str(directory), 'provider_requests': 1,
                'observed_model_usd': None, 'finish_reason': 'completed', 'activated_skill_names': []}
    fixture.host.agent = agent
    result = fixture.host.trial('task-one')
    assert result['status'] == 'evaluated'
    captured = json.loads(verify(result['capability_trajectory']))
    assert captured['task_fingerprint'] == fixture.trials[0].manifest()['input_fingerprint']
    assert captured['steps'][0]['arguments'] == {'value': 3}
    observation = benchmark.inspect_benchmark(result['observation'], 'overnight-research')
    assert observation['steps'][0]['status'] == 'succeeded'
    assert observation['capabilities'] == [captured['steps'][0]['capability']]
    assert observation['capability_input_projection'] == result['capability_input_projection']


def test_empty_capability_pool_adds_only_a_zero_count(fixture):
    from src.adapters.capability_contract import create_capability_snapshot
    empty = create_capability_snapshot('overnight-research', [], [])
    fixture.host.materials = SimpleNamespace(owner='overnight-research',
                                            catalog=lambda: {'snapshot': empty, 'catalog': []})
    fixture.host.trial('task-one')
    assert fixture.requests[0]['initial_context'] == {'reusable_capabilities': {'count': 0}}


def test_task_initial_directory_is_small_when_pool_grows(fixture):
    from src.adapters.capability_contract import capability_ref, create_capability_snapshot
    from tests.test_capability_contract import leaf
    capabilities = [leaf('directory-diagnostic-' + str(index), 'overnight-research') for index in range(12)]
    snapshot = create_capability_snapshot('overnight-research', [capability_ref(cap) for cap in capabilities], capabilities)
    catalog = [{'capability': capability_ref(cap), 'description': 'Diagnostic function ' + str(index)}
               for index, cap in enumerate(capabilities)]
    fixture.host.materials = SimpleNamespace(owner='overnight-research',
                                            catalog=lambda: {'snapshot': snapshot, 'catalog': catalog})
    fixture.host.trial('task-one')
    overview = fixture.requests[0]['initial_context']['reusable_capabilities']
    assert overview['count'] == 12 and len(overview['items']) == 8
    assert overview['next_offset'] == 8 and overview['details_tool'] == 'capability_list'


def test_host_action_overview_keeps_local_record_refs_and_bounded_text(fixture):
    def agent(request, dispatch):
        executed = dispatch('execute', {'command': 'node helper.js\n' + 'x' * 2000})
        directory = fixture.host.output / 'action-session'
        directory.mkdir()
        return {'status': 'completed', 'directory': str(directory), 'provider_requests': 1,
                'finish_reason': 'completed', 'activated_skill_names': [],
                'tools': [{'name': 'execute', 'sequence': 0, 'status': 'completed',
                           'arguments': {'command': 'node helper.js\n' + 'x' * 2000},
                           'result': executed}]}
    fixture.host.agent = agent
    result = fixture.host.trial('task-one')
    observation = benchmark.inspect_benchmark(result['observation'], 'overnight-research')
    card = observation['action_overview'][0]
    assert card['command_first_line'] == 'node helper.js'
    assert card['command_characters'] > 2000
    assert card['returncode'] == 0
    assert card['evidence_id'].startswith('evidence_')
    assert any('evidence_' + ref['sha256'] == card['evidence_id'] for ref in observation['evidence'])


def test_independent_reviewer_can_expand_only_referenced_original_evidence(fixture):
    task_result = fixture.host.trial('task-one', skill_directory=seed(fixture))
    parent = fixture.root / 'parent'
    candidate = fixture.root / 'review-candidate'
    policy = fixture.root / 'policy/reviewer-policy.md'
    parent.mkdir()
    candidate.mkdir()
    policy.parent.mkdir()
    (parent / 'SKILL.md').write_text('parent')
    (candidate / 'SKILL.md').write_text('candidate')
    policy.write_text('Independent review policy')
    detail = fixture.host.output / 'execution-detail.txt'
    detail.write_text('Original execution detail')
    nested = fixture.host.output / 'nested-evidence-index.json'
    nested.write_text(json.dumps({'evidence_refs': [file_ref(detail)]}))
    root = fixture.host.output / 'review-evidence.json'
    root.write_text(json.dumps({'evidence_indexes': [file_ref(nested)]}))
    read_results = []

    def reviewer(request, dispatch):
        assert request['mode'] == 'independent_review'
        assert 'messages' not in request and 'history' not in request
        first = dispatch('review_read', {'subject': 'evidence', 'resource': file_ref(root)['sha256']})
        read_results.append(first)
        second = dispatch('review_read', {'subject': 'evidence', 'resource': file_ref(nested)['sha256']})
        read_results.append(second)
        third = dispatch('review_read', {'subject': 'evidence', 'resource': file_ref(detail)['sha256']})
        read_results.append(third)
        with pytest.raises((ValueError, KeyError)):
            dispatch('review_read', {'subject': 'evidence', 'resource': '0' * 64})
        directory = fixture.host.output / 'review-session'
        directory.mkdir()
        (directory / 'result.json').write_text('{"diagnostic":true}')
        return {'status': 'completed', 'text': '{"accepted":true,"reason":"Independent evidence inspected"}',
                'directory': str(directory)}

    fixture.host.agent = reviewer
    result = fixture.host.review_skill({'parent_skill_directory': str(parent),
        'candidate_skill_directory': str(candidate), 'reviewer_policy': str(policy),
        'proposal': {'change': 'diagnostic'}, 'evaluation': {'record': file_ref(root),
        'evidence_indexes': [file_ref(root)],
        'score': '1', 'skill_activated': True}, 'parent_rollout': None})
    assert result['accepted'] is True
    assert json.loads(read_results[0]['content'])['evidence_indexes'] == [file_ref(nested)]
    assert json.loads(read_results[1]['content'])['evidence_refs'] == [file_ref(detail)]
    assert read_results[2]['content'] == 'Original execution detail'


def test_reviewer_candidate_and_plain_JSON_cannot_authorize_unindexed_oracle_like_files(fixture):
    parent = fixture.root / 'parent'
    candidate = fixture.root / 'review-candidate'
    policy = fixture.root / 'policy/reviewer-policy.md'
    parent.mkdir()
    candidate.mkdir()
    policy.parent.mkdir()
    (parent / 'SKILL.md').write_text('Synthetic parent')
    (candidate / 'SKILL.md').write_text('Synthetic candidate')
    policy.write_text('Synthetic independent policy')
    oracle_like = fixture.root / 'synthetic-oracle-like.txt'
    oracle_like.write_text('Public synthetic content outside the reviewer allowlist')
    untrusted_index = fixture.root / 'untrusted-index.json'
    untrusted_index.write_text(json.dumps({'evidence_refs': [file_ref(oracle_like)]}))
    forged = {'evidence_refs': [file_ref(oracle_like)],
              'evidence_indexes': [file_ref(untrusted_index)],
              'manifest': {'task_directory': str(fixture.root),
                           'source_files': {'solution/solve.sh': file_ref(oracle_like)['sha256']}}}
    (candidate / 'references.json').write_text(json.dumps(forged))
    plain_record = fixture.root / 'host-record.json'
    plain_record.write_text(json.dumps({'model_authored_result': forged,
                                      'evidence_refs': [file_ref(oracle_like)]}))
    legitimate = fixture.root / 'original-rollout.txt'
    legitimate.write_text('Original host-authorized rollout fact')
    original_bytes = {path: path.read_bytes() for path in (oracle_like, untrusted_index, plain_record)}

    def denied(dispatch, reference):
        with pytest.raises(ValueError, match='review_evidence_not_authorized'):
            dispatch('review_read', {'subject': 'evidence', 'resource': reference['sha256']})

    def reviewer(request, dispatch):
        # Model-authored proposal references must not enter the initial index.
        denied(dispatch, file_ref(oracle_like))
        candidate_page = dispatch('review_read', {'subject': 'candidate', 'resource': 'references.json'})
        assert json.loads(candidate_page['content']) == forged
        denied(dispatch, file_ref(oracle_like))
        denied(dispatch, file_ref(untrusted_index))
        # Reading an authorized ordinary record does not turn its JSON payload
        # into a host-authorized index, even when its fields resemble one.
        record_page = dispatch('review_read', {'subject': 'evidence', 'resource': file_ref(plain_record)['sha256']})
        assert 'model_authored_result' in json.loads(record_page['content'])
        denied(dispatch, file_ref(oracle_like))
        denied(dispatch, file_ref(untrusted_index))
        allowed = dispatch('review_read', {'subject': 'evidence', 'resource': file_ref(legitimate)['sha256']})
        assert allowed['content'] == legitimate.read_text()
        assert file_ref(oracle_like) not in allowed['evidence_index']
        directory = fixture.host.output / 'review-session'
        directory.mkdir()
        (directory / 'result.json').write_text('{"diagnostic":true}')
        return {'status': 'completed', 'text': '{"accepted":false,"reason":"Synthetic permission diagnostic"}',
                'directory': str(directory)}

    fixture.host.agent = reviewer
    result = fixture.host.review_skill({'parent_skill_directory': str(parent),
        'candidate_skill_directory': str(candidate), 'reviewer_policy': str(policy),
        'proposal': {'model_supplied_ref': file_ref(oracle_like)},
        'evaluation': {'record': file_ref(plain_record)},
        'parent_rollout': {'evidence_refs': [file_ref(legitimate)]}})
    assert result['accepted'] is False
    assert original_bytes == {path: path.read_bytes() for path in original_bytes}


def test_failed_reviewer_session_cannot_admit_candidate_from_parseable_text(fixture):
    parent = fixture.root / 'parent'
    candidate = fixture.root / 'review-candidate'
    policy = fixture.root / 'policy.md'
    parent.mkdir()
    candidate.mkdir()
    policy.write_text('Independent policy')
    directory = fixture.host.output / 'review-session'
    directory.mkdir()
    (directory / 'result.json').write_text('{"status":"failed"}')
    fixture.host.agent = lambda *_: {'status': 'failed',
        'text': '{"accepted":true,"reason":"Parseable but unwitnessed"}', 'directory': str(directory)}
    with pytest.raises(ValueError, match='review.*failed|review.*incomplete'):
        fixture.host.review_skill({'parent_skill_directory': str(parent),
            'candidate_skill_directory': str(candidate), 'reviewer_policy': str(policy),
            'evaluation': {}, 'proposal': {}})


def script_module():
    path = Path(__file__).resolve().parents[1] / 'scripts/run-evolution-benchmark.py'
    spec = importlib.util.spec_from_file_location('evolution_benchmark_cli_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_freezes_final_test_after_optimization_and_keeps_seed_only_label(tmp_path, monkeypatch):
    module = script_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    calls = []

    @contextmanager
    def gate(_root):
        yield SimpleNamespace(state=SimpleNamespace(reserved_usd=0, request_count=7))

    class Host:
        def __init__(self, *_args, **_kwargs):
            self.agent = lambda *_: None
            self.evaluate_skill = lambda *_: None
            self.review_skill = lambda *_: None

        def trial(self, task_id, **kwargs):
            calls.append((task_id, kwargs))
            return {'status': 'evaluated', 'score': '1', 'split': kwargs['split']}

    def optimize(seed_skill, output, **kwargs):
        calls.append(('optimization', kwargs))
        return {'status': 'completed', 'selected_skill': seed_skill, 'score': '1'}

    monkeypatch.setattr(module, 'CumulativeProposalGate', gate)
    monkeypatch.setattr(module, 'BenchmarkHost', Host)
    monkeypatch.setattr(module, 'optimize_task_skill', optimize)
    output = tmp_path / '.local/run'
    monkeypatch.setattr(module.sys, 'argv', ['run', '--training-root', str(tmp_path / 'train'),
        '--test-root', str(tmp_path / 'test'), '--source-version', 'fixed', '--ledger-root', str(tmp_path / 'ledger'),
        '--output', str(output), '--task', 'task-one', '--mode', 'skill-infinity', '--call-model'])
    module.main()
    result = json.loads((output / 'result.json').read_text())
    assert result['self_improvement'] == 'seed_only'
    assert calls[0][0] == 'optimization'
    assert calls[1][1]['split'] == 'test'
    assert calls[1][1]['skill_directory'] == result['optimization']['selected_skill']
    effective = json.loads((output / 'effective.json').read_text())
    assert effective['budget_usd'] is None and effective['max_requests'] is None


@pytest.mark.parametrize('evidence,expected', [({'accepted': False}, False),
    ({'accepted': 'true'}, False), ({'runtime_closed': True}, True), ({}, False)])
def test_timeout_scoring_requires_effective_cancel_content(tmp_path, evidence, expected):
    from src.adapters.evolution_benchmark import _model_scoreable
    path = tmp_path / 'cancel.json'
    path.write_text(json.dumps(evidence))
    assert _model_scoreable({'status': 'timeout', 'timed_out': True, 'provider_requests': 1,
                             'cancel_evidence': file_ref(path)}) is expected


def test_verifier_diagnostics_are_explicitly_readable_without_post_verification_files(fixture):
    from src.adapters.capability_contract import create_capability_snapshot
    from src.adapters.capability_investigation import Investigation
    result = fixture.host.trial('task-one')
    row = benchmark.inspect_benchmark(result['observation'], 'overnight-research')
    evaluation = result['evaluation']
    operation = json.loads(verify(evaluation['verification']))
    required = [evaluation['record'], evaluation['evidence'], evaluation['verification'],
                operation['stdout_ref'], operation['stderr_ref']]
    assert all(reference in row['evidence'] for reference in required)
    outcome = row['decision_context']['outcome']
    assert outcome['verifier_status'] == 'evaluated'
    assert outcome['diagnostic_evidence_ids'][Path(operation['stderr_ref']['path']).name] == (
        'evidence_' + operation['stderr_ref']['sha256'])
    inquiry = Investigation(create_capability_snapshot('overnight-research', [], []),
        [{'split': 'training', 'scope': 'skillsbench', 'evidence': result['observation']}],
        'skillsbench', fixture.root / 'diagnostic-inquiry', inspector=benchmark.inspect_benchmark)
    assert inquiry.read('evidence', 'evidence_' + operation['stdout_ref']['sha256'])['content'] == 'diagnostic stdout'
    assert inquiry.read('evidence', 'evidence_' + evaluation['evidence']['sha256'])['content'] == '1'
    assert not any('ground_truth' in reference['path'] or '/solution/' in reference['path']
                   for reference in row['evidence'])


def test_r3_original_observation_gets_derived_diagnostics_without_rewriting(fixture):
    result = fixture.host.trial('task-one')
    operation = json.loads(verify(result['evaluation']['verification']))
    omitted = [result['evaluation']['record'], result['evaluation']['evidence'],
               result['evaluation']['verification'], operation['stdout_ref'], operation['stderr_ref']]
    path = Path(result['observation']['path'])
    original = json.loads(path.read_text())
    original['evidence'] = [reference for reference in original['evidence'] if reference not in omitted]
    path.write_text(json.dumps(original))
    legacy = file_ref(path)
    before = path.read_bytes()
    restored = benchmark.inspect_benchmark(legacy, 'overnight-research')
    assert all(reference in restored['evidence'] for reference in omitted)
    assert restored['derived_verifier_evidence']['source_record'] == result['record']
    assert restored['derived_verifier_evidence']['origin'] == 'host_fixed_evaluation_fields'
    assert path.read_bytes() == before
    assert all(reference not in json.loads(path.read_text())['evidence'] for reference in omitted)


def test_diagnostic_recovery_verifies_original_stream_hashes(fixture):
    result = fixture.host.trial('task-one')
    operation = json.loads(verify(result['evaluation']['verification']))
    Path(operation['stdout_ref']['path']).write_text('changed verifier diagnostic')
    with pytest.raises(ValueError, match='evidence_changed'):
        benchmark.inspect_benchmark(result['observation'], 'overnight-research')


def test_diagnostic_recovery_rejects_foreign_verifier_scope(fixture):
    first = fixture.host.trial('task-one')
    second = fixture.host.trial('task-one', split='test')
    path = Path(first['record']['path'])
    original = json.loads(path.read_text())
    original['evaluation'] = second['evaluation']
    path.write_text(json.dumps(original))
    row = json.loads(verify(first['observation']))
    row['evidence'] = [file_ref(path) if reference == first['record'] else reference for reference in row['evidence']]
    observed = Path(first['observation']['path'])
    observed.write_text(json.dumps(row))
    with pytest.raises(ValueError, match='verifier_scope_changed'):
        benchmark.inspect_benchmark(file_ref(observed), 'overnight-research')
