"""Diagnostic proof-link tests; actual paid replay still needs independent execution."""
import copy
import pytest
from src.adapters.learned_decision_certificate import verified_recovered_roots
from src.motif_core.reuse.experience_registry import durable,sha,digest

def fixture(tmp_path):
 value={'candidate_sha256':'candidate','runtime_sources':{'runtime':'original'}}
 spec={'owner':'owner','task_id':'task','external_roots':{}}
 proof={'tool_call_id':'old','context':{'history':[]},'request':{'evidence':'current'},
  'resolution':{'accepted':True,'values':{}},'binding':{'tool':'stage','arguments':{'current':'id'}},'decision_result_files':[]}
 old=tmp_path/'old.json';durable(old,proof)
 p={**spec,'payload_sha256':digest(value),'runtime_sha256':digest(value['runtime_sources']),
  **{k:proof[k]for k in('context','request','resolution','binding')},'workspace':{'files':{'input':'sha'}},'paid_files':{}}
 pending=tmp_path/'pending.json';durable(pending,p)
 ref={'pending_file':str(pending),'pending_sha256':sha(pending),'previous_tool_call_id':'old',
  'proof_file':str(old),'proof_sha256':sha(old),'no_new_paid_calls':True,
  'workspace_sha256':digest(p['workspace']),'current_workspace_sha256':digest(p['workspace'])}
 new=tmp_path/'new.json';durable(new,{**proof,'tool_call_id':'new','recovered_from':ref})
 bound=[{'tool_call_id':n,'candidate':'candidate','provider':'jev','execution_proof':str(f),'execution_proof_sha256':sha(f)}for n,f in[('old',old),('new',new)]]
 event={'kind':'learned_decision_recovered','previous_tool_call_id':'old','tool_call_id':'new','no_new_paid_calls':True,
  'source_proof':str(old),'source_proof_sha256':sha(old),'execution_proof':str(new),'execution_proof_sha256':sha(new)}
 return [event],bound,{'new':{'actual':'terminal'}},value,spec,{'catalog':{'stage':{'contract':{'effect':'stage'}}}}

def test_only_unexecuted_linked_predecessors_are_excluded_not_counted_as_success(tmp_path):
 args=fixture(tmp_path);out=verified_recovered_roots(*args)
 assert len(out)==1 and out[0]['counted_as_executed']is False and out[0]['replaced_by']=='new'
 with pytest.raises(ValueError,match='actual prior'):verified_recovered_roots(args[0],args[1],{**args[2],'old':{}},*args[3:])
 with pytest.raises(ValueError,match='never actually'):verified_recovered_roots(args[0],args[1],{},*args[3:])

@pytest.mark.parametrize('change',['request','workspace','runtime','paid_calls','write','tamper'])
def test_recovery_cannot_change_decision_scope_or_hide_failed_proof(tmp_path,change):
 args=list(fixture(tmp_path));new=tmp_path/'new.json'
 if change=='runtime':args[3]={**args[3],'runtime_sources':{'runtime':'changed'}}
 elif change=='write':args[5]['catalog']['stage']['contract']['effect']='authorized_write'
 elif change=='paid_calls':args[0][0]['no_new_paid_calls']=False
 else:
  import json
  v=json.loads(new.read_text())
  if change=='request':v['request']={'changed':'semantic input'}
  elif change=='workspace':v['recovered_from']['current_workspace_sha256']='changed'
  else:v['binding']['arguments']={'changed':'id'}
  durable(new,v);args[1][1]['execution_proof_sha256']=sha(new);args[0][0]['execution_proof_sha256']=sha(new)
 with pytest.raises(ValueError):verified_recovered_roots(*args)
