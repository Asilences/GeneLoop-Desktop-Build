"""Specific repair eligibility uses native failure witnesses, not guessed types."""
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from scenarios.paper_proofreading.frontier.adapter import runtime_shape_feedback
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability,create_capability_snapshot,capability_ref
from src.adapters.capability_scene import reference
from tests.test_capability_shape_diagnostics import obj


def fixture(tmp_path,*,wrapped=True):
    rows=obj({'rows':{'type':'array'}});result=obj({'ok':{'type':'boolean'}})
    def native(name,output):
        return create_capability({'owner':'owner','contract':{'input_schema':obj({'value':rows}),
            'output_schema':obj({'stdout':{'type':'string'},'value':output}),'effects':['read']},'dependencies':[],
            'implementation':{'kind':'legacy','legacy_ref':{'backend':'script_motif','library_sha256':'a'*64,
                'library_digest':'b'*64,'object_id':name,'object_sha256':'c'*64,'certificate_sha256':'d'*64}}},
            {'lifecycle':'active','certification':'certified','migration':'legacy'})
    producer=native('producer',rows);consumer=native('consumer',result)
    seed=create_capability_snapshot('owner',[capability_ref(producer),capability_ref(consumer)],[producer,consumer])
    selected={'kind':'step','step_id':'producer','path':['value','rows']}
    if wrapped:selected={'kind':'array','items':[selected]}
    proposal={'format':'capability_compose_proposal_v1','owner':'owner','contract':{'input_schema':rows,'output_schema':result,'effects':['read']},
        'steps':[{'id':'producer','capability':capability_ref(producer),'arguments':{'kind':'object','fields':{'value':{'kind':'input','path':[]}}}},
            {'id':'consumer','capability':capability_ref(consumer),'arguments':{'kind':'object','fields':{'value':{'kind':'object','fields':{'rows':selected}}}}}],
        'output':{'kind':'step','step_id':'consumer','path':['value']}}
    candidate=compile_proposal(proposal,seed,'owner');workspace=tmp_path/'workspace';work=workspace/'calls/consumer-call';(work/'inputs').mkdir(parents=True)
    # Use JS-compatible raw bytes whose number/Unicode spellings Python would
    # change if this eligibility check incorrectly reserialized the value.
    raw='{"rows":[[{"private":"不应进入诊断","n":1e-7}]]}'.encode()
    (work/'inputs/value.json').write_bytes(raw)
    args_sha=hashlib.sha256(b'{"value":'+raw+b'}').hexdigest();root=capability_ref(candidate['capability'])
    trace={'root':root,'snapshot_sha256':candidate['snapshot']['digest'],'mode':'validate','status':'failed',
        'receipts':[{'call_id':'root','capability':root,'parent_call_id':None,'child_call_ids':['producer-call','consumer-call']},
            {'call_id':'producer-call','capability':capability_ref(producer),'parent_call_id':'root','status':'succeeded'},
            {'call_id':'consumer-call','capability':capability_ref(consumer),'parent_call_id':'root','status':'failed',
                'reason':'script_worker_failed','arguments_sha256':args_sha}]}
    trace_path=tmp_path/'trace.json';trace_path.write_text(json.dumps(trace))
    failure={'format':'script_capability_call_failure_v1','call_id':'consumer-call','program_id':'consumer',
        'capability':capability_ref(consumer),'arguments_sha256':args_sha,'input_versions':[hashlib.sha256(raw).hexdigest()],
        'diagnostic':{'format':'script_worker_failure_v1','phase':'sandbox_execution','category':'data_operation_error',
            'exception_type':'TypeError','source_line':8,'source_file':'native_module.py'}}
    failure_path=work/'failure.json';failure_path.write_text(json.dumps(failure))
    return candidate,workspace,trace_path,failure_path,trace,failure


