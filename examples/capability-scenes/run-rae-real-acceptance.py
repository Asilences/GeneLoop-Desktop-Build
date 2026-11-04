"""冻结现有论文任务并验收真实构造；默认只预检，--call-model 显式运行。"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.adapters.capability_contract import validate_capability_snapshot
from src.adapters.capability_construction_history import amount
from src.adapters.capability_improvement import read, save, evidence, validate, discover, run_improvement
from src.adapters.capability_scene import reference
from src.adapters.capability_proposal import MODEL, MAX_TOKENS
from scenarios.paper_proofreading.frontier.adapter import FrontierAdapter
from scenarios.paper_proofreading.frontier.budget import FrontierGate

REMOVED = ('discovery', 'opportunity_discovery', 'construction_feedback', 'learning_routes', 'recursive_abstraction')
SCENE = ROOT / 'scenarios/paper_proofreading/frontier'


def references(value):
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256'}:
            evidence(value)
            yield copy.deepcopy(value)
        else:
            for child in value.values():
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def native_catalogs(libraries, owner):
    """Read/validate original Script certificates, without executing a program."""
    code = ("import {buildScriptCapabilities} from './src/adapters/script_capability_runtime.ts';"
            "const x=JSON.parse(process.argv[1]);process.stdout.write(JSON.stringify("
            "x.libraries.map(r=>buildScriptCapabilities(r.path,x.owner,r.sha256))));")
    result = subprocess.run(['node', '--experimental-strip-types', '--input-type=module', '-e', code,
                             json.dumps({'libraries': libraries, 'owner': owner})], cwd=ROOT,
                            env={**os.environ, 'SSS_PYTHON': sys.executable},
                            capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(result.stdout)


def checkout_head():
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=ROOT, capture_output=True, text=True)
    if top.returncode or Path(top.stdout.strip()).resolve() != ROOT:
        return None
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


class AcceptanceAdapter(FrontierAdapter):
    def publish(self, job, candidate, attempt, expected_latest):
        result = super().publish(job, candidate, attempt, expected_latest)
        # Frontier uses the frozen host predicate and Script executor, with no
        # verifier model. This says nothing about CPU or human economic cost.
        result.update(model_requests=0, observed_model_usd=0,
                      verification_cost_scope='host_frontier_literal_predicate_no_verifier_model')
        result['execution_trace_refs'] = [reference(path) for label in ('validation', 'followup')
            if (path := Path(attempt) / 'publication' / label / 'trace.json').is_file()]
        save(Path(attempt) / 'acceptance-publication-outcome.json', result)
        return result


def prepare(source, out, budget, *, observe_builder=False):
    source = Path(source).resolve()
    source_ref = reference(source)
    original = json.loads(evidence(source_ref))
    validate('plan', original)
    if len(original['jobs']) != 1:
        raise ValueError('acceptance_single_existing_goal_required')
    job = original['jobs'][0]
    task = json.loads(evidence(job['task']))
    if not isinstance(task, dict) or not task.get('instruction'):
        raise ValueError('acceptance_task_invalid')
    snapshot = validate_capability_snapshot(json.loads(evidence(original['seed'])), original['owner'])
    catalog = json.loads(evidence(original['seed_catalog']))
    if not isinstance(catalog, dict):
        raise ValueError('acceptance_seed_catalog_invalid')
    if any(cap['certification'] != 'certified' or cap['lifecycle'] == 'archived'
           for cap in snapshot['capabilities']):
        raise ValueError('acceptance_uncertified_seed')
    if not Path(original['ledger_root']).is_dir():
        raise ValueError('acceptance_existing_ledger_required')
    template = json.loads(evidence(job['publication_plan']))
    if any(template[label]['specification']['kind'] != 'frontier_literal_v1'
           for label in ('validation', 'followup')):
        raise ValueError('acceptance_original_deterministic_checker_required')
    original_presentation = copy.deepcopy(template.get('presentation', {}))
    # Historical plans predate the existing single-source authoring view.
    # Select that native view explicitly for this new condition; this changes
    # presentation only, never the task, callable set, IR or verifier.
    template.setdefault('presentation', {})['source_primary'] = True
    added_cases = 'construction_cases' not in template
    if added_cases:
        template['construction_cases'] = [{**copy.deepcopy(case), 'split': 'training',
            'input': {'before': '/work/inputs/before.zip', 'after': '/work/inputs/after.zip'}}
            for case in template['native_cases']['paths']]
    if any(case.get('split') != 'training' for case in template['construction_cases']):
        raise ValueError('frontier_program_training_split_required')
    refs = [source_ref, original['seed'], original['seed_catalog'], job['task'], job['publication_plan']]
    refs += list(references([snapshot, catalog, template, job]))
    catalogs = native_catalogs(template['libraries'], original['owner'])
    save(out / 'native-catalogs.json', catalogs)
    save(out / 'publication-template.json', template)
    plan = copy.deepcopy(original)
    removed = {key: plan.pop(key) for key in REMOVED if key in plan}
    if observe_builder:
        plan['recursive_abstraction'] = {'enabled': True, 'builder_learning': {'enabled': True}}
    if 'learned_candidate' in plan['jobs'][0]:
        removed['jobs[0].learned_candidate'] = plan['jobs'][0].pop('learned_candidate')
    plan.update(id='rae-real-' + out.name, output=str(out / 'run'), store=str(out / 'store'),
                feedback_directory=str(out / 'feedback'), scene_adapter=reference(SCENE / 'adapter.py'),
                scene_dependencies=[reference(SCENE / name) for name in
                    ('author.py', 'check.py', 'oracle.py', 'publish.mjs', 'program_training.py')])
    limit = plan['policy']['max_repairs']
    plan['policy']['max_repairs'] = 2 if limit is None else min(2, limit)
    plan['jobs'][0]['publication_plan'] = reference(out / 'publication-template.json')
    validate('plan', plan)
    decision = discover(plan['jobs'][0])
    if decision['action'] != 'start':
        raise ValueError('acceptance_original_goal_not_admitted:' + decision['reason'])
    save(out / 'plan.json', plan)
    adapter = AcceptanceAdapter(plan)
    library = adapter.library()
    save(out / 'preflight-library.json', library)
    code_paths = [Path(__file__), *SCENE.glob('*.py'), SCENE / 'publish.mjs',
                  *ROOT.glob('src/adapters/capability_*.py'), *ROOT.glob('src/adapters/*capability*.ts'),
                  ROOT / 'src/adapters/script_motif_runtime.ts',
                  ROOT / 'src/adapters/script_runtime_compatibility.ts',
                  ROOT / 'config/script-runtime-compatibility.json',
                  ROOT / 'schemas/capability-improvement-v1.schema.json']
    frozen = {'format': 'rae_real_acceptance_v1', 'condition': 'fresh_existing_goal_no_prior_history',
        'source_plan': source_ref, 'source_refs': refs, 'task': job['task'], 'seed': original['seed'],
        'original_publication_template': job['publication_plan'], 'plan': reference(out / 'plan.json'),
        'initial_snapshot_sha256': snapshot['digest'], 'visible_snapshot_sha256': library['snapshot']['digest'],
        'removed_options': removed, 'construction_cases_added_from_original_training': added_cases,
        'authoring_view': 'source_primary_v1',
        'presentation_change': {'before': original_presentation, 'after': copy.deepcopy(template['presentation']),
            'reason': 'Explicit current native authoring view; historical plan may default to legacy_v1'},
        'original_policy': original['policy'], 'policy': plan['policy'], 'budget_usd': str(budget),
        'effective_max_reconsiderations': 0,
        'observe_builder': observe_builder,
        'repair_limit_scope': 'Each unchanged-material repair segment; certified material acquisition resets the segment in the original controller. This is not a total request cap.',
        'deadline_seconds': 2700, 'deadline_scope': 'admission_no_new_requests_after_deadline',
        'model': MODEL, 'reasoning_effort': 'off', 'max_tokens': MAX_TOKENS,
        'tool_order': [], 'ledger_root': original['ledger_root'], 'model_requests': 0,
        'total_economic_cost': None, 'measured_net_benefit': None,
        'verification_model_cost_scope': 'host_frontier_literal_predicate_no_verifier_model',
        'head': checkout_head(),
        'code_sha256': {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sorted(set(code_paths))},
        'python': sys.version, 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'platform': platform.platform(), 'scope': 'real_model_existing_task_acceptance_not_recursive_or_benefit_proof'}
    save(out / 'frozen.json', frozen)
    return plan, snapshot, adapter, frozen


def collect_attempts(plan, snapshot):
    from src.adapters.capability_contract import capability_ref
    roots = [capability_ref(cap) for cap in snapshot['capabilities'] if cap['implementation']['kind'] == 'composition']
    rows = []
    for folder in sorted(Path(plan['output']).glob('**/attempt-*')):
        if not folder.is_dir():
            continue
        files = {name: reference(folder / name) for name in ('result.json', 'candidate.json', 'proposal.json',
            'requests.jsonl', 'effective.json', 'acquisition.json', 'strategy.json', 'native/certification.json',
            'native/observations.json', 'acceptance-publication-outcome.json') if (folder / name).is_file()}
        traces = []
        for path in sorted((folder / 'publication').glob('*/trace.json')):
            trace = read(path)
            traces.append({'trace': reference(path), 'status': trace.get('status'),
                'successful_C_calls': sum(r.get('status') == 'succeeded' and r.get('capability') in roots
                                          for r in trace.get('receipts', []))})
        files.update({str(path.relative_to(folder)): reference(path)
                      for path in sorted((folder / 'publication').glob('**/*.json'))})
        rows.append({'path': str(folder), 'evidence': files, 'runtime_traces': traces})
    return rows


def run(plan, snapshot, adapter, frozen, out, budget):
    for ref in frozen['source_refs']:
        evidence(ref)
    evidence(frozen['plan'])
    for name, digest in frozen['code_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('acceptance_code_changed')
    start = time.time()
    save(out / 'started.json', {'time': start, 'deadline': start + 2700, 'automatic_resume': False})
    report = {'status': 'failed', 'model_requests': 0, 'observed_model_usd_decimal': None,
              'total_economic_cost': None, 'measured_net_benefit': None,
              'verification_model_usd_decimal': '0',
              'verification_cost_scope': 'host_frontier_literal_predicate_no_verifier_model',
              'frozen': reference(out / 'frozen.json')}
    gate = None
    try:
        with FrontierGate(plan['ledger_root'], out / 'research-requests.jsonl', deadline=start + 2700) as gate:
            report['cumulative_before'] = {'requests': gate.state.request_count, 'accounted_usd': gate.state.reserved_usd}
            gate.activate(plan['id'], str(budget))
            adapter.gate = gate
            controller = run_improvement(plan, adapter, execute=True)
            report['controller'] = controller
            report['status'] = ('accepted' if controller.get('outcomes') and
                all(row.get('status') == 'published' for row in controller['outcomes']) else 'not_accepted')
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                      error=type(error).__name__ + ':' + str(error))
        raise
    finally:
        if gate is not None and getattr(gate, 'state', None) is not None:
            keys = list(gate.request_cells)
            costs = [gate.exact_costs.get(key) for key in keys]
            report.update(model_requests=len(keys),
                observed_model_usd_decimal=str(sum(costs, Decimal(0))) if all(x is not None for x in costs) else None,
                requests=[{'request_id': rid, 'ledger_ref': str(gate.root / 'cost-ledger.jsonl'),
                    'usage': gate.completed.get(rid, {}).get('response_usage'),
                    'observed_model_usd_decimal': str(gate.exact_costs[rid]) if gate.exact_costs.get(rid) is not None else None}
                    for rid in keys],
                research_accounted_usd_decimal=str(gate.budget.spent) if gate.budget is not None else None,
                cumulative_after={'requests': gate.state.request_count, 'accounted_usd': gate.state.reserved_usd})
        try:
            report['attempts'] = collect_attempts(plan, snapshot)
        except Exception as error:
            report['evidence_collection_error'] = type(error).__name__ + ':' + str(error)
            if report['status'] == 'accepted':
                report['status'] = 'evidence_incomplete'
        report['wall_seconds'] = time.time() - start
        save(out / 'result.json', report)
    return report


def acceptance(source, output, budget='3', *, call_model=False, private_root=None, observe_builder=False):
    budget = amount(budget)
    if budget is None:
        raise ValueError('acceptance_finite_budget_required')
    private_root = (ROOT / '.local' if private_root is None else Path(private_root)).resolve()
    out = Path(output).resolve()
    if out == private_root or not out.is_relative_to(private_root):
        raise ValueError('acceptance_private_output_required')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    try:
        plan, snapshot, adapter, frozen = prepare(source, out, budget, observe_builder=observe_builder)
        if call_model:
            return run(plan, snapshot, adapter, frozen, out, budget)
        result = {'status': 'frozen_preview', 'model_requests': 0, 'frozen': reference(out / 'frozen.json')}
        save(out / 'result.json', result)
        return result
    except BaseException as error:
        save(out / 'failure.json', {'status': 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
            'error': type(error).__name__ + ':' + str(error), 'automatic_resume': False,
            'measurement': reference(out / 'result.json') if (out / 'result.json').exists() else None})
        raise


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt('acceptance_cancelled')
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget-usd', default='3')
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--observe-builder', action='store_true',
                        help='显式记录 Builder 的真实能力执行供原学习器消费；不要求模型选择任何能力')
    args = parser.parse_args()
    result = acceptance(args.source_plan, args.output, args.budget_usd, call_model=args.call_model,
                        observe_builder=args.observe_builder)
    print(json.dumps({key: result.get(key) for key in ('status', 'model_requests', 'observed_model_usd_decimal')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
