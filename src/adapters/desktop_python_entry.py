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
    if relative in {'scripts/narration_sync.py', 'scripts/notes_to_audio.py', 'scripts/powerpoint_video.py',
                    'scripts/video_motion_plan.py', 'scripts/video_sound_mix.py', 'scripts/video_subtitles.py'}:
        from src.adapters.desktop_skill_runtime import verify_source
        verify_source(skill, source)
        raise RuntimeError('GeneLoop PPT 仅制作和编辑演示文稿，不提供旁白、配音、演示视频或字幕流程。请使用 PPTX/PDF/逐页预览交付。')
    names = {'scripts/source_to_md/doc_to_md.py': 'doc_to_md',
             'scripts/source_to_md.py': 'source_to_md'}
    name = names.get(relative)
    if not name:
        os.execv(sys.executable, [sys.executable, *args])
    from src.adapters.desktop_skill_runtime import install, verify_source
    verify_source(skill, source)
    install()
    sys.path.insert(0, str(skill / 'scripts'))
    sys.path.insert(0, str(skill / 'scripts/source_to_md'))
    sys.path.insert(0, str(source.parent))
    module = __import__(name, fromlist=['main'])
    sys.argv = args
    raise SystemExit(module.main())


if __name__ == '__main__':
    main()
