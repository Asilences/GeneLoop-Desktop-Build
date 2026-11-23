"""Trusted complete-delivery checks are part of normal task acceptance, no API."""
import json,sys
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from management_tools import ManagementScene
from management_reading import coverage


def make(tmp_path,contract,objective='整理副本并核对完整交付'):
    work=tmp_path/'work';work.mkdir();(work/'a.txt').write_text('current unique evidence')
    home=ROOT/'.local/file-delivery-tests'/uuid4().hex
    spec=prepare(home/'task',work,task_id=uuid4().hex,objective=objective,owner='tests',workspace_id='tests',delivery_contract=contract)
    scene=ManagementScene(spec,home/'delivery');scene.read_task();return scene


def test_extra_copy_is_rejected_inside_submit_report_not_only_after_sdk(tmp_path):
    s=make(tmp_path,{'format':'sss-file-delivery-v1','copies':{'out/a.txt':'a.txt'},'exact_tree':True})
    plan=s.preview_actions([{'op':'copy','source':'a.txt','destination':'out/a.txt'}]);s.execute_plan(plan['plan_id'])
    extra=s.preview_actions([{'op':'copy','source':'a.txt','destination':'extra.txt'}]);s.execute_plan(extra['plan_id'])
    with pytest.raises(Exception,match='complete delivered file set'):s.submit_report('done',list(s.files()),[])
    s.restore_plan(extra['plan_id'])
    assert s.submit_report('actually complete',list(s.files()),[])['semantic_quality_verified']


def test_multiple_plan_restore_then_new_work_has_a_chronological_proof(tmp_path):
    s=make(tmp_path,{'format':'sss-file-delivery-v1','copies':{'out/a.txt':'a.txt'},'exact_tree':True})
    first=s.preview_actions([{'op':'copy','source':'a.txt','destination':'out/a.txt'}]);s.execute_plan(first['plan_id'])
    extra=s.preview_actions([{'op':'copy','source':'a.txt','destination':'extra.txt'}]);s.execute_plan(extra['plan_id'])
    s.restore_plan(extra['plan_id']);s.restore_plan(first['plan_id'])
    final=s.preview_actions([{'op':'copy','source':'a.txt','destination':'out/a.txt'}]);s.execute_plan(final['plan_id'])
    assert len(s.operation_history)==5
    assert s.submit_report('已恢复试错并完成正确交付',list(s.files()),[])['semantic_quality_verified']


def test_report_can_bind_current_ids_on_host_but_explicit_wrong_ids_still_fail(tmp_path):
    s=make(tmp_path,{'format':'sss-file-delivery-v1','copies':{'out/a.txt':'a.txt'},'exact_tree':True})
    with pytest.raises(Exception,match='required copy missing'):s.submit_report(summary='not finished',gaps=[])
    p=s.preview_actions([{'op':'copy','source':'a.txt','destination':'out/a.txt'}]);s.execute_plan(p['plan_id'])
    with pytest.raises(Exception,match='omit file_ids'):s.submit_report(summary='bad id',file_ids=['typo'],gaps=[])
    value=s.submit_report(summary='已完成且原件保留',gaps=[])
    report=json.loads((s.output/'report.json').read_text())
    assert set(report['file_ids'])==set(s.files()) and value['file_count']==2


def test_move_contract_rejects_leftover_source_and_wrong_destination(tmp_path):
    s=make(tmp_path,{'format':'sss-file-delivery-v1','preserve_originals':False,'moves':{'quarantine/a.txt':'a.txt'},'exact_tree':True})
    p=s.preview_actions([{'op':'copy','source':'a.txt','destination':'quarantine/a.txt'}]);s.execute_plan(p['plan_id'])
    with pytest.raises(Exception,match='move missing, duplicated'):s.submit_report('isolated',list(s.files()),[])
    s.restore_plan(p['plan_id'])
    p=s.preview_actions([{'op':'move','source':'a.txt','destination':'quarantine/a.txt'}]);s.execute_plan(p['plan_id'])
    assert s.submit_report('已隔离明确临时文件',list(s.files()),[])['semantic_quality_verified']


