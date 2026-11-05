"""SkillsBench 原任务的隔离 Docker 适配；模型调用仍由原 Harness 负责。"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import time
from uuid import uuid4

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from .capability_feedback import file_ref


def _files(directory):
    directory = Path(directory).resolve()
    files = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() and not path.resolve().is_relative_to(directory):
            raise ValueError('skillsbench_source_symlink_outside_task')
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = file_ref(path)['sha256']
    return files


def input_fingerprint(manifest):
    """Identify input bytes independently of task family or deployment files."""
    files = {name: digest for name, digest in manifest.get('source_files', {}).items()
             if Path(name).parts[0:1] == ('environment',)
             and not {'skills', 'tests'}.intersection(Path(name).parts)
             and Path(name).name not in ('Dockerfile', '.dockerignore')}
    if not files:
        return None
    return hashlib.sha256(json.dumps(sorted(files.values()), separators=(',', ':')).encode()).hexdigest()


def task_manifest(task_directory, *, task_id, split, source_version):
    """Freeze source bytes, including the original verifier, before deployment."""
    root = Path(task_directory).resolve()
    if (split not in ('training', 'test') or not isinstance(task_id, str) or not task_id
            or not isinstance(source_version, str) or not source_version
            or not all((root / name).is_file() for name in
                       ('instruction.md', 'task.toml', 'environment/Dockerfile', 'tests/test.sh'))):
        raise ValueError('skillsbench_task_invalid')
    config = tomllib.loads((root / 'task.toml').read_text(encoding='utf-8'))
    sources = _files(root)
    identity = {'task_id': task_id, 'source_version': source_version}
    return {'format': 'skillsbench_trial_manifest_v1', 'task_id': task_id, 'split': split,
            'source_version': source_version,
            'source_identity': hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
            'task_directory': str(root), 'source_files': sources,
            'input_fingerprint': input_fingerprint({'source_files': sources}),
            'instruction': file_ref(root / 'instruction.md'),
            'environment': config.get('environment', {}),
            'agent': config.get('agent', {}), 'verifier': config.get('verifier', {}),
            'metadata': config.get('metadata', {})}


def paired_tasks(training_root, test_root):
    """Return the published train/canonical intersection without selecting outcomes."""
    def names(root):
        return {p.name for p in Path(root).iterdir()
                if p.is_dir() and (p / 'task.toml').is_file()}
    return sorted(names(training_root) & names(test_root))


def parse_reward(directory):
    """Read Harbor's reward output. Missing or non-finite reward remains unknown."""
    directory = Path(directory)
    text = directory / 'reward.txt'
    structured = directory / 'reward.json'
    if text.is_file():
        value = text.read_text(encoding='utf-8').strip()
        source = file_ref(text)
        try:
            value = float(value)
        except ValueError:
            return {'status': 'invalid_reward', 'reward': None, 'evidence': source}
    elif structured.is_file():
        source = file_ref(structured)
        try:
            value = json.loads(structured.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError):
            return {'status': 'invalid_reward', 'reward': None, 'evidence': source}
        if isinstance(value, dict):
            value = value.get('reward')
    else:
        return {'status': 'reward_missing', 'reward': None, 'evidence': None}
    if type(value) not in (int, float) or not math.isfinite(value):
        return {'status': 'invalid_reward', 'reward': None, 'evidence': source}
    return {'status': 'scored', 'reward': float(value), 'evidence': source}


def completed_quality_rejection(directory, verification, reward):
    """Recognize completed pytest assertion failures from the original report."""
    if (verification.get('status') != 'completed' or verification.get('returncode') != 1
            or reward.get('status') != 'scored' or not 0 <= reward['reward'] < 1):
        return None
    report = Path(directory) / 'ctrf.json'
    try:
        result = json.loads(report.read_text(encoding='utf-8'))['results']
        summary, tests = result['summary'], result['tests']
        counts = [summary[key] for key in ('tests', 'passed', 'failed', 'skipped', 'pending', 'other')]
        if (any(type(value) is not int or value < 0 for value in counts)
                or summary['tests'] != len(tests) or summary['failed'] < 1
                or summary['tests'] != summary['passed'] + summary['failed']):
            return None
        for row in tests:
            if row['status'] == 'passed':
                continue
            if (row['status'] != 'failed' or row.get('raw_status') not in (None, 'call_failed')
                    or 'due to an assertion error' not in row.get('message', '')
                    or 'AssertionError' not in row.get('trace', '')):
                return None
        if (sum(row['status'] == 'passed' for row in tests) != summary['passed']
                or sum(row['status'] == 'failed' for row in tests) != summary['failed']):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return file_ref(report)


