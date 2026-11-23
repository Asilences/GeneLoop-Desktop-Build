"""Free budget and retained-counterexample regressions; model runs remain real."""
from src.adapters.experience_library import migration_budget_admits
from src.adapters.file_learning_repair import semantic_counterexamples
from src.motif_core.reuse.experience_registry import durable
import pytest

def test_unlimited_migration_accepts_unknown_pending_without_replacing_it_with_zero():
    cfg={'limits':{'budget_usd':None},'learning_cap_usd':None,'series_cap_usd':None}
    budget={'learning_spent_usd':10000,'learning_reserved_usd':None,'series':{'estimated_usd':20000},'pending_usd':None}
    assert migration_budget_admits(cfg,budget)
    assert not migration_budget_admits({**cfg,'series_cap_usd':100000},budget)
    cfg={'limits':{'budget_usd':1},'learning_cap_usd':3,'series_cap_usd':5}
    budget={'learning_spent_usd':1,'learning_reserved_usd':1,'series':{'estimated_usd':3},'pending_usd':1}
    assert migration_budget_admits(cfg,budget)
    assert not migration_budget_admits({**cfg,'learning_cap_usd':2},budget)

def test_only_actual_output_counterexamples_schedule_a_program_revision(tmp_path):
    root=tmp_path/'output-reviews-v2'
    durable(root/'semantic/result.json',{'passed':False,'error':None,'verdict':{'critical_errors':['declared argument ignored']}})
    durable(root/'transport/result.json',{'passed':False,'error':{'type':'HTTPError'},'verdict':None})
    durable(root/'parse/result.json',{'passed':False,'error':{'type':'ValueError'},'verdict':{'critical_errors':['not accepted as valid response']}})
    durable(root/'pass/result.json',{'passed':True,'error':None,'verdict':{'critical_errors':[]}})
    assert [p.parent.name for p in semantic_counterexamples(tmp_path)]==['semantic']


def test_ordinary_repair_uses_normal_retrieval_and_keeps_original_grants(tmp_path):
    from src.adapters.continuous_motif_learning import material_configuration
    cfg={'role':'candidate_certification','registry_file':'old-fixed-library','candidate_job':'old-candidate',
         'state_root':'original-account','workspace_roots':['original-copy'],'limits':{'budget_usd':None},'auto_worker':True}
    child=material_configuration(cfg,tmp_path,'ordinary')
    assert 'registry_file' not in child and 'candidate_job' not in child
    assert child['state_root']==cfg['state_root'] and child['workspace_roots']==cfg['workspace_roots'] and child['limits']==cfg['limits']
    assert child['role']=='ordinary' and child['auto_worker'] is False
    with pytest.raises(ValueError,match='cannot select a registry'):material_configuration(cfg,tmp_path,'ordinary','forced-registry')


def test_revoked_approval_is_new_failure_evidence_bound_to_original_program(tmp_path):
    from src.motif_core.reuse.experience_registry import sha
    durable(tmp_path/'compiled.json',{'source':'observed program'})
    durable(tmp_path/'revocation.json',{'format':'sss-file-script-output-counterexample-v1','compiled_sha256':sha(tmp_path/'compiled.json'),'passed':False,'error':None,'mechanical_errors':['truncated JSON'],'verdict':{'critical_errors':['truncated JSON']}})
    assert semantic_counterexamples(tmp_path)==[tmp_path/'revocation.json']
    (tmp_path/'compiled.json').write_text('{}')
    with pytest.raises(ValueError,match='counterexample binding changed'):semantic_counterexamples(tmp_path)
