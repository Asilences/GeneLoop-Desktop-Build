"""Version-checked native bindings for the unchanged, locked PPT Skill.

Only project output roots and Office document/vector conversion are rebound.
No Agent loop, semantic decision or private credential is implemented here.
"""
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def verify_source(skill, origin):
    lock = json.loads((Path(__file__).resolve().parents[2] / 'scenarios/ppt_master/skill-lock.json').read_text(encoding='utf-8'))
    relative = origin.relative_to(skill).as_posix()
    if origin.is_symlink() or hashlib.sha256(origin.read_bytes()).hexdigest() != lock['files'].get(relative):
        raise ImportError('native Skill source version changed: ' + relative)


def install():
    if os.environ.get('GENELOOP_NATIVE_SKILL_RUNTIME') != '1':
        return
    if any(isinstance(f, NativeSkillFinder) for f in sys.meta_path):
        return
    skill = Path(os.environ['GENELOOP_PPT_MASTER_ROOT']).resolve(strict=True)
    work = Path(os.environ['GENELOOP_NATIVE_WORKSPACE']).resolve(strict=True)
    lock = json.loads((Path(__file__).resolve().parents[2] / 'scenarios/ppt_master/skill-lock.json').read_text(encoding='utf-8'))
    sys.meta_path.insert(0, NativeSkillFinder(skill, work, lock['files']))


class NativeSkillFinder(importlib.abc.MetaPathFinder):
    modules = {'config', 'project_management.paths', 'source_to_md', 'source_to_md.doc_to_md',
               'doc_to_md', 'pptx_to_svg.pic_to_svg'}

    def __init__(self, skill, work, files):
        self.skill, self.work, self.files = skill, work, files

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.modules:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or not spec.origin:
            return None
        origin = Path(spec.origin)
        if not origin.is_relative_to(self.skill):
            return None
        relative = origin.relative_to(self.skill).as_posix()
        if origin.is_symlink() or origin.resolve(strict=True) != origin or hashlib.sha256(origin.read_bytes()).hexdigest() != self.files.get(relative):
            raise ImportError('native Skill source version changed: ' + relative)
        spec.loader = NativeSkillLoader(spec.loader, self)
        return spec


class NativeSkillLoader(importlib.abc.Loader):
    def __init__(self, original, binding):
        self.original, self.binding = original, binding

    def create_module(self, spec):
        return self.original.create_module(spec)

    def exec_module(self, module):
        self.original.exec_module(module)
        work = self.binding.work
        if module.__name__ == 'config':
            module.REPO_ROOT = work
            module.PROJECTS_DIR = work / 'projects'
        elif module.__name__ == 'project_management.paths':
            module.REPO_ROOT = work
            module.PROJECTS_ROOT = work / 'projects'
        elif module.__name__ in ('doc_to_md', 'source_to_md.doc_to_md'):
            original = module._convert_with_pandoc
            def convert(source, output, suffix):
                if suffix not in ('.doc', '.odt', '.rtf'):
                    return original(source, output, suffix)
                with tempfile.TemporaryDirectory(prefix='office-source-', dir=work) as tmp:
                    folder = Path(tmp)
                    _office(source, folder, 'docx')
                    return module._convert_docx(folder / (Path(source).stem + '.docx'), output)
            module._convert_with_pandoc = convert
        elif module.__name__ == 'source_to_md':
            original = module.run_backend
            def run_backend(command, script_name):
                if len(command) > 1 and Path(command[1]).resolve() == self.binding.skill / 'scripts/source_to_md/doc_to_md.py':
                    command = [command[0], str(Path(__file__).with_name('desktop_python_entry.py')), *command[1:]]
                return original(command, script_name)
            module.run_backend = run_backend
        elif module.__name__ == 'pptx_to_svg.pic_to_svg':
            def vector_preview(filename, data):
                with tempfile.TemporaryDirectory(prefix='office-vector-', dir=work) as tmp:
                    folder = Path(tmp)
                    source = folder / ('vector' + Path(filename).suffix.lower())
                    source.write_bytes(data)
                    _office(source, folder, 'png')
                    result = folder / 'vector.png'
                    return result.read_bytes() if result.is_file() else None
            module._convert_office_vector_to_png = vector_preview


def _office(source, folder, extension):
    executable = os.environ['GENELOOP_NATIVE_SOFFICE']
    profile = (Path(folder) / 'office-profile').as_uri()
    result = subprocess.run([executable, '-env:UserInstallation=' + profile, '--headless',
                             '--convert-to', extension, '--outdir', str(folder), str(source)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    if result.returncode:
        raise RuntimeError('native Office conversion failed')
