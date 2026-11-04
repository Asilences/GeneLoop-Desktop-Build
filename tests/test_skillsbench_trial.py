"""Synthetic Docker diagnostics; these checks make no model or Docker calls."""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from src.adapters.skillsbench_trial import SkillsBenchTrial, paired_tasks, parse_reward, task_manifest


def source(tmp_path, name='task'):
    root = tmp_path / name
    (root / 'environment' / 'skills' / 'curated').mkdir(parents=True)
    (root / 'tests').mkdir()
    (root / 'solution').mkdir()
    (root / 'instruction.md').write_text('Transform the input into an output.\n', encoding='utf-8')
    (root / 'task.toml').write_text('''version = "1.0"
[environment]
cpus = 1
memory_mb = 1024
allow_internet = false
build_timeout_sec = 45
[verifier]
timeout_sec = 30
''', encoding='utf-8')
    (root / 'environment' / 'Dockerfile').write_bytes(b'FROM example:fixed\r\nCOPY skills /root/.agents/skills\r\n')
    (root / 'environment' / 'input.txt').write_text('input', encoding='utf-8')
    (root / 'environment' / 'skills' / 'curated' / 'SKILL.md').write_text('Original skill', encoding='utf-8')
    (root / 'tests' / 'test.sh').write_bytes(b'#!/bin/bash\r\necho 1 > /logs/verifier/reward.txt\r\n')
    (root / 'solution' / 'solve.sh').write_text('private oracle for diagnostics', encoding='utf-8')
    return root


class DockerDiagnostic:
    def __init__(self, *, reward='1', verifier_code=0, fail_at=None):
        self.calls = []
        self.options = []
        self.reward = reward
        self.verifier_code = verifier_code
        self.fail_at = fail_at

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        self.options.append(kwargs)
        if self.fail_at == len(self.calls):
            raise subprocess.TimeoutExpired(argv, 1, output=b'partial output')
        code = 0
        if argv[1] == 'build':
            Path(argv[argv.index('--iidfile') + 1]).write_text('sha256:diagnostic\n', encoding='utf-8')
        if argv[1] == 'cp' and ':/logs/verifier/.' in argv[2]:
            if self.reward is not None:
                (Path(argv[3]) / 'reward.txt').write_text(self.reward, encoding='utf-8')
        if argv[-1] == '/tests/test.sh':
            code = self.verifier_code
        stdout = 'diagnostic stdout'
        if argv[1:3] == ['image', 'inspect']:
            stdout = '"/work"'
        if argv[1] == 'cp' and ':/work/.' in argv[2]:
            (Path(argv[3]) / 'solution.py').write_text('print("generated")', encoding='utf-8')
        return SimpleNamespace(returncode=code, stdout=stdout, stderr='')


def trial(tmp_path, runner=None):
    root = source(tmp_path)
    return SkillsBenchTrial(root, tmp_path / 'trial', task_id='same-task', split='training',
                            source_version='dataset-sha', run_command=runner or DockerDiagnostic())


def test_manifest_retains_split_identity_and_original_bytes(tmp_path):
    root = source(tmp_path)
    train = task_manifest(root, task_id='a', split='training', source_version='dataset-sha')
    test = task_manifest(root, task_id='a', split='test', source_version='dataset-sha')
    assert train['source_identity'] == test['source_identity']
    assert train['split'] != test['split']
    assert 'solution/solve.sh' in train['source_files']
    assert 'tests/test.sh' in train['source_files']
    assert train['environment']['allow_internet'] is False


def test_prepare_only_builds_environment_and_replaces_skills_in_copy(tmp_path):
    runner = DockerDiagnostic()
    adapter = trial(tmp_path, runner)
    before = adapter.manifest()
    result = adapter.prepare()
    assert result['status'] == 'prepared'
    assert result['skill_locations'] == ['/root/.agents/skills']
    assert not list((adapter.output / 'environment' / 'skills').iterdir())
    assert not (adapter.output / 'environment' / 'tests').exists()
    assert not (adapter.output / 'environment' / 'solution').exists()
    assert adapter.manifest() == before
    assert (adapter.source / 'environment' / 'skills' / 'curated' / 'SKILL.md').exists()
    assert (adapter.source / 'environment' / 'Dockerfile').read_bytes() == (
        adapter.output / 'environment' / 'Dockerfile').read_bytes()
    assert 'none' in runner.calls[1]
    assert runner.calls[1][-3] == 'sha256:diagnostic'
    assert all(':/tests' not in str(row) for row in runner.calls)


