"""Benchmark adapters must preserve backend identity and unknown outcomes."""
import importlib
from pathlib import Path
from types import SimpleNamespace
import json
import pytest

pytest.importorskip('pebble')


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts/privacy-benchmark'))
    return importlib.import_module('run_official_pii')


def test_chinese_initializer_uses_the_generic_backend_not_opf(driver,monkeypatch):
    from src.adapters import rsi_chinese_privacy
    import gpu_workers
    monkeypatch.setattr(gpu_workers,'select_worker_gpu',lambda _:None)
    monkeypatch.setattr(driver.bench,'initialize',lambda _:None)
    backend=object()
    monkeypatch.setattr(rsi_chinese_privacy,'ChineseTools',lambda settings:backend)
    driver.initialize(str(driver.bench.REPO),'unused',{'format':'geneloop.privacy-chinese/v1'})
    assert driver.BACKEND is backend


def test_unknown_baseline_is_excluded_from_paired_coverage(driver,tmp_path):
    gold=[{'start':0,'end':2,'label':'PERSON'}]
    baseline=[{'id':0,'gold':gold,'evaluation_status':'evaluation_timeout'},
              {'id':1,'gold':gold,'core':{'pred':gold}}]
    path=tmp_path/'baseline.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in baseline))
    rows=[{'id':i,'gold':gold,'core':{'pred':gold}} for i in [0,1]]
    result=driver.compare_coverage(rows,path)
    assert result['PERSON']['gold_entities']==1 and result['PERSON']['lost']==0


def test_disabled_model_is_not_reported_as_a_failed_measurement(driver):
    from compare_frozen_runs import detector_availability
    rows={0:{'official_opf':{'enabled':False,'error_type':'not_enabled'},'gold':[]}}
    assert detector_availability(rows,'official_opf')['observation_statuses']=={'not_enabled':1}
