"""Bind PPT learning quality to the shared RSI protocol and immutable deliveries.

This adapter buys no model review and never converts an absent review into a pass.
The owning worker validates account/turn ownership and file bytes before calling.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import re
import zipfile

import fitz
from PIL import Image

from .rsi_protocol import envelope, write_record
from .rsi_quality import quality_status, verify_quality_files

ROOT = Path(__file__).resolve().parents[2]
RUBRIC = ROOT / 'scenarios/ppt_master/quality-rubric.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_delivery(files):
    """Retain the existing editability/notes/render gate; decode actual PNG bytes."""
    if not all(files.get(ext) for ext in ('.pptx', '.pdf', '.png')):
        raise ValueError('PPTX/PDF/PNG delivery missing')
    with zipfile.ZipFile(files['.pptx'][-1]) as archive:
        slides = [n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml', n)]
        notes = [n for n in archive.namelist() if re.fullmatch(r'ppt/notesSlides/notesSlide[0-9]+\.xml', n)]
        if not slides or len(notes) < len(slides):
            raise ValueError('slides or speaker notes missing')
        if not any(ET.fromstring(archive.read(n)).find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t') is not None for n in slides):
            raise ValueError('editable text missing')
        with fitz.open(stream=files['.pdf'][-1].read_bytes(), filetype='pdf') as pdf:
            if pdf.page_count != len(slides):
                raise ValueError('rendered page count differs')
    for path in files['.png']:
        with Image.open(path) as image:
            if image.format != 'PNG':
                raise ValueError('invalid PNG preview')
            image.verify()
    return {'slide_count': len(slides), 'registered_png_count': len(files['.png'])}


def record_quality(output, store, turn, lane, info, files, details, review, locks):
    """Export, re-read and verify the same evidence interpreted by TS at admission."""
    output, store = Path(output), Path(store)
    rubric = json.loads(RUBRIC.read_text(encoding='utf-8'))
    row = turn['lanes'][lane]
    refs = {ext: [{'ref': p.relative_to(output).as_posix(), 'sha256': sha(p)} for p in paths]
            for ext, paths in files.items()}
    checks = [
        {'id': 'editable_text', 'status': 'passed', 'observation': 'Delivered PPTX contains native editable text; this does not establish editability of every object.', 'evidence': refs['.pptx']},
        {'id': 'speaker_notes', 'status': 'passed', 'observation': f"Delivered PPTX contains notes parts for {details['slide_count']} slides; note content was not semantically reviewed.", 'evidence': refs['.pptx']},
        {'id': 'rendered_pages', 'status': 'passed', 'observation': f"Delivered PDF and PPTX both contain {details['slide_count']} pages; no visual-quality inference.", 'evidence': refs['.pptx'] + refs['.pdf']},
        {'id': 'registered_pngs', 'status': 'passed', 'observation': f"{details['registered_png_count']} registered PNG files decode correctly; exhaustive slide coverage is not inferred.", 'evidence': refs['.png']},
    ]
    review_refs = []
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
        checks.append({'id': name, 'status': 'passed' if value is True else 'failed' if value is False else 'unknown',
                       'observation': 'Explicit user assessment; not an independent expert review.' if value is not None else 'No explicit user assessment is available.',
                       'evidence': review_refs if value is not None else []})
    task_sha = sha(Path(info['task_dir']) / 'task.json')
    binding = {'task_sha256': task_sha, 'artifact_sha256': row['output_sha256'], 'rubric_sha256': sha(RUBRIC)}
    payload = {**binding, 'task_id': info['task_id'], 'evaluator': 'geneloop-ppt-delivery-v1',
               'scope': 'mechanical delivery plus separately labelled optional explicit user assessment',
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
            'status': quality_status(record, **binding, required_checks=required),
            'mechanical_status': quality_status(record, **binding, required_checks=rubric['mechanical_checks'])}
