"""Adversarial admission diagnostics, without model calls or real account writes."""
import json
from pathlib import Path
import pytest
from src.adapters.learned_decision_certificate import execution_evidence, reviewed
from src.adapters.learned_decision_learning import schema_default_arguments, source_opportunities, generated_candidate
from src.motif_core.reuse.experience_registry import sha


def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v))


@pytest.mark.parametrize('changes',[
    {'accepted':False}, {'provider_mode':'mock'}, {'accounting_complete':False},
    {'lifecycle_verified':False}, {'metrics':{'acceptance_repairs':1}},
])
def test_task_pass_cannot_substitute_for_clean_real_execution(tmp_path,changes):
    payload=tmp_path/'payload.json';result=tmp_path/'task/result.json';origin=tmp_path/'origin'
    put(payload,{'owner':'owner'})
    put(result,{'session_id':'session'})
    put(origin/'task.json',{'owner':'owner','learning_eligible':False})
    record={'origin':str(origin),'provider_mode':'real','accepted':True,
            'accounting_complete':True,'lifecycle_verified':True,'metrics':{'acceptance_repairs':0}}
    put(tmp_path/'records/session.json',{**record,**changes})
    with pytest.raises(ValueError,match='clean, sealed'):
        execution_evidence(payload,result,tmp_path)


def test_review_needs_explicit_pass_and_no_critical_errors():
    assert reviewed({'status':'completed','answer':{'passed':True,'critical_errors':[]}})
    assert not reviewed({'status':'completed','answer':{'passed':True,'critical_errors':['wrong binding']}})
    assert not reviewed({'status':'failed','answer':{'passed':True,'critical_errors':[]}})
    assert not reviewed({'status':'completed','answer':{'passed':True}})


def test_schema_defaults_do_not_hide_explicit_argument_or_identity_changes():
    schema={'type':'object','properties':{'actions':{'type':'array','items':{'$ref':'#/$defs/Action'}}},
            '$defs':{'Action':{'type':'object','properties':{'root':{'default':'current'},'id':{'type':'string'}}}}}
    original={'actions':[{'id':'a'}]}
    explicit={'actions':[{'id':'a','root':'current'}]}
    assert schema_default_arguments(original,schema)==schema_default_arguments(explicit,schema)
    assert original=={'actions':[{'id':'a'}]}
    for action in ({'id':'a','root':'external'},{'id':'b'},{'id':'a','extra':True}):
        assert schema_default_arguments(original,schema)!=schema_default_arguments({'actions':[action]},schema)


@pytest.mark.parametrize('failure',[{'error':'tool rejected current arguments'},{'isError':True}])
def test_accepted_task_does_not_make_a_failed_local_tool_a_learning_witness(tmp_path,monkeypatch,failure):
    from src.adapters import continuous_motif_learning
    origin=tmp_path/'origin';out=tmp_path/'run';capture=out/'decision-captures/snapshot/request.json'
    call={'type':'tool-call','id':'native-model-call','name':'demo_tool','arguments':{}}
    put(origin/'task.json',{'learning_eligible':True})
    events=out/'agent-events.jsonl';events.parent.mkdir(parents=True,exist_ok=True)
    events.write_text(json.dumps({'type':'assistant/message','data':{'usage':{'totalTokens':10},'message':{'content':[call]}}})+'\n')
    put(capture,{'snapshot_id':'snapshot','session_id':'session','source_mode':'harness_plus_motif',
                 'context':{'goal':'diagnostic'},'tools':[]})
    put(capture.parent/'completion.json',{'request_sha256':sha(capture)})
    (capture.parent/'chunks.jsonl').write_text(json.dumps({'type':'block-end','block':call})+'\n')
    record=tmp_path/'record.json'
    put(record,{'provider_mode':'real','accepted':True,'accounting_complete':True,'lifecycle_verified':True,
                'origin':str(origin),'run_dir':str(out),'events_sha256':sha(events),'session_id':'session',
                'input_sha256':'current-input','upstream_requests':1,'metrics':{}})
    monkeypatch.setattr(continuous_motif_learning,'observations',lambda events:[{
        'call_id':call['id'],'name':'demo_tool','args':{},'out':{'_sss_scope':{'input_sha256':'current-input'},**failure}}])
    result=source_opportunities([record])
    assert result['opportunities']==[]
    assert len(result['excluded'])==1


