"""Admission persistence diagnostics; native trust is separately checked in TS."""
import json
import pytest
from src.adapters.capability_materials import CapabilityMaterials
from tests.test_capability_improvement import put


def test_materials_are_owner_scoped_append_only_and_recheck_original_evidence(tmp_path):
    pool=CapabilityMaterials(tmp_path/'pool','owner')
    lib=put(tmp_path/'library.json',{'diagnostic':'not a native certificate'})
    cert=put(tmp_path/'cert.json',{'diagnostic':True})
    original=(tmp_path/'library.json').read_bytes()
    kwargs=dict(backend='source_program',library=lib,refs=[cert],acquisition_key='one',opportunity='gap-one')
    pool.register(**kwargs);pool.register(**kwargs)
    assert len(pool.records())==1 and (tmp_path/'library.json').read_bytes()==original
    assert CapabilityMaterials(tmp_path/'pool','other').records()==[]
    (tmp_path/'cert.json').write_text('{}')
    with pytest.raises(ValueError,match='evidence_changed'):pool.records()


def test_material_record_tampering_and_unsupported_backend_fail(tmp_path):
    pool=CapabilityMaterials(tmp_path/'pool','owner');ref=put(tmp_path/'source.json',{})
    with pytest.raises(ValueError,match='native_evidence_required'):
        pool.register(backend='unknown_backend',library=ref,refs=[ref],acquisition_key='one',opportunity='gap')
    pool.register(backend='source_program',library=ref,refs=[ref],acquisition_key='one',opportunity='gap')
    path=next(pool.directory.glob('*.json'));row=json.loads(path.read_text());row['opportunity']='other';path.write_text(json.dumps(row))
    with pytest.raises(ValueError,match='record_changed'):pool.records()
