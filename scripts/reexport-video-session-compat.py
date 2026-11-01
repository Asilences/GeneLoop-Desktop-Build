#!/usr/bin/env python3
"""Bind the reviewed native audit persistence repair without changing learned programs."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('video_audio_compat',ROOT/'scripts/reexport-video-audio-compat.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
compat=module.compat
reviewed={'src/adapters/geneloop_native_work.ts','src/adapters/harless_file_scene.ts'}
compat.RELEASES=[(old,{'paper-web-v39':'paper-web-v40','ppt-master-v36':'ppt-master-v37'}[new],scene,contracts,allowed|reviewed) for old,new,scene,contracts,allowed in compat.RELEASES]
compat.REGISTRY_SELECTED={'paper-web-v33':'paper-web-v39','ppt-master-v30':'ppt-master-v36'}
compat.ADDITIONAL_LOCKS|={'scripts/reexport-video-session-compat.py','scripts/repair-geneloop-session-events.py','scripts/check-native-session-log.mjs','src/adapters/file_event_projection.ts'}
if __name__=='__main__':compat.main()
