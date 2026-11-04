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
from src.adapters.evolution_benchmark import BenchmarkHost, validation_dataset_splits
from src.adapters.skill_infinity_baseline import (
    create_seed_meta_skill, create_seed_task_skill, optimize_task_skill, refine_meta_skill,
)


def material_configuration(continuation, explicit_root, output):
    """Resolve the original private backend location before creating its adapter."""
    owner = 'overnight-research'
    if not isinstance(continuation, dict):
        raise ValueError('benchmark_continuation_invalid')
    if continuation and (continuation.get('format') != 'gene_benchmark_continuation_v1'
                         or continuation.get('owner') != owner):
        raise ValueError('benchmark_continuation_format_or_owner_changed')
    saved = continuation.get('material_configuration')
    if saved is not None:
        if (not isinstance(saved, dict) or set(saved) != {'owner', 'directory', 'publication_store'}
                or saved['owner'] != owner or any(not isinstance(saved[key], str) or not saved[key].strip()
                                                 for key in ('directory', 'publication_store'))):
            raise ValueError('benchmark_material_configuration_invalid')
        directory = Path(saved['directory']).resolve()
        publication = Path(saved['publication_store']).resolve()
        if explicit_root is not None and explicit_root.resolve() != directory:
            raise ValueError('benchmark_material_root_conflict: --materials-root differs from continuation material_configuration.directory')
        if not directory.is_dir():
            raise ValueError('benchmark_inherited_material_directory_missing')
    else:
        if continuation.get('snapshot', {}).get('roots') and explicit_root is None:
            raise ValueError('benchmark_legacy_material_root_required: provide --materials-root for this older continuation')
        directory = (explicit_root or output / 'materials').resolve()
        publication = directory / 'publication-store'
    private = next((ancestor for ancestor in ROOT.resolve().parents
                    if ancestor.name == '.local' and ancestor.is_dir()), (ROOT / '.local').resolve())
    if not directory.is_relative_to(private) or not publication.is_relative_to(private):
        raise ValueError('benchmark_private_material_root_required')
    return {'owner': owner, 'directory': str(directory), 'publication_store': str(publication)}


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
    parser.add_argument('--validation-split', action='append', default=[], metavar='TASK=training|test',
                        help='Dataset for this task validation; training rollouts remain training.')
    parser.add_argument('--evaluation-role', choices=['development', 'validation', 'final'])
    parser.add_argument('--continuation', type=Path)
    parser.add_argument('--verifier-env', action='append', default=[])
    parser.add_argument('--materials-root', type=Path)
    parser.add_argument('--prewarm-dependencies', action='store_true')
    parser.add_argument('--candidates', type=int, default=4)
    parser.add_argument('--meta-candidates', type=int, default=4)
    parser.add_argument('--inner-candidates', type=int, default=2)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    validation_splits = validation_dataset_splits(dict(value.split('=', 1) for value in args.validation_split))
    if validation_splits.get(args.task) == 'test':
        raise ValueError('benchmark_final_input_reserved_for_test')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.local'):
        raise ValueError('benchmark_private_output_required')
    output.mkdir(parents=True, exist_ok=False)
    continuation = json.loads(args.continuation.read_text()) if args.mode == 'geneloop' and args.continuation else {}
    material_config = material_configuration(continuation, args.materials_root, output) if args.mode == 'geneloop' else None
    effective = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    effective['validation_splits'] = validation_splits
    effective.update(budget_usd=None, max_requests=None, model='deepseek-flash',
                     reasoning_effort='off', max_tokens=393216, cumulative_ledger_reset=False,
                     material_configuration=material_config)
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
                materials = BenchmarkScriptMaterials(material_config['owner'], material_config['directory'],
                    publication_store=material_config['publication_store'])
                if continuation.get('snapshot') is not None:
                    from src.adapters.capability_contract import validate_capability_snapshot
                    inherited = validate_capability_snapshot(continuation['snapshot'], material_config['owner'])
                    available = materials.catalog()['snapshot']
                    if (any(ref not in available['roots'] for ref in inherited['roots'])
                            or any(cap not in available['capabilities'] for cap in inherited['capabilities'])):
                        raise ValueError('benchmark_inherited_material_backend_missing: selected root does not contain the continued capabilities')
            host = BenchmarkHost(args.training_root, args.test_root, output / 'host',
                                 source_version=args.source_version, gate=gate,
                                 verifier_environment=dict(value.split('=', 1) for value in args.verifier_env),
                                 materials=materials, prewarm_dependencies=args.prewarm_dependencies,
                                 validation_splits=validation_splits)
            if args.mode == 'trial':
                result = host.trial(args.task, split=args.split, evaluation_role=args.evaluation_role)
            elif args.mode == 'geneloop':
                from src.adapters.evolution_benchmark_gene import run_gene_benchmark
                result = run_gene_benchmark(host, development_tasks=args.development_task,
                    validation_tasks=args.validation_task or [args.task], test_tasks=[args.task],
                    validation_splits=validation_splits,
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
                final = host.trial(args.task, split='test', skill_directory=optimized['selected_skill'],
                                   label='final', evaluation_role='final')
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