def test_input_fingerprint_separates_input_bytes_from_family_and_deployment(tmp_path):
    root = source(tmp_path)
    before = task_manifest(root, task_id='family', split='training', source_version='dataset')
    (root / 'environment/Dockerfile').write_text('FROM different:diagnostic')
    (root / 'environment/skills/curated/SKILL.md').write_text('Changed diagnostic skill')
    (root / 'tests/test.sh').write_text('Changed diagnostic verifier')
    deployed = task_manifest(root, task_id='other-family', split='test', source_version='dataset')
    assert before['input_fingerprint'] == deployed['input_fingerprint']
    assert before['source_identity'] != deployed['source_identity']
    (root / 'environment/input.txt').write_text('Different heldout bytes')
    changed = task_manifest(root, task_id='family', split='test', source_version='dataset')
    assert before['source_identity'] == changed['source_identity']
    assert before['input_fingerprint'] != changed['input_fingerprint']


def test_candidate_skills_are_deployed_and_hashed(tmp_path):
    adapter = trial(tmp_path)
    skills = tmp_path / 'candidate'
    (skills / 'learned').mkdir(parents=True)
    (skills / 'learned' / 'SKILL.md').write_text('name: learned\nA method.', encoding='utf-8')
    adapter.prepare(skills)
    manifest = json.loads((adapter.output / 'manifest.json').read_text())
    assert set(manifest['skills']) == {'learned/SKILL.md'}
    assert not (adapter.output / 'environment' / 'skills' / 'curated').exists()


def test_single_skill_package_returns_container_resource_mapping(tmp_path):
    adapter = trial(tmp_path)
    package = tmp_path / 'one-package'
    (package / 'scripts').mkdir(parents=True)
    (package / 'SKILL.md').write_text('---\nname: a-method\ndescription: Some method\n---', encoding='utf-8')
    (package / 'scripts' / 'helper.py').write_text('print("helper")', encoding='utf-8')
    prepared = adapter.prepare(package)
    assert prepared['skill_root'] == '/root/.agents/skills'
    assert prepared['skill_mounts'] == [{'source_directory': str(package),
        'host_directory': str(adapter.output / 'environment' / 'skills' / 'one-package'),
        'container_directory': '/root/.agents/skills/one-package'}]
    assert (adapter.output / 'environment' / 'skills' / 'one-package' / 'scripts' / 'helper.py').is_file()


def test_evaluate_uses_original_verifier_after_model_execution(tmp_path):
    runner = DockerDiagnostic()
    adapter = trial(tmp_path, runner)
    adapter.prepare()
    response = adapter.execute('printf output > output.txt')
    assert response['returncode'] == 0
    result = adapter.evaluate()
    assert result['status'] == 'evaluated' and result['passed'] is True
    assert result['observed_model_usd_decimal'] is None
    assert result['reward'] == 1
    assert any(argv[1:3] == ['cp', str(adapter.source / 'tests') + '/.'] for argv in runner.calls)
    assert any(argv[-1] == '/tests/test.sh' for argv in runner.calls)
    with pytest.raises(ValueError, match='not_executable'):
        adapter.execute('cat /tests/test.sh')
    with pytest.raises(ValueError, match='not_evaluable'):
        adapter.evaluate()
    adapter.close()
    assert runner.calls[-1][1:3] == ['rm', '--force']
    assert adapter.close() is None


@pytest.mark.parametrize('value,status,reward', [('0', 'scored', 0),
    ('0.4', 'scored', 0.4), ('NaN', 'invalid_reward', None),
    ('inf', 'invalid_reward', None), ('', 'invalid_reward', None), ('garbage', 'invalid_reward', None)])
def test_reward_text_is_explicit(tmp_path, value, status, reward):
    (tmp_path / 'reward.txt').write_text(value, encoding='utf-8')
    result = parse_reward(tmp_path)
    assert result['status'] == status and result['reward'] == reward


@pytest.mark.parametrize('value', [True, {'reward': True}, {'reward': None}, {'reward': '1'}, {'other': 1}])
def test_reward_json_rejects_unknown_or_non_numeric(tmp_path, value):
    (tmp_path / 'reward.json').write_text(json.dumps(value), encoding='utf-8')
    assert parse_reward(tmp_path)['reward'] is None


def test_positive_reward_with_failed_verifier_is_not_a_pass(tmp_path):
    adapter = trial(tmp_path, DockerDiagnostic(reward='1', verifier_code=1))
    adapter.prepare()
    result = adapter.evaluate()
    assert result['status'] == 'verifier_failed' and result['passed'] is None


def test_missing_reward_keeps_unknown(tmp_path):
    adapter = trial(tmp_path, DockerDiagnostic(reward=None))
    adapter.prepare()
    result = adapter.evaluate()
    assert result['status'] == 'verifier_failed' and result['reward'] is None


