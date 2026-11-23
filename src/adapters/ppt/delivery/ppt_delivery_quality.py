"""Bind PPT learning quality to the shared RSI protocol and immutable deliveries.

This adapter buys no model review and never converts an absent review into a pass.
The owning worker validates account/turn ownership and file bytes before calling.
"""
from __future__ import annotations

import hashlib
import json
from src.adapters.filesystem_paths import Path
from xml.etree import ElementTree as ET
import re
import zipfile
from uuid import uuid4

import fitz
from PIL import Image

from src.rsi.protocol.rsi_protocol import envelope, write_record
from src.rsi.feedback.rsi_quality import quality_status, verify_quality_files

ROOT = Path(__file__).resolve().parents[4]
RUBRIC = ROOT / 'scenarios/ppt_master/quality-rubric.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def delivery_preview_files(output, task_id, files, locks):
    """Render only an immutable delivered PDF when PNGs were not published.

    User downloads and their original receipt stay unchanged. Generated evidence
    belongs to this task, includes its renderer version and never implies a judge pass.
    """
    if files.get('.png') or not files.get('.pptx') or not files.get('.pdf'):
        return files
    output = Path(output)
    if not re.fullmatch(r'[a-f0-9]{32}', task_id):
        raise ValueError('preview task identity invalid')
    task = output / 'tasks' / task_id
    if not task.is_dir() or task.resolve() != task.absolute():
        raise ValueError('preview task ownership path changed')
    pdf = Path(files['.pdf'][-1])
    if pdf.is_symlink() or pdf.stat().st_nlink != 1 or pdf.resolve() != pdf.absolute() or not pdf.is_relative_to(output):
        raise ValueError('preview PDF source changed')
    version = sha(pdf)
    render_version = hashlib.sha256(('PyMuPDF:' + fitz.VersionBind + ':width1280:v1').encode()).hexdigest()[:16]
    parent = task / 'learning-previews'
    if parent.is_symlink() or (parent.exists() and (not parent.is_dir() or parent.resolve() != parent.absolute())):
        raise ValueError('preview evidence path redirected')
    parent.mkdir(exist_ok=True, mode=0o700)
    folder = parent / (version + '-' + render_version)
    if folder.is_symlink():raise ValueError('preview evidence path redirected')
    folder.mkdir(exist_ok=True, mode=0o700)
    if folder.resolve() != folder.absolute():
        raise ValueError('preview evidence path redirected')
    manifest = folder / 'manifest.json'
    with fitz.open(pdf) as document:
        if not 1 <= len(document) <= 200:
            raise ValueError('derived preview supports one to 200 pages')
        if manifest.exists():
            if manifest.is_symlink() or manifest.stat().st_nlink != 1:
                raise ValueError('preview manifest changed')
            record = json.loads(manifest.read_text(encoding='utf-8'))
        else:
            images = []
            for number, page in enumerate(document, 1):
                if page.rect.width <= 0 or not 0 < page.rect.height / page.rect.width <= 4:
                    raise ValueError('derived preview page dimensions unsupported')
                scale = 1280 / page.rect.width
                raw = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes('png')
                path = folder / f'page-{number:03d}.png'
                if path.exists():
                    if path.is_symlink() or path.stat().st_nlink != 1 or path.read_bytes() != raw:
                        raise ValueError('interrupted preview bytes changed')
                else:
                    with path.open('xb') as stream:
                        stream.write(raw)
                    path.chmod(0o600)
                images.append({'name': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
            record = {'version': 1, 'kind': 'preview_from_immutable_delivered_pdf',
                      'pdf': pdf.relative_to(output).as_posix(), 'pdf_sha256': version,
                      'renderer': 'PyMuPDF:' + fitz.VersionBind, 'page_count': len(document), 'images': images}
            temp = manifest.with_name(manifest.name + '.' + uuid4().hex + '.tmp')
            temp.write_text(json.dumps(record, sort_keys=True), encoding='utf-8')
            temp.chmod(0o600)
            temp.replace(manifest)
        if (record.get('version') != 1 or record.get('kind') != 'preview_from_immutable_delivered_pdf' or
                record.get('pdf') != pdf.relative_to(output).as_posix() or record.get('pdf_sha256') != version or
                record.get('renderer') != 'PyMuPDF:' + fitz.VersionBind or record.get('page_count') != len(document) or
                len(record.get('images', [])) != len(document)):
            raise ValueError('preview source or renderer binding changed')
    pngs = []
    for number, row in enumerate(record['images'], 1):
        if row.get('name') != f'page-{number:03d}.png':
            raise ValueError('preview page identity changed')
        path = folder / row['name']
        if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('preview evidence bytes changed')
        locks[path.relative_to(output).as_posix()] = row['sha256']
        pngs.append(path)
    locks[manifest.relative_to(output).as_posix()] = sha(manifest)
    locks[pdf.relative_to(output).as_posix()] = version
    return {**files, '.png': pngs}


def inspect_delivery(files, *, include_content=False, require_notes=False):
    """Retain the existing editability/notes/render gate; decode actual PNG bytes."""
    files = {ext: [Path(path) for path in paths] for ext, paths in files.items()}
    if not all(files.get(ext) for ext in ('.pptx', '.pdf', '.png')):
        raise ValueError('PPTX/PDF/PNG delivery missing')
    with zipfile.ZipFile(files['.pptx'][-1]) as archive:
        slides = [n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml', n)]
        notes = [n for n in archive.namelist() if re.fullmatch(r'ppt/notesSlides/notesSlide[0-9]+\.xml', n)]
        if not slides or require_notes and len(notes) < len(slides):
            raise ValueError('slides or speaker notes missing')
        if not any(ET.fromstring(archive.read(n)).find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t') is not None for n in slides):
            raise ValueError('editable text missing')
        with fitz.open(stream=files['.pdf'][-1].read_bytes(), filetype='pdf') as pdf:
            if pdf.page_count != len(slides):
                raise ValueError('rendered page count differs')
        content = {}
        if include_content:
            content = {'artifact_formats': {ext: [{'sha256': sha(path), 'bytes': path.stat().st_size} for path in files[ext]]
                                            for ext in ('.pptx', '.pdf', '.png')},
                       'native_slide_content': [], 'speaker_notes': []}
            for part in sorted(slides):
                tree = ET.fromstring(archive.read(part))
                content['native_slide_content'].append({'part': part,
                    'native_text': [node.text for node in tree.iter() if node.tag == '{http://schemas.openxmlformats.org/drawingml/2006/main}t' and node.text],
                    'native_shapes': len(tree.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}sp')),
                    'pictures': len(tree.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}pic'))})
            for part in sorted(notes):
                tree = ET.fromstring(archive.read(part))
                content['speaker_notes'].append({'part': part, 'text': [node.text for node in tree.iter()
                    if node.tag == '{http://schemas.openxmlformats.org/drawingml/2006/main}t' and node.text]})
    for path in files['.png']:
        with Path(path).open('rb') as pixels, Image.open(pixels) as image:
            if image.format != 'PNG':
                raise ValueError('invalid PNG preview')
            image.verify()
    return {'slide_count': len(slides), 'registered_png_count': len(files['.png']),
            'notes_parts': len(notes), 'notes_required_on_every_slide': require_notes, **content}


def record_quality(output, store, turn, lane, info, files, details, review, locks):
    """Export, re-read and verify the same evidence interpreted by TS at admission."""
    output, store = Path(output), Path(store)
    rubric = json.loads(RUBRIC.read_text(encoding='utf-8'))
    row = turn['lanes'][lane]
    refs = {ext: [{'ref': p.relative_to(output).as_posix(), 'sha256': sha(p)} for p in paths]
            for ext, paths in files.items()}
    checks = [
        {'id': 'editable_text', 'status': 'passed', 'observation': 'Delivered PPTX contains native editable text; this does not establish editability of every object.', 'evidence': refs['.pptx']},
        {'id': 'speaker_notes', 'status': 'passed', 'observation':
         f"Delivered PPTX contains {details.get('notes_parts', details['slide_count'])} notes parts. " +
         ('Every slide requires a notes part. ' if details.get('notes_required_on_every_slide') else 'Notes are optional; no all-slide requirement was applied. ') +
         'Note content or preservation has not been semantically verified.', 'evidence': refs['.pptx']},
        {'id': 'rendered_pages', 'status': 'passed', 'observation': f"Delivered PDF and PPTX both contain {details['slide_count']} pages; no visual-quality inference.", 'evidence': refs['.pptx'] + refs['.pdf']},
        {'id': 'registered_pngs', 'status': 'passed', 'observation': f"{details['registered_png_count']} published PNGs or version-bound previews derived from the delivered PDF decode correctly; a visual-quality verdict is not inferred.", 'evidence': refs['.png']},
    ]
    review_refs = []
    automated = None
    index_path = store / 'background-review-index.json'
    if review is None and index_path.is_file():
        from src.adapters.ppt.learning.ppt_program_learning import checked
        index = json.loads(checked(output, index_path.relative_to(output)).read_text(encoding='utf-8'))
        entry = index.get(info['task_id'] + ':' + row['output_sha256'])
        if entry and entry.get('status') == 'reviewed':
            path = checked(output, entry['path'], entry['sha256'])
            candidate = json.loads(path.read_text(encoding='utf-8'))
            if (candidate.get('binding') != entry['binding'] or candidate['binding']['task_id'] != info['task_id'] or
                    candidate['binding']['artifact_sha256'] != row['output_sha256'] or
                    candidate['binding']['pptx_sha256'] != sha(files['.pptx'][-1])):
                raise ValueError('background_quality_binding_changed')
            automated = candidate
            review_refs = [{'ref': entry['path'], 'sha256': entry['sha256']}]
    directory = store / 'quality'
    directory.mkdir(exist_ok=True, mode=0o700)
    if review is not None:
        # Freeze the particular review instead of making every later journal
        # append invalidate the bytes of an otherwise unchanged earlier review.
        raw = json.dumps(review, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        path = directory / ('review-' + hashlib.sha256(raw).hexdigest() + '.json')
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('PPT quality review changed')
        if not path.exists():
            path.write_bytes(raw)
            path.chmod(0o600)
        review_refs = [{'ref': path.relative_to(output).as_posix(), 'sha256': sha(path)}]
    for name in rubric['review_checks']:
        value = review.get('quality', {}).get(name) if review is not None else None
        model_check = automated.get('dimensions', {}).get(name) if automated is not None else None
        status = 'passed' if value is True else 'failed' if value is False else model_check['status'] if model_check else 'unknown'
        observation = ('Explicit user assessment.' if value is not None else
                       'Separately metered model-assisted review. ' + model_check['reason'] if model_check else 'No quality assessment is available.')
        checks.append({'id': name, 'status': status, 'observation': observation,
                       'evidence': review_refs if value is not None or model_check is not None else []})
    task_sha = sha(Path(info['task_dir']) / 'task.json')
    binding = {'task_sha256': task_sha, 'artifact_sha256': row['output_sha256'], 'rubric_sha256': sha(RUBRIC)}
    payload = {**binding, 'task_id': info['task_id'], 'evaluator': 'geneloop-ppt-delivery-v1',
               'scope': 'mechanical delivery with separately labelled user or model-assisted assessment',
               'limitations': rubric['limitations'], 'checks': checks}
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    record = envelope('quality_evaluation', {'id': 'ppt-quality-' + identity[:24], **payload})
    path = directory / (identity + '.json')
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != record:
            raise ValueError('PPT quality record changed')
    else:
        write_record(path, record)
        path.chmod(0o600)
    # The shared validator checks evidence bytes, not just a reviewer's verdict.
    verify_quality_files(record, output)
    for check in checks:
        for ref in check['evidence']:
            locks[ref['ref']] = ref['sha256']
    locks[path.relative_to(output).as_posix()] = sha(path)
    required = rubric['mechanical_checks'] + rubric['review_checks']
    return {'record': path.relative_to(output).as_posix(), 'sha256': sha(path), 'binding': binding,
            'required_checks': required, 'mechanical_checks': rubric['mechanical_checks'],
            'model_failed_pages': sorted({page for dimension in (automated or {}).get('dimensions', {}).values()
                                          if dimension.get('status') == 'failed' for page in dimension.get('pages', [])}),
            'status': quality_status(record, **binding, required_checks=required),
            'layout_status': quality_status(record, **binding, required_checks=rubric['mechanical_checks'] + ['visual', 'usable']),
            'mechanical_status': quality_status(record, **binding, required_checks=rubric['mechanical_checks'])}
