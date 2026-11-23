"""Narrow OOXML edits: preserve every unselected part, render the resulting PPTX."""
from pathlib import Path
import base64
import hashlib
import json
import posixpath
import re
import subprocess
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
for prefix,uri in [('p',P),('a',A),('r',R)]:ET.register_namespace(prefix,uri)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def xml(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('native_xml_entity_rejected')
    return ET.fromstring(raw)
def ordered_slides(archive):
    relations=xml(archive.read('ppt/_rels/presentation.xml.rels'))
    targets={r.get('Id'):posixpath.normpath(r.get('Target','').lstrip('/') if r.get('Target','').startswith('/') else 'ppt/'+r.get('Target',''))
             for r in relations if r.get('TargetMode')!='External'}
    tree=xml(archive.read('ppt/presentation.xml'))
    parts=[targets.get(node.get('{'+R+'}id')) for node in tree.findall('./{'+P+'}sldIdLst/{'+P+'}sldId')]
    if not 1<=len(parts)<=200 or len(set(parts))!=len(parts) or any(not part or not part.startswith('ppt/slides/') or '..' in part.split('/') for part in parts):
        raise ValueError('native_slide_order_invalid')
    return parts
def shape_text(shape):
    return '\n'.join(''.join(n.text or '' for n in p.iter('{'+A+'}t')) for p in shape.findall('./{'+P+'}txBody/{'+A+'}p'))
def inspect_native(path):
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist())!=len(set(archive.namelist())) or sum(i.file_size for i in archive.infolist())>300_000_000:
            raise ValueError('native_archive_limits')
        result=[]
        for page,part in enumerate(ordered_slides(archive),1):
            tree=xml(archive.read(part));shapes=[]
            for shape in tree.findall('.//{'+P+'}sp'):
                props=shape.find('./{'+P+'}nvSpPr/{'+P+'}cNvPr')
                if props is not None and shape.find('./{'+P+'}txBody') is not None:
                    shapes.append({'shape_id':int(props.get('id')),'name':props.get('name'),'text':shape_text(shape)})
            result.append({'page':page,'part':part,'shapes':shapes})
        return result
def apply_edits(source,destination,expected,edits,*,literal_targets=()):
    if sha(source)!=expected:raise ValueError('native_source_version_changed')
    if not isinstance(edits,list) or not 1<=len(edits)<=500:raise ValueError('native_edits_required')
    changed={};seen=set()
    with zipfile.ZipFile(source) as archive:
        before=inspect_native(source);parts=ordered_slides(archive)
        trees={};original_trees={}
        for edit in edits:
            page,identity=edit.get('page'),edit.get('shape_id')
            if type(page) is not int or not 1<=page<=len(parts) or type(identity) is not int:raise ValueError('native_target_invalid')
            key=(page,identity)
            if key in seen:raise ValueError('native_duplicate_target_combine_edits')
            seen.add(key);part=parts[page-1]
            tree=trees.setdefault(part,xml(archive.read(part)))
            original_trees.setdefault(part,ET.tostring(tree))
            shapes=[s for s in tree.findall('.//{'+P+'}sp') if (s.find('./{'+P+'}nvSpPr/{'+P+'}cNvPr') is not None and
                s.find('./{'+P+'}nvSpPr/{'+P+'}cNvPr').get('id')==str(identity))]
            if len(shapes)!=1:raise ValueError('native_shape_not_found_use_inspect')
            shape=shapes[0];text=shape_text(shape)
            if not isinstance(edit.get('expected_text'),str) or edit['expected_text']!=text:raise ValueError('native_shape_text_changed_use_inspect')
            action=edit.get('action');body=shape.find('./{'+P+'}txBody')
            if body is None:raise ValueError('native_shape_has_no_text')
            if action=='replace_text':
                replacement=edit.get('text')
                paragraphs=body.findall('./{'+A+'}p')
                lines=replacement.split('\n') if isinstance(replacement,str) else []
                if len(lines)!=len(paragraphs):raise ValueError('native_preserve_paragraph_count')
                for paragraph,line in zip(paragraphs,lines):
                    nodes=list(paragraph.iter('{'+A+'}t'))
                    if not nodes:raise ValueError('native_empty_paragraph_requires_advanced_edit')
                    offset=0
                    for i,node in enumerate(nodes):
                        count=len(node.text or '')
                        node.text=line[offset:offset+count] if i<len(nodes)-1 else line[offset:]
                        offset+=count
            elif action=='set_alignment':
                alignment=edit.get('alignment')
                if alignment not in ('left','center','right'):raise ValueError('native_alignment_invalid')
                for paragraph in body.findall('./{'+A+'}p'):
                    props=paragraph.find('./{'+A+'}pPr')
                    if props is None:props=ET.Element('{'+A+'}pPr');paragraph.insert(0,props)
                    props.set('algn',{'left':'l','center':'ctr','right':'r'}[alignment])
            elif action=='set_font_size':
                size=edit.get('font_size_pt')
                if type(size) not in (int,float) or not 6<=size<=144:raise ValueError('native_font_size_invalid')
                for paragraph in body.findall('./{'+A+'}p'):
                    for run in paragraph.findall('./{'+A+'}r'):
                        props=run.find('./{'+A+'}rPr')
                        if props is None:props=ET.Element('{'+A+'}rPr');run.insert(0,props)
                        props.set('sz',str(round(size*100)))
            else:raise ValueError('native_action_unsupported')
        for part,tree in trees.items():
            if ET.tostring(tree)==original_trees[part]:continue
            raw=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            if raw!=archive.read(part):changed[part]=raw
        if not changed:raise ValueError('native_no_change')
        if sha(source)!=expected:raise ValueError('native_source_version_changed')
        with zipfile.ZipFile(destination,'x') as target:
            for info in archive.infolist():target.writestr(info,changed.get(info.filename,archive.read(info.filename)))
    with zipfile.ZipFile(source) as original,zipfile.ZipFile(destination) as edited:
        if original.namelist()!=edited.namelist() or any(original.read(n)!=edited.read(n) for n in original.namelist() if n not in changed):
            raise ValueError('native_unselected_parts_changed')
    unique=all(sum(shape['text']==edit['expected_text'] for shape in before[edit['page']-1]['shapes'])==1 for edit in edits)
    unique=unique and all(sum(shape['text'].count(target['text']) for shape in before[target['page']-1]['shapes'])==1
                          for target in literal_targets)
    return {'changed_parts':sorted(changed),'slide_count':len(parts),'unselected_parts_preserved':True,
            'unambiguous_text_targets':unique,'source_sha256':expected,'pptx_sha256':sha(destination)}

