"""Run official local candidates on text-only inputs; gold stays in another process."""
import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, TimeoutError, wait
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import sys
import time
import warnings

from pebble import ProcessPool

BACKEND = None
SPEC = None
INIT_SECONDS = None


def initialize(repo, config, settings):
    global BACKEND, SPEC, INIT_SECONDS
    sys.path.insert(0, repo)
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings('ignore', category=DeprecationWarning)
    from src.adapters.rsi_privacy_candidates import OfficialTools
    SPEC = config
    started = time.perf_counter()
    BACKEND = OfficialTools(settings)
    INIT_SECONDS = time.perf_counter() - started


def predict(row):
    assert set(row) == {'id','dataset','phase','text'}, 'detector_input_must_not_include_gold'
    started = time.perf_counter()
    result = {key:row[key] for key in ('id','dataset','phase')}
    result.update(chars=len(row['text']), text_sha256=hashlib.sha256(row['text'].encode()).hexdigest(), cold_seconds=INIT_SECONDS)
    if BACKEND.detector is not None:
        spans = BACKEND.native_findings(row['text'])
        result['native_pred'] = [dict(s, label=SPEC['opf']['all_labels_map'][s['label']]) for s in spans]
        mapping = BACKEND.spec['opf']['label_map']
        result['pred'] = [dict(s, label=mapping[s['label']]) for s in spans if s['label'] in mapping]
        result['native_label_counts'] = dict(Counter(s['label'] for s in spans))
    if BACKEND.scanner is not None:
        result['credential_findings'] = BACKEND.credential_count(row['text'])
    result.update(error=None, seconds=time.perf_counter() - started)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--settings',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,required=True)
    args=parser.parse_args()
    assert not args.output.exists(), 'Preserve previous attempts'
    args.output.mkdir(parents=True,mode=0o700)
    config=json.loads(args.config.read_text())
    settings=json.loads(args.settings.read_text())
    rows=[json.loads(line) for line in args.inputs.read_text().splitlines()]
    assert all(set(row)=={'id','dataset','phase','text'} for row in rows)
    assert len({(row['dataset'],row['id']) for row in rows})==len(rows)
    manifest={'candidate':'official_opf_and_credsweeper','inputs_sha256':hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
              'config_sha256':hashlib.sha256(args.config.read_bytes()).hexdigest(),
              'settings_sha256':hashlib.sha256(args.settings.read_bytes()).hexdigest(),
              'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'versions':{name:importlib.metadata.version(name) for name in ('opf','credsweeper','torch','onnxruntime','tiktoken','numpy','Pebble')},
              'gold_passed_to_detector':False,'cloud_requests':0,'workers':args.workers,
              'source_manifest_sha256':hashlib.sha256((args.repo/'config/rsi-privacy-candidate-tools.json').read_bytes()).hexdigest(),
              'adapter_sha256':hashlib.sha256((args.repo/'src/adapters/rsi_privacy_candidates.py').read_bytes()).hexdigest(),
              'sources':config['opf'],'loading':{'model_files_verified':True,'source_files_verified':True},
              'total':len(rows)}
    pending={};todo=iter(rows);statuses=Counter();completed=0
    started=time.perf_counter()
    with (args.output/'predictions-private.jsonl').open('w') as stream, ProcessPool(
            max_workers=args.workers,initializer=initialize,
            initargs=(str(args.repo.resolve()),config,settings)) as pool:
        def submit():
            try:row=next(todo)
            except StopIteration:return False
            future=pool.schedule(predict,args=(row,),timeout=config['per_call_timeout_seconds'])
            pending[future]=row
            return True
        for _ in range(args.workers):submit()
        while pending:
            ready,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in ready:
                row=pending.pop(future)
                try:result=future.result()
                except TimeoutError:
                    result={key:row[key] for key in ('id','dataset','phase')}
                    result.update(error='evaluation_timeout',seconds=config['per_call_timeout_seconds'])
                except Exception as error:
                    result={key:row[key] for key in ('id','dataset','phase')}
                    result.update(error='evaluation_error',error_type=type(error).__name__)
                stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush()
                completed+=1;statuses[result['error'] or 'available']+=1
                if completed%100==0 or completed==len(rows):
                    print(json.dumps({'completed':completed,'total':len(rows),'statuses':dict(statuses),'seconds':time.perf_counter()-started}),flush=True)
                submit()
    manifest.update(status_counts=dict(statuses),wall_seconds=time.perf_counter()-started)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    assert completed==len(rows)
    print(json.dumps({'completed':completed,'statuses':dict(statuses),'finished':True}),flush=True)


if __name__=='__main__':main()
