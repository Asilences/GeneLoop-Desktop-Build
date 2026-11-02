"""Learning route state-machine diagnostics; model/render children are replaced.

Native contract import remains real. These fixtures do not establish learning
success, source quality, paid API behavior, or production readiness.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.adapters.capability_materials import CapabilityMaterials
from src.adapters.capability_scene import reference
from tests.test_capability_improvement import put
from tests.test_source_program_bridge import library
from scenarios.remotion_edit.structured import capability_learning as module


def fixture(tmp_path,monkeypatch):
    evidence=put(tmp_path/'native-evidence.json',{'diagnostic':True})
    context=put(tmp_path/'context.json',{})
    routes=put(tmp_path/'routes.json',{'format':'source_learning_routes_v1','owner':'owner','routes':[
        {'scope':'source-test','backend':'source_program','runs':[{'run':str(tmp_path/'native'),
         'role':'training','context':context,'evidence':[evidence]}]}]})
    ledger=tmp_path/'ledger';ledger.mkdir();put(ledger/'budget-checkpoint.json',{'request_count':19,'reserved_usd':1.5});(ledger/'cost-ledger.jsonl').write_text('original-ledger\n', encoding='utf-8')
    adapter=SimpleNamespace(plan={'owner':'owner','id':'diagnostic','learning_routes':routes,'ledger_root':str(ledger)},
        materials=CapabilityMaterials(tmp_path/'materials','owner'),opportunity_key=lambda j:'original-opportunity')
    job={'id':'job','execution_scope':'source-test'}
    result={'status':'deferred','construction_gap':{'reason':'missing_primitive','requirement':'diagnostic'}}
    attempt=tmp_path/'attempt';attempt.mkdir();put(attempt/'result.json',result)
    monkeypatch.setattr(module,'collect',lambda p:({},{}))
    import scenarios.remotion_edit.structured.capability_observations as observations
    monkeypatch.setattr(observations,'inspect_run',lambda *a:{'scope':'source-test','evidence':[evidence]})
    calls=[]
    def child(args,**kw):
        calls.append(args);out=Path(args[args.index('--output')+1]);out.mkdir()
        if out.name=='learn':
            put(out/'learning-summary.json',{'observed_model_usd':None,'diagnostic':True})
        else:library(out/'library.json')
        return 0
    monkeypatch.setattr(module,'run_child',child)
    return adapter,job,result,attempt,calls


def test_dispatch_calls_existing_entries_registers_and_never_replays_same_attempt(tmp_path,monkeypatch):
    adapter,job,result,attempt,calls=fixture(tmp_path,monkeypatch)
    ledger=Path(adapter.plan['ledger_root']);before={p.name:p.read_bytes() for p in ledger.iterdir()}
    outcome=module.acquire_source(adapter,job,result,attempt)
    assert outcome['status']=='registered' and len(adapter.materials.records())==1
    assert len(calls)==2 and calls[0][1].endswith('learn_programs.py') and calls[1][1].endswith('certify_programs.py')
    assert calls[0][calls[0].index('--max-output-tokens')+1]=='393216'
    assert calls[0][calls[0].index('--ledger-root')+1]==str(ledger)
    assert all((ledger/name).read_bytes()==raw for name,raw in before.items())
    assert module.acquire_source(adapter,job,result,attempt)['status']=='deferred'
    assert len(calls)==2


def test_failed_native_certification_is_preserved_not_registered_or_retried(tmp_path,monkeypatch):
    adapter,job,result,attempt,calls=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(module,'run_child',lambda *a,**k:1)
    outcome=module.acquire_source(adapter,job,result,attempt)
    assert outcome['reason']=='source_learn_process_failed' and adapter.materials.records()==[]
    monkeypatch.setattr(module,'run_child',lambda *a,**k:pytest.fail('interrupted attempt replayed'))
    assert module.acquire_source(adapter,job,result,attempt)['status']=='deferred'


def test_missing_or_incompatible_evidence_never_dispatches(tmp_path,monkeypatch):
    adapter,job,result,attempt,calls=fixture(tmp_path,monkeypatch)
    result['construction_gap']['reason']='insufficient_evidence'
    assert module.acquire_source(adapter,job,result,attempt)['status']=='deferred' and not calls
    result['construction_gap']['reason']='missing_primitive'
    (tmp_path/'native-evidence.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError,match='evidence_changed'):module.acquire_source(adapter,job,result,attempt)
    assert not calls