def test_model_component_revision_rejects_a_host_edited_program(tmp_path):
    base=tmp_path/'base/result.json';patch=tmp_path/'patch/result.json';output=tmp_path/'revision/result.json'
    candidate={'format':'diagnostic-only','guard':['lit',False]}
    answer={'candidate':candidate};delta={'candidate_patch':{'guard':['lit',True]}}
    put(base,{'status':'completed','answer':answer})
    put(base.parent/'response.json',{'choices':[{'message':{'content':json.dumps(answer)}}]})
    put(patch,{'status':'completed','answer':delta})
    put(patch.parent/'response.json',{'choices':[{'message':{'content':json.dumps(delta)}}]})
    proof={'base_result_file':str(base),'base_result_sha256':sha(base),
           'patch_result_file':str(patch),'patch_result_sha256':sha(patch),
           'patch_response_sha256':sha(patch.parent/'response.json')}
    expected={**candidate,**delta['candidate_patch']}
    put(output,{'status':'completed','answer':{'candidate':expected},'component_revision':proof})
    assert generated_candidate(output)==expected
    put(output,{'status':'completed','answer':{'candidate':{**expected,'guard':['lit','host edit']}},'component_revision':proof})
    with pytest.raises(ValueError,match='differs from verified model'):
        generated_candidate(output)


def test_component_revision_cannot_rewrite_the_candidate_protocol(tmp_path):
    base=tmp_path/'base/result.json';patch=tmp_path/'patch/result.json';output=tmp_path/'revision/result.json'
    candidate={'format':'diagnostic-only','guard':['lit',False]};answer={'candidate':candidate}
    delta={'candidate_patch':{'format':'host-capability-bypass'}}
    put(base,{'status':'completed','answer':answer})
    put(base.parent/'response.json',{'choices':[{'message':{'content':json.dumps(answer)}}]})
    put(patch,{'status':'completed','answer':delta})
    put(patch.parent/'response.json',{'choices':[{'message':{'content':json.dumps(delta)}}]})
    put(output,{'status':'completed','answer':{'candidate':{**candidate,**delta['candidate_patch']}},'component_revision':{
        'base_result_file':str(base),'base_result_sha256':sha(base),'patch_result_file':str(patch),
        'patch_result_sha256':sha(patch),'patch_response_sha256':sha(patch.parent/'response.json')}})
    with pytest.raises(ValueError,match='invalid model component'):
        generated_candidate(output)


def test_history_learning_view_keeps_order_and_complete_chunks_without_mutating_capture():
    from src.adapters.learned_decision_learning import project_native_context, learning_system
    context={'goal':'full read','last_tool':'coverage','receipts':{'read_chunk':{'text':'second page'}},
        'history':[{'tool':'read_chunk','call_id':'first','args':{},'out':{'text':'first page','sha256':'version-a'}},
                   {'tool':'read_chunk','call_id':'second','args':{},'out':{'text':'second page','sha256':'version-a'}}]}
    assert 'history' not in project_native_context(context)
    projected=project_native_context(context,include_history=True)
    assert [r['call_id'] for r in projected['history']]==['first','second']
    projected['history'][0]['out']['text']='changed copy'
    assert context['history'][0]['out']['text']=='first page'
    prompt=learning_system({'opportunities':[{'context':context}]})
    assert 'input.history' in prompt and 'stale, missing or truncated' in prompt


def test_history_learning_refuses_to_invent_unrecorded_pages():
    from src.adapters.learned_decision_learning import project_native_context
    with pytest.raises(ValueError,match='original ordered'):
        project_native_context({'goal':'read'},include_history=True)
    with pytest.raises(ValueError,match='original ordered'):
        project_native_context({'history':[{'text':'page without native call binding'}]},include_history=True)


