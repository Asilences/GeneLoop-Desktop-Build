"""Encoding diagnostics; fake native metadata never authorizes execution."""
import copy,json
from src.adapters.capability_program_encoding import encode_complete_script
from src.adapters.capability_contract import create_capability,create_capability_snapshot,capability_ref
from tests.test_capability_improvement import put


def setup(tmp_path):
    schema={'type':'object','properties':{'delta':{'type':'array'}},'required':['delta'],'additionalProperties':False}
    library=put(tmp_path/'library.json',{'programs':[{'id':'diagnostic','inputs':[{},{}]}]})
    observations=put(tmp_path/'observations.json',[{'candidates':[{'id':'diagnostic','original_paths':['after','before'],
        'witness':{'files':{'before':{'relative':'inputs/before.zip'},'after':{'relative':'inputs/after.zip'}}}}]}])
    input_schema={'type':'object','properties':{k:{'type':'string'} for k in ('before','after')},'required':['before','after'],'additionalProperties':False}
    cap=create_capability({'owner':'owner','contract':{'input_schema':{'type':'object','properties':{'paths':{'type':'array','items':{'type':'string'}}},
        'required':['paths'],'additionalProperties':False},'output_schema':{'type':'object','properties':{'value':schema},'required':['value'],'additionalProperties':False},'effects':['read']},
        'implementation':{'kind':'legacy','legacy_ref':{'backend':'script_motif','library_sha256':library['sha256'],
        'library_digest':'a'*64,'object_id':'diagnostic','object_sha256':'b'*64,'certificate_sha256':'c'*64}},'dependencies':[]},
        {'lifecycle':'active','certification':'certified','migration':'legacy'})
    snapshot=create_capability_snapshot('owner',[capability_ref(cap)],[cap])
    task={'id':'diagnostic','contract':{'input_schema':input_schema,'output_schema':schema,'effects':['read']}}
    return task,snapshot,library,observations


def test_exact_witnessed_slot_order_is_encoded_without_a_second_model_proposal(tmp_path):
    task,snapshot,library,observations=setup(tmp_path)
    encoded=encode_complete_script(task,snapshot,library,observations)
    args=encoded['proposal']['steps'][0]['arguments']['fields']['paths']['items']
    assert args==[{'kind':'input','path':['after']},{'kind':'input','path':['before']}]
    assert encoded['candidate']['capability']['certification']=='candidate'
    assert encoded['candidate']['capability']['lifecycle']=='build_only'


def test_partial_JSON_transform_or_incompatible_output_is_not_declared_a_complete_solver(tmp_path):
    task,snapshot,library,observations=setup(tmp_path)
    other=copy.deepcopy(task);other['contract']['input_schema']['properties']['extra']={'type':'string'}
    other['contract']['input_schema']['required'].append('extra')
    assert encode_complete_script(other,snapshot,library,observations) is None
    other=copy.deepcopy(task);other['contract']['output_schema']['properties']['delta']={'type':'number'}
    assert encode_complete_script(other,snapshot,library,observations) is None
