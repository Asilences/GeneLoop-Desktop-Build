import hashlib
import zipfile
from pathlib import Path
import pytest
from src.adapters.ppt.authoring.ppt_native_edit import apply_edits,inspect_native

def fixture(tmp_path):
    path=tmp_path/'original.pptx'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('ppt/presentation.xml','<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="r1"/><p:sldId id="257" r:id="r2"/></p:sldIdLst></p:presentation>')
        archive.writestr('ppt/_rels/presentation.xml.rels','<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>')
        for number in range(1,3):
            archive.writestr(f'ppt/slides/slide{number}.xml',f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/></p:nvSpPr><p:txBody><a:p><a:r><a:rPr b="1"/><a:t>Old </a:t></a:r><a:r><a:rPr i="1"/><a:t>title {number}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
        archive.writestr('ppt/notesSlides/notesSlide1.xml','Existing notes bytes are preserved exactly')
        archive.writestr('ppt/media/image1.png',b'unchanged-media-fixture')
    return path,hashlib.sha256(path.read_bytes()).hexdigest(),inspect_native(path)

@pytest.mark.parametrize('action,extra',[('replace_text',{'text':'New title 1'}),('set_alignment',{'alignment':'center'}),('set_font_size',{'font_size_pt':26})])
def test_native_local_edits_preserve_every_unselected_part_and_original_bytes(tmp_path,action,extra):
    source,version,pages=fixture(tmp_path);target=tmp_path/'edited.pptx';shape=pages[0]['shapes'][0]
    result=apply_edits(source,target,version,[{'page':1,'shape_id':shape['shape_id'],'expected_text':shape['text'],'action':action,**extra}])
    assert result['changed_parts']==['ppt/slides/slide1.xml']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==version
    with zipfile.ZipFile(source) as old,zipfile.ZipFile(target) as new:
        for name in old.namelist():
            if name!='ppt/slides/slide1.xml':assert old.read(name)==new.read(name),name
    assert len(inspect_native(target))==2
    assert inspect_native(target)[0]['shapes'][0]['text']==(extra.get('text') or shape['text'])

def test_native_version_or_shape_mismatch_never_creates_an_output(tmp_path):
    source,version,pages=fixture(tmp_path);target=tmp_path/'edited.pptx'
    edit={'page':1,'shape_id':99999,'expected_text':'old','action':'replace_text','text':'new'}
    for expected,pattern in [('0'*64,'source_version_changed'),(version,'shape_not_found')]:
        with pytest.raises(ValueError,match=pattern):apply_edits(source,target,expected,[edit])
        assert not target.exists()
    edit['shape_id']=pages[0]['shapes'][0]['shape_id']
    with pytest.raises(ValueError,match='shape_text_changed'):apply_edits(source,target,version,[edit])
    assert not target.exists()

def test_native_noop_or_paragraph_restructure_is_explicit_not_fake_success(tmp_path):
    source,version,pages=fixture(tmp_path);shape=pages[0]['shapes'][0];target=tmp_path/'edited.pptx'
    edit={'page':1,'shape_id':shape['shape_id'],'expected_text':shape['text'],'action':'replace_text','text':shape['text']}
    with pytest.raises(ValueError,match='native_no_change'):apply_edits(source,target,version,[edit])
    edit['text']='Two\nParagraphs'
    with pytest.raises(ValueError,match='paragraph_count'):apply_edits(source,target,version,[edit])
    assert not target.exists()


def test_attachment_literal_edit_reads_target_shapes_without_rendering(tmp_path):
    from src.adapters.web.attachments.harless_attachment_text import extract_attachment
    original,version,pages=fixture(tmp_path)
    result=extract_attachment(original,ppt_text_edit_page=2)
    assert result['sha256']==version
    assert result['coverage']=='pptx_literal_edit_ooxml'
    assert result['native_edit_targets']==pages[1]
    assert result['page_count']==2 and not result['visual_content_reviewed']


def test_grouped_literal_replacement_verifies_powerpoint_bullets_in_pdf_text():
    from src.adapters.ppt.authoring.ppt_native_edit import rendered_replacement_present
    observed='Revised operating figures\n• 39 min\n• 95%\n• 60 completed visits\n03 / 04\n'
    assert rendered_replacement_present(observed,'39 min\n95%\n60 completed visits')
    assert not rendered_replacement_present(observed,'39 min\n92%\n60 completed visits')
