import ctypes.util,importlib.util,json,os
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('session_audit_repair',ROOT/'scripts/repair-geneloop-session-events.py')
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)
HEADER={'type':'session','version':3,'id':'session-11111111-1111-4111-8111-111111111111','createdAt':1,'cwd':'/work'}
PROOF={'type':'geneloop/presented-proof','seq':2,'time':3,'data':{'callId':'call','files':[{'path':'outputs/a.txt','name':'outputs/code/a.txt','bytes':3,'sha256':'a'*64}]}}
def line(row):return (json.dumps(row)+'\n').encode()
def test_envelope_only_retains_header_proof_and_native_events():
    native={'type':'turn/end','seq':3,'time':4,'data':{'turn':1,'reason':{'kind':'completed'}}}
    original=[HEADER,PROOF,native];raw=b''.join(map(line,original))
    updated,count,header=repair.transform(raw,False);rows=[json.loads(x) for x in updated.splitlines()]
    assert count==1 and header==HEADER and rows[1].pop('ignorable') is True
    assert rows==original
    assert repair.transform(updated,False)[1]==0
    bad={**PROOF,'surfaceOp':'append'}
    with pytest.raises(ValueError,match='audit'):repair.transform(line(HEADER)+line(bad),False)
def test_unknown_events_are_never_silently_authorized():
    unknown={**PROOF,'type':'other/required-event'};raw=line(HEADER)+line(unknown)
    assert repair.transform(raw,False)[:2]==(raw,0)
@pytest.mark.skipif(not ctypes.util.find_library('zstd'),reason='system libzstd is required for Linux production log maintenance')
def test_all_zstd_frames_are_retained_and_only_changed_frame_is_recompressed():
    z=repair.Zstd();first=z.compress(line(HEADER));second=z.compress(line(PROOF));last=z.compress(line({'type':'turn/end','seq':3,'time':4,'data':{}}))
    output,count,header=repair.transform(first+second+last)
    frames=list(z.frames(output));assert len(frames)==3 and frames[0][0]==first and frames[2][0]==last
    assert count==1 and header==HEADER and json.loads(frames[1][1])['ignorable'] is True
@pytest.mark.skipif(os.name!='posix',reason='Linux production kernel session lock')
def test_active_session_lock_prevents_any_repair_or_backup(tmp_path,monkeypatch):
    import fcntl
    root=tmp_path/'sessions'/'--work--'/HEADER['id'];root.mkdir(parents=True)
    path=root/'session.v3.jsonl';raw=line(HEADER)+line(PROOF);path.write_bytes(raw)
    lock=root/'session.lock';lock.write_bytes(b'')
    monkeypatch.setattr(repair,'native_check',lambda *args:None)
    with lock.open('r+') as held:
        fcntl.flock(held.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):repair.repair(path,tmp_path/'backups',True,None,'node')
    assert path.read_bytes()==raw and not (tmp_path/'backups').exists()
    link=root/'linked.jsonl';link.symlink_to(path)
    with pytest.raises(ValueError,match='symlink'):repair.fixed(link)
