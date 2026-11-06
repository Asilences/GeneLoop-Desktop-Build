"""Export trusted booking ownership without model calls or ledger mutations."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters.efficiency_rsi_registry import StudyRequestRegistry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--provider-request-refs', type=Path, required=True)
    parser.add_argument('--public', action='store_true')
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    registry = StudyRequestRegistry(load(args.study), args.journal)
    value=registry.export(load(args.provider_request_refs))
    if args.public:
        from src.adapters.geneloop_privacy import admit_publication
        admit_publication(value)
    print(json.dumps(value, ensure_ascii=False,
                     indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
