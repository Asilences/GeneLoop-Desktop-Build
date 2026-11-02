"""Encoding/diagnostic tests only. No model, rendering, or quality claims."""
import copy
import json
import pytest
from src.adapters.capability_authoring import aliases, authoring_context, expand_draft, compact_proposal, diagnose
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability_snapshot
from tests.test_capability_builder import setup


def data():
    snapshot,proposal=setup()
    task={'id':'diagnostic','instruction':'Compose current inputs','contract':proposal['contract']}
    return snapshot,proposal,task,compact_proposal(proposal,task,snapshot)


def test_compact_roundtrip_preserves_full_identity_and_choices():
    snapshot,proposal,task,draft=data()
    assert set(draft)=={'steps','output'}
    assert all(set(step)=={'id','use','args'} for step in draft['steps'])
    assert expand_draft(draft,task,snapshot)==proposal
    assert compile_proposal(expand_draft(draft,task,snapshot),snapshot,'owner')==compile_proposal(proposal,snapshot,'owner')
    context=authoring_context(task,snapshot,{})
    assert 'snapshot' not in context and 'owner' not in context
    assert context['contract_mode']=='host_fixed'


def test_open_interface_is_model_designed_and_compiled():
    snapshot,proposal,task,draft=data();del task['contract']
    with pytest.raises(ValueError,match='draft_shape'):expand_draft(draft,task,snapshot)
    draft['contract']=proposal['contract']
    assert expand_draft(draft,task,snapshot)==proposal
    assert authoring_context(task,snapshot,{})['contract_mode']=='model_designed'


def test_scene_wrapper_preserves_seed_and_admitted_material_descriptions():
    snapshot,_,task,_=data();refs=snapshot['roots']
    catalog={'source_catalog':{'seed':{'catalog':[{'capability':refs[0],
        'description':'Read current BibTeX entries','example_parameters':{'paths':['/work/inputs/current.bib']}}]},
        'admitted_materials':[{'capability':refs[1],'description':'Count current citation keys'},
                              {'capability':{'id':'not-visible','sha256':'0'*64},'description':'ignored'}]}}
    context=authoring_context(task,snapshot,catalog)
    assert [c['description'] for c in context['capabilities']]==['Read current BibTeX entries','Count current citation keys']
    assert context['capabilities'][0]['example_parameters']=={'paths':['/work/inputs/current.bib']}
    assert len(context['capabilities'])==len(refs)
    assert [c['contract'] for c in context['capabilities']]==[next(c['contract'] for c in snapshot['capabilities'] if c['id']==r['id']) for r in refs]


@pytest.mark.parametrize('extra', ['owner','format','contract','certificate','dependencies'])
def test_fixed_metadata_cannot_be_overridden(extra):
    snapshot,_,task,draft=data();draft[extra]={}
    with pytest.raises(ValueError,match='draft_shape'):expand_draft(draft,task,snapshot)


def test_alias_scope_does_not_include_closure_only_capabilities():
    snapshot,proposal,task,draft=data()
    built=compile_proposal(proposal,snapshot,'owner')['snapshot']
    draft['steps'][0]['use']='c2'
    with pytest.raises(ValueError) as error:expand_draft(draft,task,built)
    assert diagnose(error.value)['issues'][0]['path']==['steps',0,'use']


def test_learned_composition_definition_visible_without_version_copying():
    snapshot,proposal,task,_=data();built=compile_proposal(proposal,snapshot,'owner')['snapshot']
    context=authoring_context(task,built,{})
    assert context['capabilities'][0]['kind']=='composition'
    assert len(context['capabilities'][0]['definition']['steps'])==2
    assert context['capabilities'][0]['definition']['steps'][0]['use']=='non_selectable_dependency'


def test_binding_shortcuts_do_not_guess_or_strip_unknown_operators():
    snapshot,_,task,draft=data()
    for value in ({'$input':[],'extra':1},{'$unknown':[]},{'$step':[]},{'$input':[0]},{'$input':['__proto__']}):
        bad=copy.deepcopy(draft);bad['steps'][0]['args']=value
        with pytest.raises(ValueError):expand_draft(bad,task,snapshot)


