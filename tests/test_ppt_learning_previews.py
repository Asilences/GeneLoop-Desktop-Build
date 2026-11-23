"""PDF-derived learning evidence does not alter user downloads or imply quality."""
import json
import fitz
import pytest
from src.adapters.ppt.delivery.ppt_delivery_quality import delivery_preview_files


@pytest.fixture
def delivery(tmp_path):
    identity='a'*32
    (tmp_path/'tasks'/identity).mkdir(parents=True)
    pdf=tmp_path/'delivered.pdf'
    with fitz.open() as doc:
        doc.new_page(width=640,height=360).insert_text((20,30),'Frozen delivery')
        doc.save(pdf)
    return tmp_path,identity,{'.pptx':[tmp_path/'delivered.pptx'],'.pdf':[pdf]}


def test_preview_uses_frozen_pdf_and_reuses_version_bound_evidence(delivery):
    out,identity,files=delivery;raw=files['.pdf'][0].read_bytes();locks={}
    result=delivery_preview_files(out,identity,files,locks)
    assert '.png' not in files and files['.pdf'][0].read_bytes()==raw
    assert len(result['.png'])==1 and len(locks)==3
    assert delivery_preview_files(out,identity,files,{})==result
    result['.png'][0].write_bytes(b'tampered')
    with pytest.raises(ValueError,match='bytes changed'):
        delivery_preview_files(out,identity,files,{})


def test_preview_manifest_source_cannot_be_rebound(delivery):
    out,identity,files=delivery
    result=delivery_preview_files(out,identity,files,{})
    manifest=result['.png'][0].parent/'manifest.json'
    value=json.loads(manifest.read_text());value['pdf_sha256']='b'*64;manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='binding changed'):
        delivery_preview_files(out,identity,files,{})


def test_preview_requires_main_pair_and_preserves_published_pngs(delivery):
    out,identity,files=delivery
    for item in ({'.pdf':files['.pdf']},{**files,'.png':[out/'published.png']}):
        assert delivery_preview_files(out,identity,item,{}) is item


def test_preview_refuses_redirect_before_creating_children(delivery):
    out,identity,files=delivery;elsewhere=out/'elsewhere';elsewhere.mkdir()
    try:(out/'tasks'/identity/'learning-previews').symlink_to(elsewhere,target_is_directory=True)
    except OSError:pytest.skip('symlink requires local OS permission')
    with pytest.raises(ValueError,match='redirected'):
        delivery_preview_files(out,identity,files,{})
    assert not list(elsewhere.iterdir())
