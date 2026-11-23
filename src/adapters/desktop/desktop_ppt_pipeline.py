"""Native host seam over the locked PPT Master calibration and delivery tools."""
from pathlib import Path as NativePath
import hashlib
import json
import os
import runpy
import shutil
import sys
import tempfile
sys.dont_write_bytecode = True
sys.path.insert(0, str(NativePath(__file__).resolve().parents[3]))
from src.adapters.filesystem_paths import Path


def prepare(project, skill):
    from fontTools.ttLib import TTFont
    from matplotlib.font_manager import FontProperties, findfont
    script = skill / 'scripts/text_measure.py'
    sys.path.insert(0, str(script.parent))
    measurement = runpy.run_path(str(script))
    roles = measurement['_roles_from_spec_lock'](project / 'spec_lock.md')
    spec = '\n'.join((project / name).read_text(encoding='utf-8') for name in ('spec_lock.md', 'design_spec.md'))
    fonts, missing = {}, []
    for role, (family, size) in roles.items():
        families = [name.strip().strip('"\'') for name in family.split(',')]
        for weight in ('normal', 'bold'):
            path = Path(findfont(FontProperties(family=families, weight=weight), fallback_to_default=False)).resolve(strict=True)
            font = TTFont(path, fontNumber=0)
            try:
                chars = font.getBestCmap() or {}
                absent = sorted({ord(c) for c in spec if not c.isspace() and ord(c) not in chars})
            finally:
                font.close()
            fonts[role + ':' + weight] = {'file': str(path), 'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'family': family, 'size': size}
            if absent:
                missing.append({'role': role, 'weight': weight, 'codepoints': ['U+' + format(c, '04X') for c in absent]})
    rows = [(name, family, size) for name, (family, size) in roles.items()]
    calibrate = measurement['_calibration_payload']
    normal = calibrate(rows, project_path=project, source='spec_lock.md', include_outline=True)
    bold = calibrate(rows, project_path=project, source='spec_lock.md', include_outline=True, weights={name: 'bold' for name in roles})
    validation = project / 'validation'
    validation.mkdir(exist_ok=True)
    if validation.is_symlink():
        raise ValueError('invalid validation directory')
    for name, data in [('text_calibration.json', normal), ('host-typography.json', {'fonts': fonts, 'normal': normal, 'bold': bold, 'glyph_review': missing})]:
        path = validation / name
        if path.exists() and (path.is_symlink() or path.stat().st_nlink != 1):
            raise ValueError('invalid calibration file')
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'status': 'prepared', 'fonts': fonts, 'normal': normal, 'bold': bold, 'glyph_review': missing,
            'execution': sys.platform + '-local', 'scope': 'native font resolution and official PPT Master calibration; Office pixels require finalize_ppt'}


def native_render(project, output, renderer, request):
    from scenarios.ppt_master.windows_delivery import fixed_file, validate_windows_deck
    from scenarios.ppt_master.windows_source import read_source
    from stat import S_ISREG
    source = project / 'deck.pptx'
    info = source.lstat()
    if source.resolve(strict=True) != source or source.is_symlink() or not S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 30_000_000:
        raise ValueError('delivery_fixed_file_required')
    expected = request['source_sha256']
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('native_deck_changed_before_render')
    # Windows profile and session directories can leave Office's validation
    # paths beyond MAX_PATH. The worker has a short, private temporary root.
    staging_parent = None if sys.platform == 'win32' else output.parent
    with tempfile.TemporaryDirectory(prefix='glppt-', dir=staging_parent, ignore_cleanup_errors=True) as temp:
        stage = Path(temp)
        deck = stage / 'presentation.pptx'
        deck.write_bytes(data)
        count = read_source(deck, 1)['pages']
        if count != request['slide_count']:
            raise ValueError('native_deck_page_count_changed')
        texts = [read_source(deck, page)['text'].splitlines() for page in range(1, count + 1)]
        receipt = validate_windows_deck(stage, deck, texts, renderer, require_notes=False, max_slides=120)
        if not receipt['passed']:
            return {'mechanical_status': 'failed', 'findings': receipt['errors'], 'artifacts': []}
        if receipt['pptx_sha256'] != expected or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('native_deck_changed_during_render')
        publish = stage / 'publish'
        publish.mkdir()
        artifacts = []
        for row in receipt['artifacts']:
            artifact = fixed_file(row['path'], stage)
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('native_deck_artifact_changed')
            shutil.copyfile(artifact, publish / artifact.name)
            artifacts.append({**row, 'path': artifact.name})
        if sys.platform == 'win32':
            # The profile and the worker temp directory may be on different drives.
            shutil.copytree(publish, windows_output_path(output))
        else:
            publish.rename(output)
    return {'mechanical_status': 'passed', 'review_status': 'pending', 'artifacts': artifacts,
            'libreoffice_version': receipt['dependencies']['libreoffice_version']}


