"""Diagnostic fixtures for the existing miner/compiler/executor native adapter."""
import hashlib
import json
import time
from uuid import uuid4
from src.adapters.desktop import desktop_rsi as rsi
from src.adapters.desktop.desktop_rsi_catalog import catalog


def events(index):
    handle='source-'+str(index)*32
    rows=[]
    for n,args,result in [('local_document_pin',{'path':f'{index}.txt'},{'source_id':handle,'version_sha256':str(index)*64}),
                          ('local_document_read',{'source_id':handle,'page':1},{'text':'ordinary public research material'})]:
        call=str(len(rows));rows.append({'seq':len(rows),'type':'tool/call','data':{'callId':call,'name':n,'arguments':json.dumps(args)}})
        rows.append({'seq':len(rows),'type':'tool/result','data':{'message':{'source':{'kind':'tool','callId':call},'content':[{'type':'tool-result','toolCallId':call,'content':[{'type':'text','text':json.dumps(result)}]}]}}})
    return rows


def test_native_miner_reserves_independent_witness_and_uses_existing_executor(tmp_path,monkeypatch):
    root=tmp_path/'account';root.mkdir();(root/'tasks').mkdir();(root/'motifs').mkdir()
    rsi.save(root/'owner.json',{'principal':'account-a'})
    identities=[]
    for index in range(1,4):
        identity=uuid4().hex;identities.append(identity);task=root/'tasks'/identity;task.mkdir()
        rsi.save(task/'task.json',{'principal':'account-a','attempt_id':identity,'logical_task_id':uuid4().hex,
            'session_id':str(uuid4()),'scene':'paper','status':'completed','at':time.time()*1000+index,'finished_at':time.time()*1000})
        raw='\n'.join(json.dumps(row) for row in events(index))+'\n';(task/'events.jsonl').write_text(raw,encoding='utf-8')
        rsi.save(task/'admission.json',{'code_version':rsi.VERSION,'events_sha256':hashlib.sha256((task/'events.jsonl').read_bytes()).hexdigest()})
        result=rsi.learn(root)
        if index<3:assert result['certified']==0
    assert result['certified']==1
    path=next((root/'motifs').glob('*.json'));item=rsi.read(path)
    assert item['quality_cost_promoted'] is False
    assert item['artifact']['validation_trace_id']==identities[-1]
    assert identities[-1] not in item['artifact']['source_trace_ids']
    invocation=str(uuid4())
    feedback={'motif_id':item['id'],'invocation_id':invocation,'status':'completed'}
    (root/'feedback.jsonl').write_text((json.dumps(feedback)+'\n')*2+json.dumps({**feedback,
        'invocation_id':str(uuid4()),'status':'failed'})+'\n', encoding='utf-8')
    assert catalog(root)==[{'id':item['id'],'scene':'paper','tools':['local_document_pin','local_document_read'],
        'certificate':item['artifact']['certified_digest'],'witnesses':3,'reuses':1}]
    suspended=path.with_suffix('.suspended')
    suspended.touch()
    assert catalog(root)==[]
    suspended.unlink()
    actual=[]
    def run(name,args):
        actual.append((name,args))
        return {'source_id':'source-'+'f'*32,'version_sha256':'b'*64} if name=='local_document_pin' else {'text':'new task result'}
    result=rsi.run_read_motif(item['artifact'],contracts=rsi.CONTRACTS,
        bindings={'local_document_pin':{'path':'new-task.txt'},'local_document_read':{'page':1}},input_version='new-invocation',
        execute_tool=run,verify_current=lambda:None,is_read_only=lambda name:name in rsi.CONTRACTS)
    assert result.status=='completed'
    assert actual[1][1]['source_id']=='source-'+'f'*32
    # Executing a learned program is feedback, not a holdout that erases its own certificate.
    identity=uuid4().hex;task=root/'tasks'/identity;task.mkdir()
    rsi.save(task/'task.json',{'principal':'account-a','attempt_id':identity,'logical_task_id':uuid4().hex,
        'session_id':str(uuid4()),'scene':'paper','status':'completed','at':time.time()*1000+100,'finished_at':time.time()*1000})
    raw=json.dumps({'type':'tool/call','data':{'callId':'reuse','name':'local_motif_run','arguments':'{}'}})+'\n'
    (task/'events.jsonl').write_text(raw,encoding='utf-8')
    rsi.save(task/'admission.json',{'code_version':rsi.VERSION,'events_sha256':hashlib.sha256((task/'events.jsonl').read_bytes()).hexdigest()})
    assert rsi.learn(root)['certified']==1
    # A modified or unadmitted source cannot continue to certify an account program.
    (root/'tasks'/identities[0]/'events.jsonl').write_text('{}\n',encoding='utf-8')
    assert catalog(root)==[]
    assert rsi.learn(root)['certified']==0