def test_history_guard_counterexamples_invalidate_all_live_receipt_aliases():
    from src.adapters.learned_decision_certificate import history_guard_contexts
    inventory={'files':[{'file_id':'current-a','path':'a.txt','sha256':'a'*64}]}
    first={'text':'page one','truncated':False};second={'text':'page two','next_request_id':None}
    context={'goal':'read and organize','last_tool':'mcp__file_management__document_coverage',
        'receipts':{'mcp__file_management__list_files':inventory,'mcp__file_management__read_document_chunk':second,
                    'mcp__file_management__document_coverage':{'complete':True}},
        'history':[{'tool':'mcp__file_management__list_files','call_id':'list','args':{},'out':inventory},
                   {'tool':'mcp__file_management__read_document_chunk','call_id':'p1','args':{},'out':first},
                   {'tool':'mcp__file_management__read_document_chunk','call_id':'p2','args':{},'out':second}]}
    cases=history_guard_contexts(context)
    assert [r['call_id'] for r in cases['all_read_evidence_absent']['history']]==['list']
    partial=cases['all_read_evidence_partial']
    assert partial['history'][1]['out']['truncated'] is True
    assert partial['receipts']['mcp__file_management__document_coverage']['complete'] is False
    assert partial['history'][2]['out']['next_request_id']=='synthetic-unreturned-continuation'
    assert len(cases['new_inventory_member_unread']['receipts']['mcp__file_management__list_files']['files'])==2
    assert len(context['receipts']['mcp__file_management__list_files']['files'])==1
    assert context['history'][1]['out']['truncated'] is False


def test_history_requires_original_outputs_order_and_no_future_receipt():
    from src.adapters.learned_decision_learning import verify_native_history
    row={'tool':'read_chunk','call_id':'real-call','args':{'request_id':'q'},'out':{'text':'actual page'}}
    actual={'real-call':{'name':'read_chunk','args':row['args'],'out':row['out'],'result_seq':4}}
    assert verify_native_history({'history':[row]},actual,before_sequence=7)
    with pytest.raises(ValueError,match='earlier sealed'):
        verify_native_history({'history':[row,row]},actual,before_sequence=7)
    with pytest.raises(ValueError,match='earlier sealed'):
        verify_native_history({'history':[row]},actual,before_sequence=3)
    with pytest.raises(ValueError,match='earlier sealed'):
        verify_native_history({'history':[{**row,'out':{'text':'invented page'}}]},actual,before_sequence=7)


def test_candidate_schema_failure_identifies_missing_components_before_replay(tmp_path):
    from src.adapters.learned_decision_learning import compile_candidate
    candidate={'format':'geneloop-learned-decision-v1','description':'diagnostic','scope_description':'diagnostic','guard':['lit',False]}
    result=tmp_path/'proposal/result.json';sources=tmp_path/'sources.json'
    put(result,{'status':'completed','answer':{'candidate':candidate,'request':['lit',{}]}})
    put(result.parent/'response.json',{'choices':[{'message':{'content':json.dumps({'candidate':candidate,'request':['lit',{}]})}}]})
    put(sources,{'opportunities':[]})
    with pytest.raises(ValueError,match='schema mismatch: missing=bind,request,training_witnesses'):
        compile_candidate(result,sources,tmp_path/'never-published.json','fixture',{})
    assert not (tmp_path/'never-published.json').exists()


def test_component_repair_prompt_uses_only_patch_envelope_and_retains_history_rules():
    from src.adapters.learned_decision_learning import component_revision_system
    prompt=component_revision_system({'opportunities':[{'context':{'history':[]}}]})
    assert 'candidate_patch' in prompt
    assert 'Return JSON {"candidate":' not in prompt
    assert 'or candidate:null' not in prompt
    assert 'COMPLETE expression ARRAY' in prompt
    assert 'input.history' in prompt
    assert 'input.answers' in prompt
    assert 'new text heuristics' in prompt


