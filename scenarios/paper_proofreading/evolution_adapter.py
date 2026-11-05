"""Paper evidence and task evaluation adapter for the shared Evolution cycle."""
from __future__ import annotations

import copy
import json
from decimal import Decimal, localcontext
from pathlib import Path

from src.adapters.capability_contract import create_capability_snapshot
from src.adapters.capability_feedback import CapabilityFeedback, file_ref, verify
from src.adapters.capability_improvement import save
from src.adapters.capability_investigation import Investigation
from src.adapters.capability_evolution_inputs import load_builder_input_manifest
from src.adapters.capability_decision_evidence import inspect_decision
from src.adapters.capability_evolution_agent import strategy_handler
from src.adapters.evolution_benchmark import BenchmarkHost, inspect_benchmark
from src.adapters.evolution_benchmark_gene import _skill
from src.adapters.rsi_quality import compare_research_outcomes
from src.adapters.skillsbench_trial import task_manifest
from .evolution_history import index_history, inspect_history, OWNER, SCOPE

ROOT = Path(__file__).resolve().parents[2]

SELECTION_RULE = 'eligible_frozen_paired_gain_then_quality_descending_cost_ascending_sha256'


def select_pilot_candidate(admitted, validations, policy_ref):
    """Choose from observed behavior and pre-frozen quality/cost criteria."""
    ranked, excluded = [], []
    for submission in admitted:
        selection = submission['outcome']['selection']
        strategy = json.loads(verify(selection['strategy']))
        evaluation_receipt = json.loads(verify(selection['evaluation']))
        row = next((item for item in validations if item['strategy_sha256'] == strategy['revision_sha256']
                    and item['verdict'] == evaluation_receipt.get('verdict')), None)
        if row is None or row['semantic_adoption'] is not True or not row['verdict']['passed']:
            excluded.append({'strategy': strategy['id'], 'reason': 'quality_or_observable_behavior_not_passed'})
            continue
        pairs = list(zip(row['runs'][::2], row['runs'][1::2]))
        def aggregate(arm):
            trials = [pair[arm] for pair in pairs]
            if not trials or any(trial.get('score') is None or
                    trial.get('model', {}).get('observed_model_usd') is None for trial in trials):
                return {'quality': None, 'cost_usd': None, 'samples': len(trials)}
            with localcontext() as context:
                context.prec = 1024
                return {'quality': str(sum((Decimal(str(trial['score'])) for trial in trials), Decimal(0)) / len(trials)),
                        'cost_usd': str(sum((Decimal(str(trial['model']['observed_model_usd'])) for trial in trials), Decimal(0))),
                        'samples': len(trials)}
        control, candidate = aggregate(0), aggregate(1)
        comparison = compare_research_outcomes(control, candidate, policy_ref)
        if comparison['publication'] != 'eligible_scoped':
            excluded.append({'strategy': strategy['id'], 'reason': 'frozen_gain_not_eligible', 'comparison': comparison})
            continue
        ranked.append({'selection': selection, 'strategy_sha256': strategy['revision_sha256'],
                       'quality': candidate['quality'], 'task_model_cost_usd': candidate['cost_usd'],
                       'comparison': comparison})
    ranked.sort(key=lambda item: (-Decimal(item['quality']), Decimal(item['task_model_cost_usd']), item['strategy_sha256']))
    return {'format': 'capability_evolution_candidate_selection_v1',
            'owner': OWNER, 'rule': SELECTION_RULE, 'policy': policy_ref,
            'status': 'selected' if ranked else 'retain_current',
            'selection': ranked[0]['selection'] if ranked else None,
            'ranking': ranked, 'excluded': excluded,
            'scope': 'isolated_followup_only; full_research_publication_pending'}


def behavior_rollout(trial, owner):
    from src.adapters.evolution_benchmark import inspect_benchmark
    observation = inspect_benchmark(trial['observation'], owner)
    actions = [ref for ref in observation['evidence'] if Path(ref['path']).name in ('tool-calls.jsonl', 'events.jsonl')]
    return {'record': trial['record'], 'observation': trial['observation'],
            'evidence_refs': observation['evidence'], 'behavior_evidence_refs': actions}



