"""Free public release checks; original private certification is not required."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import pytest

ROOT=Path(__file__).resolve().parents[1]
FILE_RELEASES=sorted((p.name for p in (ROOT/'motif-libraries').glob('file-v*')
                     if p.name[6:].isdigit() and (p/'entry.json').is_file()),
                    key=lambda name:int(name[6:]))


def test_seeds_install_per_account_without_cloud_or_reactivating_disabled_entries():
    base=ROOT/'.local/file-seed-tests'/uuid4().hex
    code="""import json,sys;sys.path.insert(0,'scenarios/file-management')
from management_web import default_config
from src.adapters.continuous_rsi import load_config,initialize
from src.motif_core.offline.experience_registry import ExperienceRegistry
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


@pytest.mark.parametrize('version', [name for name in FILE_RELEASES if int(name[6:])>=7])
def test_seed_release_contains_only_policies_and_sanitized_certification(version):
    release=ROOT/'motif-libraries'/version;manifest=json.loads((release/'entry.json').read_text())
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
    from src.motif_core.offline.experience_registry import ExperienceRegistry,durable
    monkeypatch.setattr(continuous_rsi,'ROOT',tmp_path)
    monkeypatch.setattr(experience_library,'sources',lambda:{'diagnostic':'current'})
    release=tmp_path/'motif-libraries/file-v1';name='a'*64
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


@pytest.mark.parametrize('version', ['file-v5', 'file-v7'])
def test_historical_seed_is_provenance_only_and_cannot_activate_on_new_code(version):
    import pytest
    from src.adapters.management_seed import validate_historical_certificate,validate_certificate
    from src.motif_core.offline.experience_registry import read,sha
    release=ROOT/'motif-libraries'/version;manifest=read(release/'entry.json')
    for entry in manifest['entries']:
        payload=release/entry['payload'];certificate=release/entry['certificate'];policy=read(payload)
        assert validate_historical_certificate(policy,certificate,sha(payload))['release']==version
        with pytest.raises(ValueError,match='runtime/catalog version changed'):
            validate_certificate(policy,certificate,sha(payload))


def test_current_seed_keeps_every_previous_graph_shape_and_admits_current_code(tmp_path):
    from src.adapters.management_seed import install,validate_certificate
    from src.adapters.experience_library import policy_current,sources
    from src.motif_core.offline.experience_registry import ExperienceRegistry,read,sha,digest
    def shapes(version):
        release=ROOT/'motif-libraries'/version;manifest=read(release/'entry.json')
        return {digest(read(release/e['payload'])['artifact']['nodes']) for e in manifest['entries']}
    previous=[name for name in FILE_RELEASES if 5<=int(name[6:])<=16]
    expected=shapes('file-v5')
    assert len(expected)==4
    assert all(shapes(name)==expected for name in previous)
    version=FILE_RELEASES[-1]
    assert len(shapes(version))==6
    assert expected < shapes(version)
    # Use the same latest-compatible installation path as a fresh account.
    # An absent or stale certification must fail instead of falling back to a
    # hard-coded historical version or accepting an empty active registry.
    cfg={'state_root':str(tmp_path/'account')}
    registry=ExperienceRegistry(Path(cfg['state_root'])/'registry')
    registry.publish(reason='free current seed diagnostic')
    install(cfg)
    active=[entry for entry in registry.load()['entries'] if entry['state']=='active']
    assert len(active)==6
    versions={read(registry.root/entry['certificate']['file'])['release'] for entry in active}
    assert versions=={'file-v16','file-v17'}
    release=ROOT/'motif-libraries'/version
    runtime=sources()
    for entry in active:
        policy=read(registry.root/entry['payload'])
        certificate=registry.root/entry['certificate']['file']
        assert entry['runtime_source']==runtime and policy_current(policy,runtime)
        assert validate_certificate(policy,certificate,entry['sha256'])['release']==read(certificate)['release']
    for entry in read(release/'entry.json')['entries']:
        payload=release/entry['payload']
        certificate=release/entry['certificate']
        assert validate_certificate(read(payload),certificate,sha(payload))['release']==read(certificate)['release']


def test_file_v17_preserves_old_bytes_and_adds_two_certified_pagination_flows():
    from src.motif_core.offline.experience_registry import read
    old=ROOT/'motif-libraries/file-v16';new=ROOT/'motif-libraries/file-v17'
    old_entries={e['policy_digest']:e for e in read(old/'entry.json')['entries']}
    new_entries={e['policy_digest']:e for e in read(new/'entry.json')['entries']}
    assert old_entries.keys() < new_entries.keys()
    for name,entry in old_entries.items():
        assert new_entries[name]==entry
        for field in ['payload','certificate']:
            assert (old/entry[field]).read_bytes()==(new/entry[field]).read_bytes()
    additions=[new_entries[name] for name in new_entries.keys()-old_entries.keys()]
    assert len(additions)==2
    for entry in additions:
        policy=read(new/entry['payload']);cert=read(new/entry['certificate'])
        assert policy['format']=='sss-operation-flow-v3'
        assert policy['artifact']['certification_contract']=='sss-operation-certification-v3'
        assert policy['artifact']['max_steps']==64
        assert cert['release']=='file-v17'


def test_existing_account_receives_new_flows_without_reactivating_disabled_seed(tmp_path):
    from src.adapters.management_seed import install,validate_certificate
    from src.adapters.experience_library import sources
    from src.motif_core.offline.experience_registry import ExperienceRegistry,read,sha
    cfg={'state_root':str(tmp_path/'account')};registry=ExperienceRegistry(Path(cfg['state_root'])/'registry')
    registry.publish(reason='free upgrade diagnostic')
    old=ROOT/'motif-libraries/file-v16'
    additions=[]
    for item in read(old/'entry.json')['entries']:
        payload=old/item['payload'];certificate=old/item['certificate']
        validate_certificate(read(payload),certificate,sha(payload))
        additions.append(registry.entry(item['kind'],payload,sources(),certificate))
    registry.publish(additions,reason='free previous account fixture')
    disabled=additions[0]['entry_id']
    registry.publish(disable=[disabled],reason='account disabled this seed')
    install(cfg);state=registry.load()
    assert len(state['entries'])==6
    assert len([e for e in state['entries'] if e['state']=='active'])==5
    assert next(e for e in state['entries'] if e['entry_id']==disabled)['state']=='disabled'
    assert not list((Path(cfg['state_root'])/'records').glob('*.json'))


@pytest.mark.parametrize('changed', ['execution', 'catalog'])
def test_current_seed_rejects_changed_execution_or_catalog(monkeypatch, changed):
    from src.adapters import experience_library
    from src.adapters.management_seed import validate_certificate
    from src.motif_core.offline.experience_registry import read, sha
    release = ROOT/'motif-libraries'/FILE_RELEASES[-1]
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
