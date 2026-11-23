import json,subprocess
from pathlib import Path
import pytest
from src.motif_core.offline.compilation import decision_program_lowering as lowering
from src.motif_core.offline.compilation.decision_program_lowering import lower_program,lower_patch
from src.adapters.empirical_decision_certificate import check_empirical_guards
from src.motif_core.reuse.experience_registry import durable,sha
from src.adapters.learned_decision_learning import repair_progress_signature,repair_components,decode_model_json,materialize_program_generation,generated_candidate
from src.adapters.learned_decision_certificate import replay


def test_binding_blocks_lower_with_lexical_order_and_shadowing():
    value={'bindings':[{'name':'x','value':['lit',2]},
                       {'name':'x','value':['array',['var','x'],['lit',3]]}],
           'result':['map',['var','x'],'item',{'bindings':[{'name':'y','value':['var','item']}],'result':['var','y']}]}
    program=lower_program(value)
    result=subprocess.run(['node','--input-type=module','-e',
        "import {runProgram} from './src/adapters/paper_rsi_program.ts';let s='';for await(const x of process.stdin)s+=x;console.log(JSON.stringify(runProgram(JSON.parse(s),{})))"],
        input=json.dumps(program),capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==[2,3]
    assert value['bindings'][0]['name']=='x'


def test_literals_and_object_field_maps_are_not_reinterpreted_as_code():
    data={'bindings':[{'name':'x','value':['lit',1]}],'result':['var','x']}
    assert lower_program(['lit',data])==['lit',data]
    assert lower_program(['object',{'bindings':['lit',4],'result':['lit',5]}])==[
        'object',{'bindings':['lit',4],'result':['lit',5]}]
    with pytest.raises(ValueError,match='explicit name'):
        lower_program({'bindings':[{'name':'x'}],'result':['lit',None]})


def test_partial_read_probes_are_advisory_but_readonly_and_roles_still_enforced(tmp_path):
    payload=tmp_path/'payload.json';guard=tmp_path/'guard.json'
    durable(payload,{'candidate':{'training_witnesses':[{'snapshot_id':'a'}]}})
    names=['readonly_goal','all_read_evidence_absent','new_inventory_member_unread',
           'explicit_copy_order','lexicographic_copy_order','reverse_copy_order','category_role_order_swap']
    rows=[{'snapshot_id':'a','case':n,'passed':True}for n in names]
    rows.append({'snapshot_id':'a','case':'one_current_member_partial:csv','passed':False})
    durable(guard,{'payload_sha256':sha(payload),'cases':rows,'status':'failed'})
    assert len(check_empirical_guards(payload,guard)['advisory_failures'])==1
    rows[0]['passed']=False;durable(guard,{'payload_sha256':sha(payload),'cases':rows})
    with pytest.raises(ValueError,match='permission'):
        check_empirical_guards(payload,guard)


def test_plain_record_lowering_preserves_literal_data_and_builds_current_values():
    assert lower_program({'answer':['var','current'],'count':3})==[
        'object',{'answer':['var','current'],'count':['lit',3]}]
    literal={'bindings':[],'result':'unchanged'}
    assert lower_program(['lit',literal])==['lit',literal]


def test_repair_explanation_is_not_progress_but_program_change_is():
    a={'candidate_patch':{'guard':['lit',False]},'reason':'first'}
    b={**a,'reason':'another explanation'}
    assert repair_progress_signature(a,'same')==repair_progress_signature(b,'same')
    b['candidate_patch']={'guard':['lit',True]}
    assert repair_progress_signature(a,'same')!=repair_progress_signature(b,'same')


def test_repeated_answer_failure_can_repair_request_scope():
    candidate={'guard':['lit',True],'request':['lit',{}],'bind':['lit',{}]}
    error='training answers mismatch'
    assert repair_components(candidate,error)==['training_witnesses']
    assert repair_components(candidate,error,error)==['request','bind','training_witnesses']
    assert repair_components(candidate,'guard_never_matches')==['guard']
    assert repair_components(candidate,'invalid learned question builder')==['request']
    assert repair_components(candidate,'bounded_array_required',phase='request')==['request']
    assert repair_components(candidate,'unsafe_get',phase='bind')==['bind']


def test_preparation_scope_error_is_recorded_as_pre_provider_fallback_only_in_probe_mode():
    candidate={'format':'geneloop-learned-decision-v1','description':'diagnostic',
        'scope_description':'diagnostic','guard':['lit',True],
        'request':['get',['var','input'],['lit','request']],
        'bind':['get',['var','input'],['lit','constructor']],
        'training_witnesses':[{'snapshot_id':'a','values':{}}]}
    with pytest.raises(ValueError,match='invalid learned question builder'):
        replay(candidate,{},None)
    probe=replay(candidate,{},None,preparation_probe=True)
    assert probe['request']is None and probe['scope_fallback_before_provider']
    assert 'invalid learned question builder'in probe['preparation_error']
    context={'request':{'state':'diagnostic','questions':[{'id':'q','question':{'type':'noul','instructions':'diagnostic'}}]}}
    # A valid preparation may not hide a binding defect as a successful scope exit.
    assert replay(candidate,context,{},preparation_probe=True)['request']
    with pytest.raises(ValueError,match='unsafe_get'):
        replay(candidate,context,{})


def test_identical_duplicate_json_verdict_needs_no_paid_retry_but_conflicts_are_rejected():
    text='{"passed":true,"critical_errors":[]}'
    assert decode_model_json(text+'\n```json\n'+text+'\n```')==json.loads(text)
    assert decode_model_json('```json\n'+text+'\n```')==json.loads(text)
    with pytest.raises(ValueError,match='conflicting'):
        decode_model_json(text+'\n{"passed":false}')
    with pytest.raises(ValueError):decode_model_json(text+'\nHere is my answer.')


def test_root_lexical_generation_lowers_verbatim_and_keeps_original_response(tmp_path):
    # Synthetic decoder diagnostic only; never an actual paid-source witness.
    rawdir=tmp_path/'raw';candidate={'format':'geneloop-learned-decision-v1','description':'toy','scope_description':'toy',
        'guard':{'bindings':[],'result':False},'request':{'bindings':[],'result':{'mode':'direct'}},
        'bind':{'bindings':[],'result':None},'training_witnesses':[{'snapshot_id':'toy','values':{}}]}
    answer={'candidate':candidate};durable(rawdir/'input.json',{})
    durable(rawdir/'request.json',{'messages':[]})
    response={'choices':[{'message':{'content':json.dumps(answer)}}]};durable(rawdir/'response.json',response)
    raw=rawdir/'result.json';durable(raw,{'status':'completed','answer':answer})
    result=materialize_program_generation(raw,tmp_path/'lowered');value=generated_candidate(result)
    assert value['guard']==['lit',False]
    assert value['request']==['object',{'mode':['lit','direct']}]
    assert json.loads(raw.read_text())['answer']==answer
    replay = json.loads(result.read_text())
    replay_proof = replay['root_lowering']
    previous = next(digest for digest, version in lowering.REPLAY_DIGESTS.items() if version == lowering.VERSION)
    replay_proof['module_sha256'] = previous
    durable(result, replay)
    assert generated_candidate(result) == value
    replay_proof['module_sha256'] = 'f' * 64
    durable(result, replay)
    with pytest.raises(ValueError,match='program generation lowering changed'):generated_candidate(result)
    replay_proof['module_sha256'] = previous
    durable(result, replay)
    response['choices'][0]['message']['content']='{}';durable(rawdir/'response.json',response)
    with pytest.raises(ValueError,match='raw program generation changed'):generated_candidate(result)


def test_partial_model_tree_edit_is_retained_without_compiling_or_activating(tmp_path,monkeypatch):
    from src.adapters import learned_decision_learning as learning
    base=tmp_path/'base.json';diagnostic=tmp_path/'diagnostic.json';job=tmp_path/'repair'
    candidate={'guard':['and',['eq',['lit',1]],['count',['lit',[]],['lit',0]]],
               'request':['lit',None],'bind':['lit',None]}
    durable(base,{'candidate':candidate});durable(diagnostic,{'syntax':'two distinct malformed nodes'})
    patch={'component':'guard','base_program_sha256':learning.digest(candidate['guard']),
           'replacements':[{'path':[1],'replacement':['eq',['lit',1],['lit',1]]}]}
    def model_call(config,home,*args,**kwargs):
        durable(home/'response.json',{'choices':[{'message':{'content':json.dumps(patch)}}]})
        value={'status':'completed','answer':patch};durable(home/'result.json',value);return value
    monkeypatch.setattr(learning,'generated_candidate',lambda _:candidate)
    monkeypatch.setattr(learning,'model_json',model_call)
    monkeypatch.setattr(learning,'compile_candidate',lambda *a,**k:pytest.fail('invalid partial edit cannot compile'))
    outcome=learning.revise_program_subtrees('unused',base,diagnostic,job,1,'toy',{},'unused','guard')
    assert outcome['status']=='tree_revision_rejected'
    retained=json.loads((job/'revision-1/result.json').read_text())
    assert retained['answer']['candidate']['guard']==['and',patch['replacements'][0]['replacement'],candidate['guard'][2]]
    assert retained['component_revision']['host_authored_replacement']is False
    assert not (job/'payload-1.json').exists()


def test_existing_model_program_can_learn_from_new_sources_without_losing_provenance(tmp_path,monkeypatch):
    from src.adapters import learned_decision_learning as learning
    candidate={'format':'geneloop-learned-decision-v1','description':'toy','scope_description':'toy',
        'guard':['lit',False],'request':['lit',None],'bind':['lit',None],
        'training_witnesses':[{'snapshot_id':'old','values':{}}]}
    raw=tmp_path/'original';answer={'candidate':candidate};durable(raw/'input.json',{})
    durable(raw/'request.json',{'messages':[]})
    durable(raw/'response.json',{'choices':[{'message':{'content':json.dumps(answer)}}]})
    durable(raw/'result.json',{'status':'completed','answer':answer})
    base=materialize_program_generation(raw/'result.json',tmp_path/'base')
    sources=tmp_path/'new-sources.json';durable(sources,{'opportunities':[{'snapshot_id':'new','context':{'goal':'new toy'}}]})
    diagnostic=tmp_path/'feedback.json';durable(diagnostic,{'reason':'new real trajectories in production; toy fixture here'})
    patch={'candidate_patch':{'guard':['lit',True],'training_witnesses':[{'snapshot_id':'new','values':{}}]}}
    def model_call(config,home,system,data,**kwargs):
        durable(home/'input.json',data);durable(home/'request.json',{'messages':[]})
        durable(home/'response.json',{'choices':[{'message':{'content':json.dumps(patch)}}]})
        value={'status':'completed','answer':patch};durable(home/'result.json',value);return value
    monkeypatch.setattr(learning,'model_json',model_call)
    monkeypatch.setattr(learning,'component_revision_system',lambda *a:'toy')
    monkeypatch.setattr(learning,'compile_candidate',lambda *a,**k:{'candidate_sha256':'toy'})
    job=tmp_path/'extension';outcome=learning.revise_components('unused',base,diagnostic,job,1,'toy',{},sources,
        components=['guard','training_witnesses'],source_extension_file=sources)
    assert outcome['status']=='compiled'
    revision=job/'revision-1/result.json';learned=generated_candidate(revision)
    assert learned['guard']==['lit',True]and learned['bind']==candidate['bind']
    assert learned['training_witnesses'][0]['snapshot_id']=='new'
    assert learning.generation_root(revision)==job/'patch-1/result.json'
    durable(sources,{'opportunities':[]})
    with pytest.raises(ValueError,match='new actual training sources changed'):generated_candidate(revision)
