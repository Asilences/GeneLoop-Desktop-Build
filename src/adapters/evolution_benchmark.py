"""Shared real task host for GeneLoop and the Skill∞ paper reproduction."""
from __future__ import annotations

import json
import re
from pathlib import Path
import shlex
import shutil
import time
from uuid import uuid4

from .capability_feedback import file_ref, verify
from .capability_contract import capability_digest
from .capability_improvement import save
from .capability_proposal import parse_proposal
from .research_harness import ResearchHarness
from .skill_infinity_baseline import _card
from .skillsbench_trial import SkillsBenchTrial, input_fingerprint, task_manifest
from .benchmark_capability_tools import benchmark_capability_tools, capability_trace_projection
from .capability_motif_learning import capture_capability_trace


def _model_scoreable(model):
    if model.get('status') == 'completed':
        return True
    requests = model.get('provider_requests')
    if (model.get('status') != 'timeout' or model.get('timed_out') is not True
            or type(requests) is not int or requests <= 0):
        return False
    cancellation = model.get('cancel_evidence')
    if not isinstance(cancellation, dict) or set(cancellation) != {'path', 'sha256'}:
        return False
    try:
        evidence = json.loads(verify(cancellation))
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return (isinstance(evidence, dict)
            and (evidence.get('accepted') is True or evidence.get('runtime_closed') is True))


def _verification_evidence(evaluation, *, task_id, split, source_identity):
    """Index fixed host verifier outputs, never the post-verifier workspace."""
    if not any(evaluation.get(key) for key in ('record', 'verification', 'evidence')):
        return []
    record = evaluation.get('record')
    if not isinstance(record, dict) or set(record) != {'path', 'sha256'}:
        raise ValueError('benchmark_verifier_record_required')
    stored = json.loads(verify(record))
    if (Path(record['path']).name != 'evaluation.json' or stored.get('task_id') != task_id
            or stored.get('split') != split or stored.get('source_identity') != source_identity):
        raise ValueError('benchmark_verifier_scope_changed')
    root = Path(record['path']).resolve().parent
    references = [record]
    for key in ('evidence', 'verification'):
        reference = evaluation.get(key)
        if reference != stored.get(key):
            raise ValueError('benchmark_verifier_reference_changed')
        if reference is None:
            continue
        if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
            raise ValueError('benchmark_verifier_reference_invalid')
        path = Path(reference['path']).resolve()
        if key == 'evidence':
            if path not in (root / 'verifier/reward.txt', root / 'verifier/reward.json'):
                raise ValueError('benchmark_verifier_reward_path_changed')
            verify(reference)
            references.append(reference)
            continue
        if path.parent != root or not re.fullmatch(r'operation-[0-9]+\.json', path.name):
            raise ValueError('benchmark_verifier_operation_path_changed')
        operation = json.loads(verify(reference))
        if not isinstance(operation.get('argv'), list) or operation['argv'][-1:] != ['/tests/test.sh']:
            raise ValueError('benchmark_verifier_operation_changed')
        references.append(reference)
        for stream in ('stdout', 'stderr'):
            output = operation.get(stream + '_ref')
            if (not isinstance(output, dict) or set(output) != {'path', 'sha256'}
                    or Path(output['path']).resolve() != root / (path.stem + '.' + stream + '.txt')):
                raise ValueError('benchmark_verifier_output_path_changed')
            verify(output)
            references.append(output)
    return references


def validation_dataset_splits(mapping=None):
    if (mapping is not None and (not isinstance(mapping, dict)
            or any(not isinstance(task, str) or not task.strip() or split not in ('training', 'test')
                   for task, split in mapping.items()))):
        raise ValueError('benchmark_validation_splits_invalid')
    return dict(mapping or {})


def observation_input_fingerprint(row, *, require_manifest=False):
    """Recover old host records only from their original verified manifest."""
    state = row.get('decision_context', {}).get('state', {})
    family = state.get('task_family_identity', row.get('source_identity'))
    for reference in row.get('evidence', []):
        if Path(reference['path']).name != 'manifest.json':
            continue
        manifest = json.loads(verify(reference))
        if manifest.get('format') == 'skillsbench_trial_manifest_v1':
            if manifest.get('source_identity') != family:
                raise ValueError('benchmark_input_source_identity_changed')
            fingerprint = input_fingerprint(manifest)
            if row.get('input_fingerprint') not in (None, fingerprint):
                raise ValueError('benchmark_input_fingerprint_changed')
            return fingerprint
    if state.get('source_independence_basis') == 'verified_input_fingerprint':
        raise ValueError('benchmark_input_manifest_required')
    return None if require_manifest else row.get('input_fingerprint')