def with_preview_archive(result, output):
    from scenarios.ppt_master.windows_delivery import archive_previews
    if result['mechanical_status'] == 'passed':
        output = windows_output_path(output)
        paths = [{**row, 'path': output / row['path']} for row in result['artifacts']]
        result['artifacts'].append(archive_previews(paths, output, output / 'presentation-previews.zip'))
    return result


def windows_output_path(path):
    if sys.platform != 'win32':
        return path
    from scenarios.ppt_master.windows_delivery import windows_io_path
    return NativePath(windows_io_path(str(path)))


def run(request):
    work = Path(request['work']).resolve(strict=True)
    project = Path(request['project']).absolute()
    if not project.is_relative_to(work / 'projects') or project.resolve(strict=True) != project:
        raise ValueError('project must be inside this task projects directory')
    for path in (project, *project.parents):
        if path.is_symlink():
            raise ValueError('project path changed')
        if path == work:
            break
    output = Path(request['output']).absolute()
    if output.parent != work / 'outputs' or output.exists():
        raise ValueError('delivery must be a new directory inside task outputs')
    if request['operation'] == 'native_render':
        return with_preview_archive(native_render(project, output, Path(request['soffice']), request), output)
    skill = Path(request['skill']).resolve(strict=True)
    profiles = json.loads((Path(__file__).resolve().parents[3] / 'scenarios/ppt_master/design-profiles.json').read_text(encoding='utf-8'))
    profile = request.get('profile') or 'academic-readable-v1'
    if profile not in profiles['profiles']:
        raise ValueError('delivery_profile_unknown')
    if request.get('manifest'):
        manifest_path = Path(request['manifest']).absolute()
        if not manifest_path.is_relative_to(project) or manifest_path.resolve(strict=True) != manifest_path or manifest_path.is_symlink() or manifest_path.stat().st_nlink != 1:
            raise ValueError('delivery manifest must be a fixed file inside project')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        expected = sorted(path.relative_to(project).as_posix() for path in (project / 'svg_output').glob('*.svg'))
        if [row['source'] for row in manifest['pages']] != expected:
            raise ValueError('delivery_page_roster_or_order_changed')
    if request['operation'] == 'prepare':
        return prepare(project, skill)
    from scenarios.ppt_master.windows_delivery import export_project
    total = project / 'notes/total.md'
    pages = sorted((project / 'svg_output').glob('*.svg'))
    if total.exists() and (any(not (project / 'notes' / (page.stem + '.md')).is_file() for page in pages) or request.get('manifest') and manifest.get('notes_source') == 'total'):
        if total.is_symlink() or total.stat().st_nlink != 1:
            raise ValueError('speaker notes source changed')
        # Official title matching and splitting, not a second notes parser.
        sys.path.insert(0, str(skill / 'scripts'))
        splitter = runpy.run_path(str(skill / 'scripts/total_md_split.py'))
        notes = splitter['parse_total_md'](total, svg_stems=[page.stem for page in pages], verbose=False)
        matched, errors = splitter['check_svg_note_mapping'](pages, notes)
        if not matched:
            raise ValueError('speaker note mapping failed: ' + '; '.join(errors))
        if not splitter['split_notes'](notes, project / 'notes', verbose=False):
            raise ValueError('speaker note split failed')
    # The exporter validates and snapshots every source/notes file, then runs
    # official checks and actual LibreOffice PPTX/PDF/PNG delivery.
    result = export_project(project, output, skill, Path(request['soffice']))
    return {**with_preview_archive(result, output), 'profile': profile}


if __name__ == '__main__':
    from scenarios.ppt_master.windows_delivery import attach_render_job
    attach_render_job()
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    print(json.dumps(run(request), ensure_ascii=True))
