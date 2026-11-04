#!/usr/bin/env python3
"""Isolated SkillsBench trial or Skill∞ reproduction using the original ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.capability_improvement import save
from src.adapters.capability_proposal import CumulativeProposalGate
from src.adapters.evolution_benchmark import BenchmarkHost
from src.adapters.skill_infinity_baseline import (
    create_seed_meta_skill, create_seed_task_skill, optimize_task_skill, refine_meta_skill,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-root', required=True, type=Path)
    parser.add_argument('--test-root', required=True, type=Path)
    parser.add_argument('--source-version', required=True)
    parser.add_argument('--ledger-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--task', required=True)
    parser.add_argument('--mode', choices=['trial', 'skill-infinity', 'geneloop'], default='trial')
    parser.add_argument('--split', choices=['training', 'test'], default='training')
    parser.add_argument('--meta-task', action='append', default=[])
    parser.add_argument('--development-task', action='append', default=[])
    parser.add_argument('--validation-task', action='append', default=[])
    parser.add_argument('--continuation', type=Path)
    parser.add_argument('--verifier-env', action='append', default=[])
    parser.add_argument('--materials-root', type=Path)
    parser.add_argument('--prewarm-dependencies', action='store_true')
    parser.add_argument('--candidates', type=int, default=4)
    parser.add_argument('--meta-candidates', type=int, default=4)
    parser.add_argument('--inner-candidates', type=int, default=2)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.local'):
        raise ValueError('benchmark_private_output_required')
    output.mkdir(parents=True, exist_ok=False)
    effective = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    effective.update(budget_usd=None, max_requests=None, model='deepseek-flash',
                     reasoning_effort='off', max_tokens=393216, cumulative_ledger_reset=False)
    save(output / 'effective.json', effective)
    if not args.call_model:
        print(json.dumps({'status': 'preview', 'output': str(output)}))
        return
    result = {'status': 'failed'}
    try:
        with CumulativeProposalGate(args.ledger_root) as gate:
            materials = None
            if args.mode == 'geneloop':
                from src.adapters.benchmark_script_materials import BenchmarkScriptMaterials
                materials = BenchmarkScriptMaterials('overnight-research', args.materials_root or output / 'materials')
            host = BenchmarkHost(args.training_root, args.test_root, output / 'host',
                                 source_version=args.source_version, gate=gate,
                                 verifier_environment=dict(value.split('=', 1) for value in args.verifier_env),
                                 materials=materials, prewarm_dependencies=args.prewarm_dependencies)
            if args.mode == 'trial':
                result = host.trial(args.task, split=args.split)
            elif args.mode == 'geneloop':
                from src.adapters.evolution_benchmark_gene import run_gene_benchmark
                continuation = json.loads(args.continuation.read_text()) if args.continuation else {}
                result = run_gene_benchmark(host, development_tasks=args.development_task,
                    validation_tasks=args.validation_task or [args.task], test_tasks=[args.task],
                    output=output / 'generation', snapshot=continuation.get('snapshot'),
                    prior_selection=continuation.get('selection'),
                    prior_observations=[row['evidence'] for row in continuation.get('entries', [])],
                    history=continuation.get('history', []),
                    feedback_directory=continuation.get('feedback_directory'))
            else:
                meta = create_seed_meta_skill(output / 'seed-meta')
                if args.meta_task:
                    tasks = [{'id': task, 'seed_skill': create_seed_task_skill(
                                output / 'meta-seeds' / task, task, 'Perform ' + task + ' tasks.'),
                              'context': {'task_id': task}} for task in args.meta_task]
                    refined = refine_meta_skill(meta, tasks, output / 'meta-refinement',
                        call_agent=host.agent, evaluate=host.evaluate_skill, review=host.review_skill,
                        outer_candidate_budget=args.meta_candidates, inner_candidate_budget=args.inner_candidates)
                    save(output / 'meta-result.json', refined)
                    if refined['status'] != 'completed':
                        raise ValueError('benchmark_meta_refinement_failed')
                    meta = refined['selected_skill']
                seed = create_seed_task_skill(output / 'task-seed', args.task, 'Perform ' + args.task + ' tasks.')
                optimized = optimize_task_skill(seed, output / 'task-optimization',
                    call_agent=host.agent, evaluate=host.evaluate_skill, review=host.review_skill,
                    task_context={'task_id': args.task}, meta_skill=meta, candidate_budget=args.candidates)
                save(output / 'optimization-result.json', optimized)
                if optimized['status'] != 'completed':
                    raise ValueError('benchmark_task_optimization_failed')
                final = host.trial(args.task, split='test', skill_directory=optimized['selected_skill'], label='final')
                result = {'status': 'evaluated', 'method': 'skill_infinity_paper_reproduction',
                          'self_improvement': refined['self_improvement'] if args.meta_task else 'seed_only',
                          'optimization': optimized, 'final': final}
            result['cumulative_accounted_usd'] = gate.state.reserved_usd
            result['cumulative_requests'] = gate.state.request_count
    except Exception as error:
        result.update(status='failed', error=type(error).__name__ + ':' + str(error))
        raise
    finally:
        save(output / 'result.json', result)
    print(json.dumps({'status': result['status'], 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
