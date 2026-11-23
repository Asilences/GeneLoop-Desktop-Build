"""Free transport diagnostics; fake replies are never learning evidence."""
from email.message import Message
import http.client
import io
import json
import threading
import os
import urllib.request
from unittest.mock import patch

import pytest
from src.adapters import file_provider as provider
from src.adapters import deepseek_cost_gate


@pytest.mark.skipif(os.name != 'posix', reason='Private credentials require POSIX file modes')
def test_private_config_and_public_binding(tmp_path):
    path=tmp_path/'kouri.env'
    path.write_text('KOURI_API_KEY=private-test-secret\nKOURI_BASE_URL=https://api.kourichat.com/v1\nKOURI_MODEL=deepseek-v4.1-flash\n')
    path.chmod(0o600)
    value=provider.load(path)
    assert value['credential']=='private-test-secret'
    assert 'private-test-secret' not in json.dumps(value['provider_binding'])
    assert value['provider_binding']['cost_basis']=='reference_tariff_only_not_kouri_charge'
    path.chmod(0o644)
    with pytest.raises(ValueError,match='private'):provider.load(path)
    path.chmod(0o600)
    path.write_text('KOURI_API_KEY=x\nKOURI_BASE_URL=https://api.kourichat.com.evil.example/v1\n')
    with pytest.raises(ValueError,match='verified HTTPS'):provider.load(path)


@pytest.mark.parametrize('model,actual', [('deepseek-flash','deepseek-v4.1-flash'),('deepseek-v4-flash','deepseek-v4.1-flash'),('deepseek-v4-pro','deepseek-v4-pro')])
def test_explicit_reasoning_off_and_model_mapping(model,actual):
    value=json.loads(provider.payload(json.dumps({'model':model,'thinking':{'type':'enabled'},'reasoning_effort':'high'}).encode()))
    assert value['model']==actual and value['thinking']=={'type':'disabled'}
    assert value.get('reasoning_effort')==('none' if actual.endswith('flash') else None)


def test_standard_final_stream_usage_is_explicit_and_cache_counts_are_not_guessed():
    value=json.loads(provider.payload(json.dumps({'model':'deepseek-flash','stream':True,
        'stream_options':{'include_usage':False}}).encode()))
    assert value['stream_options']['include_usage'] is True
    raw={'prompt_tokens':100,'completion_tokens':7,'total_tokens':107,'prompt_tokens_details':{'cached_tokens':80}}
    normalized=provider.billing_usage(raw)
    assert normalized['prompt_cache_hit_tokens']==80 and normalized['prompt_cache_miss_tokens']==20
    assert 'prompt_cache_hit_tokens' not in raw
    inconsistent={'prompt_tokens':100,'completion_tokens':7,'total_tokens':119}
    assert provider.billing_usage(inconsistent)==inconsistent


@pytest.mark.parametrize('with_usage',[True,False])
def test_stream_pricing_envelope_preserves_bytes_and_explicit_final_usage(tmp_path,monkeypatch,with_usage):
    monkeypatch.setenv('HARLESS_MANAGEMENT_PRIVATE_ROOT',str(tmp_path/'private'))
    raw={'prompt_tokens':100,'completion_tokens':7,'total_tokens':107,
        'prompt_tokens_details':{'cached_tokens':80}}
    item={'model':'deepseek-v4.1-flash','choices':[]}
    if with_usage:item['usage']=raw
    wire=b'data: '+json.dumps(item).encode()+b'\n\ndata: [DONE]\n\n'
    response=io.BytesIO(wire);response.status=200;response.headers={'Content-Type':'text/event-stream'}
    class Opener:
        def open(self,request,timeout):return response
    state=deepseek_cost_gate.FileState(cap_usd=.1,output_cap=100,record=tmp_path/'ledger.jsonl',request_limit=1)
    gate=deepseek_cost_gate.create_file_server('127.0.0.1',0,'https://api.deepseek.com',state)
    with patch.object(provider.urllib.request,'build_opener',return_value=Opener()):
        provider.attach(gate,{'credential':'test-only','provider_binding':provider.binding()})
    handler=object.__new__(gate.RequestHandlerClass);handler.headers={};handler.path='/v1/chat/completions'
    relayed=[]
    def relay(stream,content_type):
        while chunk:=stream.read1(17):relayed.append(chunk)
        return b'{"usage":{}}'
    handler._stream_upstream=relay
    try:
        status,content_type,body=handler._call_upstream(b'{"model":"deepseek-flash","stream":true}','POST',stream=True)
        assert status==200 and content_type=='application/json' and b''.join(relayed)==wire
        expected=provider.billing_usage(raw) if with_usage else {}
        assert json.loads(body)['usage']==expected
        sidecar=tmp_path/'private/provider-transports/kouri-raw-usage.jsonl'
        assert json.loads(sidecar.read_text())['raw_usage']==(raw if with_usage else {})
    finally:gate.server_close()


