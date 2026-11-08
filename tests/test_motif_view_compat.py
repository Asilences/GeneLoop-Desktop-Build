"""The display route cannot silently re-certify a changed Motif program."""
import hashlib
import json
from pathlib import Path
import pytest
from src.adapters.harless_rsi_bundle import load_product_bundle

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize('previous,release,scene', [
    ('paper-web-v84', 'paper-web-v85', 'paper-proofreading'),
    ('ppt-master-v82', 'ppt-master-v83', 'ppt'),
])
def test_read_only_display_compatibility_preserves_program_and_exact_code_guards(previous, release, scene):
    old, new = (ROOT / 'motif-libraries' / name for name in (previous, release))
    for name in ('library.json', 'online-manifest.json', 'task.json', 'tool-schemas.json', 'source-evidence.json'):
        assert (new / name).read_bytes() == (old / name).read_bytes(), name
    before, after = (read(path / 'certification.json')['code_locks'] for path in (old, new))
    assert {name for name, value in before.items() if after.get(name) != value} == {'scripts/harless_gateway.mjs'}
    assert set(after) - set(before) == {
        'scripts/reexport-motif-view-compat.py', 'scripts/harless_motif_view.ts',
        'src/adapters/motif_evidence_projection.ts', 'config/motif-evidence-v1.schema.json',
    }
    pairs = read(ROOT / 'config/rsi-privacy-code-compat.json')
    for name, value in after.items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert actual == value or pairs.get(name) == {'certified': value, 'current': actual}, name
    record = read(new / 'learning-report.json')['motif_view_compatibility']
    assert record['same_online_program'] and record['same_library_and_evidence'] and record['same_mcp_schema']
    assert record['model_requests'] == record['new_training_tasks'] == 0
    assert not record['quality_cost_promoted'] and not record['raw_traces_replayed']
    assert load_product_bundle(ROOT, new, scene)['runtime_mode'] == 'execute'
    # Old bytes remain archived; the new gateway must still invalidate them.
    with pytest.raises(ValueError, match='certified runtime code changed'):
        load_product_bundle(ROOT, old, scene)


@pytest.mark.parametrize('previous,release,scene', [
    ('paper-web-v85','paper-web-v86','paper-proofreading'),
    ('ppt-master-v83','ppt-master-v84','ppt'),
])
def test_runtime_catalog_preserves_original_program_and_locks_its_new_dependencies(previous,release,scene,monkeypatch):
    from src.adapters import harless_rsi_bundle as loader
    old,new=(ROOT/'motif-libraries'/name for name in (previous,release))
    for name in ('library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json'):
        assert (new/name).read_bytes()==(old/name).read_bytes(),name
    cert=read(new/'certification.json')
    assert {'src/adapters/harless_motif_catalog.ts','config/motif-evidence-v2.schema.json',
            'scripts/reexport-motif-catalog-compat.py'} <= set(cert['code_locks'])
    assert loader.load_product_bundle(ROOT,new,scene)['runtime_mode']=='execute'
    record=read(new/'learning-report.json')['runtime_catalog_compatibility']
    assert record['same_online_program'] and record['same_library_and_evidence']
    assert record['model_requests']==record['new_training_tasks']==0
    assert not record['quality_cost_promoted']
    real=loader.sha
    for changed in ('harless_motif_catalog.ts','motif-evidence-v2.schema.json'):
        monkeypatch.setattr(loader,'sha',lambda path: '0'*64 if path.name==changed else real(path))
        with pytest.raises(ValueError,match='certified runtime code changed'):
            loader.load_product_bundle(ROOT,new,scene)
    monkeypatch.setattr(loader,'sha',real)
