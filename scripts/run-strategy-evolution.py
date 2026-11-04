#!/usr/bin/env python3
"""条件策略研究入口，沿用单次 Evolution 提案、宿主验收与原账本。"""
from __future__ import annotations

import argparse
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.capability_contract import validate_capability_snapshot
from src.adapters.capability_feedback import CapabilityFeedback, file_ref, verify
from src.adapters.capability_improvement import save
from src.adapters.capability_evolution_agent import packet, model_view, run, strategy_handler
from src.adapters.capability_decision_evidence import inspect_decision
from scenarios.paper_proofreading.frontier.budget import FrontierGate


def execute(manifest_ref, output, *, call_model=False, budget_usd='3'):
    config = json.loads(verify(manifest_ref))
    fields = {'snapshot', 'observations', 'scope', 'target', 'feedback_directory', 'ledger_root', 'host_adapter'}
    if (not fields.issubset(config) or set(config) - fields - {'parent_selection'}
            or config['target'] not in ('task', 'construction')):
        raise ValueError('strategy_evolution_manifest_invalid')
    snapshot = validate_capability_snapshot(json.loads(verify(config['snapshot'])))
    budget = Decimal(budget_usd)
    if not budget.is_finite() or budget < 0:
        raise ValueError('strategy_evolution_budget_invalid')
    output = Path(output).resolve()
    if output == ROOT / '.local' or not output.is_relative_to(ROOT / '.local'):
        raise ValueError('strategy_evolution_private_output_required')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'status': 'preview', 'model_requests': 0, 'observed_model_usd_decimal': None,
              'measured_net_benefit': None, 'actual_adoption': None}
    gate = None
    try:
        selection = packet(config['observations'], snapshot, config['scope'], output / 'evidence',
                           inspector=inspect_decision)
        save(output / 'effective.json', {'manifest': manifest_ref, 'head_protocol': 'capability_strategy_v1',
             'model': 'deepseek-flash', 'reasoning_effort': 'off', 'max_tokens': 393216,
             'budget_usd': str(budget), 'max_requests': 1, 'cumulative_ledger_reset': False,
             'code': [file_ref(Path(__file__)), file_ref(ROOT / 'src/adapters/capability_evolution_agent.py')]})
        report['packet'] = selection
        if selection['status'] != 'ready':
            report['status'] = selection['status']
            return report
        visible, _ = model_view(json.loads(verify(selection['packet'])))
        save(output / 'external-context.json', visible)
        if not call_model:
            return report
        # Explicit operator-selected trusted code supplies independent evaluation.
        # No model-generated path or validator can enter this loading boundary.
        adapter_ref = config['host_adapter']
        adapter_path = Path(adapter_ref['path']).resolve()
        if not adapter_path.is_relative_to(ROOT) or adapter_path.suffix != '.py':
            raise ValueError('strategy_evolution_host_adapter_invalid')
        adapter_source = verify(adapter_ref)
        spec = importlib.util.spec_from_file_location('strategy_evolution_host', adapter_path)
        host = importlib.util.module_from_spec(spec)
        exec(compile(adapter_source, str(adapter_path), 'exec'), host.__dict__)
        def evaluate(candidate):
            verify(adapter_ref)
            result = host.evaluate_strategy(candidate)
            verify(adapter_ref)
            return result
        feedback = CapabilityFeedback(config['feedback_directory'], snapshot['owner'])
        handler = strategy_handler(snapshot=snapshot, feedback=feedback, target=config['target'],
                                   scope=config['scope'], evaluate=evaluate,
                                   parent_selection=config.get('parent_selection'))
        kind = 'task_strategy' if config['target'] == 'task' else 'construction_strategy'
        with FrontierGate(config['ledger_root'], output / 'requests.jsonl',
                          deadline=time.time() + 2700, max_requests=1) as gate:
            gate.activate('strategy-' + output.name, str(budget))
            report['agent'] = run(selection['packet'], output / 'agent', enabled=True, gate=gate,
                snapshot=snapshot, inspector=inspect_decision, handlers={kind: handler})
            report['status'] = report['agent']['status']
        return report
    except BaseException as error:
        report.update(status='failed', error=type(error).__name__ + ':' + str(error))
        raise
    finally:
        if gate is not None and getattr(gate, 'state', None) is not None:
            costs = [gate.exact_costs.get(key) for key in gate.request_cells]
            report['model_requests'] = len(costs)
            report['observed_model_usd_decimal'] = (
                str(sum(costs, Decimal(0))) if all(c is not None for c in costs) else None)
        save(output / 'result.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--budget-usd', default='3')
    args = parser.parse_args()
    result = execute(file_ref(args.manifest), args.output, call_model=args.call_model,
                     budget_usd=args.budget_usd)
    print(json.dumps({k: result[k] for k in ('status', 'model_requests', 'observed_model_usd_decimal')}))
