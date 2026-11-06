"""Select public dependency preparation for an exact original verifier version."""
from __future__ import annotations

import json
from pathlib import Path

from .capability_feedback import file_ref
from .capability_scene import ROOT


PROFILE = ROOT / 'config/skillsbench-dependency-prewarm-v1.json'


def dependency_profile(task_directory, *, profile_path=PROFILE):
    """Return host-owned preparation steps or None for an unmatched verifier.

    The caller runs these in the fresh task container before the model starts,
    records their time/cost, and preserves the original verifier and deadline.
    """
    verifier = Path(task_directory) / 'tests/test.sh'
    if not verifier.is_file():
        return None
    reference = file_ref(verifier)
    profile_path = Path(profile_path)
    value = json.loads(profile_path.read_text(encoding='utf-8'))
    if value.get('format') != 'skillsbench_dependency_prewarm_v1':
        raise ValueError('benchmark_dependency_profile_format_invalid')
    variant = value.get('verifier_variants', {}).get(reference['sha256'])
    if reference['sha256'] not in value['verifier_sha256'] and variant is None:
        return None
    if variant is not None:
        overrides = {step['id']: step for step in variant['steps']}
        value = {**value, 'id': variant['id'],
                 'versions': {**value['versions'], **variant.get('versions', {})},
                 'steps': [overrides.get(step['id'], step) for step in value['steps']]}
    return {**value, 'profile': file_ref(profile_path), 'original_verifier': reference}