def test_actual_compiler_locates_reference_type_and_forward_dependency_failures():
    snapshot,proposal,_,_=data()
    bad=copy.deepcopy(proposal);bad['steps'][1]['capability']['sha256']='0'*64
    with pytest.raises(ValueError) as err:compile_proposal(bad,snapshot,'owner')
    diagnostic=diagnose(err.value)
    assert diagnostic['issues'][0]['path']==['steps',1,'capability']
    assert 'steps/0/capability' in diagnostic['passed_checks']
    bad=copy.deepcopy(proposal);bad['steps'][1]['arguments']['fields']['value']={'kind':'literal','value':'wrong type'}
    with pytest.raises(ValueError) as err:compile_proposal(bad,snapshot,'owner')
    diagnostic=diagnose(err.value)
    assert diagnostic['issues'][0]['path']==['steps',1,'arguments','fields','value']
    assert diagnostic['issues'][0]['expected']=={'type':'integer'}
    assert 'steps/0/arguments' in diagnostic['passed_checks']
    bad=copy.deepcopy(proposal);bad['steps'][0]['arguments']={'kind':'step','step_id':'second','path':[]}
    with pytest.raises(ValueError) as err:compile_proposal(bad,snapshot,'owner')
    assert diagnose(err.value)['issues'][0]['path']==['steps',0,'arguments','step_id']


def test_same_error_at_different_location_is_reported_by_original_validator():
    snapshot,proposal,_,_=data()
    for index in [0,1]:
        bad=copy.deepcopy(proposal);bad['steps'][index]['arguments']={'value':{'kind':'input','path':['value']}}
        with pytest.raises(ValueError) as err:compile_proposal(bad,snapshot,'owner')
        diagnostic=diagnose(err.value)
        assert diagnostic['issues'][0]['path']==['steps',index,'arguments']
        assert diagnostic['issues'][0]['actual']==bad['steps'][index]['arguments']


def test_literal_json_and_arrays_preserve_values_without_parsing_strings():
    snapshot,_,task,draft=data()
    draft['steps'][0]['args']={'value':{'$literal':{'$input':['not-a-reference']}}}
    expanded=expand_draft(draft,task,snapshot)
    assert expanded['steps'][0]['arguments']['fields']['value']=={'kind':'literal','value':{'$input':['not-a-reference']}}
    draft['output']=[{'$step':['first']},'$input.value',None,True]
    expanded=expand_draft(draft,task,snapshot)
    assert expanded['output']['items'][1]=={'kind':'literal','value':'$input.value'}


def test_wrapper_replay_edit_is_minimal_and_does_not_mutate_source():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('replay',Path(__file__).resolve().parents[1]/'scripts/replay-capability-proposal.py')
    replay=importlib.util.module_from_spec(spec);spec.loader.exec_module(replay)
    snapshot,proposal,_,_=data()
    original=copy.deepcopy(proposal)
    proposal['steps'][1]['arguments']=proposal['steps'][1]['arguments']['fields']
    before=copy.deepcopy(proposal)
    fixed,patches=replay.repair_wrappers(proposal)
    assert proposal==before and fixed==original
    assert patches[0]['path']==['steps',1,'arguments']
    assert compile_proposal(fixed,snapshot,'owner')['capability']['certification']=='candidate'
    proposal['steps'][1]['arguments']={'value':123}  # not an already typed child
    unchanged,patches=replay.repair_wrappers(proposal)
    assert unchanged==proposal and not patches


def test_different_snapshot_cannot_change_aliases_inside_existing_repair(tmp_path, monkeypatch):
    from scenarios.remotion_edit.structured import run_capability_loop as pilot
    snapshot,proposal,task,_=data()
    pilot.prepare_attempt(task=task,catalog={},snapshot=snapshot,output=tmp_path/'original')
    subset=create_capability_snapshot(snapshot['owner'],[snapshot['roots'][0]],[next(c for c in snapshot['capabilities'] if c['id']==snapshot['roots'][0]['id'])])
    with pytest.raises(ValueError,match='repair_context_changed'):
        pilot.prepare_attempt(task=task,catalog={},snapshot=subset,output=tmp_path/'changed',repair_from=tmp_path/'original')
