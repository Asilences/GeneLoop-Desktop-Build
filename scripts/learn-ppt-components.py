#!/usr/bin/env python3
"""Inventory historical pages and prepare generated components for certification."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.ppt_component_learning import collect_source, install_component_library, prepare_candidate, propose_component, proposal_request, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--proposal', type=Path)
    parser.add_argument('--heldout', type=Path)
    parser.add_argument('--install-request', type=Path)
    parser.add_argument('--certified-library', type=Path)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--budget-policy', type=Path)
    repair = parser.add_mutually_exclusive_group()
    repair.add_argument('--repair-fonts', action='store_true')
    repair.add_argument('--repair-readability', action='store_true')
    args = parser.parse_args()
    certification_mode = 'preserve'
    if args.repair_readability:
        certification_mode = 'readability_repair_v1'
    elif args.repair_fonts:
        certification_mode = 'font_repair_v1'
    witnesses, rejected, seen = [], [], set()
    for record in read_json(args.dataset)['sources']:
        try:
            witness = collect_source(record)
            if witness['source_sha256'] not in seen:
                witnesses.append(witness)
                seen.add(witness['source_sha256'])
        except (ValueError, KeyError, OSError) as error:
            rejected.append({'task_id': record.get('task_id'), 'reason': str(error)})
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(args.out / 'inventory.json', {'accepted': witnesses, 'rejected': rejected, 'extra_model_requests': 0})
    for witness in witnesses:
        write_json(args.out / (witness['source_sha256'] + '-request.json'), proposal_request(witness))
    if args.call_model:
        if len(witnesses) != 1 or not args.budget_policy or args.proposal:
            parser.error('one accepted source and --budget-policy are required for one model proposal')
        proposal = propose_component(witnesses[0], args.budget_policy, args.out / 'model-proposal',
                                     font_repair=args.repair_fonts, readability_repair=args.repair_readability)
        if args.heldout:
            prepare_candidate(witnesses[0], proposal, args.out / 'candidate', read_json(args.heldout),
                              certification_mode=certification_mode)
    if args.proposal:
        if len(witnesses) != 1 or not args.heldout:
            parser.error('one accepted source and an independent heldout input are required')
        prepare_candidate(witnesses[0], read_json(args.proposal), args.out / 'candidate', read_json(args.heldout),
                          certification_mode=certification_mode)
    if args.install_request:
        if not args.certified_library:
            parser.error('--certified-library is required for explicit installation')
        write_json(args.out / 'installation.json', install_component_library(args.install_request, args.certified_library))
    print({'sources': len(witnesses), 'rejected': len(rejected), 'proposal_prepared': bool(args.proposal)})


if __name__ == '__main__':
    main()
