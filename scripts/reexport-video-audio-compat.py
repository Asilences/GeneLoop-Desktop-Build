#!/usr/bin/env python3
"""Bind the isolated media inspection tool; do not retrain or alter learned IR."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('video_context_compat',ROOT/'scripts/reexport-video-context-compat.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
compat=module.compat
compat.RELEASES=[(old,{'paper-web-v38':'paper-web-v39','ppt-master-v35':'ppt-master-v36'}[new],scene,contracts,allowed) for old,new,scene,contracts,allowed in compat.RELEASES]
compat.REGISTRY_SELECTED={'paper-web-v33':'paper-web-v38','ppt-master-v30':'ppt-master-v35'}
compat.ADDITIONAL_LOCKS|={'scripts/reexport-video-audio-compat.py'}
if __name__=='__main__':compat.main()