class PaperEvolutionAdapter:
    """Scene data, independent task scoring and supported product receivers."""

    def __init__(self, history_ref, policy_ref, output, *, input_manifest=None,
                 require_builder_evidence=False, investigation_history=()):
        if require_builder_evidence and input_manifest is None:
            raise ValueError('paper_builder_input_audit_requires_manifest')
        self.history_ref, self.policy_ref = history_ref, policy_ref
        self.output = Path(output)
        self.root = Path(history_ref['path']).resolve().parent / 'evaluation-tasks'
        self.input_manifest = input_manifest
        self.require_builder_evidence = require_builder_evidence
        self.investigation_history = list(investigation_history)

    def load_experiences(self):
        history_ref, policy_ref, output = self.history_ref, self.policy_ref, self.output
        policy = json.loads(verify(policy_ref))
        behavior_policy = file_ref(ROOT / 'config/evolution-task-strategy-review.txt')
        # Preflight policy with neutral diagnostic values, before any model request.
        compare_research_outcomes({'quality': 1, 'cost_usd': '0', 'samples': 1},
                                  {'quality': 1, 'cost_usd': '0', 'samples': 1}, policy_ref)
        entries, sealed = index_history(history_ref, output / 'projection')
        supplied = None
        if self.input_manifest:
            input_manifest_ref = self.input_manifest
            supplied = load_builder_input_manifest(input_manifest_ref, expected_owner=OWNER, expected_scope=SCOPE)
            entries.extend(supplied['entries'])
            snapshot = supplied['snapshot']
        else:
            input_manifest_ref = None
            snapshot = create_capability_snapshot(OWNER, [], [])
        construction_refs = ({item['evidence']['sha256'] for item in supplied['entries']}
                             if supplied else set())
        def inspect_experience(reference, owner):
            if reference['sha256'] in construction_refs:
                return inspect_decision(reference, owner)
            return inspect_history(reference, owner)
        investigation = Investigation(snapshot, entries, SCOPE, output / 'investigation-input',
            inspector=inspect_experience, sealed_evidence=sealed['evaluation'],
            development_evidence=sealed['development'], history=[policy_ref, *self.investigation_history],
            objective='Investigate these real historical task experiences and current available materials. '
                      'Autonomously choose whether any change would improve later work; preserving the current method is valid.')

        self.policy = policy
        self.behavior_policy = behavior_policy
        self.supplied = supplied
        self.input_manifest_ref = input_manifest_ref
        self.snapshot = snapshot
        self.entries = entries
        self.inspect_experience = inspect_experience
        self.investigation = investigation
        return investigation

    def effective_config(self, *, max_tool_calls, timeout_seconds):
        history_ref, policy_ref = self.history_ref, self.policy_ref
        supplied, snapshot, policy = self.supplied, self.snapshot, self.policy
        input_manifest_ref, behavior_policy = self.input_manifest_ref, self.behavior_policy
        root = self.root
        task_snapshots = {role: [task_manifest(path, task_id=path.name,
            split='test' if role == 'evaluation' else 'training',
            source_version='original-five-paper-historical-replay')
            for path in sorted((root / role).iterdir())] for role in ('development', 'evaluation')}
        frozen = {'history': history_ref, 'policy': policy_ref, 'policy_values': policy,
                  'investigation_history': self.investigation_history,
                  'evolution_input_manifest': input_manifest_ref,
                  'focus_capability': supplied['focus_capability'] if supplied else None,
                  'builder_observation_count': supplied['independent_builder_sources'] if supplied else 0,
                  'builder_source_independence_basis': supplied['source_independence_basis'] if supplied else None,
                  'builder_exposure_basis': supplied['exposure_basis'] if supplied else None,
                  'input_exposure': supplied['exposure'] if supplied else 'paper_history_only',
                  'experiment_scope': 'task_strategy_pilot',
                  'creation_efficiency_evaluation': 'pending_real_builder_evaluator',
                  'builder_evidence_required': self.require_builder_evidence,
                  'behavior_review_policy': behavior_policy,
                  'behavior_review_timeout_seconds': 300, 'behavior_review_read_limit': 64,
                  'candidate_selection_rule': SELECTION_RULE,
                  'snapshot': snapshot, 'model': 'deepseek-flash', 'reasoning_effort': 'off',
                  'max_tokens': 393216, 'budget_usd': None, 'max_requests': None,
                  'max_investigation_tool_calls': max_tool_calls, 'timeout_seconds': timeout_seconds,
                  'evaluation_task_snapshots': task_snapshots, 'initial_strategies': [],
                  'max_root_candidates': 2, 'max_repairs_per_root': 2,
                  'source_code': file_ref(ROOT / '.research-code-snapshot.json')
                                 if (ROOT / '.research-code-snapshot.json').is_file() else None,
                  'data_role': 'historically_exposed_replay', 'supported_receivers': ['task_strategy'],
                  'production_default_changed': False, 'approval_scope': 'isolated_evaluation_only',
                  'skeleton_scope': 'original calls and boundaries; unknown parameter dependencies retained'}

        return frozen

    def build_receivers(self, investigation, gate):
        root, output, entries, snapshot = self.root, self.output, self.entries, self.snapshot
        policy_ref, behavior_policy = self.policy_ref, self.behavior_policy
        validation = sorted(path.name for path in (root / 'development').iterdir())
        evaluation = sorted(path.name for path in (root / 'evaluation').iterdir())
        feedback = CapabilityFeedback(output / 'feedback', OWNER)
        validations = []
        active_hypothesis = {}
        baseline_skill = output / 'review-control'
        baseline_skill.mkdir()
        (baseline_skill / 'SKILL.md').write_text('The paired control receives no evolved task strategy.\n')
        host = BenchmarkHost(root / 'development', root / 'evaluation', output / 'host',
                             source_version='original-five-paper-historical-replay', gate=gate, owner=OWNER)
        initial_costs = gate.state.reserved_usd
        def evaluate(strategy):
            verify(policy_ref)
            directory = output / ('candidate-evaluation-' + str(len(validations)))
            package = _skill(strategy, directory / 'skill')
            runs, comparisons, checks, behavior_reviews = [], [], [], []
            for task_id in validation:
                control = host.trial(task_id, label='matched-control', evaluation_role='validation')
                candidate = host.trial(task_id, skill_directory=package, label='isolated-candidate',
                                       evaluation_role='validation')
                runs.extend([control, candidate])
                def outcome(trial):
                    return {'quality': trial.get('score'), 'cost_usd': trial.get('model', {}).get('observed_model_usd'),
                            'samples': 1}
                comparison = compare_research_outcomes(outcome(control), outcome(candidate), policy_ref)
                comparison['execution_only_publication_advice'] = comparison.pop('publication')
                comparison['publication'] = 'pending_full_research_cost_and_adoption_review'
                comparison['cost_scope'] = 'paired_task_model_requests_only'
                comparisons.append(comparison)
                verify(behavior_policy)
                try:
                    behavior_review = host.review_skill({
                        'parent_skill_directory': str(baseline_skill), 'candidate_skill_directory': str(package),
                        'reviewer_policy': behavior_policy['path'],
                        'behavior_expectation': active_hypothesis['expected_behavior'],
                        'parent_rollout': behavior_rollout(control, OWNER),
                        'candidate_rollout': behavior_rollout(candidate, OWNER)})
                except Exception as error:
                    behavior_review = {'accepted': None, 'error': type(error).__name__ + ':' + str(error),
                                       'scope': 'behavior_review_inconclusive'}
                    if getattr(error, 'review_model_record', None):
                        behavior_review['model_record'] = error.review_model_record
                verify(behavior_policy)
                behavior_reviews.append(behavior_review)
                checks.extend([{'id': 'full-original-oracle-' + task_id,
                                'status': 'passed' if str(candidate.get('score')) in ('1', '1.0') else 'failed'},
                               {'id': 'native-policy-read-' + task_id,
                                'status': 'passed' if candidate.get('skill_activated') is True else 'failed'},
                               {'id': 'observable-behavior-change-' + task_id,
                                'status': 'passed' if behavior_review['accepted'] is True else
                                          'unknown' if behavior_review['accepted'] is None else 'failed'}])
            verdict = {'passed': all(row['status'] == 'passed' for row in checks), 'checks': checks,
                       'training_sources': [entry['evidence'] for entry in entries],
                       'heldout_sources': [trial['observation'] for trial in runs],
                       'evidence': [trial['record'] for trial in runs] +
                           [review['model_record'] for review in behavior_reviews if review.get('model_record')]}
            adoption = (None if any(review['accepted'] is None for review in behavior_reviews) else
                        all(review['accepted'] is True for review in behavior_reviews))
            row = {'runs': runs, 'comparisons': comparisons, 'verdict': verdict,
                   'strategy_sha256': strategy['revision_sha256'], 'hypothesis': copy.deepcopy(active_hypothesis),
                   'behavior_reviews': behavior_reviews, 'semantic_adoption': adoption,
                   'adoption_method': 'independent_paired_action_trace_review', 'usage_scope': 'isolated_evaluation',
                   'complete_research_net_benefit': None}
            save(directory / 'result.json', row)
            validations.append(row)
            return verdict
        receiver = strategy_handler(snapshot=snapshot, feedback=feedback, target='task', scope=SCOPE,
                                    evaluate=evaluate)
        def handle(candidate, context, directory):
            active_hypothesis.clear()
            active_hypothesis.update(copy.deepcopy(candidate))
            previous = len(validations)
            try:
                result = receiver(candidate, context, directory)
            except Exception as error:
                if len(validations) > previous:
                    investigation.expose_development()
                    error.evolution_diagnostic = {'development_validation': [
                        {'checks': row['verdict']['checks'], 'comparisons': row['comparisons'],
                         'semantic_adoption': row['semantic_adoption'],
                         'behavior_reviews': row['behavior_reviews']} for row in validations[previous:]]}
                    error.evolution_evidence_refs = [file_ref(output / ('candidate-evaluation-' + str(index)) / 'result.json')
                        for index in range(previous, len(validations))]
                raise
            investigation.expose_development()
            result.update(usage_scope='isolated_evaluation', selection_origin='host_selected',
                          production_default_changed=False, actual_adoption=validations[-1]['semantic_adoption'],
                          development_validation=[{'checks': row['verdict']['checks'],
                                                   'comparisons': row['comparisons'],
                                                   'semantic_adoption': row['semantic_adoption'],
                                                   'behavior_reviews': row['behavior_reviews']}
                                                  for row in validations[previous:]])
            return result

        self.host, self.feedback, self.validations = host, feedback, validations
        self.gate, self.initial_costs = gate, initial_costs
        self.evaluation = evaluation
        return {'task_strategy': handle}

    def evaluate_followup(self, result):
        output, validations, policy_ref = self.output, self.validations, self.policy_ref
        host, feedback, gate, initial_costs = self.host, self.feedback, self.gate, self.initial_costs
        evaluation = self.evaluation
        updates = {}
        admitted = [row for row in result.get('submissions', []) if row.get('outcome', {}).get('selection')]
        choice = select_pilot_candidate(admitted, validations, policy_ref)
        save(output / 'candidate-selection.json', choice)
        followups = []
        if choice['selection']:
            selected = choice['selection']
            strategy = json.loads(verify(selected['strategy']))
            package = _skill(strategy, output / 'followup-skill')
            for task_id in evaluation:
                trial = host.trial(task_id, split='test', skill_directory=package,
                                   label='isolated-followup', evaluation_role='final')
                followups.append(trial)
                feedback.observe(stage='execution', subject={'id': strategy['id'], 'sha256': strategy['revision_sha256']},
                    scope=SCOPE, status='passed' if str(trial.get('score')) in ('1', '1.0') else 'failed',
                    cost=None, evidence=[trial['record'], trial['observation']])
        updates.update(validations=validations, followups=followups,
                      complete_research_reserved_usd=str(gate.state.reserved_usd - initial_costs),
                      effect_scope='historical replay; proxy accounting and adoption require separate inspection',
                      pending={'capability': 'native_material_backend_not_configured_for_this_host',
                               'construction_strategy': 'real_builder_evaluator_unavailable',
                               'boundary': 'full_graph_compiler_not_configured'},
                      production_default_changed=False)
        updates['publication_decision'] = 'research_only_pending_full_cost_and_behavior_review'
        updates['actual_adoption'] = (True if any(row['semantic_adoption'] is True for row in validations)
                                     else None if any(row['semantic_adoption'] is None for row in validations) else False)
        updates['adoption_scope'] = 'isolated_validation; followup_behavior_not_independently_reviewed'
        updates['candidate_selection'] = file_ref(output / 'candidate-selection.json')
        observations = [trial['observation'] for row in validations for trial in row['runs']]
        observations.extend(trial['observation'] for trial in followups)

        inherited_results = [updates['candidate_selection']]
        inherited_results.extend(file_ref(output / ('candidate-evaluation-' + str(index)) / 'result.json')
                                 for index in range(len(validations)))
        inherited_results.extend(ref for item in admitted for ref in item['outcome']['selection'].values())
        return {'result': updates,
                'entries': [{'split': 'training', 'scope': SCOPE, 'evidence': ref} for ref in observations],
                'inspector': inspect_benchmark, 'history': inherited_results, 'expose_evaluation': bool(followups)}
