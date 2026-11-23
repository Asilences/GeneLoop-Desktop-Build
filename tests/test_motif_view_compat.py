"""The display route cannot silently re-certify a changed Motif program."""
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize('scene',['ppt','paper-proofreading'])
def test_current_selected_release_keeps_display_locks_and_rejects_tampering(scene,monkeypatch):
    from src.adapters.web.learning import harless_rsi_bundle as loader
    selected=next(row['rsi']['runtime_bundle'] for row in read(ROOT/'config/harless-scenes.json')['scenes'] if row['id']==scene)
    current=ROOT/selected
    locks=read(current/'certification.json')['code_locks']
    assert {'src/adapters/web/learning/harless_motif_catalog.ts','src/adapters/motif_evidence_projection.ts',
            'config/motif-evidence-v1.schema.json','config/motif-evidence-v2.schema.json'}<=set(locks)
    assert loader.load_product_bundle(ROOT,current,scene)['runtime_mode']=='execute'
    actual=loader.sha
    for changed in ('harless_motif_catalog.ts','motif-evidence-v2.schema.json'):
        monkeypatch.setattr(loader,'sha',lambda path:'0'*64 if path.name==changed else actual(path))
        with pytest.raises(ValueError,match='certified runtime code changed'):
            loader.load_product_bundle(ROOT,current,scene)
