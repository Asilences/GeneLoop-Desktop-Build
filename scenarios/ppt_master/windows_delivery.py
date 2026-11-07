"""Native desktop delivery for a prepared, self-contained ppt-master project."""
from pathlib import Path
import argparse
import base64
import io
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from scenarios.ppt_master.package import verify_installation
from scenarios.research_ppt.validation import validate_delivery
from scenarios.research_ppt.web_scope import configure_web_scope
from src.adapters.ppt_delivery_runner import fixed_file
from src.adapters.ppt_design_preflight import inspect_svg

MAX_PAGE_BYTES = 30 * 1024 * 1024
MAX_SLIDES = 200  # Match the PPT Master Generate manifest, not structured-plan limits.
MAX_NOTES_BYTES = 64 * 1024
MAX_DECK_BYTES = 200 * 1024 * 1024
PAGE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.svg')
SVG = '{http://www.w3.org/2000/svg}'
FRAGMENT_URL = re.compile(r'url\(\s*#[A-Za-z_][\w.-]*\s*\)', re.ASCII)
STATIC_ELEMENTS = frozenset(
    'svg g defs rect circle ellipse line polyline polygon path text tspan title desc '
    'linearGradient radialGradient stop clipPath image use symbol mask pattern'.split()
)

def attach_render_job():
    if sys.platform != 'win32':
        return
    # Windows closes this non-inheritable handle when the desktop cancels the
    # Python process. Stop the checker, converter and Office descendants too.
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ('per_process', ctypes.c_int64), ('per_job', ctypes.c_int64), ('flags', wintypes.DWORD),
            ('min_working_set', ctypes.c_size_t), ('max_working_set', ctypes.c_size_t),
            ('process_limit', wintypes.DWORD), ('affinity', ctypes.c_size_t),
            ('priority_class', wintypes.DWORD), ('scheduling_class', wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('basic', BasicLimits), ('io', ctypes.c_uint64 * 6), ('memory', ctypes.c_size_t * 4)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or
            not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(handle)
        raise error


def fixed_directory(path):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path or not path.is_dir():
        raise ValueError('需要固定目录，不能使用链接或重解析点。')
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('需要固定目录，不能使用链接或重解析点。')
    return path


def snapshot_file(source, destination, root, limit):
    source = fixed_file(source, root)
    with source.open('rb') as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not raw or len(raw) > limit or
            (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
        raise ValueError('输入文件为空、超过大小限制，或在复制期间发生变化。')
    raw.decode('utf-8', errors='strict')
    if destination.suffix == '.svg':
        validate_static_svg(raw)
    with destination.open('xb') as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest(), len(raw)


def validate_static_svg(raw):
    if re.search(rb'<\s*!\s*(?:DOCTYPE|ENTITY)|<\?(?!xml\s)', raw, re.I):
        raise ValueError('SVG 禁止实体、文档类型和处理指令。')
    root = ET.fromstring(raw)
    if root.tag != SVG + 'svg':
        raise ValueError('必须提供 SVG 页面。')
    pending = [(root, 0)]
    elements = 0
    while pending:
        element, depth = pending.pop()
        elements += 1
        if elements > 5000 or depth > 64:
            raise ValueError('SVG 结构超过 Windows 导出限制。')
        if not element.tag.startswith(SVG) or element.tag[len(SVG):] not in STATIC_ELEMENTS:
            raise ValueError('Windows 导出入口仅接受自包含的静态 SVG 形状和文本。')
        for name, value in element.attrib.items():
            if name == '{http://www.w3.org/XML/1998/namespace}space' and value in ('default', 'preserve'):
                continue
            if name in ('href', '{http://www.w3.org/1999/xlink}href'):
                if element.tag == SVG + 'use' and re.fullmatch(r'#[A-Za-z_][\w.-]*', value):
                    continue
                if element.tag == SVG + 'image':
                    match = re.fullmatch(r'data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=\r\n]+)', value)
                    if not match:
                        raise ValueError('图片必须为自包含PNG/JPEG/WebP/GIF；不读取外部路径或URL。')
                    raw_image = base64.b64decode(match[2], validate=True)
                    if len(raw_image) > 20 * 1024 * 1024:
                        raise ValueError('单张图片超过20MiB。')
                    from PIL import Image
                    with Image.open(io.BytesIO(raw_image)) as image:
                        if image.format.lower() != match[1] or image.width * image.height > 64 * 1024 * 1024:
                            raise ValueError('图片声明、格式或尺寸无效。')
                        image.verify()
                    continue
                raise ValueError('不接受外部SVG引用。')
            if ('{' in name or name.lower().startswith('on') or name.lower() in ('href', 'src') or
                    re.search(r'[\\@]|/\*', value) or
                    re.search(r'url\s*\(', FRAGMENT_URL.sub('', value), re.I)):
                raise ValueError('SVG 属性引用了未授权的资源。')
        pending.extend((child, depth + 1) for child in element)


def snapshot_project(project, destination):
    (destination / 'svg_output').mkdir(parents=True)
    (destination / 'notes').mkdir()
    sources = fixed_directory(project / 'svg_output')
    notes = fixed_directory(project / 'notes')
    pages = sorted(sources.glob('*.svg'))
    if not 1 <= len(pages) <= MAX_SLIDES or any(not PAGE_NAME.fullmatch(page.name) for page in pages):
        raise ValueError(f'需要 1 至 {MAX_SLIDES} 页以 ASCII 文件名命名的 SVG。')
    spec_hash, total = snapshot_file(project / 'spec_lock.md', destination / 'spec_lock.md', project, MAX_NOTES_BYTES)
    roster = []
    for page in pages:
        relative = 'svg_output/' + page.name
        note = page.stem + '.md'
        svg_hash, svg_size = snapshot_file(page, destination / relative, sources, MAX_PAGE_BYTES)
        note_hash, note_size = snapshot_file(notes / note, destination / 'notes' / note, notes, MAX_NOTES_BYTES)
        total += svg_size + note_size
        if total > MAX_DECK_BYTES:
            raise ValueError('项目超过 Windows 导出大小限制。')
        roster.append({'source': relative, 'source_sha256': svg_hash, 'notes_sha256': note_hash})
    return spec_hash, roster


def render_project(stage, snapshot, pages, skill, renderer):
    texts, findings = [], []
    for index, entry in enumerate(pages, 1):
        raw = (snapshot / entry['source']).read_bytes()
        preflight = inspect_svg(raw, check_fonts=False)
        findings.extend({**finding, 'page': index} for finding in preflight['findings'])
        texts.append([''.join(node.itertext()).strip() for node in ET.fromstring(raw).iter(SVG + 'text')])
    if findings:
        return {'passed': False, 'errors': findings, 'artifacts': []}

    pptx = stage / 'presentation.pptx'
    env = desktop_environment(stage, renderer)
    python = [sys.executable, '-E', '-s', '-B', '-X', 'utf8']
    scripts = skill / 'scripts'
    for label, argv in [
        ('official-quality', [*python, str(scripts / 'svg_quality_checker.py'), str(snapshot), '--stage', 'final',
                              '--canonical-authoring', '--json']),
        ('pptx-export', [*python, str(scripts / 'svg_to_pptx.py'), str(snapshot), '-o', str(pptx),
                         '--with-notes', '--no-animations']),
    ]:
        result = subprocess.run(argv, cwd=stage, env=env, capture_output=True, timeout=240,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            detail = (result.stderr or result.stdout).decode('utf-8', errors='replace')[-1600:]
            return {'passed': False, 'errors': [{'rule': label, 'detail': detail}], 'artifacts': []}

    return validate_windows_deck(stage, pptx, texts, renderer, env, max_slides=MAX_SLIDES)


def desktop_environment(stage, renderer):
    env = {name: os.environ[name] for name in ('SystemRoot', 'SystemDrive', 'WINDIR', 'LANG', 'LC_ALL') if name in os.environ}
    env.update(TEMP=str(stage), TMP=str(stage), TMPDIR=str(stage), HOME=str(stage),
               USERPROFILE=str(stage), APPDATA=str(stage), LOCALAPPDATA=str(stage),
               PATH=str(renderer.parent), PATHEXT='.COM', NoDefaultCurrentDirectoryInExePath='1')
    if sys.platform == 'darwin':
        from xml.sax.saxutils import escape
        fonts = Path(__file__).resolve().parents[3] / 'fonts'
        config = Path(stage) / 'fontconfig.xml'
        cache = Path(stage) / 'font-cache'
        cache.mkdir(exist_ok=True)
        config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>' +
                          escape(str(fonts)) + '</dir><cachedir>' + escape(str(cache)) + '</cachedir></fontconfig>', encoding='utf-8')
        env.update(FONTCONFIG_FILE=str(config), SAL_FONTPATH_PRIVATE=str(fonts))
    return env


def validate_windows_deck(stage, pptx, texts, renderer, env=None, *, require_notes=True, max_slides=30):
    job = stage / 'job.json'
    job.write_text('{"kind":"desktop-ppt-export"}', encoding='utf-8')
    configure_web_scope(job, stage)
    if env is None:
        env = desktop_environment(stage, renderer)
    original = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update(env)
        discovered = shutil.which('libreoffice') or shutil.which('soffice')
        if not discovered or Path(discovered).resolve(strict=True) != renderer:
            raise ValueError('无法从显式 LibreOffice 目录定位渲染器。')
        report = validate_delivery(pptx, len(texts), expected_texts=texts,
                                   validation_root=stage / 'validation', require_notes=require_notes,max_slides=max_slides)
    finally:
        os.environ.clear()
        os.environ.update(original)
    if report['passed']:
        report['artifacts'].insert(0, {'kind': 'pptx', 'path': str(pptx), 'sha256': report['pptx_sha256']})
    return report


def export_project(project, output, skill, renderer):
    if sys.platform not in {'win32', 'darwin', 'linux'}:
        raise ValueError('此平台没有桌面导出实现。')
    project, skill = fixed_directory(project), fixed_directory(skill)
    output = Path(output).absolute()
    parent = fixed_directory(output.parent)
    renderer = Path(renderer).absolute()
    fixed_directory(renderer.parent)
    fixed_file(renderer, renderer.parent)
    if renderer.name.lower() != ('soffice.com' if sys.platform == 'win32' else 'soffice'):
        raise ValueError('请使用当前平台的 LibreOffice 渲染器。')
    if output.exists() or output.is_symlink() or output.is_relative_to(project) or output.is_relative_to(skill):
        raise ValueError('输出必须是位于输入项目与工具目录之外的新文件夹。')
    locked = verify_installation(skill)
    with tempfile.TemporaryDirectory(prefix='.geneloop-ppt-', dir=parent, ignore_cleanup_errors=True) as temp:
        stage = Path(temp)
        snapshot = stage / 'project'
        spec_hash, pages = snapshot_project(project, snapshot)
        receipt = render_project(stage, snapshot, pages, skill, renderer)
        if not receipt['passed']:
            return {'mechanical_status': 'failed', 'review_status': 'pending', 'findings': receipt['errors'], 'artifacts': []}
        publish = stage / 'publish'
        publish.mkdir()
        artifacts = []
        for row in receipt['artifacts']:
            artifact = fixed_file(row['path'], stage)
            raw = artifact.read_bytes()
            if row['sha256'] != hashlib.sha256(raw).hexdigest():
                raise ValueError('渲染后的产物校验失败。')
            with (publish / artifact.name).open('xb') as stream:
                stream.write(raw)
            artifacts.append({**row, 'path': artifact.name, 'bytes': len(raw)})
        summary = {'schema_version': 1, 'execution': ('windows' if sys.platform == 'win32' else sys.platform) + '-local', 'mechanical_status': 'passed',
                   'review_status': 'pending', 'ppt_master_sha256': locked['package_sha256'],
                   'spec_sha256': spec_hash, 'pages': pages, 'artifacts': artifacts,
                   'libreoffice_version': receipt['dependencies']['libreoffice_version'],
                   'warnings': receipt['warnings']}
        (publish / 'delivery-receipt.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        publish.rename(output)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ppt-master', type=Path, required=True)
    parser.add_argument('--soffice', type=Path, required=True)
    parser.add_argument('--desktop-job', action='store_true')
    args = parser.parse_args()
    try:
        if args.desktop_job and sys.platform == 'win32':
            attach_render_job()
        result = export_project(args.project, args.output, args.ppt_master, args.soffice)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ET.ParseError) as error:
        result = {'mechanical_status': 'failed', 'review_status': 'pending', 'artifacts': [], 'error': str(error)}
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['mechanical_status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
