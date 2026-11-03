"""Model-facing source views retain semantics while hiding host audit plumbing."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scenarios.paper_proofreading.frontier.author import source_primary_context
from scenarios.paper_proofreading.frontier.prepare_D import authoring_presentation
from src.adapters.capability_authoring import authoring_context,aliases
from src.adapters.capability_contract import capability_ref,create_capability_snapshot
from src.adapters.capability_source_authoring import source_callable_interfaces
from tests.test_capability_improvement import put
from tests.test_capability_program_composition import data


def context(task,snapshot,cards=()):
    value=authoring_context(task,snapshot,{})
    value.update(source_callable_interfaces=source_callable_interfaces(snapshot),reference_interfaces=list(cards),repair=None)
    return value


def documentation(d):
    reference=capability_ref(d.native);interface=next(row for row in source_callable_interfaces(d.after) if row['capability']==reference)
    return {'format':'capability_reference_interface_v1','reference':reference,'contract':d.native['contract'],
        'source_contract':{'input_schema':interface['input_schema'],'output_schema':interface['output_schema'],'effects':['read']},
        'description':'Identical public behavior and verified scope','scope':'Documentation only; no authority'}


def test_information_card_is_identical_and_only_callable_view_grants_alias(tmp_path):
    d=data(tmp_path);card=documentation(d)
    remaining=[cap for cap in d.after['capabilities'] if cap['id']!=d.native['id']]
    desc_snapshot=create_capability_snapshot('owner',[capability_ref(cap) for cap in remaining],remaining)
    hierarchical=context(d.task,d.after,[card]);original=copy.deepcopy(hierarchical)
    yes=source_primary_context(hierarchical);no=source_primary_context(context(d.task,desc_snapshot,[card]))
    assert yes['reference_interfaces']==no['reference_interfaces']
    doc=yes['reference_interfaces'][0]
    assert doc['id']=='reference_0' and doc['contract']==card['source_contract']
    target=next(row for row in source_callable_interfaces(d.after) if row['capability']==card['reference'])
    assert {'alias':target['alias'],'reference_interface':'reference_0'} in yes['source_interfaces']
    assert not any(row.get('reference_interface')=='reference_0' for row in no['source_interfaces'])
    assert 'capabilities' not in yes and 'source_callable_interfaces' not in yes
    for view in (yes,no):
        text=json.dumps(view)
        for host in ('native_input_schema_ref','input_projection','result_path',d.native['id'],capability_ref(d.native)['sha256']):
            assert host not in text
        assert all(set(row)<={'alias','input_schema','output_schema','description','reference_interface'} for row in view['source_interfaces'])
    assert hierarchical==original


def test_material_continuation_shows_purpose_and_current_alias_only(tmp_path):
    d=data(tmp_path);full=context(d.task,d.after)
    full['material_continuation']={'current_snapshot_sha256':d.after['digest'],'acquisitions':[{
        'previous_snapshot_sha256':d.before['digest'],'newly_visible':[capability_ref(d.native)],
        'previous_gap':{'reason':'missing_primitive','requirement':'A reusable relation'},
        'program_intent':{'description':'New relation','mode':'json','source_sha256':'PRIVATE_HOST_SHA'},
        'evidence':[{'path':'/private/source.json','sha256':'PRIVATE_EVIDENCE'}],
        'current_aliases':[{'capability':capability_ref(d.native),'alias':'c7'}]}]}
    view=source_primary_context(full);record=view['material_continuation']['acquisitions'][0]
    assert record['newly_visible_aliases']==['c7']
    assert record['program_intent']=={'description':'New relation','mode':'json'}
    assert record['previous_gap']['requirement']=='A reusable relation'
    assert 'PRIVATE_' not in json.dumps(view) and 'newly_visible' not in record


def test_repair_keeps_current_aliases_missing_bindings_and_original_source_history(tmp_path):
    d=data(tmp_path);full=context(d.task,d.after);current={ref['id']:name for name,ref in aliases(d.after).items()}
    assert current[d.old['id']]!='c1'
    historical={'capability_source':"def build(value):\n    old=capability.c1(value=value['value'])\n    return old\n"}
    original=put(tmp_path/'historical-answer.json',historical)
    frozen={'format':'capability_program_composition_repair_v1','current_snapshot_sha256':d.after['digest'],
        'steps':[{'id':'old','capability':capability_ref(d.old),'current_alias':current[d.old['id']],'arguments':{'$input':[]}},
            {'id':'new','capability':capability_ref(d.native),'current_alias':current[d.native['id']],'arguments':{}}],
        'output':{'$step':['new','value']}}
    full['repair']={'previous_answer':'host placeholder','previous_result':{'status':'failed','error':'binding_missing',
        'originating_answer_ref':original,'composition_repair_context_ref':{'path':'/private/intent','sha256':'HOST'},
        'diagnostics':{'kind':'compile','issues':[{'path':['steps',1,'arguments'],'actual':None}],
            'evidence':[{'path':'/private/source','sha256':'HOST'}]}},
        'feedback':{'error':'missing_input'},'frozen_composition_intent':frozen}
    result=source_primary_context(full)['repair']
    assert json.loads(result['previous_answer'])==historical
    assert 'historical' in result['history_scope'] and 'current' in result['history_scope']
    calls=result['frozen_current_calls']['calls']
    assert calls[0]['alias']==current[d.old['id']] and calls[0]['arguments']=={'$input':[]}
    assert calls[1]['arguments']=={}  # Never invent the missing input.
    assert result['frozen_current_calls']['output']=={'$step':['new']}
    assert result['previous_result']['diagnostics']['issues'][0]['actual'] is None
    text=json.dumps(result)
    assert capability_ref(d.old)['sha256'] not in text and '/private/' not in text and 'HOST' not in text
    assert json.loads(Path(original['path']).read_text())==historical


def test_semantic_file_hash_fields_and_null_feedback_are_not_host_metadata(tmp_path):
    d=data(tmp_path);full=context(d.task,d.after)
    expected={'path':'refs.bib','sha256':'semantic_file_version'}
    full['repair']={'previous_answer':'{}','previous_result':{'status':'failed'},
        'feedback':{'checks':[{'expected':expected,'actual':None}]}}
    view=source_primary_context(full)
    assert view['repair']['feedback']['checks']==[{'expected':expected,'actual':None}]


@pytest.mark.parametrize('host_path', ['/private/source', r'C:\private\source',
    'C:/private/source', r'\\server\share\source', r'\private\source', 'C:cache/source'])
def test_host_evidence_paths_are_filtered_independently_of_current_os(tmp_path, host_path):
    d=data(tmp_path);full=context(d.task,d.after)
    semantic={'path':'refs.bib','sha256':'semantic_version'}
    full['repair']={'previous_answer':'{}','previous_result':{'status':'failed'},
        'feedback':{'evidence':[{'path':host_path,'sha256':'HOST'}],'expected':semantic}}
    original=copy.deepcopy(full)
    feedback=source_primary_context(full)['repair']['feedback']
    assert feedback['evidence']==[] and feedback['expected']==semantic
    assert full==original  # Filtering the model view preserves the host audit.


def test_profile_selects_new_view_without_changing_legacy_presentation():
    assert authoring_presentation(False,'legacy')=={}
    assert authoring_presentation(True,'legacy')=={'schema_only_examples':True,'hide_composition_definitions':True,'hide_redundant_JSON_file_variants':True}
    assert authoring_presentation(True,'creation_value_v1')['source_primary'] is True


def test_primary_view_allows_static_local_graph_helpers_without_awarding_certification():
    from scenarios.paper_proofreading.frontier.author import SOURCE_PRIMARY_SYSTEM
    assert 'Local graph helpers' in SOURCE_PRIMARY_SYSTEM and 'inlined' in SOURCE_PRIMARY_SYSTEM
    assert 'do not create certified capabilities' in SOURCE_PRIMARY_SYSTEM
    assert 'no recursion, loops, dynamic branches' in SOURCE_PRIMARY_SYSTEM
    assert 'one new computation helper once' in SOURCE_PRIMARY_SYSTEM
    assert 'This program may implement the entire task; no existing capability is mandatory' in SOURCE_PRIMARY_SYSTEM


def test_primary_prompt_uses_one_system_and_keeps_host_audit_and_old_decoder(tmp_path,monkeypatch):
    from scenarios.paper_proofreading.frontier import author
    d=data(tmp_path);alias=next(name for name,ref in aliases(d.after).items() if ref==capability_ref(d.old))
    # An old JSON spelling remains accepted but is no longer advertised by the
    # new model view. This test has no provider/model behavior evidence.
    response=SimpleNamespace(final_response=json.dumps({'steps':[{'id':'old','use':alias,'args':{'$input':[]}}],
        'output':{'$step':['old']}}),finish_reason='completed')
    class Harness:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def run(self,*args,**kwargs):return response
    monkeypatch.setattr(author,'create_harness',lambda **kwargs:Harness())
    gate=SimpleNamespace(register_attempt=lambda *a:None,budget=SimpleNamespace(limit='1'),cell='diagnostic',
        environment=lambda:{},costs=lambda output:{'provider_requests':0,'observed_model_usd':0})
    hashes=[]
    for number,cards in enumerate(([],[documentation(d)])):
        output=tmp_path/('primary-'+str(number))
        library={'snapshot':d.after,'source_catalog':{'reference_interfaces':cards},'presentation':{'source_primary':True}}
        result=author.propose(task=d.task,library=library,output=output,gate=gate,owner_id='diagnostic')
        assert result['status']=='compiled_candidate'
        effective=json.loads((output/'effective.json').read_text());hashes.append(effective['system_sha256'])
        assert effective['authoring_view']=='source_primary_v1'
        assert (output/'authoring-context-audit.json').exists()
        audit=json.loads((output/'authoring-context-audit.json').read_text())
        assert audit['capabilities'] and audit['source_callable_interfaces'][0]['capability']
        prompt=(output/'prompt.md').read_text();system,raw=prompt.split('FROZEN CONSTRUCTION CONTEXT:\n')
        assert system==author.SOURCE_PRIMARY_SYSTEM+'\n'
        assert '$program' not in system and 'composition_source' not in system and 'stdout' not in system
        model=json.loads(raw)
        assert 'capabilities' not in model and 'source_callable_interfaces' not in model
    assert hashes[0]==hashes[1]==author.pilot.sha(author.SOURCE_PRIMARY_SYSTEM)
    output=tmp_path/'legacy'
    author.propose(task=d.task,library={'snapshot':d.after,'source_catalog':{}},output=output,gate=gate,owner_id='diagnostic')
    assert (output/'prompt.md').read_text().startswith(author.SYSTEM+'\n')
    assert json.loads((output/'effective.json').read_text())['authoring_view']=='legacy_v1'
    assert not (output/'authoring-context-audit.json').exists()