def test_changed_source_rejected_before_execution(tmp_path):
    adapter = trial(tmp_path)
    adapter.prepare()
    (adapter.source / 'tests' / 'test.sh').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='source_changed'):
        adapter.execute('true')


def test_timed_out_command_stops_container_retains_artifacts_and_allows_verifier_only(tmp_path):
    runner = DockerDiagnostic(fail_at=3)
    adapter = trial(tmp_path, runner)
    adapter.prepare()
    result = adapter.execute('sleep 1000', timeout_seconds=1)
    assert result['status'] == 'timeout' and result['stdout'] == 'partial output'
    assert runner.calls[-1][1:3] == ['stop', '--time']
    assert result['execution_state'] == 'execution_timed_out'
    assert result['container_stopped'] is True
    assert adapter.prepared and adapter.started and adapter.execution_timed_out
    with pytest.raises(ValueError, match='not_executable'):
        adapter.execute('touch late-model-output')
    artifacts = adapter.collect_artifacts()
    assert artifacts['collection_phase'] == 'pre_verification'
    assert artifacts['execution_timed_out'] is True
    assert 'solution.py' in artifacts['files']
    assert not any(argv[1] == 'rm' for argv in runner.calls)
    evaluation = adapter.evaluate()
    assert evaluation['status'] == 'evaluated' and evaluation['reward'] == 1
    assert evaluation['execution_timed_out'] is True
    assert evaluation['execution_stop_evidence'] == result['stop_evidence']
    assert evaluation['verifier_restart_evidence']
    commands = [argv[1] for argv in runner.calls]
    assert commands.index('stop') < commands.index('cp') < commands.index('start')
    assert len([argv for argv in runner.calls if argv[1] == 'start']) == 1
    with pytest.raises(ValueError, match='not_executable'):
        adapter.execute('touch late-model-output')
    adapter.close()
    assert runner.calls[-1][1:3] == ['rm', '--force']
    assert not adapter.started


@pytest.mark.parametrize('failure', ['stop', 'start'])
def test_timeout_with_unconfirmed_stop_or_failed_restart_never_runs_verifier(tmp_path, failure):
    runner = DockerDiagnostic(fail_at=3)
    def command(argv, **kwargs):
        response = runner(argv, **kwargs)
        if argv[1] == failure:
            response.returncode = 1
        return response
    adapter = trial(tmp_path, command)
    adapter.prepare()
    adapter.execute('sleep 1000', timeout_seconds=1)
    assert adapter.collect_artifacts()['status'] == 'collected'
    evaluation = adapter.evaluate()
    assert evaluation['status'] == 'verifier_setup_failed'
    assert evaluation['reward'] is None and evaluation['execution_timed_out'] is True
    assert not any(argv[-1] == '/tests/test.sh' for argv in runner.calls)
    if failure == 'stop':
        assert not any(argv[1] == 'start' for argv in runner.calls)
    adapter.close()


def test_source_manifest_does_not_expose_symlinked_external_file(tmp_path):
    root = source(tmp_path)
    private = tmp_path / 'private'
    private.write_text('private', encoding='utf-8')
    (root / 'environment' / 'outside').symlink_to(private)
    with pytest.raises(ValueError, match='symlink_outside_task'):
        task_manifest(root, task_id='a', split='training', source_version='dataset-sha')


def test_pairing_uses_intersection(tmp_path):
    train = tmp_path / 'train'
    test = tmp_path / 'test'
    train.mkdir()
    test.mkdir()
    for directory in (train / 'a', train / 'b', test / 'b', test / 'c'):
        directory.mkdir()
        (directory / 'task.toml').write_text('version="1"', encoding='utf-8')
    assert paired_tasks(train, test) == ['b']


def test_trial_output_cannot_change_original_task(tmp_path):
    root = source(tmp_path)
    with pytest.raises(ValueError, match='output_inside_source'):
        SkillsBenchTrial(root, root / 'run', task_id='task', split='test', source_version='sha')


def test_candidate_installs_portable_package_if_dockerfile_has_no_copy(tmp_path):
    root = source(tmp_path)
    (root / 'environment' / 'Dockerfile').write_text('FROM example:fixed\n', encoding='utf-8')
    runner = DockerDiagnostic()
    adapter = SkillsBenchTrial(root, tmp_path / 'trial', task_id='task', split='test',
                               source_version='sha', run_command=runner)
    prepared = adapter.prepare(root / 'environment' / 'skills')
    assert prepared['skill_locations'] == ['/root/.agents/skills']
    assert runner.calls[-1][1] == 'cp' and runner.calls[-1][-1].endswith(':/root/.agents/skills')
    manifest = json.loads((adapter.output / 'manifest.json').read_text())
    assert manifest['skill_installation'] == 'portable_runtime_copy'
    assert (adapter.output / 'environment' / 'Dockerfile').read_bytes() == (
        root / 'environment' / 'Dockerfile').read_bytes()


