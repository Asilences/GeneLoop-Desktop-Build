#!/usr/bin/env python3
"""Preserve learned Paper/PPT artifacts while admitting one read-only member mount."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('video_paired_compat',ROOT/'scripts/reexport-video-paired-compat.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
compat=module.compat
compat.RELEASES=[
    ('paper-web-v41','paper-web-v42','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',{'scripts/harless_member_scenes.mjs'}),
    ('ppt-master-v38','ppt-master-v39','ppt',
     'scenarios/ppt_master/contracts.json',{'scripts/harless_member_scenes.mjs'}),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS={'scripts/reexport-video-member-lock-compat.py'}
original_record=compat.compatibility_record

def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value.update(release_scope='complete member read-only video runtime file mounts',
        repairs=['explicit_fixed_regular_package_lock_mount'],
        runtime_delta='Mount the byte-locked package-lock.json as a single read-only file in member workers; '
                      'the project root is not exposed. Learned IR and all validation rules are unchanged.')
    return value

compat.compatibility_record=compatibility_record
if __name__=='__main__':compat.main()
