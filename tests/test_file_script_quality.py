from src.adapters.file_script_quality import structured_output_errors


def test_serialized_output_cannot_be_approved_after_truncation():
    source='console.log(JSON.stringify(result).slice(0,40000))'
    assert structured_output_errors(source,['{"coverage":{"complete":true},"text":"cut'])
    assert not structured_output_errors(source,['{"coverage":{"complete":true},"text":"full"}'])


def test_plaintext_and_progress_logs_are_not_arbitrarily_forced_to_json():
    assert not structured_output_errors('console.log(text)',['{literal prose'])
    assert not structured_output_errors('console.log(JSON.stringify(result))',['progress before JSON','[1,2]'])


def test_observed_output_counterexample_revokes_once_and_preserves_old_verdict(tmp_path,monkeypatch):
    from src.adapters import file_script_quality as q
    from src.motif_core.reuse import experience_registry as er
    root=tmp_path;registry=root/'registry';job=root/'learning/candidate';delivery=root/'delivery'
    er.durable(job/'compiled.json',{'source':'console.log(JSON.stringify(result).slice(0,4))'})
    invocation=delivery/'script-runs/one/invocation.json';er.durable(invocation,{'current':'input'})
    receipt=invocation.with_name('receipt.json');er.durable(receipt,{'invocation_sha256':er.sha(invocation),'calls_sha256':er.digest([]),'public':{'script_id':'candidate','result':{'logs':['{"text":"cut']}}})
    record=root/'records/one.json';er.durable(record,{'delivery':str(delivery)})
    old_review=job/'output-reviews-v2/one/result.json';er.durable(old_review,{'passed':True,'reason':'old LLM false positive'})
    policy=registry/'policy.json';er.durable(policy,{'artifact':{'source':'console.log(JSON.stringify(result).slice(0,4))'}})
    certfile=registry/'certificate.json';er.durable(certfile,{'status':'certified_file_script_v3','candidate_lock_file':str(job/'candidate-lock.json'),'reviews':[{'record_file':str(record),'record_sha256':er.sha(record)}]})
    entry={'kind':'file_script','state':'active','entry_id':'candidate','payload':'policy.json','sha256':er.sha(policy),'certificate':{'file':'certificate.json','sha256':er.sha(certfile)}}
    class Registry:
        def __init__(self,_):self.root=registry
        def load(self):return {'generation':1,'entries':[entry]}
        def publish(self,disable,**_):assert disable==['candidate'];entry['state']='disabled'
    monkeypatch.setattr(q,'ExperienceRegistry',Registry)
    from src.adapters.file_management import experience_certification
    monkeypatch.setattr(experience_certification,'check_motif_certificate',lambda *_:None)
    old_bytes=old_review.read_bytes();cert_bytes=certfile.read_bytes()
    result=q.audit_active_outputs({},root)
    assert len(result)==1 and entry['state']=='disabled'
    assert er.read(job/'revocation.json')['new_api_requests']==0
    assert old_review.read_bytes()==old_bytes and certfile.read_bytes()==cert_bytes
    assert q.audit_active_outputs({},root)==[]