def test_verifier_timeout_stops_container_before_collecting_logs(tmp_path):
    runner = DockerDiagnostic(fail_at=5)
    adapter = trial(tmp_path, runner)
    adapter.prepare()
    result = adapter.evaluate()
    assert result['status'] == 'verifier_timeout' and result['passed'] is None
    stop = next(i for i, argv in enumerate(runner.calls) if argv[1] == 'stop')
    collect = next(i for i, argv in enumerate(runner.calls) if argv[1] == 'cp' and ':/logs/' in argv[2])
    assert stop < collect
    assert runner.calls[-1][1:3] == ['rm', '--force']
    assert not adapter.started


def test_build_and_verifier_limits_come_from_original_task(tmp_path):
    runner = DockerDiagnostic()
    adapter = trial(tmp_path, runner)
    adapter.prepare()
    adapter.evaluate()
    assert runner.options[0]['timeout'] == 45
    index = next(i for i, argv in enumerate(runner.calls) if argv[-1] == '/tests/test.sh')
    assert runner.options[index]['timeout'] == 30


def test_verifier_download_mirror_is_recorded_and_applied_without_script_changes(tmp_path):
    root = source(tmp_path)
    original = (root / 'tests' / 'test.sh').read_bytes()
    runner = DockerDiagnostic()
    environment = {'UV_DOWNLOAD_URL': 'https://releases.astral.sh/github/uv/releases/download/0.9.7'}
    adapter = SkillsBenchTrial(root, tmp_path / 'trial', task_id='task', split='test',
                               source_version='sha', run_command=runner, verifier_environment=environment)
    adapter.prepare()
    adapter.evaluate()
    command = next(argv for argv in runner.calls if argv[-1] == '/tests/test.sh')
    assert ['--env', 'UV_DOWNLOAD_URL=' + environment['UV_DOWNLOAD_URL']] == command[2:4]
    assert adapter.manifest()['effective_verifier_environment'] == environment
    assert (root / 'tests' / 'test.sh').read_bytes() == original


def test_new_trial_uses_fresh_container_even_with_same_image(tmp_path):
    runner = DockerDiagnostic()
    first = trial(tmp_path, runner)
    second = SkillsBenchTrial(first.source, tmp_path / 'second', task_id='same-task',
                              split='training', source_version='dataset-sha', run_command=runner)
    first.prepare()
    second.prepare()
    assert first.container != second.container
    assert first.image_id == second.image_id
    first.close()
    assert second.prepared
    assert all(argv[1] != 'rmi' for argv in runner.calls)


def test_collect_artifacts_keeps_original_source_as_host_observation(tmp_path):
    adapter = trial(tmp_path)
    adapter.prepare()
    adapter.evaluate()
    result = adapter.collect_artifacts()
    assert result['status'] == 'collected' and result['origin'] == 'host_collection'
    assert result['collection_phase'] == 'post_verification'
    assert result['workdir'] == '/work'
    assert 'solution.py' in result['files']
    assert Path(result['files']['solution.py']['path']).read_text() == 'print("generated")'
    assert result['index']['path'].endswith('artifact-index.json')
    adapter.close()
    assert adapter.collect_artifacts()['status'] == 'unavailable'


def test_collect_before_verifier_marks_model_workspace_snapshot(tmp_path):
    adapter = trial(tmp_path)
    adapter.prepare()
    adapter.execute('printf generated > solution.py')
    result = adapter.collect_artifacts()
    assert result['collection_phase'] == 'pre_verification'
    assert not adapter.evaluated
    adapter.evaluate()


@pytest.mark.parametrize('workdir', ['', '/', '//', None, 'relative', '/root/..'])
def test_collect_artifacts_requires_a_specific_container_workdir(tmp_path, workdir):
    runner = DockerDiagnostic()
    def execute(argv, **kwargs):
        result = runner(argv, **kwargs)
        if argv[1:3] == ['image', 'inspect']:
            result.stdout = json.dumps(workdir)
        return result
    adapter = trial(tmp_path, execute)
    adapter.prepare()
    result = adapter.collect_artifacts()
    assert result['status'] == 'unsupported'
    assert result['reason'] == 'explicit_task_workdir_required'
    assert not (adapter.output / 'artifacts').exists()
