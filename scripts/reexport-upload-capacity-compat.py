#!/usr/bin/env python3
"""Revalidate unchanged Paper/PPT programs against reviewed upload/context changes."""
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upload_compat', ROOT/'scripts/reexport-native-capabilities-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)
COMMON = {'src/adapters/dsh_web_tasks.ts', 'src/adapters/geneloop_presentation.ts',
 'src/adapters/geneloop_presentation_render.py','src/adapters/harless_attachment_text.py',
 'src/adapters/harless_comparison.ts','src/adapters/harless_file_scene.ts',
 'src/adapters/harless_task_scope.ts','src/adapters/session_files.py'}
compat.RELEASES = [
 ('paper-web-v45','paper-web-v46','paper-proofreading','scenarios/paper_proofreading/document-read-contracts.json',COMMON|{'src/adapters/paper_archive.py'}),
 ('ppt-master-v42','ppt-master-v43','ppt','scenarios/ppt_master/contracts.json',COMMON),
]
compat.REGISTRY_SELECTED = {old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-upload-capacity-compat.py',
 'src/adapters/geneloop_upload_limits.ts','src/adapters/geneloop_upload_limits.py','src/adapters/geneloop_upload_limits.json',
 'src/adapters/geneloop_chunked_upload.ts','src/adapters/web_task_request.ts','src/adapters/file_task_scope.ts',
 'src/adapters/reuse_mediation.ts','src/adapters/harless_web_client/client.js',
 'scripts/harless_public_transport.mjs','scenarios/research_ppt/documents.py'}
original = compat.compatibility_record
def record(candidate, validation_record):
 value = original(candidate, validation_record)
 value.update(repairs=['native_decoded_image_admission','uniform_200_mib_file_capacity',
  'cumulative_history_without_per_turn_file_quotas','same_parent_same_lane_cross_scene_sources',
  'authenticated_chunked_transfer_to_native_receipts'],
  runtime_delta='Upload capacity and history transport only. Same ownership, hashes, permissions and learned IR; no new training or changed matching algorithm.',
  model_task_authority_changed=False)
 return value
compat.compatibility_record=record
if __name__=='__main__':compat.main()
