"""Explicit-intent encoding diagnostics, never model/quality evidence."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from src.adapters.capability_authoring import aliases
from src.adapters.capability_contract import capability_ref,create_capability,create_capability_snapshot
from src.adapters.capability_program_encoding import freeze_program_composition,encode_program_composition
from tests.test_capability_builder import setup as builder_setup,RECORD
from tests.test_capability_improvement import put


def data(tmp_path):
    original,_=builder_setup()
    old={**original['capabilities'][-1],'certification':'certified','lifecycle':'active'}
    before=create_capability_snapshot('owner',[capability_ref(old)],[old])
    task={'id':'diagnostic','instruction':'Transform the current value','contract':{
        'input_schema':RECORD,'output_schema':RECORD,'effects':['read']},
        'program_interface':{'modes':['json','paths']}}
    program={'source':"def run(value):\n    return {'value':value['value']+1}\n",'mode':'json',
        'interface':'function_v1','description':'Diagnostic pure transform'}
    program_ref=put(tmp_path/'program.json',program)
    library=put(tmp_path/'native-library.json',{'programs':[{'id':'new-transform','inputs':[{}],
        'certification':{'passed':True}}]})
    observations=put(tmp_path/'observations.json',[{'candidates':[{'id':'new-transform',
        'witness':{'model_source_sha256':hashlib.sha256(program['source'].encode()).hexdigest()}}]}])
    native=create_capability({'owner':'owner','contract':{
        'input_schema':{'type':'object','properties':{'value':RECORD},'required':['value'],'additionalProperties':False},
        'output_schema':{'type':'object','properties':{'stdout':{'type':'string'},'value':RECORD},
            'required':['stdout','value'],'additionalProperties':False},'effects':['read']},
        'implementation':{'kind':'legacy','legacy_ref':{'backend':'script_motif','library_sha256':library['sha256'],
            'library_digest':'a'*64,'object_id':'new-transform','object_sha256':'b'*64,'certificate_sha256':'c'*64}},
        'dependencies':[]},{'lifecycle':'active','certification':'certified','migration':'legacy'})
    # Introduce an unrelated newly visible root before the old alias. The
    # intended old call must retain its identity through this actual reordering.
    for i in range(1000):
        definition={k:copy.deepcopy(old[k]) for k in ('owner','contract','implementation','dependencies')}
        definition['implementation']['legacy_ref']['object_id']='unrelated-'+str(i)
        extra=create_capability(definition,{'lifecycle':'active','certification':'certified','migration':'legacy'})
        if extra['id']<old['id']:break
    else:raise AssertionError('failed to create alias drift diagnostic')
    after=create_capability_snapshot('owner',[capability_ref(c) for c in (old,native,extra)],[old,native,extra])
    composition={'steps':[{'id':'old','use':'c1','args':{'$input':[]}},
        {'id':'new','use':'$program','args':{'value':{'$step':['old']}}}],
        'output':{'$step':['new','value']}}
    intent=freeze_program_composition(task,before,program,composition)
    intent_ref=put(tmp_path/'intent.json',intent)
    return SimpleNamespace(**locals())


def encode(d,**changes):
    values={name:getattr(d,name) for name in ('task','after','program_ref','intent_ref','library','observations')}
    values.update(changes)
    return encode_program_composition(values['task'],values['after'],values['program_ref'],
        values['intent_ref'],values['library'],values['observations'])


def test_model_choices_survive_alias_reordering_without_implicit_calls(tmp_path):
    d=data(tmp_path);original=copy.deepcopy(d.composition)
    assert next(name for name,ref in aliases(d.after).items() if ref==capability_ref(d.old))!='c1'
    encoded=encode(d);steps=encoded['proposal']['steps']
    assert [step['capability'] for step in steps]==[capability_ref(d.old),capability_ref(d.native)]
    assert steps[0]['arguments']=={'kind':'input','path':[]}
    assert steps[1]['arguments']=={'kind':'object','fields':{'value':{'kind':'step','step_id':'old','path':[]}}}
    assert encoded['proposal']['output']=={'kind':'step','step_id':'new','path':['value']}
    assert encoded['candidate']['capability']['certification']=='candidate'
    assert d.composition==original and len(steps)==2


def test_unbound_program_input_is_rejected_instead_of_filled_by_host(tmp_path):
    d=data(tmp_path);composition=copy.deepcopy(d.composition);composition['steps'][1]['args']={}
    ref=put(tmp_path/'missing-binding.json',freeze_program_composition(d.task,d.before,d.program,composition))
    with pytest.raises(ValueError,match='required_input_missing'):encode(d,intent_ref=ref)


@pytest.mark.parametrize('change',['failed-native','wrong-source','candidate-capability','hidden-new'])
def test_failed_unrelated_or_unavailable_material_cannot_resolve_program_slot(tmp_path,change):
    d=data(tmp_path);changes={}
    if change=='failed-native':
        value=json.loads((tmp_path/'native-library.json').read_text());value['programs'][0]['certification']['passed']=False
        changes['library']=put(tmp_path/'failed-library.json',value)
    elif change=='wrong-source':
        value=json.loads((tmp_path/'observations.json').read_text());value[0]['candidates'][0]['witness']['model_source_sha256']='0'*64
        changes['observations']=put(tmp_path/'wrong-source.json',value)
    elif change=='candidate-capability':
        changed=[{**c,'certification':'candidate'} if c['id']==d.native['id'] else c for c in d.after['capabilities']]
        changes['after']=create_capability_snapshot('owner',d.after['roots'],changed)
    else:
        changes['after']=create_capability_snapshot('owner',[capability_ref(d.old)],[d.old])
    with pytest.raises(ValueError,match='certified_material_missing'):encode(d,**changes)


def test_previous_capability_must_still_be_visible_with_exact_revision(tmp_path):
    d=data(tmp_path)
    only_new=create_capability_snapshot('owner',[capability_ref(d.native)],[d.native])
    with pytest.raises(ValueError,match='existing_reference_not_visible'):encode(d,after=only_new)


@pytest.mark.parametrize('target',['intent','program','observations','native-library'])
def test_changed_evidence_bytes_are_rejected_before_encoding(tmp_path,target):
    d=data(tmp_path);path=tmp_path/(target+'.json');path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError,match='evidence_changed'):encode(d)


def test_changed_task_and_program_identity_do_not_reuse_old_intent(tmp_path):
    d=data(tmp_path)
    with pytest.raises(ValueError,match='context_changed'):encode(d,task={**d.task,'instruction':'Different decision'})
    ref=put(tmp_path/'different-program.json',{**d.program,'source':d.program['source']+'# changed\n'})
    with pytest.raises(ValueError,match='context_changed'):encode(d,program_ref=ref)


def test_intent_requires_visible_alias_and_explicit_program_call(tmp_path):
    d=data(tmp_path);composition=copy.deepcopy(d.composition)
    composition['steps'][0]['use']='c999'
    with pytest.raises(ValueError,match='reference_not_visible'):
        freeze_program_composition(d.task,d.before,d.program,composition)
    composition=copy.deepcopy(d.composition);composition['steps'][1]['use']='c1'
    with pytest.raises(ValueError,match='program_slot_missing'):
        freeze_program_composition(d.task,d.before,d.program,composition)
    composition=copy.deepcopy(d.composition);composition['steps'][1]['args']={'$unknown':[]}
    with pytest.raises(ValueError,match='draft_binding'):
        freeze_program_composition(d.task,d.before,d.program,composition)


def test_frontier_consumes_explicit_intent_without_another_model_call(tmp_path,monkeypatch):
    from scenarios.paper_proofreading.frontier import adapter
    d=data(tmp_path);instance=adapter.FrontierAdapter.__new__(adapter.FrontierAdapter)
    instance.plan={'id':'diagnostic','output':str(tmp_path/'run')}
    instance.templates={'diagnostic':{'auto_wrap_complete_program':False}}
    instance.gate=SimpleNamespace(register_attempt=lambda *a:None)
    instance.pending_complete={'library':d.library,'observations':d.observations,'program':d.program,
        'program_ref':d.program_ref,'composition_intent_ref':d.intent_ref,
        'answer_ref':put(tmp_path/'original-answer.json',{'program':d.program,'composition':d.composition})}
    monkeypatch.setattr(adapter,'propose',lambda **kwargs:pytest.fail('must not call the model to reconnect explicit intent'))
    output=tmp_path/'run/attempt-1'
    result=instance.construct(d.task,{'snapshot':d.after,'source_catalog':{}},output,None,None)
    assert result['status']=='compiled_candidate' and result['model_called'] is False
    assert result['originating_composition_intent_ref']==d.intent_ref
    assert instance.pending_complete is None
    assert json.loads((output/'proposal.json').read_text())['steps'][0]['capability']==capability_ref(d.old)


def test_frontier_intent_error_records_failure_without_falling_back_to_complete_solver(tmp_path,monkeypatch):
    from scenarios.paper_proofreading.frontier import adapter
    d=data(tmp_path);instance=adapter.FrontierAdapter.__new__(adapter.FrontierAdapter)
    instance.plan={'id':'diagnostic','output':str(tmp_path/'run')}
    instance.templates={'diagnostic':{'auto_wrap_complete_program':True}}
    instance.gate=SimpleNamespace(register_attempt=lambda *a:None)
    instance.pending_complete={'library':d.library,'observations':d.observations,'program':d.program,
        'program_ref':d.program_ref,'composition_intent_ref':d.intent_ref,
        'answer_ref':put(tmp_path/'original-answer.json',{'program':d.program,'composition':d.composition})}
    (tmp_path/'intent.json').write_text('{}')
    monkeypatch.setattr(adapter,'propose',lambda **kwargs:pytest.fail('failed intent must not silently become a model request'))
    output=tmp_path/'run/attempt-1'
    result=instance.construct(d.task,{'snapshot':d.after,'source_catalog':{}},output,None,None)
    assert result['status']=='failed' and result['error']=='improvement_evidence_changed'
    assert result['model_called'] is False and not (output/'candidate.json').exists()


@pytest.mark.parametrize('source_syntax',[False,True])
def test_author_records_combined_intent_and_applies_existing_construction_selection(tmp_path,monkeypatch,source_syntax):
    from scenarios.paper_proofreading.frontier import author
    d=data(tmp_path);composition=copy.deepcopy(d.composition)
    old_alias=next(name for name,ref in aliases(d.after).items() if ref==capability_ref(d.old))
    composition['steps'][0]['use']=old_alias
    draft={'program':d.program,'composition':composition}
    if source_syntax:
        draft={'program':d.program,'composition_source':"def build(value):\n    old=capability."+old_alias+"(value=value['value'])\n    new=program(value=old)\n    return new['value']\n"}
    response=SimpleNamespace(final_response=json.dumps(draft),finish_reason='completed')
    class Harness:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def run(self,*args,**kwargs):return response
    monkeypatch.setattr(author,'create_harness',lambda **kwargs:Harness())
    gate=SimpleNamespace(register_attempt=lambda *a:None,budget=SimpleNamespace(limit='1'),cell='diagnostic',
        environment=lambda:{},costs=lambda output:{'provider_requests':0,'observed_model_usd':0})
    library={'snapshot':d.after,'source_catalog':{},'selection':{'construction':[capability_ref(d.old)]}}
    output=tmp_path/'author'
    result=author.propose(task=d.task,library=library,output=output,gate=gate,owner_id='diagnostic')
    assert result['status']=='deferred' and result['model_requested_program'] is True
    intent=json.loads((output/'composition-intent.json').read_text())
    assert intent['steps'][0]['capability']==capability_ref(d.old)
    assert result['composition_intent_ref']['sha256']==hashlib.sha256((output/'composition-intent.json').read_bytes()).hexdigest()
    context=json.loads((output/'prompt.md').read_text().split('FROZEN CONSTRUCTION CONTEXT:\n')[1])
    assert context['capabilities'][0]['alias']==old_alias
    assert (output/'composition-source.py').exists()==source_syntax
    if source_syntax:
        encoded=encode_program_composition(d.task,d.after,put(tmp_path/'requested-program.json',d.program),
            result['composition_intent_ref'],d.library,d.observations)
        assert len(encoded['proposal']['steps'])==2


def test_source_spelling_of_existing_composition_keeps_explicit_bindings():
    from scenarios.paper_proofreading.frontier.author import expand_source_request
    source="def build(value):\n    result=capability.c7(paths=[value['file']])\n    return result['value']\n"
    assert expand_source_request({'composition_source':source})=={'steps':[
        {'id':'result','use':'c7','args':{'paths':[{'$input':['file']}]}}],
        'output':{'$step':['result','value']}}
    with pytest.raises(ValueError,match='shape_invalid'):
        expand_source_request({'composition_source':source,'composition':{}})


def test_native_certification_failure_never_creates_pending_intent_or_candidate(tmp_path,monkeypatch):
    from scenarios.paper_proofreading.frontier import adapter
    d=data(tmp_path);instance=adapter.FrontierAdapter.__new__(adapter.FrontierAdapter)
    instance.plan={'id':'diagnostic','output':str(tmp_path/'run')}
    instance.templates={'diagnostic':{'native_cases':{'json':[]},'auto_wrap_complete_program':True}}
    instance.gate=None
    output=tmp_path/'run/attempt-0';output.mkdir(parents=True)
    put(output/'program.json',d.program);(output/'answer.txt').write_text('diagnostic answer')
    monkeypatch.setattr(adapter,'propose',lambda **kwargs:{'status':'deferred','program_request':str(output/'program.json'),
        'composition_intent_ref':d.intent_ref})
    def reject(*args,**kwargs):raise ValueError('diagnostic_native_certification_failure')
    monkeypatch.setattr(adapter,'learn',reject)
    result=instance.construct(d.task,{'snapshot':d.after,'source_catalog':{}},output,None,None)
    assert result['status']=='failed' and result['error']=='frontier_native_material_rejected'
    assert instance.pending_complete is None and 'native_library' not in result
    assert instance.acquire({},result,output)=={'status':'deferred','reason':'frontier_no_certified_material'}
