"""Attribute frozen R2 text-layer changes; no gold enters a recognizer.

Public summaries contain counts only. Full spans and source text stay in the
isolated output. This is retrospective development analysis, not unseen testing.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

VARIANTS = ('current', 'no_script_filter', 'no_prose_protection', 'raw_all', 'split_views', 'raw_person_only', 'union_person_views')
BENCH = None
TEXT = None


def initialize(config):
    global BENCH, TEXT
    import run_pii
    from src.adapters import rsi_text_privacy
    BENCH, TEXT = run_pii, rsi_text_privacy
    BENCH.initialize(config)


def protected(text):
    return ([m.span(1) for m in TEXT.STAT_ABBREVIATION.finditer(text)]
            + [m.span() for m in TEXT.STAT_SAMPLE_SIZE.finditer(text)]
            + [m.span() for m in TEXT._PROTOCOL_WORD.finditer(text)])


def select_findings(items, text, starts=None, ends=None, *, script=True, prose=True, kind=None, ner_labels=None, exclude_ner=()):
    findings = []
    protected_spans = protected(text)
    for language, results in items:
        for finding in copy.deepcopy(results):
            ner = finding.recognition_metadata.get('recognizer_name') == 'SpacyRecognizer'
            if kind is not None and ner != (kind == 'ner'):
                continue
            if ner and (finding.entity_type in exclude_ner or ner_labels is not None and finding.entity_type not in ner_labels):
                continue
            if ner:
                a, b = finding.start, finding.end
                if prose and any(x <= a and b <= y for x, y in protected_spans):
                    continue
                if script and TEXT._has_han(text[a:b]) != (language == 'zh'):
                    continue
            if starts is not None:
                finding.start, finding.end = starts[finding.start], ends[finding.end - 1]
            findings.append(finding)
    return findings


def render(text, findings):
    BENCH.CAPTURE.clear()
    BENCH.CAPTURE_ENABLED = True
    try:
        output = BENCH.ANONYMIZER.anonymize(text=text, analyzer_results=findings).text
        spans = BENCH.CAPTURE[-1][1] if BENCH.CAPTURE else []
    finally:
        BENCH.CAPTURE_ENABLED = False
    return output, spans


def signature(spans):
    return sorted((s['start'], s['end'], s['label']) for s in spans)


def evaluate(record):
    text, gold = record['text'], record['gold']
    analyzer = BENCH.MODULE_ANALYZER
    original = analyzer.analyze
    canonical, starts, ends = TEXT._normalized_view(text)
    calls = []
    def capture(*args, **kwargs):
        results = original(*args, **kwargs)
        assert kwargs['text'] == canonical
        calls.append((kwargs['language'], copy.deepcopy(results)))
        return results
    BENCH.CAPTURE.clear(); BENCH.CAPTURE_ENABLED = True
    try:
        with patch.object(analyzer, 'analyze', capture):
            actual_output = TEXT.anonymize_text(text)
        actual_spans = BENCH.CAPTURE[-1][1] if BENCH.CAPTURE else []
    finally:
        BENCH.CAPTURE_ENABLED = False
    assert signature(actual_spans) == record['r2_signature'], 'frozen_r2_prediction_drift'
    manual_output, manual_spans = render(text, select_findings(calls, canonical, starts, ends))
    assert manual_output == actual_output and signature(manual_spans) == signature(actual_spans)
    if canonical == text:
        raw_calls = calls
    else:
        raw_calls = []
        for language in ('en', 'zh'):
            if language == 'zh' and not TEXT._has_han(text):
                continue
            entities = sorted(set(analyzer.get_supported_entities(language=language)) - TEXT.NON_IDENTITY_ENTITIES - {'URL'})
            raw_calls.append((language, original(text=text, language=language, entities=entities, score_threshold=.4)))
    candidates = {
        'current': (actual_output, actual_spans),
        'no_script_filter': render(text, select_findings(calls, canonical, starts, ends, script=False)),
        'no_prose_protection': render(text, select_findings(calls, canonical, starts, ends, prose=False)),
        'raw_all': render(text, select_findings(raw_calls, text)),
        'split_views': render(text, select_findings(calls, canonical, starts, ends, kind='pattern') + select_findings(raw_calls, text, kind='ner')),
        'raw_person_only': render(text, select_findings(calls, canonical, starts, ends, exclude_ner=('PERSON',))
            + select_findings(raw_calls, text, kind='ner', ner_labels={'PERSON'})),
        'union_person_views': render(text, select_findings(calls, canonical, starts, ends)
            + select_findings(raw_calls, text, kind='ner', ner_labels={'PERSON'})),
    }
    chunks = BENCH.context_chunks(text, gold, BENCH.CONFIG['semantics_proxy_min_non_pii_chunk_chars'])
    baseline_covered = {i for s in actual_spans for i in range(s['start'], s['end'])}
    result = {'id': record['id'], 'dataset': record['dataset'], 'normalization_changed':canonical != text, 'variants':{}}
    for name, (output, spans) in candidates.items():
        covered = {i for s in spans for i in range(s['start'], s['end'])}
        by_type = defaultdict(Counter)
        for span in gold:
            locations = set(range(span['start'], span['end']))
            now, before = locations <= covered, locations <= baseline_covered
            by_type[span['label']].update(gold_entities=1, fully_covered_entities=int(now),
                gained_over_current=int(now and not before), lost_from_current=int(before and not now))
        result['variants'][name] = {'chars':BENCH.character_metrics(text,gold,spans),
            'context_chunks':len(chunks), 'retained_context_chunks':sum(chunk in output for chunk in chunks),
            'by_gold_type':{key:dict(value) for key,value in by_type.items()}}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--r2-results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--limit',type=int,default=0)
    args=parser.parse_args()
    import run_pii as bench
    config=json.loads(args.config.read_text())
    args.output.mkdir(parents=True,mode=0o700,exist_ok=False)
    summary={'analysis':'frozen-r2-cached-rule-ablation','config_sha256':hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'workers':args.workers,
        'gold_passed_to_detector':False,'new_gitleaks_or_full_module_calls':0,'independent_unseen_evaluation':False,'datasets':{}}
    for name in ('zh_formal','zh_chat','en_test'):
        records,_=bench.load_records(args.inputs,name,config)
        previous={row['id']:row for row in map(json.loads,(args.r2_results/f'{name}-records.jsonl').read_text().splitlines())}
        if args.limit:records=records[:args.limit]
        for row in records:
            assert row['gold']==previous[row['id']]['gold'] and len(row['text'])==previous[row['id']]['chars']
            row['r2_signature']=signature(previous[row['id']]['core']['pred'])
        started=time.perf_counter();totals={variant:{'chars':Counter(),'by_gold_type':defaultdict(Counter),'context_chunks':0,'retained_context_chunks':0} for variant in VARIANTS}
        changed=0
        with (args.output/f'{name}-private.jsonl').open('w') as stream:
            with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(str(args.config),)) as pool:
                for i,row in enumerate(pool.map(evaluate,records,chunksize=16),1):
                    stream.write(json.dumps(row)+'\n');changed+=row['normalization_changed']
                    for variant,values in row['variants'].items():
                        totals[variant]['chars'].update(values['chars'])
                        for label,counts in values['by_gold_type'].items():totals[variant]['by_gold_type'][label].update(counts)
                        for field in ('context_chunks','retained_context_chunks'):totals[variant][field]+=values[field]
                    if i%500==0:print(json.dumps({'dataset':name,'completed':i}),flush=True)
        summary['datasets'][name]={'rows':len(records),'normalization_changed_rows':changed,'wall_seconds':time.perf_counter()-started,'variants':totals}
        (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps({'dataset':name,'finished':len(records)}),flush=True)


if __name__=='__main__':main()