def benchmark_evaluation_role(record):
    state = record.get('decision_context', {}).get('state', {})
    state = state if isinstance(state, dict) else {}
    role = record.get('evaluation_role') or state.get('evaluation_role')
    if role is not None:
        if role not in ('development', 'validation', 'final'):
            raise ValueError('benchmark_evaluation_role_invalid')
        return role
    label = record.get('label', state.get('label', '')) or ''
    if 'validation' in label:
        return 'validation'
    if 'development' in label or label == 'training':
        return 'development'
    return 'final' if record.get('split', state.get('split')) == 'test' else 'development'


class BenchmarkHost:
    """Identical task inputs, tools, model transport and verifier for both arms."""

    def __init__(self, training_root, test_root, output, *, source_version, gate,
                 verifier_environment=None, materials=None, prewarm_dependencies=False, validation_splits=None):
        self.training = Path(training_root).resolve()
        self.test = Path(test_root).resolve()
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.source_version = source_version
        self.gate = gate
        self.verifier_environment = verifier_environment
        self.materials = materials
        self.prewarm_dependencies = prewarm_dependencies
        self.validation_splits = validation_dataset_splits(validation_splits)
        self.agent = ResearchHarness(gate, self.output / 'model-sessions')
        self.observations = []

    def input_fingerprint(self, task_id, split):
        source = (self.test if split == 'test' else self.training) / task_id
        return task_manifest(source, task_id=task_id, split=split,
                             source_version=self.source_version)['input_fingerprint']

    def trial(self, task_id, *, split='training', skill_directory=None, label='initial', evaluation_role=None):
        evaluation_role = benchmark_evaluation_role({'evaluation_role': evaluation_role,
                                                     'split': split, 'label': label})
        directory = self.output / 'trials' / (task_id + '-' + label + '-' + uuid4().hex)
        directory.parent.mkdir(exist_ok=True)
        source = (self.test if split == 'test' else self.training) / task_id
        trial = SkillsBenchTrial(source, directory, task_id=task_id,
                                 split=split, source_version=self.source_version,
                                 verifier_environment=self.verifier_environment)
        bundle = None
        cards = []
        if skill_directory is not None:
            card = _card(skill_directory)
            bundle = self.output / 'skill-bundles' / uuid4().hex
            bundle.mkdir(parents=True)
            installed = bundle / card['name']
            shutil.copytree(skill_directory, installed)
            cards.append({**card, 'path': str(installed)})
        started = time.monotonic()
        result = {'status': 'failed', 'task_id': task_id, 'split': split, 'dataset_split': split,
                  'evaluation_role': evaluation_role, 'label': label,
                  'input_fingerprint': trial.manifest()['input_fingerprint']}
        capability_receipts = []
        try:
            prepared = trial.prepare(skills_directory=bundle)
            if self.prewarm_dependencies:
                from .benchmark_dependency_profile import dependency_profile
                profile = dependency_profile(source)
                preparation = {'status': 'not_applicable', 'profile': profile, 'operations': [],
                               'scope': 'public_dependency_setup_before_model', 'model_requests': 0}
                try:
                    if profile is not None:
                        preparation['status'] = 'preparing'
                        environment = ' '.join(shlex.quote(key + '=' + value)
                            for key, value in (self.verifier_environment or {}).items()
                            if key in profile['environment_keys'])
                        for step in profile['steps']:
                            command = ('env ' + environment + ' /bin/bash -lc ' + shlex.quote(step['command']))
                            operation = trial.execute(command, timeout_seconds=step['timeout_seconds'])
                            preparation['operations'].append({'id': step['id'], 'operation': operation['record']})
                            if operation['status'] != 'completed' or operation['returncode'] != 0:
                                preparation['status'] = 'failed'
                                raise RuntimeError('benchmark_dependency_preparation_failed:' + step['id'])
                        preparation['status'] = 'prepared'
                finally:
                    save(directory / 'dependency-preparation.json', preparation)
                    result['dependency_preparation'] = file_ref(directory / 'dependency-preparation.json')
            if cards:
                cards[0]['resource_base'] = prepared.get('skill_root', '/.agents/skills') + '/' + cards[0]['name']
            timeout = trial.manifest()['agent'].get('timeout_sec', 600)
            deadline = time.monotonic() + timeout
            capability_tools = []
            capability_dispatch = None
            capability_overview = None
            if self.materials is not None:
                native_catalog = self.materials.catalog()
                available = native_catalog['snapshot']
                result['capability_context'] = {'snapshot_sha256': available['digest'], 'roots': available['roots']}
                descriptions = {card['capability']['id']: card.get('description')
                                for card in native_catalog.get('catalog', [])}
                capability_overview = {'count': len(available['roots'])}
                if available['roots']:
                    capability_overview.update(items=[{'capability_id': ref['id'],
                        'description': descriptions.get(ref['id'])} for ref in available['roots'][:8]],
                        next_offset=8 if len(available['roots']) > 8 else None,
                        details_tool='capability_list')
                capability_tools, capability_dispatch, capability_receipts = benchmark_capability_tools(
                    self.materials, trial, directory / 'capability-calls', task_id + '-' + split)

            def dispatch(name, arguments):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('benchmark_agent_deadline')
                if capability_dispatch is not None and name in ('capability_list', 'capability_call'):
                    return capability_dispatch(name, arguments)
                if name != 'execute':
                    raise ValueError('benchmark_tool_unknown')
                execution = trial.execute(arguments['command'], timeout_seconds=remaining)
                return {key: execution[key] for key in ('status', 'returncode', 'stdout', 'stderr', 'record')}

            tool = {'name': 'execute', 'description': 'Execute a shell command in this task container. '
                    'Read inputs, write your implementation and outputs, and inspect your results here.',
                    'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}},
                                   'required': ['command'], 'additionalProperties': False}}
            request = {'mode': 'benchmark_task', 'prompt': verify(prepared['instruction']).decode('utf-8'),
                       'system': 'Complete the supplied task using the available container tool. '
                                 'All commands run in the task container. Return after writing the requested outputs.',
                       'available_skill_cards': cards, 'tools': [tool, *capability_tools], 'timeout_seconds': timeout}
            if capability_overview is not None:
                request['initial_context'] = {'reusable_capabilities': capability_overview}
            model = self.agent(request, dispatch)
            collected = trial.collect_artifacts()
            if collected.get('index'):
                index = json.loads(verify(collected['index']))
                save(directory / 'pre-verification-artifact-index.json', {
                    **index, 'phase': 'pre_verification', 'original_index': collected['index']})
                collected = {**collected, 'phase': 'pre_verification',
                             'original_index': collected['index'],
                             'index': file_ref(directory / 'pre-verification-artifact-index.json')}
            result['artifacts'] = collected
            evaluation = trial.evaluate()
            result.update(status='evaluated', model=model, evaluation=evaluation,
                          model_scoreable=_model_scoreable(model),
                          skill_activated=bool(model.get('activated_skill_names')) if cards else None,
                          score=str(evaluation['reward'])
                              if evaluation.get('status') == 'evaluated' and _model_scoreable(model)
                              and evaluation.get('reward') is not None else None,
                          manifest=prepared['manifest'])
        except Exception as error:
            result['error'] = type(error).__name__ + ':' + str(error)
        finally:
            if capability_receipts:
                save(directory / 'capability-call-records.json', capability_receipts)
                result['capability_calls'] = file_ref(directory / 'capability-call-records.json')
                try:
                    projection = capability_trace_projection(capability_receipts)
                    save(directory / 'capability-input-projection.json', projection)
                    trace = capture_capability_trace(projection['snapshot'], task_id=projection['task_id'],
                        task_input=projection['trace_inputs'], task_fingerprint=projection['task_fingerprint'],
                        calls=projection['calls'])
                    save(directory / 'capability-trajectory.json', trace)
                    result['capability_trajectory'] = file_ref(directory / 'capability-trajectory.json')
                    result['capability_input_projection'] = file_ref(directory / 'capability-input-projection.json')
                except Exception as error:
                    result['capability_capture_pending'] = type(error).__name__ + ':' + str(error)
            result['elapsed_seconds'] = time.monotonic() - started
            result['cleanup'] = trial.close()
            save(directory / 'result.json', result)
        observation = self._observation(trial, result, directory)
        self.observations.append(observation)
        return {**result, 'record': file_ref(directory / 'result.json'), 'observation': observation}

    def _observation(self, trial, result, directory):
        manifest = trial.manifest()
        model = result.get('model', {})
        evaluation = result.get('evaluation', {})
        evidence = [file_ref(directory / 'result.json'), manifest['instruction']]
        diagnostics = _verification_evidence(evaluation, task_id=trial.task_id, split=trial.split,
                                             source_identity=manifest['source_identity'])
        evidence.extend(diagnostics)
        if (directory / 'manifest.json').is_file():
            evidence.append(file_ref(directory / 'manifest.json'))
        events = Path(model.get('directory', directory)) / 'events.jsonl'
        if events.is_file():
            evidence.append(file_ref(events))
        tool_log = Path(model.get('directory', directory)) / 'tool-calls.jsonl'
        if tool_log.is_file():
            evidence.append(file_ref(tool_log))
        for name in ('result.json', 'requests.jsonl'):
            path = Path(model.get('directory', directory)) / name
            if path.is_file():
                evidence.append(file_ref(path))
        row = {'owner': 'overnight-research', 'task_id': trial.task_id + '-' + trial.split,
               'source_identity': manifest['source_identity'], 'relation': 'benchmark-task-work',
               'input_fingerprint': manifest['input_fingerprint'],
               'stage': 'execution', 'status': 'passed' if evaluation.get('passed') else 'failed',
               'quality': 'official_verifier' if evaluation.get('reward') is not None else 'unreviewed',
               'counterexample': False, 'capabilities': [], 'steps': [],
               'model_decision_count': model.get('provider_requests'),
               'observed_cost_usd': model.get('observed_model_usd'),
               'cost_attribution': 'task_model_requests_only; construction and shared research are separate',
               'decision_context': {'objective': verify(manifest['instruction']).decode('utf-8'),
                    'state': {'task_id': trial.task_id, 'split': trial.split, 'dataset_split': trial.split,
                              'evaluation_role': result['evaluation_role'], 'label': result['label']},
                    'outcome': {'reward': evaluation.get('reward'), 'error': result.get('error'),
                                'model_finish': model.get('finish_reason'),
                                'verifier_status': evaluation.get('status'),
                                'diagnostic_evidence_ids': {Path(ref['path']).name: 'evidence_' + ref['sha256']
                                                            for ref in diagnostics}}},
               'evidence': evidence, 'interaction_evidence': []}
        actions = []
        for index, action in enumerate(model.get('tools', [])):
            arguments = action.get('arguments')
            command = arguments.get('command') if isinstance(arguments, dict) else None
            outcome = action.get('result')
            outcome = outcome if isinstance(outcome, dict) else {}
            reference = outcome.get('record') or outcome.get('receipt')
            if isinstance(reference, dict) and set(reference) == {'path', 'sha256'}:
                verify(reference)
                row['evidence'].append(reference)
                evidence_id = 'evidence_' + reference['sha256']
            else:
                evidence_id = None
            first_line = command.splitlines()[0] if isinstance(command, str) and command.splitlines() else None
            stderr = outcome.get('stderr')
            actions.append({'index': index, 'name': action.get('name'), 'status': action.get('status'),
                'command_first_line': first_line[:240] if first_line is not None else None,
                'command_characters': len(command) if isinstance(command, str) else None,
                'returncode': outcome.get('returncode'),
                'stderr_preview': stderr[:240] if isinstance(stderr, str) else None,
                'evidence_id': evidence_id,
                'original_tool_sequence': action.get('sequence', index)})
        row['action_overview'] = actions
        row['action_scope'] = 'deterministic_host_callback_action_projection; full native events retained separately'
        artifacts = result.get('artifacts', {})
        if artifacts.get('phase') == 'pre_verification' and artifacts.get('index'):
            artifact_index = json.loads(verify(artifacts['index']))
            if artifact_index.get('phase') != 'pre_verification':
                raise ValueError('benchmark_artifact_phase_changed')
            row['evidence'].append(artifacts['index'])
            files = artifact_index.get('files', {})
            row['evidence'].extend(reference for name, reference in files.items()
                                   if Path(name).suffix in ('.py', '.js', '.json', '.csv', '.txt', '.md', '.obj'))
        for name in ('capability_calls', 'capability_input_projection', 'capability_trajectory'):
            if result.get(name):
                row['evidence'].append(result[name])
        if result.get('capability_trajectory'):
            captured = json.loads(verify(result['capability_trajectory']))
            row['capabilities'] = list({step['capability']['id']: step['capability']
                                       for step in captured['steps']}.values())
            row['steps'] = captured['steps']
            row['capability_trajectory'] = result['capability_trajectory']
            if result.get('capability_input_projection'):
                row['capability_input_projection'] = result['capability_input_projection']
            row['observation_level'] = 'actual_runtime_calls_with_host_argument_projection'
        path = directory / 'experience.json'
        save(path, row)
        return file_ref(path)

    def evaluate_skill(self, request):
        task_id = request['context']['task_id']
        split = self.validation_splits.get(task_id, 'training') if request['split'] == 'validation' else 'training'
        result = self.trial(task_id, split=split, skill_directory=request['skill_directory'],
                            label=request['split'],
                            evaluation_role='validation' if request['split'] == 'validation' else 'development')
        if result.get('score') is None:
            raise ValueError('benchmark_trial_unscored:' + result.get('error', result['status']))
        observation = inspect_benchmark(result['observation'], 'overnight-research')
        evidence_path = Path(result['record']['path']).parent / 'evaluation-evidence-index.json'
        save(evidence_path, {'evidence_refs': [result['record'], result['observation'], *observation['evidence']],
                             'evidence_indexes': [], 'scope': 'original_task_and_verifier_diagnostics_no_oracle'})
        return {'score': result['score'], 'skill_activated': result['skill_activated'],
                'record': result['record'], 'observation': result['observation'],
                'evidence_indexes': [file_ref(evidence_path)],
                'validation_scope': 'canonical_validation_input' if split == 'test' else 'fresh_run_of_training_variant',
                'dataset_split': split, 'evaluation_role': result['evaluation_role'],
                'observed_model_usd_decimal': str(result['model']['observed_model_usd'])
                    if result['model'].get('observed_model_usd') is not None else None}

    def review_skill(self, request):
        parent = Path(request['parent_skill_directory'])
        candidate = Path(request['candidate_skill_directory'])
        policy = Path(request['reviewer_policy'])
        roots = {'parent': parent, 'candidate': candidate, 'policy': policy.parent}
        references = {}
        evidence_indexes = set()

        def register_host_evidence(value):
            # Match SkillInfinityRun._register_evidence: only explicit host
            # fields authorize reads, and only host indexes may extend them.
            if not isinstance(value, dict):
                raise ValueError('review_host_evidence_index_invalid')
            for field in ('evidence_refs', 'evidence_indexes'):
                for reference in value.get(field, []):
                    if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
                        raise ValueError('review_host_evidence_reference_invalid')
                    verify(reference)
                    references[reference['sha256']] = dict(reference)
                    if field == 'evidence_indexes':
                        evidence_indexes.add(reference['sha256'])

        for field in ('evaluation', 'parent_rollout', 'candidate_rollout'):
            host_result = request.get(field)
            if host_result is None:
                continue
            register_host_evidence(host_result)
            for name in ('record', 'observation'):
                if host_result.get(name) is not None:
                    register_host_evidence({'evidence_refs': [host_result[name]]})

        def dispatch(name, arguments):
            if name != 'review_read':
                raise ValueError('review_tool_unknown')
            if arguments['subject'] == 'evidence':
                if arguments['resource'] not in references:
                    raise ValueError('review_evidence_not_authorized')
                reference = references[arguments['resource']]
                raw = verify(reference)
                path = Path(reference['path'])
            else:
                base = roots[arguments['subject']]
                path = (base / arguments['resource']).resolve()
                if not path.is_relative_to(base) or not path.is_file():
                    raise ValueError('review_resource_invalid')
                reference = file_ref(path)
                raw = verify(reference)
            text = raw.decode('utf-8')
            if arguments['subject'] == 'evidence' and reference['sha256'] in evidence_indexes:
                register_host_evidence(json.loads(text))
            offset, limit = arguments.get('offset', 0), arguments.get('limit', 12000)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 64000:
                raise ValueError('review_page_invalid')
            end = min(offset + limit, len(text))
            return {'content': text[offset:end], 'evidence': reference, 'characters': len(text),
                    'next_offset': end if end < len(text) else None,
                    'evidence_index': list(references.values())}

        model = self.agent({'mode': 'independent_review',
            'system': 'Independently review the proposed skill against original evaluation evidence.',
            'prompt': 'Review this candidate. Inspect the parent, candidate and reviewer policy with review_read. '
                      'Use subject evidence with a SHA256 identifier to inspect original evaluation, '
                      'rollout, request and cost records. Relevant references:\n' + json.dumps(list(references.values()))
                      + '\nEvaluate substantive changes, activation and the stated hypothesis. Return exactly JSON '
                      '{"accepted":true or false,"reason":"evidence-grounded reason"}.\n'
                      + json.dumps({key: value for key, value in request.items()
                                    if key not in ('parent_skill_directory', 'candidate_skill_directory')}, ensure_ascii=False),
            'tools': [{'name': 'review_read', 'description': 'Read a resource in the independent review scope.',
                       'parameters': {'type': 'object', 'properties': {
                           'subject': {'type': 'string', 'enum': ['parent', 'candidate', 'policy', 'evidence']},
                           'resource': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
                           'limit': {'type': 'integer', 'minimum': 1, 'maximum': 64000}}, 'required': ['subject', 'resource'],
                           'additionalProperties': False}}], 'available_skill_cards': []}, dispatch)
        if model.get('status') != 'completed':
            raise ValueError('benchmark_review_failed_or_incomplete')
        verdict = parse_proposal(model['text'])
        return {**verdict, 'model_record': file_ref(Path(model['directory']) / 'result.json')}


