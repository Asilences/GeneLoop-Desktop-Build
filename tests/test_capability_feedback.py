"""Offline mechanism diagnostics; synthetic evidence is not empirical RSI benefit."""
import copy
import json
from pathlib import Path
import pytest
from src.adapters.capability_feedback import CapabilityFeedback, file_ref
from src.adapters.capability_contract import capability_ref, create_capability_snapshot
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_authoring import authoring_context, aliases
from tests.test_capability_builder import setup


def fixture(tmp_path):
    snapshot,proposal=setup()
    caps=[{**c,'certification':'certified','lifecycle':'active'} for c in snapshot['capabilities']]
    snapshot=create_capability_snapshot('owner',snapshot['roots'],caps)
    library={'snapshot':snapshot,'catalog':[],'head':None}
    path=tmp_path/'evidence.json';path.write_text('{"diagnostic":true}')
    return CapabilityFeedback(tmp_path/'feedback','owner'),library,file_ref(path),proposal


def fact(manager,ref,evidence,**kwargs):
    return manager.observe(stage='execution',subject=ref,scope='same-task-rubric',status='passed',evidence=[evidence],**kwargs)


def test_execution_cost_changes_choice_only_with_common_scope(tmp_path):
    manager,library,evidence,_=fixture(tmp_path);a,b=library['snapshot']['roots']
    fact(manager,a,evidence,cost=5);fact(manager,b,evidence,cost=1)
    assert manager.select_execution(library,[a,b],'same-task-rubric')[0]==b
    # Cost from another task family is not used as a universal score.
    assert manager.select_execution(library,[a,b],'unseen-task')[0]==sorted([a,b],key=lambda r:r['id'])[0]
    fact(manager,b,evidence,cost=None)
    assert manager.select_execution(library,[a,b],'same-task-rubric')[0]==a
    assert all(f['benefit'] is None for f in manager.read()['facts'].values())


def test_creation_value_changes_actual_builder_context_without_changing_aliases(tmp_path):
    manager,library,evidence,proposal=fixture(tmp_path);a,b=library['snapshot']['roots']
    manager.observe(stage='construction',subject=b,beneficiary=a,scope='construction',status='passed',evidence=[evidence])
    projected=manager.project(library)
    context=authoring_context({'id':'t','instruction':'diagnostic','contract':proposal['contract']},
        library['snapshot'],{'preferred_roots':projected['selection']['construction']})
    assert context['capabilities'][0]['alias']==next(k for k,v in aliases(library['snapshot']).items() if v==b)
    assert projected['snapshot']==library['snapshot']


def test_failed_attempt_cost_changes_next_opportunity_order_and_facts_deduplicate(tmp_path):
    manager,_,evidence,_=fixture(tmp_path)
    args=dict(stage='attempt',subject=None,scope='a',status='failed',cost=2,evidence=[evidence])
    manager.observe(**args);manager.observe(**args)
    assert len(manager.read()['facts'])==1
    assert [j['id'] for j in manager.prioritize([{'id':'a'},{'id':'b'}])]==['b','a']
    assert CapabilityFeedback(tmp_path/'feedback','other').read()['facts']=={}
    Path(evidence['path']).write_text('{}')
    with pytest.raises(ValueError,match='evidence_changed'):manager.prioritize([{'id':'a'}])


def test_withdraw_transitive_closure_preserves_unrelated_root_and_old_bytes(tmp_path):
    manager,library,evidence,proposal=fixture(tmp_path);snapshot=library['snapshot'];a,b=snapshot['roots']
    c=compile_proposal(proposal,snapshot,'owner')['capability'];c={**c,'certification':'certified','lifecycle':'active'}
    with_c=create_capability_snapshot('owner',[*snapshot['roots'],capability_ref(c)],[*snapshot['capabilities'],c])
    proposal['steps']=[{'id':'c','capability':capability_ref(c),'arguments':{'kind':'input','path':[]}}]
    proposal['output']={'kind':'step','step_id':'c','path':[]}
    d=compile_proposal(proposal,with_c,'owner')['capability'];d={**d,'certification':'certified','lifecycle':'active'}
    library['snapshot']=create_capability_snapshot('owner',[*with_c['roots'],capability_ref(d)],[*with_c['capabilities'],d])
    original=copy.deepcopy(library)
    manager.withdraw(a,'version_changed',evidence)
    result=manager.project(library)
    assert result['snapshot']['roots']==[b]
    assert {r['capability']['id'] for r in result['recovery_queue']}=={a['id'],c['id'],d['id']}
    assert library==original
    manager.withdraw(b,'version_changed',evidence)
    assert manager.project(library)['snapshot'] is None
    assert len(json.loads((manager.directory/'recovery-queue.json').read_text()))==4


def test_recovery_requires_checked_new_publication_and_archive_retains_material(tmp_path):
    manager,library,evidence,_=fixture(tmp_path);a,b=library['snapshot']['roots']
    manager.withdraw(a,'version_changed',evidence)
    publication={'publication_sha256':'old','publication':{'root':a},'snapshot':library['snapshot']}
    with pytest.raises(ValueError,match='fresh_validation'):
        manager.recover(a,lambda task_id:publication)
    publication['publication_sha256']='new'
    manager.recover(a,lambda task_id:{**publication,'publication':{**publication['publication'],'task_id':task_id}})
    with pytest.raises(ValueError,match='replacement_evidence'):manager.archive(a,b,library)
    fact(manager,a,evidence);fact(manager,b,evidence)
    manager.archive(a,b,library)
    assert manager.select_execution(library,[a,b],'same-task-rubric')[0]==b
    assert a in manager.project(library)['selection']['construction']


@pytest.mark.parametrize('cost',[True,-1,float('nan'),float('inf')])
def test_cost_not_silently_coerced(tmp_path,cost):
    manager,library,evidence,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='cost_invalid'):fact(manager,library['snapshot']['roots'][0],evidence,cost=cost)
