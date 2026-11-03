"""Offline mechanism diagnostics; synthetic evidence is not empirical RSI benefit."""
import copy
import builtins
import importlib.util
import json
from pathlib import Path
import pytest
from src.adapters.capability_feedback import CapabilityFeedback, execution_cost, file_ref
from src.adapters.capability_contract import capability_ref, create_capability_snapshot
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_authoring import authoring_context, aliases
from tests.test_capability_builder import setup
from src.adapters.file_lock import exclusive_lock


def fixture(tmp_path):
    snapshot,proposal=setup()
    caps=[{**c,'certification':'certified','lifecycle':'active'} for c in snapshot['capabilities']]
    snapshot=create_capability_snapshot('owner',snapshot['roots'],caps)
    library={'snapshot':snapshot,'catalog':[],'head':None}
    path=tmp_path/'evidence.json';path.write_text('{"diagnostic":true}', encoding='utf-8')
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


@pytest.mark.parametrize('observation', [None, {}, {'cost': 0}, {'billing_usd': 0},
    {'observed_model_usd': None}, {'observed_model_usd_decimal': None},
    {'observed_model_usd': None, 'observed_model_usd_decimal': None}])
def test_execution_observation_unknown_cost_never_defaults_to_zero(observation):
    assert execution_cost(observation) is None


@pytest.mark.parametrize('observation', [{'observed_model_usd': 0},
    {'observed_model_usd': 0.0}, {'observed_model_usd_decimal': '0.000'},
    {'observed_model_usd': 0, 'observed_model_usd_decimal': '0'}])
def test_execution_observation_explicit_zero_is_a_known_cost(observation):
    assert execution_cost(observation) == 0


@pytest.mark.parametrize('observation', [{'observed_model_usd': True},
    {'observed_model_usd': -1}, {'observed_model_usd': float('nan')},
    {'observed_model_usd': float('inf')}, {'observed_model_usd': '0.1'},
    {'observed_model_usd_decimal': '-0.01'}, {'observed_model_usd_decimal': 'NaN'},
    {'observed_model_usd_decimal': 'Infinity'}, {'observed_model_usd_decimal': 0.1},
    {'observed_model_usd_decimal': ''}])
def test_execution_observation_invalid_cost_is_rejected(observation):
    with pytest.raises(ValueError, match='execution_cost_invalid'):
        execution_cost(observation)


@pytest.mark.parametrize('observation', [{'observed_model_usd': 0.1, 'observed_model_usd_decimal': '0.2'},
    {'observed_model_usd': 0.1, 'observed_model_usd_decimal': '0.1000000000000000001'},
    {'observed_model_usd': None, 'observed_model_usd_decimal': '0'},
    {'observed_model_usd': 0, 'observed_model_usd_decimal': None}])
def test_execution_observation_conflicting_precision_or_unknown_fields_are_rejected(observation):
    with pytest.raises(ValueError, match='execution_cost_inconsistent'):
        execution_cost(observation)


@pytest.mark.parametrize('amount', ['1e10000', '1e-10000'])
def test_execution_sorting_format_cannot_turn_positive_cost_into_zero_or_infinity(amount):
    with pytest.raises(ValueError, match='execution_cost_not_representable'):
        execution_cost({'observed_model_usd_decimal': amount})


