"""Frozen hash-selected pilot of the generic contract; raw rows stay private."""
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import time
import run_pii as bench

DATASETS = ('zh_formal', 'zh_chat', 'en_test')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scalar', action='store_true')
    parser.add_argument('--limit-per-dataset', type=int, default=12)
    args = parser.parse_args()
    total_started = time.perf_counter()
    assert not args.output.exists()
    args.output.mkdir(mode=0o700)
    bench.initialize(str(args.config))
    from src.adapters.rsi_privacy_candidates import candidate_context
    from src.adapters import geneloop_privacy as privacy
    from src.adapters.privacy_diagnostics import observe_privacy
    backend = None
    if args.settings:
        from src.adapters.rsi_chinese_privacy import ChineseTools
        backend = ChineseTools(json.loads(args.settings.read_text()))
    if args.scalar:
        privacy.text_batch_context = lambda _: nullcontext()
    rows = []
    started = time.perf_counter()
    with candidate_context(backend):
        for dataset in DATASETS:
            records, _ = bench.load_records(args.root, dataset, bench.CONFIG)
            records.sort(key=lambda r: hashlib.sha256((dataset+':'+str(r['id'])).encode()).digest())
            for record in records[:args.limit_per_dataset]:
                with observe_privacy() as stages:
                    row = bench.evaluate_record(record)
                row['stages'] = stages
                rows.append(row)
                with (args.output/'rows-private.jsonl').open('a') as stream:
                    stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        packet_texts = []
        for dataset in ('zh_formal', 'zh_chat'):
            records, _ = bench.load_records(args.root, dataset, bench.CONFIG)
            records.sort(key=lambda r: hashlib.sha256((dataset+':'+str(r['id'])).encode()).digest())
            packet_texts.extend(record['text'] for record in records[:4])
        packet_started = time.perf_counter()
        with observe_privacy() as packet_stages:
            try:
                output = privacy.learning_view({'segments': packet_texts, 'count': len(packet_texts)})
                packet = {'accepted':True, 'sha256':hashlib.sha256(json.dumps(output,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
            except privacy.PrivacyRejected as error:
                packet = {'accepted':False, 'reason':error.reason, 'detector':error.detector}
        packet.update(seconds=time.perf_counter()-packet_started, stages=packet_stages)
    summary = {'records':len(rows), 'wall_seconds':time.perf_counter()-started,
        'total_seconds_including_initialization':time.perf_counter()-total_started, 'multi_field_packet':packet,
        'source_commit':__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=bench.REPO,text=True).strip(),
        'settings_sha256':hashlib.sha256(args.settings.read_bytes()).hexdigest() if args.settings else None,
        'selection':'sha256(dataset:id), ascending; no gold used', 'scalar':args.scalar,
        'source_files':{name:hashlib.sha256((bench.REPO/name).read_bytes()).hexdigest() for name in [
            'src/adapters/geneloop_privacy.py','src/adapters/rsi_text_privacy.py','src/adapters/rsi_chinese_privacy.py',
            'src/adapters/rsi_privacy_candidates.py','config/rsi-privacy-chinese-tools.json']},
        'cloud_requests':0, 'datasets':{}}
    for dataset in DATASETS:
        items=[r for r in rows if r['dataset']==dataset]
        summary['datasets'][dataset]={'records':len(items), 'accepted':sum(r['module']['accepted'] for r in items),
            'core_errors':sum(bool(r['core']['error_type']) for r in items),
            'gold_entities':sum(r['core'].get('chars',{}).get('gold_entities',0) for r in items),
            'fully_covered_entities':sum(r['core'].get('chars',{}).get('fully_covered_entities',0) for r in items),
            'masked_non_pii_chars':sum(r['core'].get('chars',{}).get('masked_non_pii_chars',0) for r in items),
            'non_pii_chars':sum(r['core'].get('chars',{}).get('non_pii_chars',0) for r in items)}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
