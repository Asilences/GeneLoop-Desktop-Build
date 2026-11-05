"""Version-bound role calibration through the locked ppt-master implementation."""
from pathlib import Path
import base64
import hashlib
import importlib.metadata
import json
import runpy
import subprocess
import sys

if __package__:
    from .ppt_design_preflight import font_coverage


def prepare_ppt(request):
    project = Path(request['project'])
    if not project.is_relative_to('/work/projects') or project.resolve() != project:
        raise ValueError('preparation_project_outside_workspace')
    inputs = {}
    for name in ('spec_lock.md', 'design_spec.md'):
        path = project / name
        if path.is_symlink() or path.resolve() != path or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('preparation_design_files_required')
        inputs[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    script = Path('/opt/geneloop/ppt-master/scripts/text_measure.py')
    sys.path.insert(0, str(script.parent))
    measurement = runpy.run_path(str(script))
    roles = measurement['_roles_from_spec_lock'](project / 'spec_lock.md')
    faces, glyph_findings = {}, []
    text = '\n'.join((project / name).read_text() for name in inputs)
    for name, (family, size) in roles.items():
        for weight in ('regular', 'bold'):
            face = font_coverage(family, weight)
            missing = sorted({ord(c) for c in text if not c.isspace() and ord(c) not in face['characters']})
            faces[name + ':' + weight] = {**{k: v for k, v in face.items() if k != 'characters'},
                                        'file_sha256': hashlib.sha256(Path(face['file']).read_bytes()).hexdigest()}
            if missing:
                glyph_findings.append({'role': name, 'weight': weight, 'font_family': family,
                                       'codepoints': ['U+' + format(c, '04X') for c in missing]})
    packages = {}
    for name in ('Pillow', 'fonttools', 'CairoSVG', 'PyMuPDF'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    dependencies = {'inputs': inputs, 'faces': faces, 'packages': packages,
                    'python': sys.version, 'measure_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
                    'host_environment': request['environment'], 'implementation_sha256': request['implementation_sha256']}
    key = hashlib.sha256(json.dumps(dependencies, sort_keys=True).encode()).hexdigest()
    validation = project / 'validation'
    validation.mkdir(exist_ok=True)
    if validation.is_symlink() or validation.resolve() != validation:
        raise ValueError('preparation_validation_changed')
    path = validation / 'host-typography.json'
    calibration = validation / 'text_calibration.json'
    for target in (path, calibration):
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_file() or target.stat().st_nlink != 1:
                raise ValueError('preparation_output_changed')
    if path.is_file() and not path.is_symlink() and calibration.is_file() and not calibration.is_symlink():
        old = json.loads(path.read_text())
        if old.get('key') == key and old.get('calibration_sha256') == hashlib.sha256(calibration.read_bytes()).hexdigest():
            return {**old, 'reused_calibration': True}
    argv = [sys.executable, str(script), 'calibrate', str(project), '--outline', '--json']
    normal = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=120)
    normal_data = json.loads(normal.stdout)
    bold_args = [value for name, (family, size) in roles.items() for value in ('--role', f'{name}:{family}:{size}:bold')]
    bold = subprocess.run([*argv, *bold_args], capture_output=True, text=True, check=True, timeout=120)
    bold_data = json.loads(bold.stdout)
    # Keep the official normal-role table at its documented path. The host
    # receipt supplies the additional bold table without losing normal rates.
    calibration.write_text(json.dumps(normal_data, ensure_ascii=False, indent=2) + '\n')
    result = {'version': 1, 'key': key, 'dependencies': dependencies, 'fonts': faces,
              'normal': normal_data, 'bold': bold_data, 'glyph_review': glyph_findings,
              'status': 'prepared', 'reused_calibration': False,
              'calibration_sha256': hashlib.sha256(calibration.read_bytes()).hexdigest(),
              'next_action': 'compose_pages_using_role_rates',
              'scope': 'role calibration and installed font coverage; actual page rendering is checked by finalize_ppt'}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


if __name__ == '__main__':
    print(json.dumps(prepare_ppt(json.loads(base64.b64decode(sys.argv[1]))), ensure_ascii=False))
