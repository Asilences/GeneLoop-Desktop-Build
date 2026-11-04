"""Run the approved Generate export and inspect actual Office artifacts."""
from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

if __package__:
    from .ppt_design_preflight import inspect_svg, font_independent_signature, apply_font_rule
    from .ppt_annotation_repair import repair_module_annotations


def fixed_file(path, root):
    path, root = Path(path), Path(root)
    if not path.is_relative_to(root) or path.resolve() != path.absolute():
        raise ValueError('delivery_path_outside_workspace')
    stat = path.lstat()
    if not path.is_file() or path.is_symlink() or stat.st_nlink != 1 or stat.st_size > 30_000_000:
        raise ValueError('delivery_fixed_file_required')
    return path


def run_delivery(request):
    import fitz
    project = Path(request['project'])
    manifest = json.loads(fixed_file(request['manifest'], project).read_text())
    pages = manifest.get('pages')
    if not isinstance(pages, list) or not pages or len(pages) > 200:
        raise ValueError('delivery_page_manifest_required')
    expected = sorted((project / 'svg_output').glob('*.svg'))
    declared = [fixed_file(project / row['source'], project / 'svg_output') for row in pages]
    if len(set(declared)) != len(declared) or expected != declared:
        raise ValueError('delivery_page_roster_or_order_changed')
    fixed_file(project / 'spec_lock.md', project)
    output = Path(request['output'])
    if output.parent != Path('/work/outputs'):
        raise ValueError('delivery_output_outside_workspace')
    output.mkdir(mode=0o700)
    findings, page_receipts, applied_rules, annotation_repairs = [], [], [], []
    request['_page_receipts'] = page_receipts
    request['_applied_font_rules'] = applied_rules
    request['_annotation_repairs'] = annotation_repairs
    for index, source in enumerate(declared, 1):
        raw = source.read_bytes()
        initial_sha = hashlib.sha256(raw).hexdigest()
        repaired, changes = repair_module_annotations(raw)
        if repaired is not None:
            source.write_bytes(repaired)
            annotation_repairs.append({'source': str(source), 'before_sha256': initial_sha,
                                       'after_sha256': hashlib.sha256(repaired).hexdigest(), 'changes': changes,
                                       'operation': 'module_annotations_only_v1'})
            raw = repaired
        report = inspect_svg(raw)
        if manifest.get('allow_font_fallback') is True and any(item['rule'] == 'missing_glyphs' for item in report['findings']):
            for rule in request.get('font_rules', []):
                repaired = apply_font_rule(raw, rule)
                if repaired is None:
                    continue
                next_report = inspect_svg(repaired)
                if next_report['findings']:
                    continue
                before_sha = hashlib.sha256(raw).hexdigest()
                source.write_bytes(repaired)
                applied_rules.append({'rule_id': rule['id'], 'source': str(source), 'before_sha256': before_sha,
                                      'after_sha256': hashlib.sha256(repaired).hexdigest()})
                raw, report = repaired, next_report
                break
        page_receipts.append({'page': index, 'source': str(source),
                              'source_initial_sha256': initial_sha,
                              'source_sha256': hashlib.sha256(raw).hexdigest(), 'font_independent_signature': font_independent_signature(raw),
                              'text_sha256': hashlib.sha256(json.dumps([''.join(node.itertext()) for node in ET.fromstring(raw).iter()
                                                                      if node.tag.rsplit('}', 1)[-1] == 'text'], ensure_ascii=False).encode()).hexdigest(),
                              'preflight': report})
        findings.extend({**item, 'page': index} for item in report['findings'])
    if findings:
        return {'mechanical_status': 'failed', 'review_status': 'pending', 'findings': findings,
                'artifacts': [], 'page_receipts': page_receipts, 'applied_font_rules': applied_rules, 'applied_annotation_repairs': annotation_repairs}
    commands = []
    request['_commands'] = commands

    def execute(argv, label):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=240, env={**os.environ, 'SAL_DISABLE_OPENCL': '1'})
        log = output / (label + '.log')
        log.write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
        commands.append({'stage': label, 'exit_code': result.returncode, 'log': str(log)})
        if result.returncode:
            report = project / 'validation/svg_quality_report.json'
            if label == 'official-quality' and report.is_file():
                checked = json.loads(fixed_file(report, project).read_text())
                request['_stage_findings'] = [
                    {'rule': 'official_svg_check', 'severity': 'error', 'page': index,
                     'file': row.get('file', row.get('path')), 'detail': error}
                    for index, row in enumerate(checked.get('files', []), 1) for error in row.get('errors', [])]
            raise ValueError('delivery_stage_failed_' + label)

    skill = Path('/opt/geneloop/ppt-master/scripts')
    execute([sys.executable, str(skill / 'svg_quality_checker.py'), str(project), '--stage', 'final',
             '--canonical-authoring', '--json'], 'official-quality')
    if manifest.get('notes_source') == 'total':
        fixed_file(project / 'notes/total.md', project)
        execute([sys.executable, str(skill / 'total_md_split.py'), str(project)], 'notes-split')
    pptx = output / 'presentation.pptx'
    execute([sys.executable, str(skill / 'svg_to_pptx.py'), str(project), '-o', str(pptx),
             '--with-notes', '--no-animations'], 'pptx-export')
    profile = output / 'office-profile'
    execute(['/opt/geneloop/libreoffice/program/soffice', '-env:UserInstallation=' + profile.as_uri(),
             '--headless', '--convert-to', 'pdf:impress_pdf_Export', '--outdir', str(output), str(pptx)], 'office-render')
    pdf_path = fixed_file(output / 'presentation.pdf', output)
    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
          'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
    with zipfile.ZipFile(fixed_file(pptx, output)) as archive:
        for index in range(1, len(pages) + 1):
            slide = ET.fromstring(archive.read('ppt/slides/slide' + str(index) + '.xml'))
            if not slide.findall('.//a:t', ns):
                findings.append({'rule': 'editable_text_missing', 'page': index, 'severity': 'error'})
            notes_path = 'ppt/notesSlides/notesSlide' + str(index) + '.xml'
            notes_text = ''
            if notes_path in archive.namelist():
                notes = ET.fromstring(archive.read(notes_path))
                for shape in notes.findall('.//p:sp', ns):
                    placeholder = shape.find('.//p:ph', ns)
                    if placeholder is not None and placeholder.get('type') == 'body':
                        notes_text += ''.join(node.text or '' for node in shape.findall('.//a:t', ns))
            if not notes_text.strip():
                findings.append({'rule': 'speaker_notes_missing', 'page': index, 'severity': 'error'})
    artifacts = [pptx, pdf_path]
    with fitz.open(pdf_path) as document:
        if document.page_count != len(pages):
            findings.append({'rule': 'rendered_page_count', 'severity': 'error'})
        for index, page in enumerate(document, 1):
            path = output / ('page-' + str(index).zfill(3) + '.png')
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(path)
            artifacts.append(path)
            # Comparison uses visible content, without interpreting line-box overlaps.
            source_root = ET.fromstring(declared[index - 1].read_bytes()) if index <= len(declared) else None
            expected_text = [''.join(node.itertext()).strip() for node in source_root.iter()
                             if node.tag.rsplit('}', 1)[-1] == 'text'] if source_root is not None else []
            rendered_text = ''.join(page.get_text().split())
            for text in expected_text:
                normalized = ''.join(text.split())
                if normalized and normalized not in rendered_text:
                    findings.append({'rule': 'rendered_text_requires_review', 'page': index, 'severity': 'review',
                                     'text': text})
    return {'mechanical_status': 'failed' if any(f['severity'] == 'error' for f in findings) else 'passed',
            'review_status': 'pending', 'findings': findings, 'page_receipts': page_receipts, 'commands': commands,
            'applied_font_rules': applied_rules,
            'applied_annotation_repairs': annotation_repairs,
            'artifacts': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                          for p in artifacts]}


def main():
    request = json.loads(base64.b64decode(sys.argv[1]))
    try:
        result = run_delivery(request)
    except Exception as error:
        result = {'mechanical_status': 'failed', 'review_status': 'pending', 'artifacts': [],
                  'retryable': isinstance(error, subprocess.TimeoutExpired), 'output_directory': request.get('output'),
                  'page_receipts': request.get('_page_receipts', []), 'applied_font_rules': request.get('_applied_font_rules', []),
                  'applied_annotation_repairs': request.get('_annotation_repairs', []), 'commands': request.get('_commands', []),
                  'findings': request.get('_stage_findings') or [{'rule': 'delivery_execution_failed', 'severity': 'error', 'detail': str(error)}]}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