def test_first_write_process_fault_resumes_the_same_flight_once(tmp_path):
    work=tmp_path/'work';work.mkdir();(work/'a.txt').write_text('current original')
    home=ROOT/'.local/file-delivery-tests'/uuid4().hex
    spec=prepare(home/'task',work,task_id=uuid4().hex,objective='复制资料到out，保留原件',owner='tests',workspace_id='tests',
        delivery_contract={'format':'sss-file-delivery-v1','copies':{'out/a.txt':'a.txt'},'exact_tree':True})
    spec['experiment_interrupt_after_first_write']=True
    s=ManagementScene(spec,home/'delivery');s.read_task()
    plan=s.preview_actions([{'op':'copy','source':'a.txt','destination':'out/a.txt'}])
    with pytest.raises(SystemExit,match='first-write'):s.execute_plan(plan['plan_id'])
    stamp=(work/'out/a.txt').stat().st_mtime_ns
    s=ManagementScene(spec,home/'delivery');s.read_task();s.execute_plan(plan['plan_id'])
    assert (work/'out/a.txt').stat().st_mtime_ns==stamp
    assert s.submit_report('已恢复且没有重复复制',list(s.files()),[])['semantic_quality_verified']


def test_two_topic_copies_are_allowed_under_original_fm02_scope(tmp_path):
    s=make(tmp_path,{'format':'sss-file-delivery-v1','categories':{'sources':['a.txt'],'prefixes':['topic/one','topic/two','topic/three'],'min_copies':1,'max_copies':2},'exact_tree':True})
    for target in ['topic/one/a.txt','topic/two/a.txt']:
        p=s.preview_actions([{'op':'copy','source':'a.txt','destination':target}]);s.execute_plan(p['plan_id'])
    assert s.submit_report('cross-topic evidence',list(s.files()),[])['semantic_quality_verified']


def test_full_text_stream_and_late_index_positions(tmp_path):
    s=make(tmp_path,{'format':'sss-file-delivery-v1','exact_tree':True,'require_reads':[{'path':'a.txt','mode':'text'}]},'全文读取，保持原件不变')
    # Prepare a fresh task, so the larger source is not an unrecorded mutation.
    work=tmp_path/'long';work.mkdir();(work/'long.txt').write_text('prefix '*1600+'late_unique_target\n')
    home=ROOT/'.local/file-delivery-tests'/uuid4().hex
    spec=prepare(home/'task',work,task_id=uuid4().hex,objective='全文读取并检索',owner='tests',workspace_id='tests')
    s=ManagementScene(spec,home/'delivery');s.read_task();f=s.list_files()['files'][0];h=s.pin_file(f['file_id'])
    preview=s.read_file(h['source_id']);assert preview['truncated']
    with pytest.raises(Exception,match='complete source text'):s.build_index([h['source_id']])
    d=s.open_document(h['source_id']);qid=d['request_id']
    while qid:qid=s.read_document_chunk(qid)['next_request_id']
    assert s.document_coverage(d['document_id'])['complete']
    s.build_index([h['source_id']]);result=s.search_index('late_unique_target')
    hit=result['matches'][0]['positions'][0];assert hit['offset']>6000 and hit['page']==1


def test_host_predicate_binding_cannot_change_after_task_creation(tmp_path):
    s=make(tmp_path,{'format':'sss-file-delivery-v1','exact_tree':True})
    spec=json.loads((s.output.parent/'task/input.json').read_text());spec['quality']['delivery_contract']['exact_tree']=False
    other=ManagementScene(spec,s.output.parent/'new-delivery');other.read_task()
    with pytest.raises(Exception,match='original goal binding'):other.submit_report('done',list(other.files()),[])
