import json
import pytest
from src.adapters.file_cost_evidence import POLICY,ledger_evidence,record_evidence
from src.motif_core.reuse.experience_registry import durable

def ledger(tmp_path,**overrides):
    row={'request_id':1,'response_status':200,'observed_peak_usd':None,'reserved_upper_usd':.5,
         'response_usage':{'prompt_tokens':100,'completion_tokens':7,'total_tokens':100}}
    row.update(overrides);p=tmp_path/'cost-ledger.jsonl';p.write_text(json.dumps(row)+'\n');return p

def test_authorized_incoherent_usage_keeps_raw_counters_and_full_upper_bound(tmp_path):
    p=ledger(tmp_path);before=p.read_bytes();proof=ledger_evidence(p,1,.5,False,POLICY)
    assert proof['reference_or_upper_usd']==.5 and proof['observed_usage_complete'] is False
    assert proof['counter_inconsistencies'][0]['raw_usage']['total_tokens']==100
    assert proof['provider_invoice_verified'] is False and p.read_bytes()==before
    with pytest.raises(ValueError):ledger_evidence(p,1,.5,False)

@pytest.mark.parametrize('changes',[
    {'response_status':503},{'response_usage':{}},{'reserved_upper_usd':None},
    {'reserved_upper_usd':float('inf')},
    {'response_usage':{'prompt_tokens':100,'completion_tokens':7,'total_tokens':107}},
])
def test_transport_missing_usage_and_unbounded_cost_are_still_rejected(tmp_path,changes):
    with pytest.raises(ValueError):ledger_evidence(ledger(tmp_path,**changes),1,.5,False,POLICY)

def test_every_paid_request_and_original_total_must_reconcile(tmp_path):
    p=ledger(tmp_path)
    with pytest.raises(ValueError):ledger_evidence(p,2,.5,False,POLICY)
    with pytest.raises(ValueError):ledger_evidence(p,1,0,False,POLICY)

def test_old_task_not_retroactively_authorized(tmp_path):
    p=ledger(tmp_path);origin=tmp_path/'origin';durable(origin/'enrollment.json',{'config':{}})
    r={'origin':str(origin),'run_dir':str(tmp_path),'accounting_complete':True,'observed_usage_complete':False,'upstream_requests':1,'cost_usd':.5}
    with pytest.raises(ValueError,match='original task'):record_evidence(r,POLICY)

@pytest.mark.parametrize('failure',['accepted','lifecycle','repair','mock'])
def test_bounded_cost_certificate_cannot_bypass_execution_quality(tmp_path,monkeypatch,failure):
    from src.adapters import file_script_learning as learning
    from src.motif_core.reuse.experience_registry import sha
    monkeypatch.setattr(learning,'checked_script_policy',lambda _:None)
    policy={'policy_digest':'candidate','artifact':{'source_task_fingerprints':[]}}
    lock=tmp_path/'lock.json';durable(lock,{})
    record={'role':'native_certification','provider_mode':'real','accepted':True,'lifecycle_verified':True,
            'observed_usage_complete':False,'metrics':{'acceptance_repairs':0}}
    if failure=='accepted':record['accepted']=False
    if failure=='lifecycle':record['lifecycle_verified']=False
    if failure=='repair':record['metrics']['acceptance_repairs']=1
    if failure=='mock':record['provider_mode']='mock'
    f=tmp_path/'record.json';durable(f,record)
    review={'role':'native_certification','task_fingerprint':'new-1','record_file':str(f),'record_sha256':sha(f)}
    cert={'status':'certified_file_script_v4','holdout_used':False,'quality_and_permission_required':True,
          'policy_digest':'candidate','payload_sha256':'payload','candidate_lock_file':str(lock),'candidate_lock_sha256':sha(lock),
          'native_review':review,'reviews':[{**review,'task_fingerprint':'new-2'},{**review,'task_fingerprint':'new-3'}],
          'accounting_policy':POLICY}
    certificate=tmp_path/'certificate.json';durable(certificate,cert)
    with pytest.raises(ValueError,match='failed, repaired or unmetered'):learning.verify_script_certificate(policy,certificate,'payload')
