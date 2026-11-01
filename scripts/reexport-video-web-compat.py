#!/usr/bin/env python3
"""Review the exact shared-runtime diff and re-export unchanged certified IR.

No model work, training, policy promotion or video Motif certification occurs.
Published libraries and their five immutable artifacts remain byte-identical.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('certified_compat_exporter',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(spec);spec.loader.exec_module(compat)
SHARED={
    'config/geneloop-capabilities.md','scripts/harless_gateway.mjs',
    'scripts/harless_member_scenes.mjs','src/adapters/dsh_web_tasks.ts',
    'src/adapters/geneloop_command_broker.ts','src/adapters/geneloop_fs.ts',
    'src/adapters/geneloop_shell.ts','src/adapters/harless_comparison_artifacts.ts',
    'src/adapters/harless_scenarios.py','src/adapters/harless_task_scope.ts',
}
compat.RELEASES=[
    ('paper-web-v33','paper-web-v37','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',SHARED|{'src/adapters/session_report.py'}),
    ('ppt-master-v30','ppt-master-v34','ppt',
     'scenarios/ppt_master/contracts.json',SHARED|{'scenarios/ppt_master/prompt.md','src/adapters/harless_settings.ts'}),
]
compat.REGISTRY_SELECTED={'paper-web-v33':'paper-web-v33','ppt-master-v30':'ppt-master-v30'}
compat.ADDITIONAL_LOCKS|={
    'scripts/reexport-video-web-compat.py','src/adapters/geneloop_video.ts',
    'scenarios/remotion_edit/web_server.py','scenarios/remotion_edit/web-scenario.json',
    'scenarios/remotion_edit/web-prompt.md','scenarios/remotion_edit/server.py',
    'scenarios/remotion_edit/structured/server.py',
}
previous_record=compat.compatibility_record
def compatibility_record(candidate,validation_record):
    record=previous_record(candidate,validation_record)
    record.update(release_scope='server/GitHub integration and isolated ordinary video scene',
                  video_motif_certified=False,video_motif_published=False,
                  repairs=['read_only_generated_artifact_paths','autonomous_design_instruction_alignment',
                           'Session_bound_video_tools_and_delivery','fixed_private_renderer_broker'])
    return record
compat.compatibility_record=compatibility_record
if __name__=='__main__':compat.main()
