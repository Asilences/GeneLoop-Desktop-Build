"""Real image transforms in a temporary directory; no cloud or model calls."""
import hashlib
from pathlib import Path
import pytest
from PIL import Image
from src.adapters.ppt.sources.ppt_preview_runner import preview_region


@pytest.fixture
def preview(tmp_path):
    (tmp_path/'outputs').mkdir()
    source=tmp_path/'outputs/page.png'
    Image.new('RGB',(100,80),'navy').save(source)
    request={'path':'/work/outputs/page.png','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'output':'/work/outputs/ppt-preview-test.png','crop':{'left':10,'top':10,'right':40,'bottom':30},'scale':3}
    return tmp_path,source,request


def test_real_crop_preserves_source_and_returns_new_png(preview):
    root,source,request=preview
    result=preview_region(request,workspace=root)
    assert (result['width'],result['height'])==(90,60)
    assert result['source_modified'] is False and result['model_requests_inside']==0
    assert hashlib.sha256(source.read_bytes()).hexdigest()==request['source_sha256']
    with Image.open(root/'outputs/ppt-preview-test.png') as image:
        assert image.format=='PNG' and image.size==(90,60)
    with pytest.raises(FileExistsError):preview_region(request,workspace=root)


@pytest.mark.parametrize('crop',[{'left':-1,'top':0,'right':10,'bottom':10},{'left':0,'top':0,'right':101,'bottom':10},
 {'left':10,'top':0,'right':10,'bottom':10},{'left':0,'top':0,'right':10.5,'bottom':10},{'left':True,'top':0,'right':10,'bottom':10},{}])
def test_invalid_crops_never_write_an_output(preview,crop):
    root,source,request=preview
    with pytest.raises(ValueError,match='crop_invalid'):preview_region({**request,'crop':crop},workspace=root)
    assert list((root/'outputs').iterdir())==[source]


@pytest.mark.parametrize('field,value',[('path','/work/inputs/private.png'),('path','/work/outputs/../page.png'),
 ('output','/work/outputs/page.png'),('output','/tmp/page.png'),('source_sha256','0'*64),('scale',5),('scale',True)])
def test_path_version_and_scale_validation_preserves_original(preview,field,value):
    root,source,request=preview
    with pytest.raises(ValueError):preview_region({**request,field:value},workspace=root)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==request['source_sha256']


def test_symlink_preview_source_is_rejected(preview):
    root,source,request=preview
    alias=root/'outputs/alias.png'
    try:alias.symlink_to(source)
    except OSError:pytest.skip('symlink creation is unavailable for this account')
    with pytest.raises(ValueError,match='path_changed'):preview_region({**request,'path':'/work/outputs/alias.png'},workspace=root)
