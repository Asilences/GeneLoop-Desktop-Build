"""Post-hoc attribution, not a detector score or a change to benchmark gold.

Uses the pinned upstream validator/pattern on annotated card values solely to
explain completed R2 misses. These gold-selected validation calls are distinct
from benchmark predictions, where gold never enters a detector.
"""
import argparse
from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import unicodedata

import regex
import run_pii as bench


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--r2-results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    from presidio_analyzer.predefined_recognizers import CreditCardRecognizer
    from src.adapters.rsi_text_privacy import _normalized_view
    card=CreditCardRecognizer()
    config=json.loads(args.config.read_text())
    patterns=[regex.compile(p.regex,card.global_regex_flags) for p in card.patterns]
    summary={'purpose':'post-hoc upstream card validation attribution; not a detection score',
        'gold_selected_values_passed_to_validator_only':True,'gold_changed':False,'detector_predictions_changed':False,
        'validator_source_sha256':hashlib.sha256(inspect.getsource(CreditCardRecognizer).encode()).hexdigest(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'datasets':{}}
    for dataset in ('zh_formal','zh_chat','en_test'):
        rows,_=bench.load_records(args.root,dataset,config)
        previous={r['id']:r for r in map(json.loads,(args.r2_results/f'{dataset}-records.jsonl').read_text().splitlines())}
        counts=Counter();groups=Counter()
        for row in rows:
            canonical,starts,ends=_normalized_view(row['text'])
            exact=set()
            for pattern in patterns:
                for found in pattern.finditer(canonical):
                    a,b=found.span()
                    exact.add((a,b) if starts is None else (starts[a],ends[b-1]))
            old=previous[row['id']]
            assert old['gold']==row['gold']
            native={i for p in old['native']['pred'] for i in range(p['start'],p['end'])}
            core={i for p in old['core']['pred'] for i in range(p['start'],p['end'])}
            for span in row['gold']:
                if span['label']!='CREDIT_CARD':continue
                value=unicodedata.normalize('NFKC',row['text'][span['start']:span['end']])
                try:valid=bool(card.validate_result(value));status='valid' if valid else 'invalid'
                except (ValueError,TypeError):valid=None;status='validation_error_non_digit'
                full=any(pattern.fullmatch(value) for pattern in patterns)
                in_document=(span['start'],span['end']) in exact
                indices=set(range(span['start'],span['end']))
                counts.update(gold_entities=1,valid_luhn=int(valid is True),invalid_luhn=int(valid is False),validation_error=int(valid is None),
                    upstream_full_pattern_on_value=int(full),upstream_exact_pattern_in_document=int(in_document),
                    pattern_value_but_not_document=int(full and not in_document),native_fully_covered=int(indices<=native),r2_core_fully_covered=int(indices<=core))
                groups[f'{status}:pattern_value={bool(full)}:pattern_document={in_document}']+=1
        summary['datasets'][dataset]={'counts':dict(counts),'combinations':dict(groups)}
    args.output.write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary['datasets']))


if __name__=='__main__':
    main()
