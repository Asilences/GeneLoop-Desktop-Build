#!/usr/bin/env python3
"""Remove only duplicate file-count admission checks; preserve all source guards."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('binding_compat',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(spec);spec.loader.exec_module(compat)
compat.RELEASES=[
 ('paper-web-v46','paper-web-v47','paper-proofreading','scenarios/paper_proofreading/document-read-contracts.json',{'src/adapters/harless_rsi_binding.ts'}),
 ('ppt-master-v43','ppt-master-v44','ppt','scenarios/ppt_master/contracts.json',{'src/adapters/harless_rsi_binding.ts'}),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS={'scripts/reexport-upload-binding-compat.py','src/adapters/harless_rsi_binding.ts'}
original=compat.compatibility_record
def record(candidate,validation_record):
 value=original(candidate,validation_record)
 value.update(repairs=['remove_duplicate_scene_file_count_check'],runtime_delta='Remove only 8/16-file admission ceilings from source binding. Nonempty sources, ownership, hashes, paths, permissions, learned programs and matching algorithm unchanged.',model_task_authority_changed=False)
 return value
compat.compatibility_record=record
if __name__=='__main__':compat.main()