def inspect_benchmark(reference, owner):
    value = json.loads(verify(reference))
    if value.get('owner') != owner:
        raise ValueError('benchmark_experience_owner_changed')
    for evidence in value['evidence']:
        verify(evidence)
        if Path(evidence['path']).suffix == '.json':
            try:
                candidate = json.loads(verify(evidence))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if (isinstance(candidate, dict) and candidate.get('format') == 'skillsbench_artifact_index_v1'
                    and candidate.get('phase') != 'pre_verification'):
                raise ValueError('benchmark_artifact_pre_verification_required')
    # R3 stored the original trial result but omitted its verifier diagnostics
    # from the evidence index. Derive this view without changing that record.
    for evidence in value['evidence'][:]:
        path = Path(evidence['path']).resolve()
        if path.name != 'result.json' or path.parent != Path(reference['path']).resolve().parent:
            continue
        original = json.loads(verify(evidence))
        state = value.get('decision_context', {}).get('state', {})
        if original.get('task_id') != state.get('task_id') or original.get('split') != state.get('split'):
            raise ValueError('benchmark_original_trial_scope_changed')
        diagnostics = _verification_evidence(original.get('evaluation', {}), task_id=original['task_id'],
            split=original['split'], source_identity=value['source_identity'])
        outcome = value.get('decision_context', {}).get('outcome')
        if isinstance(outcome, dict):
            outcome['verifier_status'] = original.get('evaluation', {}).get('status')
            outcome['diagnostic_evidence_ids'] = {Path(ref['path']).name: 'evidence_' + ref['sha256']
                                                  for ref in diagnostics}
        added = [item for item in diagnostics if item not in value['evidence']]
        if added:
            value['evidence'].extend(added)
            value['derived_verifier_evidence'] = {'origin': 'host_fixed_evaluation_fields',
                'source_record': evidence, 'references': added,
                'scope': 'original_quality_diagnostics_only_no_post_verification_artifacts'}
        break
    # Preserve the original family/version identity in stored evidence. The
    # investigation view counts witnessed input instances across task families.
    state = value.setdefault('decision_context', {}).setdefault('state', {})
    family = value['source_identity']
    if state.get('task_family_identity', family) != family:
        raise ValueError('benchmark_task_family_identity_changed')
    fingerprint = observation_input_fingerprint(value, require_manifest=True)
    state['task_family_identity'] = family
    state['source_independence_basis'] = 'legacy_family_identity'
    if fingerprint is not None:
        value['input_fingerprint'] = fingerprint
        value['source_identity'] = capability_digest({'benchmark_input_fingerprint': fingerprint})
        state['source_independence_basis'] = 'verified_input_fingerprint'
    return value
