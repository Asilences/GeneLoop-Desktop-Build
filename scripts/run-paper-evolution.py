#!/usr/bin/env python3
"""Run one paper-history investigation through existing Harness and receivers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.capability_contract import create_capability_snapshot
from src.adapters.capability_feedback import CapabilityFeedback, file_ref, verify
from src.adapters.capability_improvement import save
from src.adapters.capability_investigation import Investigation
from src.adapters.capability_evolution_inputs import load_builder_input_manifest
from src.adapters.capability_decision_evidence import inspect_decision
from src.adapters.capability_evolution_investigation import run_investigation
from src.adapters.capability_evolution_agent import strategy_handler
from src.adapters.capability_proposal import CumulativeProposalGate
from src.adapters.evolution_benchmark import BenchmarkHost
from src.adapters.evolution_benchmark_gene import _skill
from src.adapters.research_harness import ResearchHarness
from src.adapters.rsi_quality import compare_research_outcomes
from src.adapters.skillsbench_trial import task_manifest
from scenarios.paper_proofreading.evolution_history import index_history, inspect_history, OWNER, SCOPE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ledger-root', type=Path, required=True)
    parser.add_argument('--evolution-input-manifest', type=Path)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--max-tool-calls', type=int, required=True)
    parser.add_argument('--timeout-seconds', type=int, required=True)
    parser.add_argument('--prior-result', type=Path, action='append', default=[])
    args = parser.parse_args()
    if args.max_tool_calls < 1 or args.timeout_seconds < 1:
        parser.error('finite positive tool count and deadline required')
    if args.call_model and sys.platform != 'linux':
        parser.error('real model evaluation runs on the configured Linux research server')
    if args.call_model and not args.evolution_input_manifest:
        parser.error('real Evolution requires a certified Capability and independent Builder construction evidence')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    history_ref, policy_ref = file_ref(args.history.resolve()), file_ref(args.policy.resolve())
    policy = json.loads(verify(policy_ref))
    # Preflight policy with neutral diagnostic values, before any model request.
    compare_research_outcomes({'quality': 1, 'cost_usd': '0', 'samples': 1},
                              {'quality': 1, 'cost_usd': '0', 'samples': 1}, policy_ref)
    entries, sealed = index_history(history_ref, output / 'projection')
    supplied = None
    if args.evolution_input_manifest:
        input_manifest_ref = file_ref(args.evolution_input_manifest.resolve())
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
    if args.call_model and not supplied['snapshot']['roots']:
        parser.error('real Evolution requires a certified Capability and independent Builder construction evidence')
    investigation = Investigation(snapshot, entries, SCOPE, output / 'investigation-input',
        inspector=inspect_experience, sealed_evidence=sealed['evaluation'],
        development_evidence=sealed['development'], history=[policy_ref],
        objective='Investigate these real historical task experiences and current available materials. '
                  'Autonomously choose whether any change would improve later work; preserving the current method is valid.')
    root = args.history.resolve().parent / 'evaluation-tasks'
    task_snapshots = {role: [task_manifest(path, task_id=path.name,
        split='test' if role == 'evaluation' else 'training',
        source_version='original-five-paper-historical-replay')
        for path in sorted((root / role).iterdir())] for role in ('development', 'evaluation')}
    frozen = {'history': history_ref, 'policy': policy_ref, 'policy_values': policy,
              'evolution_input_manifest': input_manifest_ref,
              'focus_capability': supplied['focus_capability'] if supplied else None,
              'builder_observation_count': supplied['independent_builder_sources'] if supplied else 0,
              'input_exposure': supplied['exposure'] if supplied else 'paper_history_only',
              'snapshot': snapshot, 'model': 'deepseek-flash', 'reasoning_effort': 'off',
              'max_tokens': 393216, 'budget_usd': None, 'max_requests': None,
              'max_investigation_tool_calls': args.max_tool_calls, 'timeout_seconds': args.timeout_seconds,
              'evaluation_task_snapshots': task_snapshots, 'initial_strategies': [],
              'max_root_candidates': 2, 'max_repairs_per_root': 2,
              'source_code': file_ref(ROOT / '.research-code-snapshot.json')
                             if (ROOT / '.research-code-snapshot.json').is_file() else None,
              'data_role': 'historically_exposed_replay', 'supported_receivers': ['task_strategy'],
              'production_default_changed': False, 'approval_scope': 'isolated_evaluation_only',
              'skeleton_scope': 'original calls and boundaries; unknown parameter dependencies retained'}
    save(output / 'effective.json', frozen)
    save(output / 'overview.json', investigation.overview())
    if not args.call_model:
        save(output / 'result.json', {'status': 'preview', 'model_requests': 0})
        print(json.dumps({'status': 'preview', 'observations': len(entries)}))
        return
    validation = sorted(path.name for path in (root / 'development').iterdir())
    evaluation = sorted(path.name for path in (root / 'evaluation').iterdir())
    feedback = CapabilityFeedback(output / 'feedback', OWNER)
    validations = []
    with CumulativeProposalGate(args.ledger_root) as gate:
        host = BenchmarkHost(root / 'development', root / 'evaluation', output / 'host',
                             source_version='original-five-paper-historical-replay', gate=gate)
        initial_costs = gate.state.reserved_usd
        def evaluate(strategy):
            verify(policy_ref)
            directory = output / ('candidate-evaluation-' + str(len(validations)))
            package = _skill(strategy, directory / 'skill')
            runs, comparisons, checks = [], [], []
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
                checks.extend([{'id': 'full-original-oracle-' + task_id,
                                'status': 'passed' if str(candidate.get('score')) in ('1', '1.0') else 'failed'},
                               {'id': 'native-policy-read-' + task_id,
                                'status': 'passed' if candidate.get('skill_activated') is True else 'failed'}])
            verdict = {'passed': all(row['status'] == 'passed' for row in checks), 'checks': checks,
                       'training_sources': [entry['evidence'] for entry in entries],
                       'heldout_sources': [trial['observation'] for trial in runs],
                       'evidence': [trial['record'] for trial in runs]}
            row = {'runs': runs, 'comparisons': comparisons, 'verdict': verdict,
                   'semantic_adoption': None, 'usage_scope': 'isolated_evaluation',
                   'complete_research_net_benefit': None}
            save(directory / 'result.json', row)
            validations.append(row)
            return verdict
        receiver = strategy_handler(snapshot=snapshot, feedback=feedback, target='task', scope=SCOPE,
                                    evaluate=evaluate)
        def handle(candidate, context, directory):
            previous = len(validations)
            try:
                result = receiver(candidate, context, directory)
            except Exception as error:
                if len(validations) > previous:
                    investigation.expose_development()
                    error.evolution_diagnostic = {'development_validation': [
                        {'checks': row['verdict']['checks'], 'comparisons': row['comparisons'],
                         'semantic_adoption': None} for row in validations[previous:]]}
                    error.evolution_evidence_refs = [file_ref(output / ('candidate-evaluation-' + str(index)) / 'result.json')
                        for index in range(previous, len(validations))]
                raise
            investigation.expose_development()
            result.update(usage_scope='isolated_evaluation', selection_origin='host_selected',
                          production_default_changed=False, actual_adoption=None,
                          development_validation=[{'checks': row['verdict']['checks'],
                                                   'comparisons': row['comparisons']}
                                                  for row in validations[previous:]])
            return result
        result = run_investigation(investigation, call_agent=ResearchHarness(gate, output / 'model-sessions'),
            handlers={'task_strategy': handle}, output=output / 'agent',
            max_tool_calls=args.max_tool_calls, timeout_seconds=args.timeout_seconds,
            prior_results=[file_ref(path) for path in args.prior_result], require_no_change_evidence=True)
        # Independent later replay only after successful admission. Development feedback is already exposed.
        admitted = [row for row in result.get('submissions', []) if row.get('outcome', {}).get('selection')]
        followups = []
        if admitted:
            selected = admitted[-1]['outcome']['selection']
            strategy = json.loads(verify(selected['strategy']))
            package = _skill(strategy, output / 'followup-skill')
            for task_id in evaluation:
                trial = host.trial(task_id, split='test', skill_directory=package,
                                   label='isolated-followup', evaluation_role='final')
                followups.append(trial)
                feedback.observe(stage='execution', subject={'id': strategy['id'], 'sha256': strategy['revision_sha256']},
                    scope=SCOPE, status='passed' if str(trial.get('score')) in ('1', '1.0') else 'failed',
                    cost=None, evidence=[trial['record'], trial['observation']])
        result.update(validations=validations, followups=followups,
                      complete_research_reserved_usd=str(gate.state.reserved_usd - initial_costs),
                      effect_scope='historical replay; proxy accounting and adoption require separate inspection',
                      pending={'capability': 'native_material_backend_not_configured_for_this_host',
                               'construction_strategy': 'real_builder_evaluator_unavailable',
                               'boundary': 'full_graph_compiler_not_configured'},
                      production_default_changed=False)
        result['publication_decision'] = 'research_only_pending_full_cost_and_behavior_review'
        result['actual_adoption'] = None
        observations = [trial['observation'] for row in validations for trial in row['runs']]
        observations.extend(trial['observation'] for trial in followups)
        if observations:
            from src.adapters.evolution_benchmark import inspect_benchmark
            feedback_view = Investigation(create_capability_snapshot('overnight-research', [], []),
                [{'split': 'training', 'scope': SCOPE, 'evidence': ref} for ref in observations],
                SCOPE, output / 'next-investigation-input', inspector=inspect_benchmark,
                objective='Inspect exposed replay outcomes and costs from the preceding evolution attempt.')
            save(output / 'feedback-overview.json', feedback_view.overview())
            result['feedback_requery'] = {'status': 'queryable', 'observations': len(observations),
                'exposure': 'now_exposed_development_replay',
                'overview': file_ref(output / 'feedback-overview.json')}
        else:
            decision_path = output / 'decision-feedback.json'
            save(decision_path, {'format': 'evolution_investigation_decision_v1',
                'status': result['status'], 'investigation': file_ref(output / 'agent' / 'result.json'),
                'production_default_changed': False})
            feedback_view = Investigation(snapshot, entries, SCOPE, output / 'next-investigation-input',
                inspector=inspect_history, sealed_evidence=sealed['evaluation'],
                development_evidence=sealed['development'], history=[policy_ref, file_ref(decision_path)],
                objective='Review the preceding investigation decision and its original evidence.')
            save(output / 'feedback-overview.json', feedback_view.overview())
            result['feedback_requery'] = {'status': 'queryable', 'observations': 0,
                'decision': file_ref(decision_path), 'overview': file_ref(output / 'feedback-overview.json')}
        save(output / 'result.json', result)
        print(json.dumps({'status': result['status'], 'submissions': len(result.get('submissions', [])),
                          'followups': len(followups)}))


if __name__ == '__main__':
    main()
