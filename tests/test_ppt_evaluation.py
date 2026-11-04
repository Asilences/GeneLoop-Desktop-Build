"""Offline evaluation boundaries; no model calls or service mutation."""
import pytest
from src.adapters.ppt_evaluation import bind_evidence_ids,category_costs,select_pptx,validate_failed_delivery_review

def row(name,version,verified=True):return {'name':name,'sha256':version*64,'host_verified':verified}

def test_same_bytes_renamed_final_alias_is_not_ambiguous():
    result=select_pptx([row('outputs/older.pptx','a'),row('outputs/final.pptx','b'),row('outputs/final_editable.pptx','b')],'`final_editable.pptx`')
    assert result['sha256']=='b'*64 and len(result['same_version_aliases'])==2

def test_unique_actual_pptx_does_not_require_generator_png_registration():
    assert select_pptx([row('outputs/final.pptx','a')],'已完成')['sha256']=='a'*64

def test_answer_reference_cannot_authorize_unverified_file():
    with pytest.raises(ValueError,match='no_host_verified'):select_pptx([row('outputs/final.pptx','a',False)],'final.pptx')

def test_multiple_versions_without_explicit_choice_remain_unknown():
    with pytest.raises(ValueError,match='ambiguous'):select_pptx([row('outputs/v1.pptx','a'),row('outputs/v2.pptx','b')],'已完成')

def test_revision_reuses_previous_only_if_it_is_the_actual_sole_output():
    assert select_pptx([row('outputs/final.pptx','a')],'final.pptx',previous_sha256='a'*64)['sha256']=='a'*64

def test_previous_version_excluded_when_both_old_and_new_are_delivered():
    assert select_pptx([row('outputs/old.pptx','a'),row('outputs/new.pptx','b')],'old.pptx new.pptx',previous_sha256='a'*64)['sha256']=='b'*64

CAT=[{'evidence_id':'E0001','kind':'source_page','ref':'paper#p2','sha256':'a'*64,'source_id':'paper','source_page':2},
     {'evidence_id':'E0002','kind':'slide_image','ref':'slide-1.png','sha256':'b'*64,'slide':1}]
def bind(d):return bind_evidence_ids({'dimensions':[d],'critical_unknowns':[]},CAT,expected_bindings={'task_sha256':'c'*64},artifact_id='artifact',slide_count=2)

def test_explicit_id_binds_exact_source_without_copying_hash():
    d={'id':'scientific_accuracy','score':8,'status':'passed','evidence':[{'evidence_id':'E0001','slide':1}]}
    out=bind(d);proof=out['dimensions'][0]['evidence'][0]
    assert proof['sha256']=='a'*64 and proof['ref']=='paper#p2' and out['task_sha256']=='c'*64
    assert d['evidence']==[{'evidence_id':'E0001','slide':1}]

@pytest.mark.parametrize('evidence',[{'evidence_id':'E9999','slide':1},{'evidence_id':'E0002','slide':2},
 {'evidence_id':'E0001','slide':1,'sha256':'f'*64},{'evidence_id':'E0001','slide':0}])
def test_bad_ids_wrong_slide_and_contradictions_remain_unknown(evidence):
    out=bind({'id':'scientific_accuracy','score':9,'status':'passed','evidence':[evidence]})
    assert out['dimensions'][0]['score'] is None and out['critical_unknowns']

def test_missing_evidence_is_not_invented_and_real_unknown_is_preserved():
    out=bind({'id':'usability','score':None,'status':'unknown','reason':'non-target slide changed','evidence':[]})
    assert out['dimensions'][0]['score'] is None and out['dimensions'][0]['evidence']==[]

def test_conflicting_top_level_binding_is_rejected():
    with pytest.raises(ValueError,match='binding_conflict'):
        bind_evidence_ids({'artifact_id':'foreign','dimensions':[]},CAT,expected_bindings={},artifact_id='own',slide_count=1)

def test_review_cost_never_enters_generation_and_unknown_charge_stays_unknown():
    out=category_costs([{'task_id':'g','request_id':1,'response_status':200,'observed_peak_usd':.1},
       {'task_id':'j','request_id':1,'response_status':200,'observed_peak_usd':.2},
       {'task_id':'g','request_id':2,'response_status':502,'observed_peak_usd':None}],generation_ids=['g'],review_ids=['j'])
    assert out['generation']=={'requests':2,'known_proxy_usd':'0.1','unknown_cost_requests':1}
    assert out['review']['known_proxy_usd']=='0.2'
    with pytest.raises(ValueError,match='overlap'):category_costs([],generation_ids=['g'],review_ids=['g'])


def failed_review():
    return {'artifact_id':'missing','task_completion_score':0,'deck_quality_score':None,
      'coverage':{'images_seen':[],'text_seen':[],'unreviewed':[]},'failure_summary':'No final PPTX',
      'dimensions':[{'id':name,'score':0 if name=='task_fulfillment' else None,
        'status':'failed' if name=='task_fulfillment' else 'unknown','reason':'No final artifact'}
        for name in ('scientific_accuracy','task_fulfillment','narrative','figures_and_sources','visual_readability','usability')]}


def test_failure_audit_can_preserve_textual_limitations_without_claiming_pages():
    raw=failed_review();raw['coverage']['unreviewed']=['无最终PPTX；无逐页文本或像素证据']
    out=validate_failed_delivery_review(raw,artifact_id='missing')
    assert out['coverage']['unreviewed']==[] and out['model_original_coverage']==raw['coverage']
    assert out['unreviewed_delivery_limitations']==raw['coverage']['unreviewed']
    assert out['dimensions']==raw['dimensions'] and raw['coverage']['unreviewed']


@pytest.mark.parametrize('coverage',[{'images_seen':[1],'text_seen':[],'unreviewed':[]},
 {'images_seen':[],'text_seen':[],'unreviewed':[1]},
 {'images_seen':[],'text_seen':[],'unreviewed':['slide-1']},
 {'images_seen':[],'text_seen':[],'unreviewed':'No deck'}])
def test_failure_audit_rejects_invented_or_untyped_page_coverage(coverage):
    raw=failed_review();raw['coverage']=coverage
    with pytest.raises(ValueError):validate_failed_delivery_review(raw,artifact_id='missing')


def test_failure_audit_rejects_positive_or_wrongly_bound_quality():
    raw=failed_review();raw['deck_quality_score']=7
    with pytest.raises(ValueError):validate_failed_delivery_review(raw,artifact_id='missing')
    raw=failed_review();raw['dimensions'][0].update(score=8,status='passed')
    with pytest.raises(ValueError):validate_failed_delivery_review(raw,artifact_id='missing')
    with pytest.raises(ValueError):validate_failed_delivery_review(failed_review(),artifact_id='other')
