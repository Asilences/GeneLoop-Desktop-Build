#!/usr/bin/env python3
"""Compile an offline compose proposal; does not execute, certify or publish it."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters.capability_builder import compile_proposal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal', type=Path, required=True)
    parser.add_argument('--construction-snapshot', type=Path, required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--output', type=Path, required=True, help='New candidate build JSON; existing files are never overwritten.')
    args = parser.parse_args()
    result = compile_proposal(json.loads(args.proposal.read_text(encoding='utf-8')),
                              json.loads(args.construction_snapshot.read_text(encoding='utf-8')), args.owner)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'candidate_id': result['capability']['id'], 'snapshot_sha256': result['snapshot']['digest'],
                      'certification': 'candidate', 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