def test_semantic_necessity_rejects_deterministic_decorative_or_wrong_tool_reviews():
    from src.adapters.learned_decision_learning import semantic_necessity_passes
    answer={'witnessed_tools':['demo_classify'],'decision_scope':'whole_witnessed_tool_call',
        'requires_semantic_model':True,'deterministic_solution_sufficient':False,
        'unresolved_semantic_predicate':'Which meaning best describes the current unstructured text?',
        'bounded_answer_types':['choice'],'critical_errors':[]}
    assert semantic_necessity_passes({'status':'completed','answer':answer},['demo_classify'])
    for patch in ({'deterministic_solution_sufficient':True},{'requires_semantic_model':'true'},
                  {'unresolved_semantic_predicate':''},{'bounded_answer_types':['free_text']},
                  {'witnessed_tools':['earlier_copy_tool']},{'critical_errors':['missing evidence']}):
        assert not semantic_necessity_passes({'status':'completed','answer':{**answer,**patch}},['demo_classify'])
    assert not semantic_necessity_passes({'status':'failed','answer':answer},['demo_classify'])


def test_structured_learning_response_keeps_raw_function_arguments_and_rejects_other_tools():
    from src.adapters.learned_decision_learning import model_response_answer,normalize_learning_stream
    frames=[{'model':'diagnostic','choices':[{'delta':{'tool_calls':[{'index':0,'id':'call-real','function':{'name':'submit_learning_result','arguments':'{"candidate_patch":'}}]}}]},
            {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':'{"guard":["lit",true]}}'}}]}}]}]
    transport='\n'.join('data: '+json.dumps(v) for v in frames)+'\ndata: [DONE]\n'
    raw=normalize_learning_stream(transport)
    assert raw['choices'][0]['message']['content']==''
    assert model_response_answer({'response_decoder':'function_arguments'},raw)=={'candidate_patch':{'guard':['lit',True]}}
    raw['choices'][0]['message']['tool_calls'][0]['function']['name']='some_task_tool'
    with pytest.raises(ValueError,match='structured learning response'):
        model_response_answer({'response_decoder':'function_arguments'},raw)


def test_partial_component_recovery_cannot_cherry_pick_by_semantic_result(tmp_path):
    from src.adapters.learned_decision_learning import recover_syntax_valid_components
    base=tmp_path/'base/result.json';patch=tmp_path/'patch/result.json';out=tmp_path/'recovered/result.json'
    candidate={'format':'diagnostic-only','guard':['lit',False],'bind':['lit',None]}
    answer={'candidate':candidate};delta={'candidate_patch':{'guard':['eval',['lit','not allowed']],'bind':['lit',{'diagnostic':'unchanged raw model value'}]}}
    put(base,{'status':'completed','answer':answer})
    put(base.parent/'response.json',{'choices':[{'message':{'content':json.dumps(answer)}}]})
    put(patch,{'status':'completed','answer':delta})
    put(patch.parent/'response.json',{'choices':[{'message':{'content':json.dumps(delta)}}]})
    result=recover_syntax_valid_components(base,patch,out,['guard','bind'])
    assert result['component_revision']['admitted_components']==['bind']
    assert generated_candidate(out)=={**candidate,'bind':delta['candidate_patch']['bind']}
    assert result['component_revision']['task_score_used_for_selection'] is False
    forged=json.loads(out.read_text());forged['component_revision']['admitted_components']=['guard'];put(out,forged)
    with pytest.raises(ValueError,match='all syntax-valid'):
        generated_candidate(out)


def test_unordered_source_namespace_abstains_on_temporal_goal_variants():
    from src.adapters.learned_decision_certificate import copy_order_guard_contexts
    original={'goal':'Read and classify current files.','history':[{'tool':'real_read'}]}
    variants=copy_order_guard_contexts(original)
    assert set(variants)=={'explicit_copy_order','lexicographic_copy_order','reverse_copy_order'}
    assert all(v['goal'].startswith(original['goal']) and v['history']==original['history'] for v in variants.values())
    assert original['goal']=='Read and classify current files.'


def test_model_subtree_revision_preserves_raw_replacements_and_rejects_overlap():
    from src.motif_core.offline.compilation.decision_program_revision import apply_model_tree_edits
    from src.motif_core.reuse.experience_registry import digest
    program=['array',['lit',1],['lit',2]]
    answer={'component':'bind','base_program_sha256':digest(program),
            'replacements':[{'path':[1],'replacement':['lit',3]}]}
    assert apply_model_tree_edits(program,answer,'bind')==['array',['lit',3],['lit',2]]
    assert program==['array',['lit',1],['lit',2]]
    with pytest.raises(ValueError,match='overlapping'):
        apply_model_tree_edits(program,{**answer,'replacements':answer['replacements']*2},'bind')
    with pytest.raises(ValueError,match='base changed'):
        apply_model_tree_edits(program,{**answer,'base_program_sha256':'wrong'},'bind')
    with pytest.raises(ValueError,match='existing node'):
        apply_model_tree_edits(program,{**answer,'replacements':[{'path':[-1],'replacement':['lit',3]}]},'bind')


def test_tree_revision_provenance_cannot_replace_host_stored_program(tmp_path):
    from src.motif_core.reuse.experience_registry import digest
    base=tmp_path/'base/result.json';patch=tmp_path/'patch/result.json';out=tmp_path/'composite/result.json'
    candidate={'bind':['array',['lit',1]],'guard':['lit',True]}
    answer={'candidate':candidate};delta={'component':'bind','base_program_sha256':digest(candidate['bind']),
                                       'replacements':[{'path':[1],'replacement':['lit',2]}]}
    put(base,{'status':'completed','answer':answer})
    put(base.parent/'response.json',{'choices':[{'message':{'content':json.dumps(answer)}}]})
    put(patch,{'status':'completed','answer':delta})
    put(patch.parent/'response.json',{'choices':[{'message':{'content':json.dumps(delta)}}]})
    value={'status':'completed','answer':{'candidate':{**candidate,'bind':['array',['lit',2]]}},
           'component_revision':{'base_result_file':str(base),'base_result_sha256':sha(base),
             'patch_result_file':str(patch),'patch_result_sha256':sha(patch),
             'patch_response_sha256':sha(patch.parent/'response.json'),'tree_component':'bind','allowed_components':['bind']}}
    put(out,value)
    assert generated_candidate(out)['bind']==['array',['lit',2]]
    value['answer']['candidate']['bind']=['array',['lit',999]];put(out,value)
    with pytest.raises(ValueError,match='differs from verified'):
        generated_candidate(out)


def test_model_tree_moves_only_relocate_existing_expressions():
    from src.motif_core.offline.compilation.decision_program_revision import apply_model_tree_edits
    from src.motif_core.reuse.experience_registry import digest
    invalid=['let','outer',['lit',1],['let','inner',['lit',2]],['var','inner']]
    answer={'component':'bind','base_program_sha256':digest(invalid),
            'moves':[{'from':[4],'path':[3,3]}]}
    assert apply_model_tree_edits(invalid,answer,'bind')==[
        'let','outer',['lit',1],['let','inner',['lit',2],['var','inner']]]
    assert len(invalid)==5
    with pytest.raises(ValueError,match='own descendant'):
        apply_model_tree_edits(invalid,{**answer,'moves':[{'from':[3],'path':[3,3]}]},'bind')
    with pytest.raises(ValueError,match='array insertion'):
        apply_model_tree_edits(invalid,{**answer,'moves':[{'from':[4],'path':[3,30]}]},'bind')


def test_component_revision_recovers_root_contract_after_tree_revision(tmp_path,monkeypatch):
    import src.adapters.learned_decision_learning as learning
    root=tmp_path/'root/result.json';current=tmp_path/'tree/result.json'
    source=tmp_path/'sources.json';diagnostic=tmp_path/'diagnostic.json'
    put(root,{'status':'completed'})
    put(root.parent/'input.json',{'source_equivalence_policy':'root-declared-policy',
                                 'no_certification_or_test_materials_supplied':True})
    put(current,{'component_revision':{'base_result_file':str(root),
                                      'patch_result_file':str(tmp_path/'tree-patch/result.json')}})
    put(tmp_path/'tree-patch/input.json',{'component':'bind'})
    put(source,{'opportunities':[{'context':{'goal':'source goal'}}]});put(diagnostic,{'error':'training-only'})
    monkeypatch.setattr(learning,'generated_candidate',lambda _: {'guard':['lit',True]})
    monkeypatch.setattr(learning,'component_revision_system',lambda *_:'diagnostic-only')
    observed={}
    def no_paid_call(_config,_home,_system,data,**kwargs):
        observed.update(data);return {'status':'failed','error':'offline diagnostic, no API'}
    monkeypatch.setattr(learning,'model_json',no_paid_call)
    result=learning.revise_components('unused',current,diagnostic,tmp_path/'job',1,'owner',{},source,components=['guard'])
    assert result['status']=='generation_failed'
    assert observed['source_equivalence_policy']=='root-declared-policy'
    assert observed['no_certification_or_test_materials_supplied'] is True


def test_category_role_guard_mutates_goal_aliases_without_changing_material():
    from src.adapters.learned_decision_certificate import quoted_category_guard_contexts
    goal='按「说明」「许可」「数据」「会议」分类复制。'
    original={'goal':goal,'receipts':{'mcp__file_management__read_task':{'objective':goal},'real_read':{'text':'unchanged body'}},
              'history':[{'tool':'mcp__file_management__read_task','out':{'objective':goal}}]}
    cases=quoted_category_guard_contexts(original)
    assert len(cases)==3
    for context in cases.values():
        assert context['goal']!=goal
        assert context['receipts']['mcp__file_management__read_task']['objective']==context['goal']
        assert context['history'][0]['out']['objective']==context['goal']
        assert context['receipts']['real_read']==original['receipts']['real_read']
    assert original['goal']==goal and original['history'][0]['out']['objective']==goal


def test_boundary_full_read_requires_each_identity_and_current_version():
    from src.adapters.learned_decision_learning import complete_file_read_evidence
    files=[{'file_id':'a','sha256':'same-bytes'},{'file_id':'b','sha256':'same-bytes'}]
    context={'receipts':{'mcp__file_management__list_files':{'files':files}},'history':[
        {'tool':'mcp__file_management__pin_files','arguments':{'file_ids':['a','b']},'out':{'file_ids':['a','b'],'source_ids':['sa','sb']}},
        {'tool':'mcp__file_management__read_files','out':{'reads':[
            {'file_id':'a','source_id':'sa','sha256':'same-bytes','status':'readable','text':'preview','truncated':True},
            {'file_id':'b','source_id':'sb','sha256':'same-bytes','status':'readable','text':'full','truncated':False}]}},
        {'tool':'mcp__file_management__document_coverage','out':{'source_id':'sb','source_sha256':'same-bytes','complete':True}}]}
    assert complete_file_read_evidence(context)['complete'] is False
    context['history'].append({'tool':'mcp__file_management__document_coverage','out':{
        'source_id':'sa','source_sha256':'wrong-version','complete':True}})
    assert complete_file_read_evidence(context)['complete'] is False
    context['history'].append({'tool':'mcp__file_management__document_coverage','out':{
        'source_id':'sa','source_sha256':'same-bytes','complete':True}})
    assert complete_file_read_evidence(context)['complete'] is True
    assert complete_file_read_evidence({'receipts':{},'history':[]})['complete'] is False


def test_partial_member_guard_keeps_other_members_and_all_original_receipts():
    from src.adapters.learned_decision_learning import complete_file_read_evidence
    from src.adapters.learned_decision_certificate import individual_read_guard_contexts
    files=[{'file_id':x,'sha256':x+'-version'}for x in ['a','b']]
    original={'goal':'read completely','receipts':{'mcp__file_management__list_files':{'files':files}},'history':[
        {'tool':'mcp__file_management__pin_files','out':{'file_ids':['a','b'],'source_ids':['sa','sb']}},
        *[{'tool':'mcp__file_management__read_file','out':{'file_id':x,'source_id':'s'+x,'sha256':x+'-version',
            'status':'readable','text':'full body','truncated':False}}for x in ['a','b']],
        *[{'tool':'mcp__file_management__document_coverage','out':{'source_id':'s'+x,'source_sha256':x+'-version',
            'complete':True}}for x in ['a','b']]]}
    assert complete_file_read_evidence(original)['complete']
    cases=individual_read_guard_contexts(original)
    for name,context in cases.items():
        proof=complete_file_read_evidence(context)
        assert not proof['complete']
        assert [x['file_id']for x in proof['files']if not x['complete']]==[name.split(':',1)[1]]
        assert len(context['history'])==4
    assert len(original['history'])==5 and complete_file_read_evidence(original)['complete']


def test_incomplete_learning_source_is_rejected_before_any_generation_fee(tmp_path,monkeypatch):
    import src.adapters.learned_decision_learning as learning
    source=tmp_path/'sources.json';selection=tmp_path/'selection.json'
    put(source,{'opportunities':[{'snapshot_id':'actual-boundary','context':{'receipts':{
        'mcp__file_management__list_files':{'files':[{'file_id':'a','sha256':'version'}]}}}}]})
    put(selection,{'status':'completed','answer':{'selected_snapshot_ids':['actual-boundary']}})
    def forbidden(*args,**kwargs):raise AssertionError('incomplete source must never trigger paid generation')
    monkeypatch.setattr(learning,'model_json',forbidden)
    result=learning.generate_from_selection('unused',source,selection,tmp_path/'job',1,require_complete_file_reads=True)
    assert result['status']=='incomplete_training_source' and result['candidate_generation_requests']==0


def test_schema_shape_retrieval_keeps_choice_values_and_ids_as_parameters():
    from src.adapters.learned_decision_learning import rank_repeated_source_pairs
    schema={'type':'object','properties':{'item':{'type':'string'},'category':{'enum':['left','right']}}}
    def source(i,category,session):return {'snapshot_id':i,'session_id':session,
        'context':{'goal':'Classify current raw content.','receipts':{'item':i}},
        'tools':[{'name':'route','parameters':schema}],
        'native_call':{'tool':'route','arguments':{'item':i,'category':category}}}
    rows=rank_repeated_source_pairs({'opportunities':[source('a','left','one'),source('b','right','two')]})
    assert len(rows)==1 and rows[0]['selected_snapshot_ids']==['a','b']
    assert rows[0]['semantic_necessity_not_established'] is True
    assert not rank_repeated_source_pairs({'opportunities':[source('a','left','same'),source('b','right','same')]})
    different=source('b','right','two');different['tools']=[{'name':'route','parameters':{'type':'object'}}]
    assert not rank_repeated_source_pairs({'opportunities':[source('a','left','one'),different]})


def test_direct_input_forwarding_is_not_misreported_as_semantically_determined():
    from src.adapters.learned_decision_learning import rank_repeated_source_pairs
    rows=[{'snapshot_id':x,'session_id':x,'context':{'goal':'Choose relevant current item.','receipts':{'ids':['a','b']}},
           'tools':[{'name':'pick','parameters':{'type':'object'}}],'native_call':{'tool':'pick','arguments':{'id':x}}}for x in ['a','b']]
    pair=rank_repeated_source_pairs({'opportunities':rows})[0]
    assert pair['output_novelty_score']==0 and pair['semantic_necessity_not_established'] is True


def test_whole_generation_repair_cannot_drop_prior_reading_or_source_policy(tmp_path,monkeypatch):
    import src.adapters.learned_decision_learning as learning
    from src.adapters.decision_source_equivalence import POLICY
    previous=tmp_path/'prior/result.json';source=tmp_path/'sources.json'
    put(previous,{'status':'completed','answer':{'candidate':{}},'response_decoder':'function_arguments'})
    put(previous.parent/'input.json',{'source_boundary_reading_policy':'all_current_files_complete_before_decision_v1',
                                     'source_equivalence_policy':POLICY})
    put(source,{'opportunities':[{'context':{'goal':'actual goal'}}]})
    observed={}
    def no_paid_call(*args,**kwargs):observed.update(kwargs);return {'status':'failed','error':'offline-only diagnostic'}
    monkeypatch.setattr(learning,'generate_from_selection',no_paid_call)
    result=learning.refine_from_compiler('unused',source,'unused',tmp_path/'job',previous,2,'owner',{})
    assert result['status']=='generation_failed'
    assert observed['require_complete_file_reads'] is True
    assert observed['allow_disjoint_copy_reordering'] is True
    assert observed['structured_output'] is True