def test_observed_array_operation_failure_gives_bounded_repair_feedback_without_changing_contract(tmp_path):
    candidate,workspace,trace_path,failure_path,trace,failure=fixture(tmp_path);original=copy.deepcopy(candidate)
    feedback=runtime_shape_feedback(candidate,trace_path,workspace)
    assert feedback['checks'][0]['status']=='failed'
    observation=feedback['checks'][0]['observation'];shapes=observation['argument_shapes']
    assert observation['step_id']=='consumer' and shapes['declared_contract_passed'] and shapes['issues']==[]
    assert observation['observed_array_layers'][0]['binding_path']==['steps',1,'arguments','fields','value','fields','rows','items',0]
    assert observation['observed_array_layers'][0]['contract_violation'] is False
    assert observation['evidence']['worker_failure']==reference(failure_path)
    assert '不应进入诊断' not in repr(feedback) and candidate==original


@pytest.mark.parametrize('change',['unknown','timeout','cancelled','wrong-arguments','wrong-capability','wrong-program','changed-value','wrong-root','no-advisory'])
def test_unknown_unbound_or_unrelated_failure_does_not_request_shape_repair(tmp_path,change):
    candidate,workspace,trace_path,failure_path,trace,failure=fixture(tmp_path,wrapped=change!='no-advisory')
    if change=='unknown':failure['diagnostic'].update(category='unknown',exception_type=None)
    elif change=='timeout':trace['receipts'][-1]['reason']='script_worker_timeout'
    elif change=='cancelled':trace['status']='interrupted';trace['receipts'][-1]['status']='interrupted'
    elif change=='wrong-arguments':failure['arguments_sha256']='f'*64
    elif change=='wrong-capability':failure['capability']={'id':'cap_'+'f'*24,'sha256':'f'*64}
    elif change=='wrong-program':failure['program_id']='other'
    elif change=='changed-value':(failure_path.parent/'inputs/value.json').write_text('{}')
    elif change=='wrong-root':trace['root']={'id':'cap_'+'f'*24,'sha256':'f'*64}
    trace_path.write_text(json.dumps(trace));failure_path.write_text(json.dumps(failure))
    assert runtime_shape_feedback(candidate,trace_path,workspace) is None


@pytest.mark.parametrize('committed',[False,True])
def test_publication_only_requests_shape_repair_before_commit(tmp_path,monkeypatch,committed):
    from scenarios.paper_proofreading.frontier import adapter
    candidate,workspace,trace_path,*_=fixture(tmp_path/'fixture')
    instance=adapter.FrontierAdapter.__new__(adapter.FrontierAdapter)
    instance.plan={'owner':'owner','store':str(tmp_path/'store')};instance.materials=type('Materials',(),{'records':lambda self:[]})()
    inputs=[]
    for version in (0,1):
        path=tmp_path/('input-'+str(version)+'.json');path.write_text(json.dumps({'version':version}))
        inputs.append({'path':'/work/inputs/task.json','source':reference(path)})
    instance.templates={'job':{'libraries':[],**{label:{'id':'case-'+label,'input':{'rows':[]},
        'inputs':[inputs[index]],'specification':{'kind':'diagnostic'}} for index,label in enumerate(('validation','followup'))}}}
    attempt=tmp_path/'attempt';attempt.mkdir();(attempt/'candidate.json').write_text(json.dumps(candidate))
    def publication(args,**kwargs):
        output=attempt/'publication';(output/'validation').mkdir(parents=True)
        (output/'result.json').write_text(json.dumps({'status':'failed','error':'cycle_execution_failed'}))
        shutil.copyfile(trace_path,output/'validation/trace.json')
        shutil.copytree(workspace/'calls',attempt/'validation-workspace/calls')
        if committed:(output/'publication.json').write_text('{}')
        return 1
    monkeypatch.setattr(adapter,'run_child',publication)
    result=instance.publish({'id':'job'},candidate,attempt,None)
    assert result['committed']==committed
    assert result['repairable']==(not committed)
    assert bool(result['feedback'])==(not committed)
