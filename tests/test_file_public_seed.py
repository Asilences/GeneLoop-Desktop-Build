"""Free public release checks; original private certification is not required."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import pytest

ROOT=Path(__file__).resolve().parents[1]
FILE_RELEASE = ROOT / 'motif-libraries/file-management'


def test_seeds_install_per_account_without_cloud_or_reactivating_disabled_entries():
    base=ROOT/'.local/file-seed-tests'/uuid4().hex
    code="""import json,sys;sys.path.insert(0,'scenarios/file-management')
from management_web import default_config
from src.adapters.continuous_rsi import load_config,initialize
from src.motif_core.reuse.experience_registry import ExperienceRegistry
p=default_config(True);cfg=load_config(p);r=ExperienceRegistry(__import__('pathlib').Path(cfg['state_root'])/'registry')
state=r.load();assert len([e for e in state['entries'] if e['state']=='active'])>=1
entry=state['entries'][0]['entry_id'];r.publish(disable=[entry],reason='free disable diagnostic')
initialize(cfg);state=r.load();assert next(e for e in state['entries'] if e['entry_id']==entry)['state']=='disabled'
assert not list((__import__('pathlib').Path(cfg['state_root'])/'records').glob('*.json'))
print(json.dumps({'state':cfg['state_root'],'entries':len(state['entries']),'paid_calls':0}))"""
    results=[]
    for account in ['one','two']:
        env={**os.environ,'HARLESS_MANAGEMENT_PRIVATE_ROOT':str(base/account),'DEEPSEEK_API_KEY':''}
        results.append(json.loads(subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env=env,text=True)))
    assert results[0]['state']!=results[1]['state']
    assert all(row['paid_calls']==0 for row in results)


def test_seed_release_contains_only_policies_and_sanitized_certification():
    release = FILE_RELEASE
    manifest=json.loads((release/'entry.json').read_text())
    assert manifest['raw_private_evidence_published'] is False
    for name in manifest['files']:
        raw=(release/name).read_text()
        assert '/Users/' not in raw and '/home/' not in raw and 'record_file' not in raw
        assert name.startswith(('policies/','certificates/'))
    for entry in manifest['entries']:
        cert=json.loads((release/entry['certificate']).read_text())
        assert cert['grants_execution'] is False and cert['holdout_used'] is False
        assert all(w['accepted'] and not w['repairs'] and w['observed_usage_complete'] for w in cert['witnesses'])


def test_incompatible_seed_is_retained_once_and_allows_ordinary_fallback(tmp_path,monkeypatch):
    from src.adapters import management_seed as seed,continuous_rsi,experience_library
    from src.motif_core.reuse.experience_registry import ExperienceRegistry,durable
    monkeypatch.setattr(continuous_rsi,'ROOT',tmp_path)
    monkeypatch.setattr(experience_library,'sources',lambda:{'diagnostic':'current'})
    release=tmp_path/'motif-libraries/file-management';name='a'*64
    durable(release/'policies'/f'{name}.json',{})
    durable(release/'certificates'/f'{name}.json',{})
    durable(release/'entry.json',{'runtime_source':{'diagnostic':'current'},'entries':[{'policy_digest':name,'payload':f'policies/{name}.json','certificate':f'certificates/{name}.json'}],'files':{f'policies/{name}.json':'test',f'certificates/{name}.json':'test'}})
    def reject(*_):raise ValueError('diagnostic catalog mismatch')
    monkeypatch.setattr(seed,'validate_certificate',reject)
    cfg={'state_root':str(tmp_path/'account')};ExperienceRegistry(Path(cfg['state_root'])/'registry').publish(reason='free empty fixture')
    assert seed.install(cfg)['entries']==[]
    assert seed.install(cfg)['entries']==[]
    receipts=list((Path(cfg['state_root'])/'seed-rejections').glob('*.json'))
    assert len(receipts)==1 and json.loads(receipts[0].read_text())['activated'] is False


def test_fresh_account_admits_only_current_independently_certified_seeds(tmp_path):
    from src.adapters.management_seed import install, validate_certificate
    from src.adapters.experience_library import policy_current, sources
    from src.motif_core.reuse.experience_registry import ExperienceRegistry, read

    cfg = {'state_root': str(tmp_path/'account')}
    registry = ExperienceRegistry(Path(cfg['state_root'])/'registry')
    registry.publish(reason='fresh account')
    install(cfg)
    active = [entry for entry in registry.load()['entries'] if entry['state'] == 'active']
    manifest = read(FILE_RELEASE/'entry.json')
    assert manifest['entries']
    assert not any(FILE_RELEASE.parent.glob('file-v*'))
    assert {entry['entry_id'] for entry in active} == {entry['policy_digest'] for entry in manifest['entries']}
    for entry in active:
        policy = read(registry.root/entry['payload'])
        certificate = registry.root/entry['certificate']['file']
        assert entry['runtime_source'] == sources() and policy_current(policy, sources())
        assert validate_certificate(policy, certificate, entry['sha256'])['release'] == manifest['release']


@pytest.mark.parametrize('changed', ['execution', 'catalog'])
def test_current_seed_rejects_changed_execution_or_catalog(monkeypatch, changed):
    from src.adapters import experience_library
    from src.adapters.management_seed import validate_certificate
    from src.motif_core.reuse.experience_registry import read, sha
    release = FILE_RELEASE
    item = read(release/'entry.json')['entries'][0]
    payload, certificate = release/item['payload'], release/item['certificate']
    policy = read(payload)
    validate_certificate(policy, certificate, sha(payload))
    if changed == 'execution':
        monkeypatch.setattr(experience_library, 'current_execution_version', lambda: 'changed')
    else:
        monkeypatch.setattr(experience_library, 'current_contracts', lambda _runtime: {})
    with pytest.raises(ValueError, match='runtime/catalog version changed'):
        validate_certificate(policy, certificate, sha(payload))
