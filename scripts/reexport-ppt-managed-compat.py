#!/usr/bin/env python3
"""Bind managed PPT delivery and learning to main's published read libraries."""
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ppt_managed_exporter', ROOT / 'scripts/reexport-native-capabilities-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)

shared = {
    'scripts/harness-web.py', 'scripts/learn-web-ppt-tasks.py',
    'src/adapters/dsh_web_tasks.ts', 'src/adapters/geneloop_command_broker.ts',
    'src/adapters/geneloop_native_work.ts', 'src/adapters/harless_comparison_artifacts.ts',
    'src/adapters/harless_ppt_learning.ts', 'src/adapters/harless_public_output.ts',
    'src/adapters/harless_web_client/client.js', 'src/adapters/ppt_master_recovery.ts',
}
compat.RELEASES = [
    ('ppt-master-v44', 'ppt-master-v71', 'ppt', 'scenarios/ppt_master/contracts.json', shared | {
        'scenarios/ppt_master/converted_source.py', 'scenarios/ppt_master/prompt.md',
        'scenarios/ppt_master/requirements.txt', 'scenarios/ppt_master/server.py',
        'scripts/learn-ppt-master-motif.py',
    }),
    ('paper-web-v47', 'paper-web-v73', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json', shared | {'src/adapters/geneloop_command_client.mjs'}),
]
compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS |= {
    'scripts/reexport-ppt-managed-compat.py', 'scripts/learn-ppt-components.py',
    'scripts/certify-artifact-motifs.mjs', 'scripts/learn-artifact-motifs.py',
    'scripts/run-artifact-motif.mjs', 'src/adapters/geneloop_command_client.mjs',
    'src/adapters/artifact_motif_runtime.ts', 'src/adapters/artifact_motif_shell.ts',
    'src/adapters/artifact_motif_trace.ts', 'src/adapters/artifact_motif_compiler.py',
    'src/adapters/artifact_motif_transport.ts',
    'src/adapters/ppt_annotation_repair.py', 'src/adapters/ppt_component_cache.ts',
    'src/adapters/ppt_component_equivalence.py', 'src/adapters/ppt_component_learning.py',
    'src/adapters/ppt_component_literals.py', 'src/adapters/ppt_component_render.py',
    'src/adapters/ppt_component_schema.ts', 'src/adapters/ppt_component_tool.ts',
    'src/adapters/ppt_delivery_learning.py', 'src/adapters/ppt_delivery_pipeline.ts',
    'src/adapters/ppt_delivery_quality.py', 'src/adapters/ppt_delivery_runner.py',
    'src/adapters/ppt_delivery_state.ts', 'src/adapters/ppt_design_preflight.py',
    'src/adapters/ppt_evaluation.py', 'src/adapters/ppt_learning_evidence.py',
    'src/adapters/ppt_learning_evidence.ts', 'src/adapters/ppt_page_learning.py',
    'src/adapters/ppt_preparation_runner.py', 'src/adapters/ppt_program_broker.ts',
    'src/adapters/ppt_program_learning.py', 'src/adapters/ppt_program_learning.ts',
    'src/adapters/ppt_capability_broker.ts',
    'src/adapters/rsi_quality.py', 'src/adapters/rsi_quality.ts',
    'src/adapters/rsi_protocol.py', 'src/adapters/rsi_protocol.ts',
    'schemas/rsi-protocol-v1.schema.json', 'scenarios/ppt_master/design-profiles.json',
    'scenarios/ppt_master/quality-rubric.json', 'scenarios/ppt_master/runtime-policy.md',
}
original_record = compat.compatibility_record


def compatibility_record(candidate, validation_record):
    value = original_record(candidate, validation_record)
    value['release_scope'] = 'managed_ppt_delivery_and_account_local_learning_on_current_main'
    value['repairs'] += [
        'versioned_role_typography', 'shared_office_delivery', 'module_annotation_repair',
        'immutable_single_task_learning_sources', 'independent_page_program_certification',
        'version_guarded_component_revision', 'final_component_delivery_lineage',
    ]
    value['runtime_delta'] = (
        'The original read IR, evidence and MCP schemas are retained. '
        'Learned page programs require separate Artifact certification and future-task validation.'
    )
    return value


compat.compatibility_record = compatibility_record
if __name__ == '__main__':
    if '--rae-integration' in sys.argv:
        sys.argv.remove('--rae-integration')
        reviewed = {
            'scripts/reexport-ppt-managed-compat.py',
            'src/adapters/capability_improvement.py',
            'src/adapters/capability_proposal.py',
            'src/adapters/capability_scene.py',
        }
        compat.RELEASES = [
            ('ppt-master-v75', 'ppt-master-v76', 'ppt', 'scenarios/ppt_master/contracts.json', reviewed),
            ('paper-web-v77', 'paper-web-v78', 'paper-proofreading',
             'scenarios/paper_proofreading/document-read-contracts.json', reviewed),
        ]
        compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
        compat.ADDITIONAL_LOCKS |= {
            'schemas/capability-improvement-v1.schema.json',
            'src/adapters/capability_motif_learning.py',
            'src/adapters/capability_builder_application.py',
            'src/adapters/capability_source_authoring.py',
            'src/adapters/capability_program_training.py',
            'src/adapters/capability_construction_history.py',
            'src/adapters/capability_feedback.py',
            'src/adapters/capability_evolution.py',
        }
    elif '--member-transport-fix' in sys.argv:
        sys.argv.remove('--member-transport-fix')
        reviewed = {
            'scripts/reexport-ppt-managed-compat.py', 'scripts/run-artifact-capability.mjs',
            'src/adapters/artifact_capability_runtime.ts', 'src/adapters/artifact_motif_runtime.ts',
            'src/adapters/artifact_motif_transport.ts', 'src/adapters/ppt_capability_budget.py',
            'src/adapters/ppt_component_learning.py', 'src/adapters/ppt_program_broker.ts',
        }
        compat.RELEASES = [
            ('ppt-master-v74', 'ppt-master-v75', 'ppt', 'scenarios/ppt_master/contracts.json', reviewed),
            ('paper-web-v76', 'paper-web-v77', 'paper-proofreading',
             'scenarios/paper_proofreading/document-read-contracts.json', reviewed),
        ]
        compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
    compat.main()
