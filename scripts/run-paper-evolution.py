#!/usr/bin/env python3
"""Configure the Paper adapter and launch GeneLoop's shared Evolution cycle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.capability_feedback import file_ref
from src.adapters.capability_improvement import save
from src.adapters.capability_proposal import CumulativeProposalGate
from src.adapters.evolution_cycle import run_evolution_cycle
from src.adapters.research_harness import ResearchHarness
from scenarios.paper_proofreading.evolution_adapter import PaperEvolutionAdapter, select_pilot_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ledger-root', type=Path, required=True)
    parser.add_argument('--evolution-input-manifest', type=Path)
    parser.add_argument('--require-builder-evidence', action='store_true',
                        help='Require extra Capability/Builder input for a focused input audit; receiver support is unchanged.')
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--max-tool-calls', type=int, required=True)
    parser.add_argument('--timeout-seconds', type=int, required=True)
    parser.add_argument('--prior-result', type=Path, action='append', default=[])
    parser.add_argument('--investigation-history', type=Path, action='append', default=[])
    args = parser.parse_args()
    if args.max_tool_calls < 1 or args.timeout_seconds < 1:
        parser.error('finite positive tool count and deadline required')
    if args.call_model and sys.platform != 'linux':
        parser.error('real model evaluation runs on the configured Linux research server')
    if args.require_builder_evidence and not args.evolution_input_manifest:
        parser.error('the dedicated Builder investigation requires --evolution-input-manifest')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    adapter = PaperEvolutionAdapter(file_ref(args.history.resolve()), file_ref(args.policy.resolve()), output,
        input_manifest=file_ref(args.evolution_input_manifest.resolve()) if args.evolution_input_manifest else None,
        require_builder_evidence=args.require_builder_evidence,
        investigation_history=[file_ref(path.resolve()) for path in args.investigation_history])
    investigation = adapter.load_experiences()
    save(output / 'effective.json', adapter.effective_config(max_tool_calls=args.max_tool_calls,
                                                           timeout_seconds=args.timeout_seconds))
    save(output / 'overview.json', investigation.overview())
    if not args.call_model:
        save(output / 'result.json', {'status': 'preview', 'model_requests': 0})
        print(json.dumps({'status': 'preview', 'observations': len(investigation.observations)}))
        return
    with CumulativeProposalGate(args.ledger_root) as gate:
        handlers = adapter.build_receivers(investigation, gate)
        result, _ = run_evolution_cycle(investigation,
            call_agent=ResearchHarness(gate, output / 'model-sessions'), handlers=handlers, output=output,
            limits={'max_tool_calls': args.max_tool_calls, 'timeout_seconds': args.timeout_seconds,
                    'require_no_change_evidence': True},
            prior_results=[file_ref(path) for path in args.prior_result],
            followup_evaluator=adapter.evaluate_followup)
        print(json.dumps({'status': result['status'], 'submissions': len(result.get('submissions', [])),
                          'followups': len(result.get('followups', []))}))


if __name__ == '__main__':
    main()
