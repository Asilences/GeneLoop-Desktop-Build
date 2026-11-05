"""Validate host-supplied, already exposed Capability and Builder evidence.

This is an input adapter over the existing Capability snapshot and decision
evidence protocols. It does not create a registry, alter ownership, or certify
any artifact.
"""
from __future__ import annotations

import json

from .capability_contract import validate_capability_snapshot
from .capability_decision_evidence import inspect_decision
from .capability_feedback import verify


def load_builder_input_manifest(reference, *, expected_owner, expected_scope):
    manifest = json.loads(verify(reference))
    fields = {'format', 'owner', 'scope', 'exposure', 'snapshot',
              'focus_capability', 'construction_observations'}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValueError('evolution_input_manifest_shape_invalid')
    if (manifest['format'] != 'capability_evolution_builder_inputs_v1'
            or manifest['owner'] != expected_owner
            or manifest['scope'] != expected_scope
            or manifest['exposure'] != 'historically_exposed'):
        raise ValueError('evolution_input_manifest_identity_or_role_invalid')
    snapshot = validate_capability_snapshot(json.loads(verify(manifest['snapshot'])), expected_owner)
    focus = manifest['focus_capability']
    if focus not in snapshot['roots']:
        raise ValueError('evolution_input_focus_capability_not_active_root')
    capabilities = {item['id']: item for item in snapshot['capabilities']}
    pending, visited = [focus], set()
    while pending:
        reference = pending.pop()
        if reference['id'] in visited:
            continue
        capability = capabilities.get(reference['id'])
        if (capability is None or capability['revision_sha256'] != reference['sha256']
                or capability['certification'] != 'certified' or capability['lifecycle'] != 'active'):
            raise ValueError('evolution_input_focus_capability_not_certified_active')
        visited.add(reference['id'])
        pending.extend(capability['dependencies'])
    references = manifest['construction_observations']
    if not isinstance(references, list) or len(references) < 2:
        raise ValueError('evolution_input_independent_builder_observations_required')
    entries, identities = [], set()
    for item in references:
        row = inspect_decision(item, expected_owner)
        if row.get('evaluation_role') == 'evaluation':
            raise ValueError('evolution_input_evaluation_source_not_exposed')
        if row.get('stage') != 'construction':
            raise ValueError('evolution_input_builder_observation_required')
        if focus not in row.get('capabilities', []):
            raise ValueError('evolution_input_builder_capability_not_available')
        if not row.get('source_identity') or row['source_identity'] in identities:
            raise ValueError('evolution_input_builder_sources_not_independent')
        identities.add(row['source_identity'])
        entries.append({'split': 'training', 'scope': expected_scope, 'evidence': item})
    return {'snapshot': snapshot, 'entries': entries,
            'exposure': manifest['exposure'], 'focus_capability': focus,
            'independent_builder_sources': len(identities),
            'source_independence_basis': 'distinct_verified_task_identities; source_family_requires_host_audit',
            'exposure_basis': 'host_manifest_declaration; original_bytes_and_existing_evaluation_role_revalidated'}
