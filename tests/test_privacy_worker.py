import json
import subprocess
from types import SimpleNamespace

import pytest

from src.adapters import geneloop_learning_trace as trace
from src.adapters import geneloop_privacy_worker as worker


def test_worker_rejects_unknown_operations_fields_and_private_transport_ids():
    for payload in [{'id':'sdk','operation':'unapproved','value':{}},
                    {'id':'sdk','operation':'learning','value':{},'extra':'private'},
                    {'id':'owner@example.com','operation':'learning','value':{}}]:
        output=worker.process((json.dumps(payload)+'\n').encode())
        assert output['ok'] is False and 'value' not in output
        assert 'owner@example.com' not in json.dumps(output)
    output=worker.process(b'{"id":"sdk","id":"sdk","operation":"learning","value":{}}\n')
    assert output['ok'] is False and output['reason']=='ambiguous_json'


def test_sdk_timeout_never_publishes_a_partial_learning_view(tmp_path,monkeypatch):
    observed=[]
    monkeypatch.setenv('GENELOOP_PRIVACY_ENV_SENTINEL','must-not-forward')
    def blocked(args,**kwargs):
        assert '-B' in args
        observed.append(kwargs)
        raise subprocess.TimeoutExpired(args,120)
    monkeypatch.setattr(trace.subprocess,'run',blocked)
    target=tmp_path/'sdk-timeout'
    assert trace.capture_native_events(target,[],session_id='synthetic-session',status='completed') is False
    assert (target/'privacy-learning-rejected').is_file()
    assert not (target/'privacy-learning.json').exists()
    assert observed[0]['timeout']==120
    assert 'GENELOOP_PRIVACY_ENV_SENTINEL' not in observed[0]['env']


def test_offline_serialization_failure_cannot_publish_partial_json(tmp_path,monkeypatch):
    monkeypatch.setattr(trace,'_run_worker_once',lambda *args,**kwargs:{'bad':float('nan')})
    assert trace.capture_run(tmp_path,'chat','completed',[]) is False
    assert not (tmp_path/'privacy-learning.json').exists()
    assert not list(tmp_path.glob('.privacy-learning-*.tmp'))
    assert (tmp_path/'privacy-learning-rejected').is_file()


def test_offline_capture_and_cli_timeout_use_the_same_owned_child_boundary(tmp_path,monkeypatch,capsys):
    observed=[]
    def blocked(args,**kwargs):
        observed.append(kwargs)
        raise subprocess.TimeoutExpired(args,120)
    monkeypatch.setattr(trace.subprocess,'run',blocked)
    assert trace.capture_run(tmp_path,'coding','completed',[]) is False
    assert (tmp_path/'privacy-learning-rejected').is_file()
    assert not (tmp_path/'privacy-learning.json').exists()
    monkeypatch.setattr(trace.sys,'argv',['import','--authorized','--input',str(tmp_path/'events.jsonl'),
        '--catalog',str(tmp_path/'catalog.json'),'--scene','coding','--status','completed','--start','0'])
    with pytest.raises(SystemExit) as error:trace.main()
    assert error.value.code==1
    captured=capsys.readouterr()
    assert captured.out=='' and captured.err=='geneloop_privacy_rejected\n'
    assert len(observed)==2 and all(row['timeout']==120 for row in observed)


def test_offline_cli_keeps_relative_sources_bound_to_invoking_directory(tmp_path,monkeypatch,capsys):
    monkeypatch.chdir(tmp_path)
    observed=[]
    def completed(operation,value):observed.append((operation,value));return {'accepted':True}
    monkeypatch.setattr(trace,'_run_worker_once',completed)
    monkeypatch.setattr(trace.sys,'argv',['import','--authorized','--input','events.jsonl',
        '--catalog','catalog.json','--scene','coding','--status','completed','--start','0'])
    trace.main()
    assert json.loads(capsys.readouterr().out)=={'accepted':True}
    operation,value=observed[0]
    assert operation=='project'
    assert value['input']==str(tmp_path/'events.jsonl') and value['catalog']==str(tmp_path/'catalog.json')


def test_sharing_projects_one_immutable_source_for_admission_and_topology(tmp_path,monkeypatch):
    catalog=tmp_path/'catalog.json';catalog.write_text('{"allowed_tools":[]}')
    events=[{'type':'user/message','data':{'content':[]}}];reads=[];seen=[]
    def read(path,start):reads.append(path);return events
    def project(value,*args,semantic=True,**kwargs):seen.append(value);return {'semantic':semantic}
    monkeypatch.setattr(trace,'_read_events',read)
    monkeypatch.setattr(trace,'project',project)
    monkeypatch.setattr(trace,'sharing_object',lambda value,allowed:value)
    assert trace.prepare_trace(tmp_path/'events.jsonl','chat','completed',0,catalog,True)=={'semantic':False}
    assert len(reads)==1 and len(seen)==2 and seen[0] is seen[1]
