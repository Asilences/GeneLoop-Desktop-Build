#!/usr/bin/env python3
"""单次离线 Evolution Agent；默认预览，真实调用复用原研究账本与论文验收。"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.capability_contract import capability_digest, capability_ref, validate_capability_snapshot
from src.adapters.capability_evolution_agent import packet, run, inspect_graph, boundary_handler, model_view, SYSTEM
from src.adapters.capability_feedback import CapabilityFeedback, file_ref, verify
from src.adapters.capability_improvement import save
from src.adapters.capability_motif_learning import _checked
from scenarios.paper_proofreading.frontier.budget import FrontierGate


def read(ref):
    return json.loads(verify(ref))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def preflight(manifest):
    if set(manifest) != {'snapshot', 'training', 'heldout', 'prior_candidate', 'scope', 'acceptance', 'ledger_root'}:
        raise ValueError('evolution_manifest_invalid')
    snapshot = validate_capability_snapshot(read(manifest['snapshot']))
    training = [_checked(read(ref), snapshot['owner']) for ref in manifest['training']]
    heldout = [_checked(read(ref), snapshot['owner']) for ref in manifest['heldout']]
    if len(training) < 2 or not heldout:
        raise ValueError('evolution_independent_train_and_heldout_required')
    observations = [inspect_graph(ref, snapshot['owner']) for ref in [*manifest['training'], *manifest['heldout']]]
    if len({r['source_identity'] for r in observations}) != len(observations):
        raise ValueError('evolution_train_heldout_source_overlap')
    acceptance = read(manifest['acceptance'])
    validator = load('evolution_paper_validation', ROOT / 'scripts/validate-recursive-paper-candidate.py')
    # Verify the old host acceptance configuration before exposing the model.
    # Its candidate is replaced only after the original learner compiles one.
    validator.preflight(acceptance)
    if acceptance['source_trace'] not in manifest['training']:
        raise ValueError('evolution_acceptance_training_source_required')
    prior = read(manifest['prior_candidate']); cap = prior.get('compiled', prior); cap = cap.get('capability', cap)
    if capability_ref(cap) not in snapshot['roots'] or cap['certification'] != 'certified' or cap['lifecycle'] != 'active':
        raise ValueError('evolution_prior_not_active')
    if cap != next(c for c in snapshot['capabilities'] if c['id'] == cap['id']):
        raise ValueError('evolution_prior_snapshot_changed')
    return snapshot, training, heldout, acceptance, validator, cap


def match_heldout(candidate, training, heldout):
    """Frozen host rule: match the proposed observed relation, never an answer.

    No heldout content is sent to the model. Ambiguous/repeated matches defer.
    """
    signatures = []
    for trace in training:
        calls = candidate['proposal']['regions'][trace['task_id']]
        signatures.append([step['capability'] for step in trace['steps'] if step['call_id'] in calls])
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise ValueError('evolution_training_relation_inconsistent')
    signature = signatures[0]; regions = {}
    for trace in heldout:
        steps = trace['steps']; matches = [steps[i:i + len(signature)] for i in range(len(steps) - len(signature) + 1)
            if [step['capability'] for step in steps[i:i + len(signature)]] == signature]
        if len(matches) != 1:
            raise ValueError('evolution_heldout_relation_not_unique')
        regions[trace['task_id']] = [step['call_id'] for step in matches[0]]
    return regions


def execute(manifest_ref, output, *, call_model=False, budget_usd='3', max_requests=1, context_bytes=30000):
    output = Path(output).resolve()
    if output == ROOT / '.local' or not output.is_relative_to(ROOT / '.local'):
        raise ValueError('evolution_private_output_required')
    budget = Decimal(budget_usd)
    if not budget.is_finite() or budget < 0 or type(max_requests) is not int or max_requests != 1:
        raise ValueError('evolution_single_proposal_finite_budget_required')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    start = time.monotonic(); gate = None
    report = {'status': 'failed', 'model_requests': 0, 'total_economic_cost': None,
              'measured_net_benefit': None, 'baseline_comparison': 'not_run', 'manifest': manifest_ref}
    try:
        manifest = read(manifest_ref)
        snapshot, training, heldout, acceptance, validator, prior = preflight(manifest)
        evidence_packet = packet([{'split': 'training', 'scope': manifest['scope'], 'evidence': ref}
            for ref in manifest['training']], snapshot, manifest['scope'], output / 'evidence', context_bytes=context_bytes)
        save(output / 'frozen.json', {'manifest': manifest_ref, 'snapshot': snapshot['digest'],
            'packet': evidence_packet, 'model': 'deepseek-flash', 'reasoning_effort': 'off', 'max_tokens': 393216,
            'budget_usd': str(budget), 'max_requests': max_requests, 'ledger_root': manifest['ledger_root'],
            'context_limit_utf8_bytes': context_bytes, 'heldout_matching': 'unique_exact_capability_sequence',
            'production_enabled': False, 'cumulative_ledger_reset': False,
            'code': [file_ref(path) for path in [Path(__file__), ROOT / 'src/adapters/capability_evolution_agent.py',
                ROOT / 'src/adapters/capability_goal_proposal.py', ROOT / 'src/adapters/capability_evolution.py',
                ROOT / 'scenarios/paper_proofreading/frontier/budget.py']]})
        if evidence_packet['status'] != 'ready':
            report.update(status=evidence_packet['status']); return report
        visible, _ = model_view(read(evidence_packet['packet']))
        save(output / 'external-model-context.json', visible)
        (output / 'external-prompt.txt').write_text(SYSTEM + '\nFROZEN TASK NEEDS AND CAPABILITIES:\n' +
            json.dumps(visible, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        if not call_model:
            report.update(status='preview', packet=evidence_packet['packet']); return report
        feedback = CapabilityFeedback(output / 'feedback', snapshot['owner'])
        for reference, observation in zip(manifest['training'], [inspect_graph(r, snapshot['owner']) for r in manifest['training']]):
            feedback.observe(stage='attempt', subject=capability_ref(prior), scope=manifest['scope'],
                             status=observation['status'], cost=None, evidence=[reference, *observation['evidence']])
        def accept(row, directory):
            candidate_path = directory.parent / (directory.name + '-candidate.json')
            save(candidate_path, row)
            config = copy.deepcopy(acceptance); config['candidate'] = file_ref(candidate_path)
            # Host checker, original independent inputs, libraries unchanged.
            return validator.run_manifest(config, directory, execute=True)
        def boundary(candidate, context, directory):
            verify(manifest_ref)
            # The matching algorithm and all heldout sources were frozen before
            # the model turn; the candidate supplies no heldout inputs/answers.
            regions = match_heldout(candidate, training, heldout)
            handle = boundary_handler(training=training, heldout=heldout, snapshot=snapshot,
                feedback=feedback, prior_candidate=manifest['prior_candidate'], scope=manifest['scope'],
                heldout_regions=regions, accept=accept)
            return handle(candidate, context, directory)
        with FrontierGate(manifest['ledger_root'], output / 'research-requests.jsonl',
                          deadline=time.time() + 2700, max_requests=max_requests) as gate:
            gate.activate('evolution-' + output.name, str(budget))
            report['cumulative_before'] = {'requests': gate.state.request_count, 'accounted_usd': gate.state.reserved_usd}
            report['agent'] = run(evidence_packet['packet'], output / 'agent', enabled=True,
                                 gate=gate, snapshot=snapshot, handlers={'boundary': boundary})
            report['status'] = report['agent']['status']
        return report
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                      error=type(error).__name__ + ':' + str(error))
        raise
    finally:
        if gate is not None and getattr(gate, 'state', None) is not None:
            costs = [gate.exact_costs.get(key) for key in gate.request_cells]
            report.update(model_requests=len(costs),
                observed_model_usd_decimal=str(sum(costs, Decimal(0))) if all(c is not None for c in costs) else None,
                requests=[{'request_id': key, 'usage': gate.completed.get(key, {}).get('response_usage'),
                           'observed_model_usd_decimal': str(gate.exact_costs[key]) if gate.exact_costs.get(key) is not None else None}
                          for key in gate.request_cells],
                cumulative_after={'requests': gate.state.request_count, 'accounted_usd': gate.state.reserved_usd},
                request_evidence=file_ref(output / 'research-requests.jsonl'))
        report['elapsed_seconds'] = time.monotonic() - start
        save(output / 'result.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--budget-usd', default='3')
    parser.add_argument('--max-requests', type=int, default=1)
    parser.add_argument('--context-bytes', type=int, default=30000)
    args = parser.parse_args()
    result = execute(file_ref(args.manifest), args.output, call_model=args.call_model,
                     budget_usd=args.budget_usd, max_requests=args.max_requests, context_bytes=args.context_bytes)
    print(json.dumps({k: result.get(k) for k in ('status', 'model_requests', 'observed_model_usd_decimal')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
