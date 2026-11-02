"""Verifier fail-closed diagnostics; real media checks run on Linux Docker."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest

PATH=Path(__file__).resolve().parents[1]/'scenarios/remotion_edit/structured/verify_capability_outputs.py'
spec=importlib.util.spec_from_file_location('capability_output_verifier',PATH)
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def setup(tmp_path):
    work=tmp_path/'work';work.mkdir()
    return {'workspace':str(work),'runtime_directory':str(tmp_path),'media_tools_directory':str(tmp_path),'inputs':[]}


def test_missing_outputs_cannot_certify_even_when_runtime_claims_success(tmp_path):
    manifest=setup(tmp_path)
    with patch.object(checker.subprocess,'run',side_effect=AssertionError('must not dispatch')):
        result=checker.verify(manifest,{'status':'succeeded','result':{'videos':[]}},
                              {'outputs':[{'width':640}]},tmp_path/'qa')
    assert result['passed'] is False
    assert next(row for row in result['checks'] if row['id']=='output_count')['status']=='failed'


def test_external_or_symlink_escape_artifacts_rejected_before_media_execution(tmp_path):
    manifest=setup(tmp_path);outside=tmp_path/'private.bin';outside.write_bytes(b'private')
    linked=Path(manifest['workspace'])/'video.mp4';linked.symlink_to(outside)
    with patch.object(checker.subprocess,'run',side_effect=AssertionError('must not dispatch')):
        for path in (outside,linked):
            with pytest.raises(ValueError,match='output_scope'):
                checker.verify(manifest,{'status':'succeeded','result':{'videos':[{'video_path':str(path)}]}},
                               {'outputs':[{'width':640}]},tmp_path/'qa')