def test_host_execution_observation_cost_changes_scoped_choice_and_keeps_evidence(tmp_path):
    manager, library, _, _ = fixture(tmp_path); a, b = library['snapshot']['roots']
    def record(name, payload):
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps(payload), encoding='utf-8')
        source = file_ref(path)
        fact(manager, {'a': a, 'b': b}[name], source, cost=execution_cost(payload))
        return source
    first = record('a', {'observed_model_usd': 0.12, 'observed_model_usd_decimal': '0.120'})
    second = record('b', {'observed_model_usd_decimal': '0.03'})
    assert manager.select_execution(library, [a, b], 'same-task-rubric')[0] == b
    assert manager.select_execution(library, [a, b], 'another-scope')[0] == sorted([a, b], key=lambda r: r['id'])[0]
    facts = list(manager.read()['facts'].values())
    assert {row['cost'] for row in facts} == {0.12, 0.03}
    assert {ref['sha256'] for row in facts for ref in row['evidence']} == {first['sha256'], second['sha256']}
    assert all(row['benefit'] is None for row in facts)
    fact(manager, b, second, cost=execution_cost({'observed_model_usd': None}))
    assert manager.select_execution(library, [a, b], 'same-task-rubric')[0] == a
    Path(second['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence_changed'):
        manager.select_execution(library, [a, b], 'same-task-rubric')


def test_creation_value_changes_actual_builder_context_without_changing_aliases(tmp_path):
    manager,library,evidence,proposal=fixture(tmp_path);a,b=library['snapshot']['roots']
    manager.observe(stage='construction',subject=b,beneficiary=a,scope='construction',status='passed',evidence=[evidence])
    projected=manager.project(library)
    context=authoring_context({'id':'t','instruction':'diagnostic','contract':proposal['contract']},
        library['snapshot'],{'preferred_roots':projected['selection']['construction']})
    assert context['capabilities'][0]['alias']==next(k for k,v in aliases(library['snapshot']).items() if v==b)
    assert projected['snapshot']==library['snapshot']


def test_withdrawn_exact_successor_changes_builder_ranking_without_erasing_history(tmp_path):
    manager,library,evidence,proposal=fixture(tmp_path);a,b=library['snapshot']['roots']
    c=compile_proposal(proposal,library['snapshot'],'owner')['capability']
    c={**c,'lifecycle':'active','certification':'certified'};cref=capability_ref(c)
    library['snapshot']=create_capability_snapshot('owner', [a,b,cref], [*library['snapshot']['capabilities'],c])
    manager.observe(stage='construction',subject=b,beneficiary=cref,scope='construction',
                    status='passed',evidence=[evidence])
    def first_builder_root():
        projected=manager.project(library)
        context=authoring_context({'id':'t','instruction':'diagnostic','contract':proposal['contract']},
            projected['snapshot'],{'preferred_roots':projected['selection']['construction']})
        return aliases(projected['snapshot'])[context['capabilities'][0]['alias']]
    assert first_builder_root()==b
    manager.withdraw({**cref,'sha256':'0'*64},'different_revision',evidence)
    assert first_builder_root()==b
    fact(manager,cref,evidence);fact(manager,a,evidence)
    manager.archive(cref,a,library)
    assert first_builder_root()==b
    assert cref not in manager.project(library)['selection']['execution']
    facts=copy.deepcopy(manager.read()['facts'])
    manager.withdraw(cref,'independent_counterexample',evidence)
    assert first_builder_root()==a
    assert manager.read()['facts']==facts
    assert any(row['beneficiary']==cref and row['stage']=='construction' for row in facts.values())


def test_failed_attempt_cost_changes_next_opportunity_order_and_facts_deduplicate(tmp_path):
    manager,_,evidence,_=fixture(tmp_path)
    args=dict(stage='attempt',subject=None,scope='a',status='failed',cost=2,evidence=[evidence])
    manager.observe(**args);manager.observe(**args)
    assert len(manager.read()['facts'])==1
    assert [j['id'] for j in manager.prioritize([{'id':'a'},{'id':'b'}])]==['b','a']
    assert CapabilityFeedback(tmp_path/'feedback','other').read()['facts']=={}
    Path(evidence['path']).write_text('{}', encoding='utf-8')
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
    assert len(json.loads((manager.directory/'recovery-queue.json').read_text(encoding='utf-8')))==4


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


def test_feedback_import_does_not_require_posix_fcntl(monkeypatch):
    original=builtins.__import__
    def portable_import(name,*args,**kwargs):
        if name=='fcntl':raise ModuleNotFoundError("No module named 'fcntl'")
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',portable_import)
    spec=importlib.util.spec_from_file_location('src.adapters.feedback_portability_diagnostic',
        Path(__file__).resolve().parents[1]/'src/adapters/capability_feedback.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.CapabilityFeedback


def test_busy_feedback_lock_refuses_write_and_unicode_facts_roundtrip(tmp_path):
    manager,library,evidence,_=fixture(tmp_path);ref=library['snapshot']['roots'][0]
    with exclusive_lock(manager.directory/'writer.lock'):
        with pytest.raises(BlockingIOError):fact(manager,ref,evidence)
    assert manager.read()['facts']=={}
    manager.observe(stage='execution',subject=ref,scope='中文场景与重复键检查',status='passed',evidence=[evidence])
    assert next(iter(manager.read()['facts'].values()))['scope']=='中文场景与重复键检查'
