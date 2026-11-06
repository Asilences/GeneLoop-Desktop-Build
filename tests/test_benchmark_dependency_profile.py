"""Pure dependency profile selection diagnostics, no Docker/model/network."""
import json
from pathlib import Path

from src.adapters.benchmark_dependency_profile import PROFILE, dependency_profile
from src.adapters.capability_feedback import file_ref


def test_matching_original_verifier_gets_pinned_public_dependency_steps(tmp_path):
    verifier = tmp_path / 'task/tests/test.sh'
    verifier.parent.mkdir(parents=True)
    verifier.write_text('#!/bin/bash\n# synthetic selection fixture\n')
    value = json.loads(PROFILE.read_text())
    value['verifier_sha256'] = [file_ref(verifier)['sha256']]
    profile = tmp_path / 'profile.json'
    profile.write_text(json.dumps(value))
    result = dependency_profile(verifier.parents[1], profile_path=profile)
    assert result['original_verifier'] == file_ref(verifier)
    assert result['profile'] == file_ref(profile)
    assert result['versions']['uv'] == '0.9.7'
    assert result['versions']['pytest'] == '8.4.1'
    assert result['versions']['pytest-json-ctrf'] == '0.3.5'
    assert result['environment_keys'] == ['UV_DOWNLOAD_URL']
    assert '--version --version' in result['steps'][3]['command']
    assert all('/tests/' not in step['command'] and '/app/gt' not in step['command']
               for step in result['steps'])


def test_unmatched_verifier_has_no_automatic_preparation(tmp_path):
    verifier = tmp_path / 'task/tests/test.sh'
    verifier.parent.mkdir(parents=True)
    verifier.write_text('#!/bin/bash\n# unknown verifier\n')
    assert dependency_profile(verifier.parents[1]) is None


def test_missing_verifier_has_no_automatic_preparation(tmp_path):
    assert dependency_profile(tmp_path) is None


def test_equipment_exact_hash_variant_adds_original_unpinned_pandas_only(tmp_path):
    verifier = tmp_path / 'task/tests/test.sh'
    verifier.parent.mkdir(parents=True)
    verifier.write_text('#!/bin/bash\n# equipment variant selection fixture\n')
    value = json.loads(PROFILE.read_text())
    variant = next(iter(value['verifier_variants'].values()))
    value['verifier_variants'] = {file_ref(verifier)['sha256']: variant}
    profile = tmp_path / 'profile.json'
    profile.write_text(json.dumps(value))
    result = dependency_profile(verifier.parents[1], profile_path=profile)
    assert result['id'].endswith('-pandas')
    assert '--with pandas pytest' in result['steps'][3]['command']
    assert 'unpinned' in result['versions']['pandas']
    assert result['steps'][:3] == value['steps'][:3]
    assert result['steps'][4:] == value['steps'][4:]