def test_truncated_provider_http_error_settles_before_reply(tmp_path):
    class TruncatedBody(io.BytesIO):
        def read(self, *args, **kwargs):
            raise http.client.IncompleteRead(b'{"usage":{"cost":"0.001"}}', 80)

    class Opener:
        def open(self, request, timeout):
            headers = Message()
            headers['Content-Type'] = 'application/json'
            headers['Retry-After'] = '7'
            headers['X-Request-ID'] = 'truncated-fixture'
            raise urllib.error.HTTPError(request.full_url, 503, 'fixture', headers, TruncatedBody())

    state = deepseek_cost_gate.FileState(
        cap_usd=.1, output_cap=100, request_limit=1, record=tmp_path/'ledger.jsonl')
    gate = deepseek_cost_gate.create_file_server('127.0.0.1', 0, provider.ORIGIN, state)
    with patch.object(provider.urllib.request, 'build_opener', return_value=Opener()):
        provider.attach(gate, {'credential':'test-only', 'provider_binding':provider.binding()})
    thread = threading.Thread(target=gate.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    client = http.client.HTTPConnection('127.0.0.1', gate.server_port, timeout=3)
    try:
        body = json.dumps({'model':'deepseek-flash', 'max_tokens':100, 'stream':True, 'messages':[]})
        client.request('POST', '/v1/chat/completions', body, {'Content-Type':'application/json'})
        response = client.getresponse()
        assert response.status == 502
        assert response.getheader('Retry-After') == '7'
        assert not state.pending
        receipt = json.loads(state.record.read_text())
        assert receipt['response_status'] == 502 and state.request_count == 1
        assert receipt['response_usage'] == {}
        assert receipt['observed_peak_usd'] is None
        assert receipt['reservation_released_usd'] == 0
        assert state.reserved_usd == pytest.approx(receipt['reserved_upper_usd'], abs=1e-8)
        upstream = receipt['upstream_response']
        assert upstream['http_status'] == 503 and not upstream['response_complete']
        assert upstream['outcome'] == 'transport_error'
        assert upstream['transport_error_type'] == 'IncompleteRead'
        assert upstream['request_ids'] == {'x-request-id':'truncated-fixture'}
        assert upstream['raw_usage']['cost'] == '0.001'
        assert response.read() == b'{"error":"File provider unavailable"}'
    finally:
        client.close()
        gate.shutdown()
        gate.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize('selective', [False, True], ids=['file-sdk', 'web'])
def test_meter_remains_and_credential_is_host_only(tmp_path,selective):
    state_type = deepseek_cost_gate.State if selective else deepseek_cost_gate.FileState
    create_server = deepseek_cost_gate.create_server if selective else deepseek_cost_gate.create_file_server
    state=state_type(cap_usd=.1,output_cap=100,record=tmp_path/'ledger.jsonl',request_limit=1)
    gate=create_server('127.0.0.1',0,provider.ORIGIN,state)
    original=gate.RequestHandlerClass;requests=[]
    fake=io.BytesIO(json.dumps({'choices':[{'message':{'role':'assistant','content':'ok'}}],
        'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,'completion_tokens':1,'total_tokens':11}}).encode())
    fake.headers={'Content-Type':'application/json'};fake.status=200
    class Opener:
        def open(self,request,timeout):requests.append(request);return fake
    p={'credential':'host-secret','provider_binding':provider.binding()}
    with patch.object(provider.urllib.request,'build_opener',return_value=Opener()):provider.attach(gate,p,selective=selective)
    assert gate.RequestHandlerClass is not original
    thread=threading.Thread(target=gate.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:
        headers={'Content-Type':'application/json','Authorization':'Bearer child-placeholder'}
        if selective:headers[provider.HEADER]=provider.binding()['binding_sha256']
        request=urllib.request.Request(f'http://127.0.0.1:{gate.server_port}/v1/chat/completions',
            data=json.dumps({'model':'deepseek-flash','messages':[{'role':'user','content':'hello'}],'max_tokens':100,'stream':False}).encode(),headers=headers)
        with urllib.request.urlopen(request) as response:assert response.status==200
        assert len(requests)==1
        actual=requests[0]
        assert actual.full_url=='https://api.kourichat.com/v1/chat/completions'
        assert actual.get_header('Authorization')=='Bearer host-secret'
        assert provider.HEADER.lower() not in {k.lower() for k in actual.headers}
        assert json.loads(actual.data)['model']=='deepseek-v4.1-flash'
        with pytest.raises(urllib.error.HTTPError) as denied:urllib.request.urlopen(request)
        assert denied.value.code==429 and len(requests)==1
        rows=[json.loads(line) for line in state.record.read_text().splitlines()]
        assert any(r.get('response_status')==200 and r.get('response_usage',{}).get('total_tokens')==11 for r in rows)
        assert 'host-secret' not in state.record.read_text()
    finally:gate.shutdown();gate.server_close();thread.join(3)


def test_selective_transport_keeps_other_scenes(tmp_path):
    state=deepseek_cost_gate.State(cap_usd=.1,output_cap=100,record=tmp_path/'ledger.jsonl',request_limit=2)
    gate=deepseek_cost_gate.create_server('127.0.0.1',0,'https://api.deepseek.com',state)
    base=gate.RequestHandlerClass
    with patch.object(base,'_call_upstream',return_value=(200,'application/json',b'{}')) as original:
        provider.attach(gate,{'credential':'host-secret','provider_binding':provider.binding()},selective=True)
        handler=object.__new__(gate.RequestHandlerClass);handler.headers={};handler.path='/v1/chat/completions'
        assert handler._call_upstream(b'{}','POST')[0]==200 and original.call_count==1
        handler.headers={provider.HEADER:'changed'}
        assert handler._call_upstream(b'{}','POST')[0]==400 and original.call_count==1
    gate.server_close()


def test_fresh_body_material_recognizes_frozen_read_contract(tmp_path):
    from src.adapters.file_script_learning import fresh_read_material
    path=tmp_path/'current.txt';path.write_text('memorized old text')
    spec={'rules':{'read_only':True},'quality':{'requirements':[], 'delivery_contract':{
        'format':'sss-file-delivery-v1','preserve_originals':True,'exact_tree':True,'require_reads':[{'path':'current.txt','mode':'text'}]}}}
    assert fresh_read_material(spec,tmp_path,'new-independent-body')
    assert 'memorized old text' not in path.read_text()
    spec['quality']['delivery_contract']['report_terms']=['semantic conclusion']
    assert not fresh_read_material(spec,tmp_path,'different')


def test_independent_source_certification_changes_names_bodies_counts_and_pages(tmp_path):
    import copy
    import pymupdf
    from src.adapters.file_script_learning import fresh_read_material
    from src.motif_core.reuse.experience_registry import digest
    counts=[];page_counts=[]
    for i,variant in enumerate(('native-cert','execute-cert-0','execute-cert-1')):
        root=tmp_path/variant;root.mkdir()
        (root/'old.txt').write_text('old body')
        document=pymupdf.open();document.new_page().insert_text((30,40),'original body');document.save(root/'old.pdf');document.close()
        contract={'format':'sss-file-delivery-v1','preserve_originals':True,'exact_tree':True,
            'require_reads':[{'path':'old.txt','mode':'text'},{'path':'old.pdf','mode':'text'}]}
        spec={'rules':{'read_only':True},'quality':{'requirements':[],'goal':{},'delivery_contract':copy.deepcopy(contract)}}
        assert fresh_read_material(spec,root,'independent-'+str(i),variant)
        files=list(root.iterdir());counts.append(len(files))
        assert not {'old.txt','old.pdf'} & {p.name for p in files}
        with pymupdf.open(next(p for p in files if p.suffix=='.pdf')) as doc:page_counts.append(len(doc))
        assert spec['quality']['goal']['delivery_contract_sha256']==digest(spec['quality']['delivery_contract'])
        assert {r['path'] for r in spec['quality']['delivery_contract']['require_reads']}=={p.name for p in files}
    assert counts==[2,3,4] and page_counts==[3,5,2]
