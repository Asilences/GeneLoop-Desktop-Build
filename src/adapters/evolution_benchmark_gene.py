"""Thin GeneLoop task-policy experiment over the shared benchmark task host.

Actual model sessions and official scoring belong to BenchmarkHost. Candidate
policies reuse the original strategy sidecar, admission, Feedback and native
skill discovery. Python helpers use the existing Script native material path.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .capability_contract import create_capability_snapshot, validate_capability_snapshot
from .capability_evolution_agent import strategy_handler
from .capability_evolution_investigation import run_investigation
from .capability_feedback import CapabilityFeedback, execution_cost, file_ref, verify
from .capability_improvement import save
from .capability_investigation import Investigation
from .capability_strategy import strategy_context, strategy_ref
from .evolution_benchmark import (
    benchmark_evaluation_role, inspect_benchmark, observation_input_fingerprint, validation_dataset_splits,
)


OWNER = 'overnight-research'


def _quality(trial, threshold):
    evaluation = trial.get('evaluation', {})
    raw = evaluation.get('reward')
    amount = None
    if raw is not None and not isinstance(raw, bool):
        try:
            value = Decimal(str(raw))
            amount = value if value.is_finite() else None
        except InvalidOperation:
            pass
    verified = evaluation.get('status') == 'evaluated'
    scoreable = trial.get('score') is not None
    return {'raw_reward': raw, 'quality_threshold': str(threshold),
            'verifier_succeeded': verified,
            'trial_scoreable': scoreable,
            'full_quality': amount >= threshold if amount is not None and verified and scoreable else None,
            'paper_positive_reward_pass': amount > 0 if amount is not None and verified and scoreable else None}


def _tasks(values, minimum=1):
    if (not isinstance(values, (list, tuple)) or len(values) < minimum
            or any(not isinstance(value, str) or not value.strip() for value in values)
            or len(set(values)) != len(values)):
        raise ValueError('gene_benchmark_task_partition_invalid')
    return list(values)


def _skill(strategy, directory):
    """Expose the original versioned policy as a standard discoverable package."""
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    name = 'geneloop-policy-' + strategy['revision_sha256'][:16]
    text = ('---\nname: ' + name + '\ndescription: '
            + json.dumps(strategy['applicability'], ensure_ascii=False) + '\n---\n\n'
            '# Applicability\n\n' + strategy['applicability'] + '\n\n'
            '# Decision method\n\n' + strategy['decision_policy'] + '\n\n'
            '# Capability references\n\n'
            + json.dumps(strategy['capability_refs'], ensure_ascii=False) + '\n')
    (directory / 'SKILL.md').write_text(text, encoding='utf-8')
    save(directory / 'strategy.json', strategy)
    return directory


def _native_helper_proposal(proposal):
    if not isinstance(proposal, dict):
        raise ValueError('gene_benchmark_capability_proposal_invalid: expected an object')
    if set(proposal) == {'source', 'description', 'example_evidence_ids'}:
        return {'program': {'source': proposal['source'], 'description': proposal['description'],
                            'mode': 'json', 'interface': 'function_v1'},
                'example_evidence_ids': proposal['example_evidence_ids']}
    if set(proposal) == {'program', 'example_evidence_ids'} and isinstance(proposal['program'], dict):
        program = {**proposal['program']}
        program.setdefault('mode', 'json')
        program.setdefault('interface', 'function_v1')
        return {**proposal, 'program': program}
    raise ValueError('gene_benchmark_capability_proposal_invalid: expected proposal fields '
                     'source, description, example_evidence_ids; mode=json and '
                     'interface=function_v1 are supplied by the host. Received fields=' + str(sorted(proposal)))


def _example_files(candidate, context, investigation):
    proposal = _native_helper_proposal(candidate['proposal'])
    if (not isinstance(proposal['example_evidence_ids'], list)
            or len(proposal['example_evidence_ids']) < 2
            or any(not isinstance(value, str) for value in proposal['example_evidence_ids'])
            or len(set(proposal['example_evidence_ids'])) != len(proposal['example_evidence_ids'])):
        raise ValueError('gene_benchmark_capability_proposal_invalid')
    available = {}
    for row in context['observations']:
        for reference in row['evidence']:
            if Path(reference['path']).suffix != '.json':
                continue
            try:
                index = json.loads(verify(reference))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if (not isinstance(index, dict) or index.get('format') != 'skillsbench_artifact_index_v1'
                    or index.get('phase') != 'pre_verification'):
                continue
            for source in index.get('files', {}).values():
                identifier = 'evidence_' + source['sha256']
                if source in row['evidence'] and identifier in investigation.evidence:
                    verify(source)
                    item = available.setdefault(identifier, {'reference': source, 'source_identities': set()})
                    item['source_identities'].add(row['source_identity'])
    selected = []
    for identifier in proposal['example_evidence_ids']:
        if identifier not in available:
            raise ValueError('gene_benchmark_example_not_in_selected_pre_verification_files')
        item = available[identifier]
        selected.append({'evidence_id': identifier, 'reference': item['reference'],
                         'source_identities': sorted(item['source_identities'])})
    # The native learner certifies only the first two prepared inputs.
    if len({source for item in selected[:2] for source in item['source_identities']}) < 2:
        raise ValueError('gene_benchmark_example_independent_sources_required')
    return selected


def _recursive_learning(runs, directory, *, materials=None, publish=None, prior_observations=()):
    from .capability_motif_learning import _checked
    groups = {}
    invalid_sources = []
    duplicates = []
    combined = []
    for reference in prior_observations:
        try:
            row = inspect_benchmark(reference, OWNER)
            trajectory = row.get('capability_trajectory')
            if trajectory is None:
                continue
            if trajectory not in row['evidence']:
                raise ValueError('recursive_prior_trajectory_not_indexed')
            state = row.get('decision_context', {}).get('state', {})
            if state.get('split') not in ('training', 'test'):
                raise ValueError('recursive_prior_original_split_required')
            projection = row.get('capability_input_projection')
            if projection is None:
                projection = next((ref for ref in row['evidence']
                    if Path(ref['path']).name == 'capability-input-projection.json'), None)
            if projection is None or projection not in row['evidence']:
                raise ValueError('recursive_prior_input_projection_not_indexed')
            combined.append({'split': state['split'], 'capability_trajectory': trajectory,
                             'capability_input_projection': projection,
                             'evaluation_role': benchmark_evaluation_role(row),
                             'input_fingerprint': observation_input_fingerprint(row),
                             'source_identity': row['source_identity'], 'observation': reference, 'historical': True})
        except Exception as error:
            invalid_sources.append({'evidence': reference, 'reason': type(error).__name__ + ':' + str(error)})
    combined.extend(runs)
    # Older records retain their original split semantics and historical scope.
    combined.sort(key=lambda trial: benchmark_evaluation_role(trial) != 'final')
    for trial in combined:
        reference = trial.get('capability_trajectory')
        if reference is None:
            continue
        try:
            trace = json.loads(verify(reference))
            trace = _checked(trace, trace['snapshot']['owner'])
            if trial.get('split') not in ('training', 'test'):
                raise ValueError('recursive_original_split_required')
            projection = trial.get('capability_input_projection')
            if projection is not None:
                value = json.loads(verify(projection))
                if (value.get('snapshot') != trace['snapshot'] or value.get('task_id') != trace['task_id']
                        or value.get('task_fingerprint') != trace['task_fingerprint']
                        or value.get('trace_inputs') != trace['task_input'] or value.get('calls') != trace['calls']):
                    raise ValueError('recursive_original_projection_changed')
            source = trial.get('source_identity', trace['task_fingerprint'])
            fingerprint = trial.get('input_fingerprint')
            if trial.get('observation') is not None:
                row = inspect_benchmark(trial['observation'], OWNER)
                source = row['source_identity']
                fingerprint = observation_input_fingerprint(row)
                if trace['owner'] != row['owner']:
                    raise ValueError('recursive_original_owner_changed')
                if row.get('capability_trajectory') != reference:
                    raise ValueError('recursive_observation_trajectory_changed')
            group = groups.setdefault(trace['snapshot']['digest'], {
                'training': [], 'heldout': [], 'evidence': [], 'sources': set(), 'fingerprints': set(), 'refs': {}, 'historical': [], 'historical_heldout': []})
            split = 'heldout' if benchmark_evaluation_role(trial) == 'final' else 'training'
            source_key = 'input:' + fingerprint if fingerprint else 'legacy-source:' + source
            if source_key in group['sources'] or trace['task_fingerprint'] in group['fingerprints']:
                duplicates.append({'evidence': reference, 'source_identity': source, 'split': trial['split'],
                                   'reason': 'original_source_or_fingerprint_already_counted'})
                continue
            group['sources'].add(source_key)
            group['fingerprints'].add(trace['task_fingerprint'])
            group[split].append(trace)
            group['refs'][trace['digest']] = reference
            if trial.get('historical'):
                group['historical'].append(reference)
                if split == 'heldout':
                    group['historical_heldout'].append(reference)
        except Exception as error:
            invalid_sources.append({'evidence': reference, 'reason': type(error).__name__ + ':' + str(error)})
    for group in groups.values():
        group['evidence'] = [group['refs'][trace['digest']] for trace in [*group['training'], *group['heldout']]]
    eligible = [group for group in groups.values() if len(group['training']) >= 2 and group['heldout']]
    if not eligible:
        return {'status': 'pending', 'reason': 'two_training_and_one_heldout_native_call_traces_required',
                'invalid_sources': invalid_sources, 'duplicates': duplicates,
                'groups': [{'snapshot_sha256': digest, 'training': len(group['training']),
                            'heldout': len(group['heldout'])} for digest, group in groups.items()]}
    outcomes = []
    for group in sorted(eligible, key=lambda item: item['training'][0]['snapshot']['digest']):
        folder = Path(directory) if len(eligible) == 1 else Path(directory) / (
            'recursive-group-' + group['training'][0]['snapshot']['digest'])
        folder.mkdir(parents=True, exist_ok=True)
        outcomes.append(_learn_recursive_group(group, folder, materials=materials, publish=publish))
    if len(outcomes) == 1:
        return {**outcomes[0], 'invalid_sources': invalid_sources, 'duplicates': duplicates}
    status = next(status for status in ('published', 'candidates', 'pending', 'failed', 'no_candidates')
                  if any(outcome['status'] == status for outcome in outcomes))
    return {'status': status, 'groups': outcomes, 'invalid_sources': invalid_sources, 'duplicates': duplicates,
            'evidence': [reference for group in eligible for reference in group['evidence']]}


def _learn_recursive_group(group, directory, *, materials, publish):
    from .capability_motif_learning import learn_capability_motifs
    try:
        learned = learn_capability_motifs(group['training'], group['heldout'], group['training'][0]['snapshot'])
        save(directory / 'recursive-learning.json', learned)
        result = {'status': 'candidates' if learned['candidates'] else 'no_candidates',
                'result': file_ref(directory / 'recursive-learning.json'), 'evidence': group['evidence'],
                'publication': 'pending_independent_original_store_publication',
                'snapshot_sha256': group['training'][0]['snapshot']['digest'],
                'certification_scope': 'historical_source_equivalence' if group['historical'] else 'source_equivalence',
                'independent_quality': 'pending_fresh_semantic_task_evaluation',
                'historical_evidence': group['historical'],
                'previously_disclosed_heldout': group['historical_heldout']}
        if materials is not None and learned['candidates']:
            if publish is None:
                from .benchmark_capability_publication import publish_recursive_candidate
                publish = publish_recursive_candidate
            publications = []
            for index, candidate in enumerate(learned['candidates']):
                try:
                    outcome = publish(candidate, group['evidence'], materials=materials,
                                      output=directory / ('recursive-publication-' + str(index)))
                except Exception as error:
                    outcome = {'status': 'failed', 'reason': type(error).__name__ + ':' + str(error)}
                publications.append(outcome)
            result['publications'] = publications
            result['status'] = ('published' if any(row['status'] == 'published' for row in publications)
                                else 'failed' if all(row['status'] == 'failed' for row in publications) else 'pending')
            result['publication'] = result['status']
            result['followup'] = 'pending_actual_later_task_consumption'
        return result
    except Exception as error:
        return {'status': 'pending', 'reason': type(error).__name__ + ':' + str(error),
                'evidence': group['evidence']}


def run_gene_benchmark(host, *, development_tasks, validation_tasks, test_tasks,
                       output, scope='skillsbench', snapshot=None, prior_selection=None,
                       prior_observations=(), history=(), feedback_directory=None, quality_threshold='1',
                       validation_splits=None):
    """Run one generation, then freeze and test its selection exactly once.

    Returned continuation evidence is available to a later generation. Reusing
    canonical task IDs after seeing their outcomes must be reported as adaptive
    replay by that caller rather than independent final-test evidence.
    """
    prior_observations = list(prior_observations)
    development = _tasks(development_tasks, minimum=0 if prior_observations else 2)
    validation = _tasks(validation_tasks)
    tests = _tasks(test_tasks)
    validation_splits = validation_dataset_splits(validation_splits if validation_splits is not None
                                                 else getattr(host, 'validation_splits', None))
    if isinstance(quality_threshold, bool):
        raise ValueError('gene_benchmark_quality_threshold_invalid')
    try:
        threshold = Decimal(str(quality_threshold))
    except InvalidOperation as error:
        raise ValueError('gene_benchmark_quality_threshold_invalid') from error
    if not threshold.is_finite() or threshold <= 0:
        raise ValueError('gene_benchmark_quality_threshold_invalid')
    if any(validation_splits.get(task, 'training') == 'training'
           for task in set(development).intersection(validation)):
        raise ValueError('gene_benchmark_development_validation_overlap')
    materials = getattr(host, 'materials', None)
    if materials is not None and materials.owner != OWNER:
        raise ValueError('gene_benchmark_material_owner_changed')
    material_configuration = None
    if materials is not None and getattr(materials, 'directory', None) is not None:
        material_directory = Path(materials.directory).resolve()
        material_configuration = {'owner': materials.owner, 'directory': str(material_directory),
            'publication_store': str(Path(getattr(materials, 'publication_store',
                                                  material_directory / 'publication-store')).resolve())}
    initial = materials.catalog()['snapshot'] if materials is not None else create_capability_snapshot(OWNER, [], [])
    snapshot = validate_capability_snapshot(snapshot if snapshot is not None else initial, OWNER)
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError('gene_benchmark_scope_required')
    directory = Path(output)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    feedback_root = Path(feedback_directory) if feedback_directory is not None else directory / 'feedback'
    feedback = CapabilityFeedback(feedback_root, OWNER)
    prior_history = list(history)
    observations = list(prior_observations)
    observed_canonical = set()
    for reference in observations:
        row = inspect_benchmark(reference, OWNER)
        state = row.get('decision_context', {}).get('state', {})
        if isinstance(state, dict) and state.get('split') == 'test':
            observed_canonical.add(state.get('task_id'))
    if observed_canonical.intersection(tests):
        raise ValueError('gene_benchmark_final_test_already_observed')
    selected = prior_selection
    packages = {}
    if selected is not None:
        strategy_context(selected, snapshot, target='task', scope=scope, feedback=feedback)
        inherited = json.loads(verify(selected['strategy']))
        packages[inherited['id']] = _skill(inherited, directory / 'inherited-skill')
        prior_history.extend([selected['strategy'], selected['evaluation']])
    result = {'format': 'gene_benchmark_generation_v1', 'owner': OWNER, 'scope': scope,
              'status': 'running', 'development': [], 'validation': [], 'test': [],
              'quality_threshold': str(threshold),
              'selection': None, 'selection_rule': 'latest_independently_admitted_candidate',
              'actual_adoption': None, 'measured_net_benefit': None,
              'capability_acquisitions': [], 'snapshot_before': snapshot,
              'pending': {'construction_strategy': 'real_builder_adapter_unavailable',
                          'capability': 'native_certification_adapter_unavailable',
                          'boundary': 'supported_runtime_trace_adapter_unavailable'}}
    save(directory / 'effective.json', {'owner': OWNER, 'scope': scope,
         'snapshot': snapshot, 'material_configuration': material_configuration,
         'development_tasks': development, 'validation_tasks': validation,
         'validation_splits': validation_splits,
         'test_tasks': tests, 'prior_observations': observations, 'history': prior_history,
         'quality_threshold': str(threshold),
         'budget_usd': None, 'max_requests': None, 'production_enabled': False})
    validations = []
    native_records = []

    def construction_history():
        # File names and source groups are host-owned. Model strings or paths
        # embedded in proposals never authorize further evidence reads.
        sources = {'investigation': [], 'validation': [], 'native': native_records,
                   'recursive': [], 'model_session': []}
        for path in sorted((directory / 'investigation').glob('*.json')):
            sources['investigation'].append(file_ref(path))
        for path in sorted(directory.glob('validation-*/result.json')):
            sources['validation'].append(file_ref(path))
        for pattern in ('recursive-learning.json', 'recursive-learning-status.json',
                        'recursive-publication-*/result.json', 'recursive-group-*/recursive-learning.json',
                        'recursive-group-*/recursive-publication-*/result.json'):
            sources['recursive'].extend(file_ref(path) for path in sorted(directory.glob(pattern)))
        inquiry = result.get('investigation', {})
        agent = inquiry.get('agent_result', {})
        session = agent.get('directory')
        if session is not None:
            # This directory comes from the trusted Harness return value.
            for name in ('result.json', 'request.json', 'effective.json', 'requests.jsonl',
                         'events.jsonl', 'answer.txt', 'cancel-evidence.json'):
                path = Path(session) / name
                if path.is_file():
                    sources['model_session'].append(file_ref(path))
        manifest = {'format': 'gene_benchmark_construction_feedback_v1', 'owner': OWNER,
            'scope': scope, 'origin': 'trusted_benchmark_host',
            'status': inquiry.get('status', result['status']),
            'submissions': [{'status': row.get('status'), 'kind': row.get('candidate', {}).get('kind'),
                             'reason': row.get('reason'), 'outcome_status': row.get('outcome', {}).get('status')}
                            for row in inquiry.get('submissions', [])],
            'finish': inquiry.get('finish'), 'sources': sources,
            'model_cost': {key: agent.get(key) for key in ('provider_requests', 'observed_model_usd',
                                                         'observed_model_usd_decimal')},
            'cost_scope': 'Shared Evolution investigation and proposal session only; not per capability or task. '
                          'Independent validation task costs remain in their observations. '
                          'Native certification and non-model costs are unknown unless separately recorded.',
            'native_certification_cost_usd': None, 'measured_creation_value': None}
        save(directory / 'construction-feedback.json', manifest)
        return file_ref(directory / 'construction-feedback.json')

    try:
        prior_package = packages.get(json.loads(verify(selected['strategy']))['id']) if selected else None
        for task_id in development:
            trial = host.trial(task_id, split='training', skill_directory=prior_package,
                               label='gene-development', evaluation_role='development')
            trial['quality_assessment'] = _quality(trial, threshold)
            result['development'].append(trial)
            observations.append(trial['observation'])
        development_refs = list(observations)
        source_identities = {inspect_benchmark(reference, OWNER)['source_identity'] for reference in development_refs}
        if len(source_identities) < 2:
            raise ValueError('gene_benchmark_independent_development_required')
        development_inputs = {observation_input_fingerprint(inspect_benchmark(reference, OWNER))
                              for reference in development_refs}
        development_inputs.discard(None)
        validation_inputs = set()

        def evaluate(strategy):
            folder = directory / ('validation-' + str(len(validations)))
            package = _skill(strategy, folder / 'skill')
            runs = []
            evaluation = {'strategy': strategy_ref(strategy), 'runs': runs, 'skill_directory': str(package)}
            validations.append(evaluation)
            checks = []
            for task_id in validation:
                dataset = validation_splits.get(task_id, 'training')
                if hasattr(host, 'input_fingerprint') and host.input_fingerprint(task_id, dataset) in development_inputs:
                    raise ValueError('gene_benchmark_validation_input_overlap')
                trial = host.trial(task_id, split=dataset, skill_directory=package,
                                   label='gene-independent-validation', evaluation_role='validation')
                runs.append(trial)
                trial['quality_assessment'] = _quality(trial, threshold)
                actual = inspect_benchmark(trial['observation'], OWNER)
                fingerprint = observation_input_fingerprint(actual)
                if fingerprint is None:
                    raise ValueError('gene_benchmark_validation_input_unknown')
                if fingerprint in development_inputs:
                    raise ValueError('gene_benchmark_validation_input_overlap')
                validation_inputs.add(fingerprint)
                passed = trial['quality_assessment']['full_quality'] is True
                activated = trial.get('skill_activated') is True
                checks.extend([{'id': 'official-full-quality-' + task_id,
                                'status': 'passed' if passed else 'failed'},
                               {'id': 'native-activation-' + task_id,
                                'status': 'passed' if activated else 'failed'}])
            verdict = {'passed': all(check['status'] == 'passed' for check in checks),
                       'checks': checks, 'training_sources': development_refs,
                       'heldout_sources': [trial['observation'] for trial in runs],
                       'evidence': [trial['record'] for trial in runs]}
            evaluation['verdict'] = verdict
            save(folder / 'result.json', evaluation)
            evaluation['record'] = file_ref(folder / 'result.json')
            packages[strategy['id']] = package
            return verdict

        admit = strategy_handler(snapshot=snapshot, feedback=feedback, target='task', scope=scope,
                                 evaluate=evaluate, parent_selection=prior_selection)

        def validation_feedback(start):
            recent = validations[start:]
            references = []
            cards = []
            for evaluation in recent:
                if evaluation.get('record') is not None:
                    references.append(evaluation['record'])
                for trial in evaluation['runs']:
                    actual = inspect_benchmark(trial['observation'], OWNER)
                    references.extend([trial['record'], trial['observation'], *actual['evidence']])
                    cards.append({'task_id': trial['task_id'], 'split': trial['split'],
                                  'verifier_status': trial.get('evaluation', {}).get('status'),
                                  'quality_assessment': trial.get('quality_assessment'),
                                  'skill_activated': trial.get('skill_activated'),
                                  'record_evidence_id': 'evidence_' + trial['record']['sha256'],
                                  'observation_evidence_id': 'evidence_' + trial['observation']['sha256'],
                                  'diagnostic_evidence_ids': actual.get('decision_context', {}).get('outcome', {}).get(
                                      'diagnostic_evidence_ids', {})})
            unique = {(ref['path'], ref['sha256']): ref for ref in references}
            for reference in unique.values():
                verify(reference)
            return {'checks': [check for row in recent for check in row.get('verdict', {}).get('checks', [])],
                    'validation_feedback': cards, 'evidence_refs': list(unique.values())}

        def task_strategy(candidate, context, candidate_directory):
            nonlocal selected
            proposed_refs = candidate['proposal'].get('capability_refs', [])
            if materials is not None:
                latest = materials.catalog()['snapshot']
                if any(ref not in snapshot['roots'] and ref in latest['roots'] for ref in proposed_refs):
                    return {'status': 'pending', 'reason': 'new_material_requires_next_generation_snapshot',
                            'snapshot_sha256': latest['digest']}
            start = len(validations)
            try:
                outcome = admit(candidate, context, candidate_directory)
            except Exception as error:
                if not any(row['runs'] for row in validations[start:]):
                    raise
                return {'status': 'rejected', 'reason': type(error).__name__ + ':' + str(error),
                        **validation_feedback(start)}
            selected = outcome['selection']
            feedback_result = validation_feedback(start)
            feedback_result['evidence_refs'].extend(outcome['selection'].values())
            return {**outcome, **feedback_result}

        entries = [{'split': 'training', 'scope': scope, 'evidence': reference}
                   for reference in development_refs]
        investigation = Investigation(snapshot, entries, scope, directory / 'evidence',
            inspector=inspect_benchmark, history=prior_history,
            objective='Minimize complete future execution and construction cost at the same task quality. '
                      'Use actual cross-task evidence to improve abstractions and make later capability creation easier. '
                      'Count investigation, learning, evaluation, repairs and failures, preserving unknown costs.')
        handlers = {'task_strategy': task_strategy}
        if materials is not None:
            result['pending'].pop('capability')
            def capability(candidate, context, candidate_directory):
                selected_files = _example_files(candidate, context, investigation)
                candidate_directory.mkdir(parents=True, mode=0o700, exist_ok=False)
                save(candidate_directory / 'candidate.json', {'candidate': candidate,
                    'example_provenance': selected_files, 'origin': 'host_resolution_of_model_selected_file_ids'})
                acquisition_root = materials.directory / 'acquisitions' if hasattr(materials, 'directory') else None
                prior_native = set(acquisition_root.iterdir()) if acquisition_root is not None and acquisition_root.exists() else set()
                try:
                    acquired = materials.acquire(_native_helper_proposal(candidate['proposal'])['program'],
                        [item['reference'] for item in selected_files],
                        file_ref(candidate_directory / 'candidate.json'), context['scope'])
                finally:
                    if acquisition_root is not None and acquisition_root.exists():
                        for folder in sorted(set(acquisition_root.iterdir()) - prior_native):
                            for name in ('request.json', 'result.json', 'preparation.json',
                                         'native/observations.json', 'native/certification.json'):
                                path = folder / name
                                if path.is_file():
                                    native_records.append(file_ref(path))
                native_records.extend(acquired.get('native_evidence', []))
                result['capability_acquisitions'].append(acquired)
                return {**acquired, 'availability': 'next_task_material_snapshot',
                        'semantic_task_quality': 'pending_actual_independent_task_evaluation'}
            handlers['capability'] = capability

        def call_agent(request, dispatch):
            if materials is not None:
                request = {**request, 'prompt': request['prompt'] + '\nA native Python helper backend is available. '
                    'For kind capability, proposal is exactly {source:Python_source, '
                    'description:text, example_evidence_ids:[indexed_file_evidence_id,...]}. '
                    'The host supplies the fixed JSON/function_v1 protocol. Implement def run(value). '
                    'Select at least two actual pre-verification artifact input files from independent '
                    'inspected experiences. Files are mechanically wrapped as {data:parsed_JSON} or '
                    '{text:UTF8_text}. The original Script compiler and sandbox independently check '
                    'source equivalence; later task quality is evaluated separately. '
                    'Newly registered abilities enter the next task snapshot; using their references '
                    'in a strategy requires the next Evolution generation.'}
            return host.agent(request, dispatch)

        result['investigation'] = run_investigation(investigation, call_agent=call_agent,
            handlers=handlers, output=directory / 'investigation')
        result['validation'] = validations
        package = None
        if selected is not None:
            policy = strategy_context(selected, snapshot, target='task', scope=scope, feedback=feedback)
            strategy = json.loads(verify(selected['strategy']))
            package = packages[strategy['id']]
            save(directory / 'selection.json', selected)
            result['selection'] = selected
            result['skill_directory'] = str(package)
            prior_history.extend([selected['strategy'], selected['evaluation'], file_ref(directory / 'selection.json')])
            result['selected_subject'] = policy['strategy']
        for task_id in tests:
            if hasattr(host, 'input_fingerprint'):
                fingerprint = host.input_fingerprint(task_id, 'test')
                if fingerprint is None or fingerprint in development_inputs | validation_inputs:
                    raise ValueError('gene_benchmark_final_test_input_already_observed')
            trial = host.trial(task_id, split='test', skill_directory=package,
                               label='gene-frozen-test', evaluation_role='final')
            trial['quality_assessment'] = _quality(trial, threshold)
            result['test'].append(trial)
            observations.append(trial['observation'])
            if selected is not None:
                quality = trial['quality_assessment']['full_quality']
                status = 'passed' if quality is True else 'failed' if quality is False else 'unknown'
                feedback.observe(stage='execution', subject=result['selected_subject'], scope=scope,
                    status=status, cost=execution_cost(trial.get('model')),
                    evidence=[selected['strategy'], selected['evaluation'], trial['record'], trial['observation']])
        observations.extend(trial['observation'] for evaluation in validations for trial in evaluation['runs'])
        result['recursive_learning'] = _recursive_learning(
            [*result['development'], *[trial for evaluation in validations for trial in evaluation['runs']],
             *result['test']], directory, materials=materials, prior_observations=prior_observations)
        save(directory / 'recursive-learning-status.json', result['recursive_learning'])
        next_snapshot = materials.catalog()['snapshot'] if materials is not None else snapshot
        result['snapshot_after'] = next_snapshot
        prior_history.append(construction_history())
        save(directory / 'continuation.json', {
            'format': 'gene_benchmark_continuation_v1', 'owner': OWNER, 'scope': scope,
            'snapshot': next_snapshot, 'material_configuration': material_configuration,
            'selection': selected, 'feedback_directory': str(feedback_root),
            'quality_threshold': str(threshold),
            'entries': [{'split': 'training', 'scope': scope, 'evidence': reference} for reference in observations],
            'history': prior_history,
            'observed_canonical_tasks': tests,
            'evaluation_rule': 'Use fresh task IDs for later independent final evaluation; repeated canonical tasks are adaptive replay.'})
        result.update(status='completed', continuation=file_ref(directory / 'continuation.json'),
                      actual_adoption={'strategy_read_trials': sum(trial.get('skill_activated') is True
                                                                 for trial in result['test']),
                                       'tested_trials': len(result['test']),
                                       'semantic_effect': 'requires inspection of original task actions'})
        return result
    except Exception as error:
        result.update(status='failed', error=type(error).__name__ + ':' + str(error))
        raise
    finally:
        result['validation'] = validations
        result['selection'] = selected
        save(directory / 'result.json', result)