def run_native(request,workspace=Path('/work')):
    def local(logical):
        if not isinstance(logical,str) or not logical.startswith(('/work/inputs/','/work/outputs/','/work/projects/')) or '\\' in logical or '..' in logical.split('/'):
            raise ValueError('native_path_invalid')
        path=workspace/logical[len('/work/'):]
        if path.resolve()!=path.absolute() or path.is_symlink():raise ValueError('native_path_changed')
        return path
    source=local(request['source'])
    if not source.is_file() or source.stat().st_nlink!=1 or source.stat().st_size>30_000_000 or source.suffix.lower()!='.pptx':raise ValueError('native_source_invalid')
    if sha(source)!=request['source_sha256']:raise ValueError('native_source_version_changed')
    if request.get('operation')=='native_inspect':
        return {'source':request['source'],'source_sha256':sha(source),'pages':inspect_native(source),'model_requests_inside':0}
    output=local(request['output'])
    if output.parent!=workspace/'outputs':raise ValueError('native_output_invalid')
    output.mkdir(mode=0o700);pptx=output/'presentation.pptx'
    if request.get('operation')=='native_render':
        count=len(inspect_native(source))
        if request.get('slide_count')!=count:raise ValueError('native_render_expected_page_count_changed')
        shutil.copyfile(source,pptx)
        result={'slide_count':count,'source_sha256':sha(source),'pptx_sha256':sha(pptx),'changed_parts':[]}
    else:
        result=apply_edits(source,pptx,request['source_sha256'],request['edits'],literal_targets=request.get('literal_targets', ()))
    command=['/opt/geneloop/libreoffice/program/soffice','-env:UserInstallation='+(output/'office-profile').as_uri(),
       '--headless','--convert-to','pdf:impress_pdf_Export','--outdir',str(output),str(pptx)]
    done=subprocess.run(command,capture_output=True,text=True,timeout=240)
    (output/'office-render.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
    if done.returncode or not (output/'presentation.pdf').is_file():raise ValueError('native_office_render_failed')
    import fitz
    artifacts=[pptx,output/'presentation.pdf']
    with fitz.open(output/'presentation.pdf') as pdf:
        if len(pdf)!=result['slide_count']:raise ValueError('native_render_page_count_changed')
        if request.get('operation')=='native_edit':
            result['rendered_replacements_verified']=all(edit.get('action')=='replace_text' and
                rendered_replacement_present(pdf[edit['page']-1].get_text(),edit['text']) for edit in request['edits'])
        for page_no,page in enumerate(pdf,1):
            image=output/f'page-{page_no:03d}.png';page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(image);artifacts.append(image)
    if sha(source)!=request['source_sha256']:raise ValueError('native_source_version_changed')
    return {**result,'mechanical_status':'passed','review_status':'pending','findings':[],'model_requests_inside':0,
      'page_receipts':[{'page':n} for n in range(1,result['slide_count']+1)],
      'artifacts':[{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in artifacts]}

def rendered_replacement_present(page_text,replacement):
    # PowerPoint stores bullets in paragraph properties. Office inserts their
    # glyphs into PDF text, between lines of the edited OOXML shape.
    without_bullets=re.sub(r'(?m)^[ \t]*[•◦▪‣][ \t]*','',page_text)
    expected=' '.join(replacement.split())
    return bool(expected) and any(expected in ' '.join(text.split()) for text in (page_text,without_bullets))


if __name__=='__main__':
    try:result=run_native(json.loads(base64.b64decode(sys.argv[1])))
    except Exception as error:result={'mechanical_status':'failed','error':{'code':str(error)[:160],'kind':type(error).__name__},'model_requests_inside':0}
    print(json.dumps(result,ensure_ascii=False))
