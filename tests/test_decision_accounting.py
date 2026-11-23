"""Free original-pool bookkeeping tests; no model calls."""
import json,os,sys,tempfile,subprocess,uuid
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.name != 'posix', reason='Private decision meter requires POSIX file modes')

@pytest.fixture
def context():
    (ROOT/'.local').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='test-decision-account-',dir=ROOT/'.local') as name:
        home=Path(name);root=home/'rsi/current';root.mkdir(parents=True)
        original={'runs':{'original':{'status':'settled','cost_usd':.37,'role':'ordinary'}}}
        (root/'pool.json').write_text(json.dumps(original))
        cfg=home/'config.json';cfg.write_text(json.dumps({'state_root':str(root),'series_cap_usd':None,'learning_cap_usd':None,'limits':{'budget_usd':None}}))
        file=home/'meter.json';file.write_text(json.dumps({'format':'geneloop-decision-account-v1','private_root':str(home),'state_root':str(root),'owner':'account-a','original_config':str(cfg)}));file.chmod(0o600)
        record=home/'decision';record.mkdir()
        event={'format':'geneloop-typed-decision-v1','call_id':str(uuid.uuid4()),'owner':'account-a','task_id':'task-a','parent_call_id':'parent-a','scene':'files','contract':'example-v1','provider':'jev','packet_sha256':'a'*64,'record_directory':str(record),'status':'started'}
        yield file,root,cfg,event,original

def call(file,event):
    r=subprocess.run([sys.executable,str(ROOT/'scripts/decision-meter.py')],input=json.dumps({'context_file':str(file),'event':event}),text=True,capture_output=True,cwd=ROOT)
    return r,json.loads(r.stdout)

def test_original_runs_and_unknown_currency_survive_idempotent_enrollment_and_seal(context):
    file,root,cfg,e,original=context
    assert call(file,e)[0].returncode==0
    assert call(file,e)[1]['duplicate'] is True
    e={**e,'status':'completed','upstream_attempts':1,'provider_reported_cost':.002,'provider_cost_currency':None,'reference_cost_usd':None,'reported_usage':{'input_tokens':70,'output_tokens':8,'cost':.002},'invoice_verified':False}
    assert call(file,e)[0].returncode==0
    assert call(file,e)[1]['duplicate'] is True
    pool=json.loads((root/'pool.json').read_text());assert pool['runs']==original['runs']
    row=pool['decision_calls'][e['call_id']];assert row['reference_cost_usd'] is None and row['provider_reported_cost']==.002
    assert row['provider_cost_currency'] is None and row['parent_call_id']=='parent-a'

def test_unknown_pricing_cannot_bypass_finite_original_grant(context):
    file,root,cfg,e,original=context
    v=json.loads(cfg.read_text());v['series_cap_usd']=1;cfg.write_text(json.dumps(v))
    r,v=call(file,e);assert r.returncode and 'finite grants' in v['error']
    assert json.loads((root/'pool.json').read_text())==original

def test_seal_rejects_cross_owner_or_changed_original_binding(context):
    file,root,cfg,e,original=context
    assert call(file,e)[0].returncode==0
    assert call(file,{**e,'owner':'another','status':'completed'})[0].returncode
    assert call(file,{**e,'task_id':'another','status':'completed'})[0].returncode
    assert json.loads((root/'pool.json').read_text())['decision_calls'][e['call_id']]['status']=='started'

def test_private_context_and_original_enrollment_are_required(context):
    file,root,cfg,e,original=context
    assert call(file,{**e,'status':'completed'})[0].returncode
    file.chmod(0o644);assert call(file,e)[0].returncode
    assert json.loads((root/'pool.json').read_text())==original

def test_protocol_failure_cost_is_reconciled_without_changing_failed_status(context):
    file,root,cfg,e,original=context
    e={**e,'provider':'deepseek'}
    assert call(file,e)[0].returncode==0
    failed={**e,'status':'failed','upstream_attempts':1}
    assert call(file,failed)[0].returncode==0
    raw=Path(e['record_directory'])/'transport-response.txt'
    raw.write_text(json.dumps({'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110,'prompt_tokens_details':{'cached_tokens':20}}}))
    reconcile={**failed,'status':'cost_reconciled'}
    r,v=call(file,reconcile);assert r.returncode==0
    assert abs(v['reference_cost_usd']-.00003612)<1e-12
    assert call(file,reconcile)[0].returncode==0
    pool=json.loads((root/'pool.json').read_text())
    assert pool['runs']==original['runs']
    assert pool['decision_calls'][e['call_id']]['status']=='failed'
    assert pool['decision_reconciliations'][e['call_id']]['semantic_result_remains_failed'] is True
    raw.write_text(json.dumps({'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':101}}))
    assert call(file,reconcile)[0].returncode
