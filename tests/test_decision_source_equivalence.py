"""Source-comparison proofs only: no model, file mutation or task execution."""
import copy
import pytest
from src.adapters.decision_source_equivalence import source_argument_proof
from src.adapters.learned_decision_certificate import source_review_passes


def fixture():
    actions=[{'op':'mkdir','destination':'out'},
             {'op':'copy','file_ids':['a'],'destination':'out/a.txt'},
             {'op':'copy','file_ids':['b'],'destination':'out/b.txt'}]
    name='mcp__file_management__preview_actions'
    source={'tools':[{'name':name,'parameters':{'type':'object'}}],
        'native_call':{'tool':name,'arguments':{'actions':actions}},
        'native_output':{'status':'validated_management_plan'},
        'context':{'receipts':{'mcp__file_management__list_files':{'files':[
            {'file_id':i,'path':i+'.txt','root_id':'workspace','sha256':i*64}for i in ['a','b']]}}}}
    binding={'tool':name,'arguments':{'actions':copy.deepcopy([actions[0],actions[2],actions[1]])}}
    return binding,source


def test_only_opt_in_proves_copy_permutation_without_changing_either_plan():
    binding,source=fixture();before=copy.deepcopy((binding,source))
    assert source_argument_proof(binding,source) is None
    proof=source_argument_proof(binding,source,allow_disjoint_copies=True)
    assert proof['kind']=='disjoint_new_workspace_copy_permutation_v2'
    assert proof['new_targets']==['out/a.txt','out/b.txt']
    assert proof['requires_independent_goal_order_review'] is True
    assert (binding,source)==before


@pytest.mark.parametrize('change',['move','external','existing','duplicate','prefix','batch','changed_source','traversal','mkdir_target','unapproved'])
def test_dependencies_or_different_effects_never_become_permutation_proofs(change):
    b,s=fixture();actions=b['arguments']['actions'];original=s['native_call']['arguments']['actions']
    if change=='move':actions[1]['op']=original[2]['op']='move'
    elif change=='external':actions[1]['destination_root']=original[2]['destination_root']='outside'
    elif change=='existing':actions[1]['destination']=original[2]['destination']='a.txt'
    elif change=='duplicate':actions[1]['destination']=original[2]['destination']='out/a.txt'
    elif change=='prefix':actions[0]={'op':'mkdir','destination':'different'}
    elif change=='batch':actions[1]['file_ids']=original[2]['file_ids']=['a','b']
    elif change=='changed_source':actions[1]['file_ids']=['a']
    elif change=='traversal':actions[1]['destination']=original[2]['destination']='out/../escape'
    elif change=='mkdir_target':actions[1]['destination']=original[2]['destination']='out'
    elif change=='unapproved':s['native_output']['status']='confirmation_required'
    assert source_argument_proof(b,s,allow_disjoint_copies=True) is None


def test_copy_math_alone_cannot_admit_a_goal_with_temporal_constraints():
    value={'source_replay_proofs':[{'kind':'disjoint_new_workspace_copy_permutation_v2'}]}
    answer={'passed':True,'critical_errors':[]}
    for review in [answer,{**answer,'unordered_copy_order_permitted':False}]:
        assert not source_review_passes({'status':'completed','answer':review},value)
    assert source_review_passes({'status':'completed','answer':{**answer,'unordered_copy_order_permitted':True}},value)
    assert source_review_passes({'status':'completed','answer':answer},{})


def test_v2_cannot_relabel_an_old_generation_without_declared_policy(tmp_path):
    import json
    from src.adapters.learned_decision_learning import compile_candidate
    from src.motif_core.reuse.experience_registry import durable,digest
    model=tmp_path/'proposal/result.json'
    candidate={'format':'geneloop-learned-decision-v1','description':'diagnostic',
        'scope_description':'diagnostic','guard':['lit',False],'request':['lit',{}],
        'bind':['lit',None],'training_witnesses':[]}
    data={};system='diagnostic legacy contract'
    durable(model,{'status':'completed','answer':{'candidate':candidate},'input_sha256':digest({'system':system,'data':data})})
    durable(model.parent/'response.json',{'choices':[{'message':{'content':json.dumps({'candidate':candidate})}}]})
    durable(model.parent/'input.json',data)
    durable(model.parent/'request.json',{'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(data)}]})
    with pytest.raises(ValueError,match='declared before actual model generation'):
        compile_candidate(model,tmp_path/'unused-sources.json',tmp_path/'never-published.json','fixture',{},allow_disjoint_copy_reordering=True)
    assert not (tmp_path/'never-published.json').exists()