class SkillsBenchTrial:
    """One fresh trial. Only environment/ is built; tests enter after execution.

    ``run_command`` is the original subprocess-compatible host executor. The
    adapter performs no model calls and does not change the source task.
    """

    def __init__(self, task_directory, output_directory, *, task_id, split,
                 source_version, run_command=None, verifier_environment=None):
        self.source = Path(task_directory).resolve()
        self.output = Path(output_directory).resolve()
        if self.output.is_relative_to(self.source):
            raise ValueError('skillsbench_output_inside_source')
        self.task_id = task_id
        self.split = split
        self.source_version = source_version
        self._run_command = run_command or subprocess.run
        self.container = 'geneloop-bench-' + uuid4().hex
        self.image_id = None
        self.operation = 0
        self.prepared = False
        self.evaluated = False
        self.started = False
        self.execution_timed_out = False
        self.execution_stopped = False
        self.execution_stop = None
        self._manifest = task_manifest(self.source, task_id=task_id, split=split,
                                       source_version=source_version)
        self.verifier_environment = {**self._manifest['verifier'].get('env', {}),
                                     **(verifier_environment or {})}
        if any(not isinstance(key, str) or not key or '=' in key or '\x00' in key
               or not isinstance(value, str) or '\x00' in value
               for key, value in self.verifier_environment.items()):
            raise ValueError('skillsbench_verifier_environment_invalid')
        self._manifest['effective_verifier_environment'] = self.verifier_environment

    def manifest(self):
        return json.loads(json.dumps(self._manifest))

    def _check_source(self):
        if _files(self.source) != self._manifest['source_files']:
            raise ValueError('skillsbench_source_changed')

    def _save(self, name, value):
        path = self.output / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        return file_ref(path)

    def _invoke(self, argv, *, timeout_seconds=None):
        self.operation += 1
        stem = 'operation-' + str(self.operation).zfill(4)
        started = time.monotonic()
        result = {'argv': list(argv), 'status': 'failed', 'returncode': None}
        try:
            process = self._run_command(list(argv), capture_output=True, text=True,
                                        errors='replace', timeout=timeout_seconds, check=False)
            result.update(status='completed', returncode=process.returncode)
            stdout, stderr = process.stdout, process.stderr
        except subprocess.TimeoutExpired as error:
            result['status'] = 'timeout'
            stdout, stderr = error.stdout or '', error.stderr or ''
        except OSError as error:
            stdout, stderr = '', str(error)
        if isinstance(stdout, bytes):
            stdout = stdout.decode('utf-8', errors='replace')
        if isinstance(stderr, bytes):
            stderr = stderr.decode('utf-8', errors='replace')
        for kind, value in (('stdout', stdout), ('stderr', stderr)):
            path = self.output / (stem + '.' + kind + '.txt')
            path.write_text(value, encoding='utf-8')
            result[kind] = value
            result[kind + '_ref'] = file_ref(path)
        result['elapsed_seconds'] = time.monotonic() - started
        result['record'] = self._save(stem + '.json', result)
        return result

    def prepare(self, skills_directory=None):
        self._check_source()
        dockerfile = (self.source / 'environment' / 'Dockerfile').read_text(encoding='utf-8')
        skill_locations = re.findall(r'^\s*COPY\s+(?:--\S+\s+)*skills/?\s+(\S+)\s*$',
                                     dockerfile, re.MULTILINE)
        portable_install = skills_directory is not None and not skill_locations
        if portable_install:
            skill_locations = ['/root/.agents/skills']
        self.output.mkdir(parents=True, mode=0o700, exist_ok=False)
        context = self.output / 'environment'
        shutil.copytree(self.source / 'environment', context)
        skills = context / 'skills'
        if skills.exists():
            shutil.rmtree(skills)
        if skills_directory is None:
            skills.mkdir()
        else:
            # Force a source snapshot and reject escaping links before copying.
            _files(skills_directory)
            source_skills = Path(skills_directory).resolve()
            if (source_skills / 'SKILL.md').is_file():
                skills.mkdir()
                shutil.copytree(source_skills, skills / source_skills.name)
            else:
                shutil.copytree(source_skills, skills)
        skill_locations = [path.rstrip('/') for path in skill_locations]
        skill_root = '/root/.agents/skills' if '/root/.agents/skills' in skill_locations else (
            skill_locations[0] if skill_locations else None)
        mounts = []
        if skills_directory is not None and skill_root is not None:
            original = Path(skills_directory).resolve()
            for package in sorted(skills.iterdir()):
                if package.is_dir() and (package / 'SKILL.md').is_file():
                    mounts.append({'source_directory': str(original if (original / 'SKILL.md').is_file()
                                                            else original / package.name),
                                   'host_directory': str(package),
                                   'container_directory': skill_root + '/' + package.name})
        deployed = _files(context)
        self._save('manifest.json', {**self._manifest, 'deployed_environment': deployed,
                                    'skills': _files(skills), 'skill_locations': skill_locations,
                                    'skill_root': skill_root, 'skill_mounts': mounts,
                                    'build_environment': {'DOCKER_BUILDKIT': os.environ.get('DOCKER_BUILDKIT')},
                                    'skill_installation': 'portable_runtime_copy' if portable_install else 'original_dockerfile'})
        image_file = self.output / 'image-id.txt'
        build = self._invoke(['docker', 'build', '--iidfile', str(image_file), str(context)],
                            timeout_seconds=self._manifest['environment'].get('build_timeout_sec'))
        if build['returncode'] != 0 or not image_file.is_file():
            raise RuntimeError('skillsbench_image_build_failed')
        self.image_id = image_file.read_text(encoding='utf-8').strip()
        argv = ['docker', 'run', '--detach', '--name', self.container]
        environment = self._manifest['environment']
        if environment.get('cpus') is not None:
            argv += ['--cpus', str(environment['cpus'])]
        if environment.get('memory_mb') is not None:
            argv += ['--memory', str(environment['memory_mb']) + 'm']
        if environment.get('allow_internet') is False:
            argv += ['--network', 'none']
        argv += ['--entrypoint', '/bin/sh', self.image_id, '-c',
                 'while :; do sleep 3600; done']
        # A failed start can still have created the named container.
        self.started = True
        start = self._invoke(argv)
        if start['returncode'] != 0:
            self.close()
            raise RuntimeError('skillsbench_container_start_failed')
        if portable_install:
            created = self._invoke(['docker', 'exec', self.container, '/bin/mkdir', '-p', skill_locations[0]])
            copied = self._invoke(['docker', 'cp', str(skills) + '/.', self.container + ':' + skill_locations[0]])
            if created['returncode'] != 0 or copied['returncode'] != 0:
                self.close()
                raise RuntimeError('skillsbench_skill_installation_failed')
        self.prepared = True
        return {'status': 'prepared', 'container': self.container, 'image_id': self.image_id,
                'skill_locations': skill_locations,
                'skill_root': skill_root, 'host_skill_root': str(skills), 'skill_mounts': mounts,
                'instruction': self._manifest['instruction'],
                'manifest': file_ref(self.output / 'manifest.json')}

    def execute(self, command, *, timeout_seconds=None):
        if not self.prepared or self.evaluated or self.execution_timed_out:
            raise ValueError('skillsbench_trial_not_executable')
        if not isinstance(command, str) or not command:
            raise ValueError('skillsbench_command_invalid')
        self._check_source()
        result = self._invoke(['docker', 'exec', self.container, '/bin/bash', '-lc', command],
                              timeout_seconds=timeout_seconds)
        if result['status'] == 'timeout':
            self.execution_timed_out = True
            stopped = self._invoke(['docker', 'stop', '--time', '0', self.container], timeout_seconds=10)
            self.execution_stopped = stopped['returncode'] == 0
            self.execution_stop = stopped['record']
            result.update(execution_timed_out=True, execution_state='execution_timed_out',
                          container_stopped=self.execution_stopped, stop_evidence=self.execution_stop)
            result['timeout_evidence'] = self._save('execution-timeout.json', result)
        return result

    def evaluate(self):
        if not self.prepared or self.evaluated:
            raise ValueError('skillsbench_trial_not_evaluable')
        self._check_source()
        self.evaluated = True
        restart = None
        ready = not self.execution_timed_out
        if self.execution_timed_out and self.execution_stopped:
            restart = self._invoke(['docker', 'start', self.container], timeout_seconds=10)
            ready = restart['returncode'] == 0
        setup = self._invoke(['docker', 'exec', self.container, '/bin/mkdir', '-p', '/logs/verifier']) \
            if ready else {'returncode': None}
        copied = self._invoke(['docker', 'cp', str(self.source / 'tests') + '/.', self.container + ':/tests']) \
            if ready else {'returncode': None}
        if setup['returncode'] != 0 or copied['returncode'] != 0:
            result = {'status': 'verifier_setup_failed', 'reward': None, 'passed': None}
        else:
            argv = ['docker', 'exec']
            for key, value in self.verifier_environment.items():
                argv += ['--env', key + '=' + value]
            verification = self._invoke(argv + [self.container, '/bin/bash', '/tests/test.sh'],
                                        timeout_seconds=self._manifest['verifier'].get('timeout_sec'))
            timed_out = verification['status'] == 'timeout'
            if timed_out:
                self._invoke(['docker', 'stop', '--time', '0', self.container])
                self.prepared = False
            logs = self.output / 'verifier'
            logs.mkdir()
            collected = self._invoke(['docker', 'cp', self.container + ':/logs/verifier/.', str(logs)])
            reward = parse_reward(logs) if collected['returncode'] == 0 else {
                'status': 'reward_collection_failed', 'reward': None, 'evidence': None}
            rejection = completed_quality_rejection(logs, verification, reward)
            valid = reward['status'] == 'scored' and (verification['returncode'] == 0 or rejection is not None)
            result = {**reward, 'status': 'evaluated' if valid else 'verifier_failed',
                      'passed': reward['reward'] > 0 if valid else None,
                      'verification': verification['record']}
            if rejection is not None:
                result.update(verifier_outcome='quality_rejected', quality_rejection_evidence=rejection)
            if timed_out:
                result['status'] = 'verifier_timeout'
                self.close()
        result.update(task_id=self.task_id, split=self.split,
                      input_fingerprint=self._manifest['input_fingerprint'],
                      execution_timed_out=self.execution_timed_out,
                      execution_stop_evidence=self.execution_stop,
                      verifier_restart_evidence=restart['record'] if restart else None,
                      source_identity=self._manifest['source_identity'],
                      observed_model_usd_decimal=None, quality='official_verifier',
                      manifest=file_ref(self.output / 'manifest.json'))
        result['record'] = self._save('evaluation.json', result)
        return result

    def collect_artifacts(self):
        """Snapshot the public task workspace before cleanup as a host action."""
        if not self.started or self.image_id is None:
            return {'status': 'unavailable', 'reason': 'container_closed'}
        inspected = self._invoke(['docker', 'image', 'inspect', self.image_id,
                                  '--format', '{{json .Config.WorkingDir}}'])
        try:
            workdir = json.loads(inspected['stdout'])
        except (ValueError, TypeError):
            workdir = None
        if isinstance(workdir, str) and workdir:
            workdir = posixpath.normpath(workdir)
        if (inspected['returncode'] != 0 or not isinstance(workdir, str)
                or not workdir.strip('/') or not workdir.startswith('/')):
            return {'status': 'unsupported', 'reason': 'explicit_task_workdir_required',
                    'configured_workdir': workdir, 'evidence': inspected['record']}
        directory = self.output / 'artifacts'
        directory.mkdir(exist_ok=False)
        copied = self._invoke(['docker', 'cp', self.container + ':' + workdir.rstrip('/') + '/.',
                               str(directory)])
        files, links = {}, {}
        for path in sorted(directory.rglob('*')):
            relative = path.relative_to(directory).as_posix()
            if path.is_symlink():
                links[relative] = str(path.readlink())
            elif path.is_file():
                files[relative] = file_ref(path)
        result = {'format': 'skillsbench_artifact_index_v1', 'origin': 'host_collection',
                  'collection_phase': 'post_verification' if self.evaluated else 'pre_verification',
                  'execution_timed_out': self.execution_timed_out,
                  'status': 'collected' if copied['returncode'] == 0 else 'collection_failed',
                  'task_id': self.task_id, 'split': self.split, 'workdir': workdir,
                  'source_identity': self._manifest['source_identity'],
                  'scope': 'task_workdir_snapshot_including_initial_files',
                  'files': files, 'symlinks': links, 'copy_evidence': copied['record']}
        result['index'] = self._save('artifact-index.json', result)
        return result

    def close(self):
        if self.started:
            self.started = False
            self.prepared = False
            return self._invoke(['docker', 'rm', '--force', self.container])
        return None
