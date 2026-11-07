"""Run locked Skill CLI modules with native bindings, leaving their bytes intact."""
import importlib.util
import os
from pathlib import Path
import sys


def main():
    args = sys.argv[1:]
    # These flags do not change script selection. Preserve ordinary -c/-m and
    # unknown interpreter modes by forwarding them to the original interpreter.
    while args and args[0] in ('-B', '-u'):
        args.pop(0)
    if not args or args[0].startswith('-'):
        os.execv(sys.executable, [sys.executable, *args])
    source = Path(args[0]).resolve()
    skill = Path(os.environ['GENELOOP_PPT_MASTER_ROOT']).resolve()
    if not source.is_relative_to(skill):
        os.execv(sys.executable, [sys.executable, *args])
    relative = source.relative_to(skill).as_posix()
    names = {'scripts/source_to_md/doc_to_md.py': 'source_to_md.doc_to_md',
             'scripts/video_subtitles.py': 'video_subtitles'}
    name = names.get(relative)
    if not name:
        os.execv(sys.executable, [sys.executable, *args])
    from src.adapters.desktop_skill_runtime import install, verify_source
    verify_source(skill, source)
    if name == 'video_subtitles':
        speech = Path(os.environ['GENELOOP_NATIVE_SPEECH_ROOT'])
        if not (speech / 'provenance.json').is_file():
            raise RuntimeError('随包字幕对齐组件缺失，请修复桌面安装。')
        sys.path.insert(0, str(speech / 'site'))
        os.environ['XDG_CACHE_HOME'] = str(speech / 'cache')
        os.environ['NUMBA_CACHE_DIR'] = str(Path(os.environ['GENELOOP_NATIVE_WORKSPACE']) / '.cache/numba')
    install()
    sys.path.insert(0, str(skill / 'scripts'))
    sys.path.insert(0, str(source.parent))
    module = __import__(name, fromlist=['main'])
    sys.argv = args
    raise SystemExit(module.main())


if __name__ == '__main__':
    main()
