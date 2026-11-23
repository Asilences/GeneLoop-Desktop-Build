from pathlib import Path
import hashlib
from uuid import uuid4
import pytest
from PIL import Image
from src.adapters.ppt.sources.ppt_preview_runner import prepare_asset

def test_local_source_crop_resize_has_provenance_and_never_touches_a_slide(tmp_path):
    work=tmp_path/'work';(work/'inputs').mkdir(parents=True);(work/'projects/deck/images').mkdir(parents=True)
    source=work/'inputs/source.png';Image.new('RGB',(100,60),'red').save(source)
    version=hashlib.sha256(source.read_bytes()).hexdigest()
    request={'source':'/work/inputs/source.png','project':'/work/projects/deck','id':str(uuid4()),
     'crop':{'left':10,'top':10,'right':90,'bottom':50},'width':160}
    result=prepare_asset(request,workspace=work)
    assert (result['width'],result['height'])==(160,80)
    assert result['source_sha256']==version and result['source_modified'] is False
    assert hashlib.sha256(source.read_bytes()).hexdigest()==version
    assert Image.open(work/result['path'][len('/work/'):]).size==(160,80)

def test_asset_rejects_traversal_and_out_of_bounds_crop(tmp_path):
    work=tmp_path/'work';(work/'inputs').mkdir(parents=True);(work/'projects/deck/images').mkdir(parents=True)
    Image.new('RGB',(20,20),'red').save(work/'inputs/source.png')
    request={'source':'/work/inputs/../../private.png','project':'/work/projects/deck','id':str(uuid4())}
    with pytest.raises(ValueError,match='source_invalid'):prepare_asset(request,workspace=work)
    request.update(source='/work/inputs/source.png',crop={'left':0,'top':0,'right':99,'bottom':20})
    with pytest.raises(ValueError,match='outside_image'):prepare_asset(request,workspace=work)


def test_large_valid_source_defaults_to_supported_width(tmp_path):
    work=tmp_path/'work';(work/'inputs').mkdir(parents=True);(work/'projects/deck/images').mkdir(parents=True)
    Image.new('RGB',(5000,100),'red').save(work/'inputs/source.png')
    result=prepare_asset({'source':'/work/inputs/source.png','project':'/work/projects/deck','id':str(uuid4())},workspace=work)
    assert (result['width'],result['height'])==(4096,82)
