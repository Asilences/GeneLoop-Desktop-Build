"""Exact compatibility export for desktop integration of PR161/162/163.

Uses the existing exporter; preserves the certified IR, schemas and source
evidence. This is not new learning or Windows/macOS workflow certification.
"""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('desktop_integration_exporter',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(spec);spec.loader.exec_module(compat)
COMMON={
    'scripts/harless_gateway.mjs','src/adapters/capability_construction_history.py',
    'src/adapters/capability_goal_proposal.py','src/adapters/capability_proposal.py',
    'src/adapters/dsh_web_tasks.ts','src/adapters/geneloop_video.ts',
}
compat.RELEASES=[
    ('ppt-master-v109','ppt-master-desktop-v24','ppt','scenarios/ppt_master/contracts.json',
     COMMON|{'scenarios/ppt_master/converted_source.py'}),
    ('paper-web-v111','paper-web-desktop-v24','paper-proofreading','scenarios/paper_proofreading/document-read-contracts.json',
     COMMON|{'scenarios/paper_proofreading/server.py','scripts/export-online-motif-manifest.py'}),
]
compat.REGISTRY_SELECTED={'ppt-master-v109':'ppt-master-desktop-v23','paper-web-v111':'paper-web-desktop-v23'}
compat.ADDITIONAL_LOCKS|={
    'scripts/reexport-desktop-pr-integration.py','src/adapters/harless_motif_catalog.ts',
    'src/adapters/motif_evidence_projection.ts','config/motif-evidence-v2.schema.json',
    'src/adapters/geneloop_privacy.py','src/adapters/geneloop_privacy.ts',
    'src/adapters/geneloop_privacy_worker.py','src/adapters/privacy_worker_pool.ts',
    'src/adapters/rsi_privacy_candidates.py','src/adapters/rsi_privacy_policy.py',
    'src/adapters/rsi_privacy_recognizers.py','src/adapters/rsi_privacy_tools.py',
    'config/geneloop-privacy-policy-v1.json','config/rsi-privacy-tools.json',
    'config/rsi-privacy-candidate-tools.json','schemas/geneloop-privacy-policy.schema.json',
}
original=compat.compatibility_record
def compatibility_record(candidate,validation_record):
    value=original(candidate,validation_record)
    value.update(release_scope='desktop_pr161_162_163_source_integration',
                 repairs=['desktop_native_output_adapter','motif_read_only_catalog','shared_privacy_admission'],
                 native_desktop_workflow_certified=False,
                 runtime_delta='Reuses existing Paper/PPT read programs under the exact merged source closure. No new training, model calls, platform certification or quality/cost promotion.')
    return value
compat.compatibility_record=compatibility_record
if __name__=='__main__':compat.main()
