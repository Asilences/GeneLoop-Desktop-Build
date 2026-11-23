"""Frozen external PII evaluation; stores per-record data in PRIVATE output only.

No production rule mutations. Standard entity scoring is delegated to nervaluate.
This driver never submits gold entity fields to a detector or to learning_view.
"""
import argparse
import ast
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import json
import logging
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

# A reused environment may prepend an older checkout through a .pth file.
# Evaluation must import the source next to this driver, not that old snapshot.
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG = None
NATIVE = None
MODULE_ANALYZER = None
ANONYMIZER = None
CAPTURE = None
SCAN_EVENTS = None
CAPTURE_ENABLED = False
COLD_SECONDS = None


def canonical(label):
    return CONFIG['type_map'].get(label, label.upper())


def exact_occurrences(text, value):
    if not isinstance(value, str) or not value:
        return []
    result = []
    position = 0
    while (start := text.find(value, position)) >= 0:
        result.append((start, start + len(value)))
        position = start + len(value)
    return result


def load_records(root, dataset, config):
    spec = config['datasets'][dataset]
    path = root / spec['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == spec['sha256']
    audit = Counter()
    records = []
    if dataset.startswith('zh_'):
        raw = [json.loads(line) for line in path.read_text().splitlines()]
    else:
        import duckdb
        cursor = duckdb.connect().execute('select * from read_parquet(?)', [str(path)])
        names = [column[0] for column in cursor.description]
        raw = [dict(zip(names, row)) for row in cursor.fetchall()]
    assert len(raw) == spec['rows']
    for index, item in enumerate(raw):
        text = item['text']
        entities = item['entities']
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except json.JSONDecodeError:
                entities = ast.literal_eval(entities)
        gold = set()
        for entity in entities:
            audit['annotation_items'] += 1
            if dataset.startswith('zh_'):
                start, end = entity['start'], entity['end']
                assert 0 <= start < end <= len(text) and text[start:end] == entity['text']
                spans = [(start, end)]
                labels = [entity.get('type', entity.get('label'))]
            else:
                spans = exact_occurrences(text, entity['entity'])
                labels = entity['types']
                if not spans:
                    audit['unlocatable_annotation_items'] += 1
                if len(spans) > 1:
                    audit['repeated_value_annotation_items'] += 1
                if len(labels) != 1:
                    audit['multi_label_annotation_items'] += 1
            for label in labels:
                for start, end in spans:
                    gold.add((start, end, config['type_map'].get(label, label.upper())))
        ordered = sorted(gold)
        audit['gold_spans'] += len(gold)
        audit['overlapping_adjacent_spans'] += sum(b[0] < a[1] for a, b in zip(ordered, ordered[1:]))
        records.append({'id': index, 'dataset': dataset, 'text': text,
                        'gold': [{'start': s, 'end': e, 'label': label} for s, e, label in ordered]})
    return records, dict(audit)


def capture_operations(anonymizer):
    """Observe official pre-replacement coordinates; do not infer from output.

    Even mask output can change length when upstream retains overlapping types.
    This pinned offline adapter observes the actual operation without changing it.
    """
    import inspect
    import importlib.metadata
    assert importlib.metadata.version('presidio-anonymizer') == '2.2.365'
    original = anonymizer._operate
    assert list(inspect.signature(original).parameters)[:4] == ['text', 'pii_entities', 'operators_metadata', 'operator_type']

    def observed(*args, **kwargs):
        if CAPTURE_ENABLED:
            assert not args
            text = kwargs['text']
            spans = [{'start': entity.start, 'end': entity.end, 'label': canonical(entity.entity_type)}
                     for entity in kwargs['pii_entities']]
            assert all(0 <= span['start'] < span['end'] <= len(text) for span in spans)
            CAPTURE.append((len(text), spans))
        return original(*args, **kwargs)

    anonymizer._operate = observed


def initialize(config_path):
    global CONFIG, NATIVE, MODULE_ANALYZER, ANONYMIZER, CAPTURE, SCAN_EVENTS, COLD_SECONDS
    initialized_at = time.perf_counter()
    CONFIG = json.loads(Path(config_path).read_text())
    if CONFIG.get('privacy_policy_sha256'):
        from src.adapters.rsi_privacy_policy import POLICY, POLICY_SHA256
        assert CONFIG['privacy_policy_sha256']==POLICY_SHA256, 'privacy_policy_drift'
        assert CONFIG['supported_text_tags']==POLICY['text']['declared_categories'], 'privacy_evaluation_scope_drift'
    logging.disable(logging.CRITICAL)
    # Native recognizer, offline bundled suffix list. No network/cache downloads.
    import tldextract
    tldextract.extract = tldextract.TLDExtract(suffix_list_urls=())
    from presidio_analyzer import AnalyzerEngine
    from src.adapters import rsi_text_privacy as text_privacy
    from src.adapters import geneloop_privacy as privacy
    if Path(privacy.__file__).resolve() != REPO / 'src/adapters/geneloop_privacy.py':
        raise RuntimeError('privacy_benchmark_source_mismatch')
    MODULE_ANALYZER, ANONYMIZER = text_privacy._presidio()
    NATIVE = AnalyzerEngine(nlp_engine=MODULE_ANALYZER.nlp_engine, supported_languages=['en', 'zh'])
    CAPTURE = []
    SCAN_EVENTS = []

    capture_operations(ANONYMIZER)
    original_scan = privacy._scan

    def observed_scan(text, **options):
        try:
            return original_scan(text, **options)
        except subprocess.CalledProcessError as exc:
            SCAN_EVENTS.append('credential_hit' if exc.returncode == 1 else 'scanner_error')
            raise
        except Exception:
            SCAN_EVENTS.append('scanner_error')
            raise

    privacy._scan = observed_scan
    # Force initialization before timing per-document hot inference.
    assert ANONYMIZER is not None
    COLD_SECONDS = time.perf_counter() - initialized_at


def module_result(text):
    from src.adapters.geneloop_privacy import learning_view, PrivacyRejected
    SCAN_EVENTS.clear()
    started = time.perf_counter()
    try:
        output = learning_view({'text': text})
        return {'accepted': True, 'text': output.get('text', ''),
                'output_sha256': hashlib.sha256(json.dumps(output,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
                'seconds': time.perf_counter() - started}
    except PrivacyRejected as error:
        reason = SCAN_EVENTS[-1] if SCAN_EVENTS else 'policy_or_processing_rejection'
        return {'accepted': False, 'reason': reason, 'decision_reason':getattr(error,'reason','unavailable'),
                'decision_detector':getattr(error,'detector',None),
                'seconds': time.perf_counter() - started}


def character_metrics(text, gold, pred):
    true = set()
    guessed = set()
    for span in gold:
        true.update(range(span['start'], span['end']))
    for span in pred:
        guessed.update(range(span['start'], span['end']))
    return {'gold_chars': len(true), 'covered_gold_chars': len(true & guessed),
            'non_pii_chars': len(text) - len(true), 'masked_non_pii_chars': len(guessed - true),
            'gold_entities': len(gold), 'fully_covered_entities': sum(set(range(s['start'], s['end'])) <= guessed for s in gold)}


def context_chunks(text, gold, minimum):
    intervals = sorted((span['start'], span['end']) for span in gold)
    end = 0
    chunks = []
    for start, stop in intervals:
        if start - end >= minimum:
            chunks.append(text[end:start])
        end = max(end, stop)
    if len(text) - end >= minimum:
        chunks.append(text[end:])
    return chunks


def evaluate_record(record):
    global CAPTURE_ENABLED
    from src.adapters.rsi_text_privacy import anonymize_text, _has_han, _scan
    text, gold = record['text'], record['gold']
    result = {'id': record['id'], 'dataset': record['dataset'], 'gold': gold, 'chars': len(text),
              'worker_pid': os.getpid(), 'cold_init_seconds': COLD_SECONDS}
    started = time.perf_counter()
    CAPTURE.clear()
    CAPTURE_ENABLED = True
    error = None
    try:
        findings = NATIVE.analyze(text=text, language='en', score_threshold=CONFIG['score_threshold'])
        if _has_han(text):
            findings += NATIVE.analyze(text=text, language='zh', score_threshold=CONFIG['score_threshold'])
        native_output = ANONYMIZER.anonymize(text=text, analyzer_results=findings).text
        pred = CAPTURE[-1][1] if CAPTURE else []
    except Exception as exc:
        error = type(exc).__name__
        pred, native_output = [], text
    finally:
        CAPTURE_ENABLED = False
    result['native'] = {'pred': pred, 'seconds': time.perf_counter() - started,
                        'error_type': error, 'chars': character_metrics(text, gold, pred)}
    CAPTURE.clear()
    CAPTURE_ENABLED = True
    started = time.perf_counter()
    error = None
    try:
        core_output = anonymize_text(text)
        pred = CAPTURE[-1][1] if CAPTURE else []
    except Exception as exc:
        error = type(exc).__name__
        pred, core_output = [], text
    finally:
        CAPTURE_ENABLED = False
    result['core'] = {'pred': pred, 'seconds': time.perf_counter() - started,
                     'error_type': error, 'chars': character_metrics(text, gold, pred)}
    started = time.perf_counter()
    try:
        _scan(text)
        gitleaks = {'flagged': False}
    except subprocess.CalledProcessError as exc:
        gitleaks = {'flagged': exc.returncode == 1, 'error': exc.returncode != 1}
    except Exception:
        gitleaks = {'error': True}
    gitleaks['seconds'] = time.perf_counter() - started
    result['gitleaks'] = gitleaks
    full = module_result(text)
    chunks = context_chunks(text, gold, CONFIG['semantics_proxy_min_non_pii_chunk_chars'])
    for name, output in [('native', native_output), ('core', core_output)]:
        result[name]['context_chunks'] = len(chunks)
        result[name]['retained_context_chunks'] = sum(chunk in output for chunk in chunks) if not result[name]['error_type'] else 0
    if full['accepted']:
        output = full.pop('text')
        full['gold_entities'] = len(gold)
        full['literal_residual_entities'] = sum(text[s['start']:s['end']] in output for s in gold)
        if CONFIG.get('module_residual_by_gold_type', False):
            full['by_gold_type'] = {label: {
                'gold_entities': sum(s['label'] == label for s in gold),
                'literal_residual_entities': sum(s['label'] == label and text[s['start']:s['end']] in output for s in gold),
            } for label in sorted({s['label'] for s in gold})}
        full['any_literal_residual'] = full['literal_residual_entities'] > 0
        full['context_chunks'] = len(chunks)
        full['retained_context_chunks'] = sum(chunk in output for chunk in chunks)
    result['module'] = full
    return result


def standard_scores(gold, predicted):
    from nervaluate import Evaluator
    tags = sorted({s['label'] for row in gold + predicted for s in row})
    def convert(rows):
        return [[dict(s, end=s['end'] - 1) for s in row] for row in rows]
    evaluation = Evaluator(convert(gold), convert(predicted), tags=tags, loader='dict').evaluate()
    overall = {scheme: asdict(value) for scheme, value in evaluation['overall'].items()}
    entities = {tag: {scheme: asdict(value) for scheme, value in schemes.items()} for tag, schemes in evaluation['entities'].items()}
    present_tags = sorted({s['label'] for row in gold for s in row})
    macro = {scheme: {metric: statistics.mean(entities[tag][scheme][metric] for tag in present_tags)
                     for metric in ('precision', 'recall', 'f1')} for scheme in overall} if present_tags else {}
    return {'overall': overall, 'macro_gold_present_tags': macro, 'entities': entities}


def timing(values):
    values = sorted(values)
    if not values:
        return {}
    return {'sum_seconds': sum(values), 'p50_seconds': statistics.median(values),
            'p95_seconds': values[min(len(values) - 1, int(len(values) * .95))]}


def summarize(rows, audit):
    result = {'rows': len(rows), 'annotation_audit': audit}
    result['worker_cold_init_seconds'] = list({r['worker_pid']: r['cold_init_seconds'] for r in rows}.values())
    for name in ('native', 'core'):
        gold = [r['gold'] for r in rows]
        predictions = [r[name]['pred'] for r in rows]
        supported = set(CONFIG['supported_text_tags'])
        chars = Counter()
        for row in rows:
            chars.update(row[name]['chars'])
        result[name] = {'full_taxonomy': standard_scores(gold, predictions),
                        'processing_error_types': dict(Counter(r[name]['error_type'] for r in rows if r[name].get('error_type'))),
                        'supported_subset': standard_scores([[s for s in r if s['label'] in supported] for r in gold],
                                                            [[s for s in r if s['label'] in supported] for r in predictions]),
                        'character_counts': dict(chars), 'timing': timing([r[name]['seconds'] for r in rows]),
                        'context_chunks': sum(r[name]['context_chunks'] for r in rows),
                        'retained_context_chunks': sum(r[name]['retained_context_chunks'] for r in rows)}
    accepted = [r['module'] for r in rows if r['module']['accepted']]
    result['module'] = {'accepted': len(accepted), 'rejected': len(rows) - len(accepted),
                        'rejection_reasons': dict(Counter(r['module']['reason'] for r in rows if not r['module']['accepted'])),
                        'accepted_with_literal_residual': sum(r['any_literal_residual'] for r in accepted),
                        'literal_residual_entities': sum(r['literal_residual_entities'] for r in accepted),
                        'accepted_gold_entities': sum(r['gold_entities'] for r in accepted),
                        'context_chunks': sum(r['context_chunks'] for r in accepted),
                        'retained_context_chunks': sum(r['retained_context_chunks'] for r in accepted),
                        'timing': timing([r['module']['seconds'] for r in rows])}
    if CONFIG.get('module_residual_by_gold_type', False):
        labels = sorted({label for row in accepted for label in row['by_gold_type']})
        result['module']['by_gold_type'] = {label: {
            field: sum(row['by_gold_type'].get(label, {}).get(field, 0) for row in accepted)
            for field in ('gold_entities', 'literal_residual_entities')
        } for label in labels}
    result['gitleaks'] = {'flagged': sum(r['gitleaks'].get('flagged', False) for r in rows),
                         'errors': sum(r['gitleaks'].get('error', False) for r in rows),
                         'timing': timing([r['gitleaks']['seconds'] for r in rows])}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--audit-only', action='store_true')
    parser.add_argument('--score-only', action='store_true')
    args = parser.parse_args()
    global CONFIG
    CONFIG = json.loads(args.config.read_text())
    args.output.mkdir(exist_ok=True, parents=True)
    manifest = {'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
                'config': CONFIG, 'datasets': {}, 'cloud_requests': 0, 'cloud_api_cost': 0}
    for dataset in ('zh_formal', 'zh_chat', 'en_test'):
        records, audit = load_records(args.root, dataset, CONFIG)
        print(json.dumps({'dataset': dataset, 'rows': len(records), 'audit': audit}), flush=True)
        if args.audit_only:
            continue
        private_path = args.output / f'{dataset}-records.jsonl'
        started = time.perf_counter()
        if args.score_only:
            rows = [json.loads(line) for line in private_path.read_text().splitlines()]
        else:
            assert not private_path.exists(), 'Preserve existing runs; choose a new output directory'
            rows = []
            with private_path.open('w') as stream:
                with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize, initargs=(str(args.config.resolve()),)) as pool:
                    for row in pool.map(evaluate_record, records, chunksize=16):
                        rows.append(row)
                        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                        if len(rows) % 500 == 0:
                            stream.flush()
                            print(json.dumps({'dataset': dataset, 'completed': len(rows)}), flush=True)
        manifest['datasets'][dataset] = summarize(rows, audit)
        manifest['datasets'][dataset]['wall_seconds'] = time.perf_counter() - started
        (args.output / 'pii-summary.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    if args.audit_only:
        print('audit_only_no_detector_invocations', flush=True)


if __name__ == '__main__':
    main()
