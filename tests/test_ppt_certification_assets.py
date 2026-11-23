"""Native certification freezes independent image inputs without touching originals."""
import json
import hashlib
import os
from PIL import Image
import pytest
from src.adapters.ppt.learning.ppt_workflow_certification import snapshot_native_assets


@pytest.fixture
def owned(tmp_path):
    task_id='1'*32;source=tmp_path/'tasks'/task_id;source.mkdir(parents=True)
    workspace=tmp_path/'workspace';(workspace/'code').mkdir(parents=True)
    image=workspace/'code/figure.png';Image.new('RGB',(40,20),'navy').save(image)
    (source/'task-state.json').write_text(json.dumps({'user_id':'owner','status':'completed','scene':'ppt'}))
    (source/'effective-config.json').write_text(json.dumps({'user_id':'owner','workspace':str(workspace),'ppt_execution_strategy':'ppt_master'}))
    store=tmp_path/'learning/ppt-owner';store.mkdir(parents=True)
    trace={'task_id':task_id,'records':[{'call_id':'a','name':'compose_ppt_page','arguments':{'content':{'image':'/work/figure.png'}}}]}
    return tmp_path,store,{'user':'owner'},trace,{'setup_calls':['a'],'write_calls':[]},image


def test_freezes_exact_image_bytes_and_reuses_snapshot(owned):
    out,store,request,trace,case,image=owned;original=image.read_bytes()
    assets=snapshot_native_assets(out,store,request,trace,case)
    assert len(assets)==1 and assets[0]['sha256']==hashlib.sha256(original).hexdigest()
    assert (out/assets[0]['ref']).read_bytes()==original==image.read_bytes()
    assert snapshot_native_assets(out,store,request,trace,case)==assets
    (out/assets[0]['ref']).write_bytes(b'tampered')
    with pytest.raises(ValueError,match='snapshot_changed'):snapshot_native_assets(out,store,request,trace,case)


def test_changed_current_input_creates_a_new_bound_case_not_a_false_historical_match(owned):
    out,store,request,trace,case,image=owned
    first=snapshot_native_assets(out,store,request,trace,case)
    Image.new('RGB',(40,20),'green').save(image)
    second=snapshot_native_assets(out,store,request,trace,case)
    assert first[0]['sha256']!=second[0]['sha256'] and (out/first[0]['ref']).exists()


def test_rejects_foreign_owner_and_escaping_or_linked_images(owned):
    out,store,request,trace,case,image=owned
    with pytest.raises(ValueError,match='owner_changed'):snapshot_native_assets(out,store,{'user':'foreign'},trace,case)
    trace['records'][0]['arguments']['content']['image']='/work/../figure.png'
    with pytest.raises(ValueError,match='path_invalid'):snapshot_native_assets(out,store,request,trace,case)
    trace['records'][0]['arguments']['content']['image']='/work/figure.png'
    try:os.link(image,image.with_name('hardlink.png'))
    except OSError:pytest.skip('hardlink unsupported')
    with pytest.raises(ValueError,match='path_changed'):snapshot_native_assets(out,store,request,trace,case)


def test_text_only_certification_needs_no_asset_folder(owned):
    out,store,request,trace,case,_=owned;trace['records'][0]['arguments']['content'].pop('image')
    assert snapshot_native_assets(out,store,request,trace,case)==[]
    assert not (store/'workflows').exists()
