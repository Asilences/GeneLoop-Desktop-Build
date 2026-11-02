"""Future-run preparation diagnostics; no historical freeze or model is changed."""
import json
import shutil
import sys
from datetime import datetime,timezone
import pytest
from scenarios.paper_proofreading.frontier import freeze
from tests.test_frontier_oracle import project


def test_deadline_requires_a_timezone_and_a_future_instant():
    future='2040-01-01T08:00:00+08:00'
    expected=datetime(2040,1,1,tzinfo=timezone.utc).timestamp()
    assert freeze.deadline_epoch(future,now=0)==expected
    assert freeze.deadline_epoch('2040-01-01T00:00:00Z',now=0)==expected
    for value in [None,'invalid','2040-01-01T00:00:00']:
        with pytest.raises(ValueError,match='frontier_deadline_'):freeze.deadline_epoch(value,now=0)
    with pytest.raises(ValueError,match='deadline_expired'):freeze.deadline_epoch(future,now=expected)


def test_new_freeze_is_reusable_and_D_has_no_C_construction_restriction(tmp_path,monkeypatch):
    inputs=tmp_path/'inputs';inputs.mkdir()
    source=project(inputs/'atc-v0.zip',{'main.tex':r'\cite{A}\bibliography{refs}',
                                     'refs.bib':'@article{A,title={One}}'})
    for name in ['atc-v1','qlora-v0','qlora-v1','qlora-v2']:shutil.copyfile(source,inputs/(name+'.zip'))
    (inputs/'manifest.json').write_text('{"scope":"synthetic protocol diagnostic only"}',encoding='utf8')
    out=tmp_path/'frozen-v1'
    monkeypatch.setattr(sys,'argv',['freeze','--inputs',str(inputs),'--output',str(out),
        '--experiment-id','future-diagnostic','--deadline-utc','2040-01-01T00:00:00Z'])
    freeze.main()
    ref,protocol,deadline=freeze.protocol_reference(tmp_path)
    assert ref['path']==str((out/'protocol.json').resolve())
    assert protocol['experiment_id']==protocol['capability_owner']=='future-diagnostic'
    assert deadline==datetime(2040,1,1,tzinfo=timezone.utc).timestamp()
    task=json.loads((out/'task-D.json').read_text(encoding='utf8'))
    assert task['instruction']==freeze.DETAILS['D']
    assert task['audit_semantics'].startswith('Join bibliography entries ONLY')
    assert task['literal_parser_semantics']['latex']==freeze.DETAILS['tex']
    assert 'not replace both parsers' not in task['audit_semantics']
    # Historical relocated plans remain explicit and byte-preserving.
    relocated={**protocol,'experiment_id':'existing-relocated'}
    old=out/'protocol-server.json';old.write_text(json.dumps(relocated),encoding='utf8')
    assert freeze.protocol_reference(tmp_path)[1]['experiment_id']=='existing-relocated'
    assert freeze.protocol_reference(tmp_path,out/'protocol.json')[1]['experiment_id']=='future-diagnostic'
