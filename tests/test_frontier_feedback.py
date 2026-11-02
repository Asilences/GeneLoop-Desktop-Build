"""Final-review counterexamples reach existing root selection, without models."""
import json
import pytest
from src.adapters.capability_contract import capability_ref,create_capability_snapshot
from src.adapters.capability_feedback import CapabilityFeedback
from src.adapters.capability_scene import reference
from scenarios.paper_proofreading.frontier.feedback import record_final_feedback
from tests.test_capability_contract import leaf,compose


def review(tmp_path,quality):
    a=leaf('A');c=compose([a]);d=compose([c])
    owner=a['owner'];root=capability_ref(d)
    artifact={'cell':'D-0','construction':{'outcomes':[{'status':'published','capability':root}]},
              'final_cases':[{'quality':q} for q in quality]}
    path=tmp_path/'artifact.json';path.write_text(json.dumps(artifact),encoding='utf8')
    plan={'store':str(tmp_path/'store'),'owner':owner}
    library={'snapshot':create_capability_snapshot(owner,[capability_ref(c),root],[a,c,d]),'catalog':[]}
    return plan,reference(path),library,capability_ref(c),root


def verdict(passed):
    return {'passed':passed,'checks':[{'id':'independent_relation','status':'passed' if passed else 'failed','observation':'Manual diagnostic'}]}


def test_final_counterexample_withdraws_D_but_does_not_blame_its_C(tmp_path):
    plan,ref,library,c,d=review(tmp_path,[verdict(True),verdict(False)])
    result=record_final_feedback(plan,'D-0',ref,'frozen-scope')
    assert result['action']=='withdraw_root'
    feedback=CapabilityFeedback(tmp_path/'store/feedback',plan['owner'])
    projected=feedback.project(library)
    assert projected['snapshot']['roots']==[c]
    assert feedback.read()['blocked'][d['id']]['reason']=='independent_final_quality_failed'
    assert c['id'] not in feedback.read()['blocked']


@pytest.mark.parametrize('quality',[[{'passed':False,'execution_error':'process unavailable','checks':[]}],
                                  [{'passed':True,'checks':[]}],
                                  [verdict(True),{'passed':False,'execution_error':'timeout','checks':[]}]])
def test_unknown_quality_never_withdraws_the_root(tmp_path,quality):
    plan,ref,library,_,_=review(tmp_path,quality)
    result=record_final_feedback(plan,'D-0',ref,'frozen-scope')
    assert result['status']=='unknown' and result['action']=='record_only'
    feedback=CapabilityFeedback(tmp_path/'store/feedback',plan['owner'])
    assert feedback.read()['blocked']=={} and feedback.project(library)['snapshot']==library['snapshot']


def test_success_records_fact_without_recovering_previously_withdrawn_root(tmp_path):
    plan,ref,_,_,root=review(tmp_path,[verdict(True)])
    feedback=CapabilityFeedback(tmp_path/'store/feedback',plan['owner']);feedback.withdraw(root,'old_counterexample',ref)
    assert record_final_feedback(plan,'D-0',ref,'frozen-scope')['status']=='passed'
    assert root['id'] in feedback.read()['blocked']


def test_review_cell_and_immutable_evidence_must_match(tmp_path):
    plan,ref,_,_,_=review(tmp_path,[verdict(False)])
    with pytest.raises(ValueError,match='cell_changed'):record_final_feedback(plan,'other',ref,'scope')
    from pathlib import Path
    Path(ref['path']).write_text('{}',encoding='utf8')
    with pytest.raises(ValueError,match='evidence_changed'):record_final_feedback(plan,'D-0',ref,'scope')
