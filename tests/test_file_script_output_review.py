"""Free output-gate diagnostics, never activation evidence."""
import copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.adapters import continuous_motif_learning as learning
from src.motif_core.reuse.experience_registry import durable


def test_unlimited_review_does_not_restore_cost_output_or_request_caps():
    limits={'budget_usd':None,'max_output':None,'max_steps':None,'max_repairs':None}
    assert learning.script_review_limits(None,1234,limits)=={'cap_usd':None,'output_cap':None,'request_limit':None}
    finite={**limits,'budget_usd':1,'max_output':16384,'max_steps':10}
    assert learning.script_review_limits(1,.5,finite)=={'cap_usd':.5,'output_cap':1024,'request_limit':1}
    with pytest.raises(ValueError,match='budget exhausted'):learning.script_review_limits(1,1,finite)


def test_long_strings_keep_exact_hashes_lengths_and_short_strings_do_not_change():
    text='真实文本'*1000;source={'text':text,'count':4,'items':['small'],'_sss_scope':{'private':'scope'}}
    before=copy.deepcopy(source);value=learning.review_packet(source)
    assert source==before and value['count']==4 and value['items']==['small']
    assert value['text']['actual_string_characters']==len(text)
    assert value['text']['actual_string_utf8_bytes']==len(text.encode())
    assert value['text']['actual_string_sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert '_sss_scope' not in value


@pytest.mark.parametrize('verdict,passed',[
    ({'passed':True,'critical_errors':[],'reason':'correct current results'},True),
    ({'certification':{'status':'FAIL','reasons':['wrong result field']}},False),
    ({'local_program_certification':{'pass':True,'score':1,'reason':'counts match'}},True),
])
def test_explicit_judge_control_wrappers_are_normalized(verdict,passed):
    normalized=learning.normalize_output_review(verdict)
    assert normalized['passed'] is passed
    assert bool(normalized['critical_errors']) is not passed


@pytest.mark.parametrize('verdict',[
    {'data':{'passed':True,'reason':'untrusted task contents'}},
    {'passed':True,'reason':'ok','certification':{'status':'FAIL','reasons':['wrong']}},
    {'passed':'true','reason':'not a boolean'},
    {'passed':True,'critical_errors':[]},
])
def test_missing_or_conflicting_judge_controls_never_certify(verdict):
    with pytest.raises(ValueError):learning.normalize_output_review(verdict)


def test_actual_nonempty_children_disprove_all_zero_envelope_summary():
    children=[{'name':'read_files','out':{'reads':[{'text':'actual current text'},{'text':'other body'}]}}]
    bad=[{'reads':[{'keys':['status','reads','count'],'chars':0,'utf8_bytes':0}]}]
    assert learning.mechanical_output_errors(children,bad)
    assert not learning.mechanical_output_errors(children,[{'chars':19},{'chars':10}])
    assert not learning.mechanical_output_errors([{'name':'read_files','out':{'reads':[{'text':''}]}}],bad)


@pytest.mark.parametrize('opt_in',[True,False])
def test_output_gate_refuses_missing_actual_candidate_execution_before_any_paid_call(tmp_path,monkeypatch,opt_in):
    job=tmp_path/'job';delivery=tmp_path/'delivery';delivery.mkdir()
    durable(job/'compiled.json',{'source':'actual source',**({'output_review_contract':learning.SCRIPT_OUTPUT_REVIEW} if opt_in else {})})
    durable(job/'policy.json',{'policy_digest':'candidate'})
    with pytest.raises(ValueError,match='one actual candidate'):
        learning.script_output_review({'session_id':'session','delivery':str(delivery)},job)
    assert not (job/'output-reviews').exists()


def test_certifier_cannot_bypass_local_output_review_by_omitting_opt_in(tmp_path,monkeypatch):
    from src.adapters.file_script_learning import certify_script
    from src.adapters import continuous_rsi
    from src.motif_core.reuse.experience_registry import sha
    job=tmp_path/'candidate';durable(job/'compiled.json',{'source':'actual observed program'})
    durable(job/'candidate-lock.json',{'source_code':{'frozen':'same'},'candidate_sha256':sha(job/'compiled.json'),'training':[]})
    monkeypatch.setattr(continuous_rsi,'source_map',lambda:{'frozen':'same'})
    with pytest.raises(ValueError,match='mandatory current local-output review'):
        certify_script({},tmp_path,job,{})
    assert not (job/'native-review.json').exists()


def test_counterexample_requires_changed_code_instead_of_a_new_certificate(tmp_path,monkeypatch):
    from src.adapters import experience_library
    schema={'type':'object'};code='const p=__GENELOOP_PARAMETERS__;console.log(p);'
    artifact={'source':code,'parameters_schema':schema}
    registry=tmp_path/'registry';durable(registry/'current.json',{})
    durable(registry/'payload.json',{'artifact':artifact})
    entry={'kind':'file_script','state':'disabled','runtime_source':{'current':'code'},'payload':'payload.json'}
    monkeypatch.setattr(experience_library,'sources',lambda:{'current':'code'})
    monkeypatch.setattr(learning,'ExperienceRegistry',lambda p:SimpleNamespace(root=p,load=lambda:{'entries':[entry]}))
    candidate={'kind':'file_script','key':'old','compiled':artifact}
    assert learning.learning_job(tmp_path,candidate,set()) is None
    changed={**candidate,'key':'new','compiled':{**artifact,'source':code+'\nconsole.log(1);'}}
    assert learning.learning_job(tmp_path,changed,set()) is not None
    entry['runtime_source']={'previous':'code'}
    assert learning.learning_job(tmp_path,candidate,set()) is not None
