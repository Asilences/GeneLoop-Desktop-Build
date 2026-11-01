#!/usr/bin/env python3
"""Source-lock the reviewed video source handoff; retain frozen learning artifacts."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('video_web_compat',ROOT/'scripts/reexport-video-web-compat.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
compat=module.compat
compat.RELEASES=[(old,{'paper-web-v37':'paper-web-v38','ppt-master-v34':'ppt-master-v35'}[new],scene,contracts,allowed) for old,new,scene,contracts,allowed in compat.RELEASES]
compat.REGISTRY_SELECTED={'paper-web-v33':'paper-web-v37','ppt-master-v30':'ppt-master-v34'}
compat.ADDITIONAL_LOCKS|={'scripts/reexport-video-context-compat.py'}
if __name__=='__main__':compat.main()
