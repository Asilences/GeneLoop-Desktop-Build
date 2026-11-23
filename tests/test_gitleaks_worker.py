"""Official scanner reuse: isolation, exact cache keys, and fail-closed guard."""
import hashlib
import os
from pathlib import Path
import subprocess
import pytest

from src.adapters import rsi_gitleaks_worker as worker, rsi_text_privacy as text


def test_exact_reuse_lives_only_in_one_transaction(monkeypatch):
    monkeypatch.setenv('SSS_RSI_GITLEAKS_DEDUP','1')
    first=worker.scan_key(b'same',('verified-binary','rules-v1'))
    changed=worker.scan_key(b'same',('verified-binary','rules-v2'))
    with worker.gitleaks_transaction():
        assert not worker.already_checked(first)
        worker.remember_clear(first)
        with worker.gitleaks_transaction():
            assert worker.already_checked(first)
            assert not worker.already_checked(changed)
            assert not worker.already_checked(worker.scan_key(b'same ',('verified-binary','rules-v1')))
    with worker.gitleaks_transaction():assert not worker.already_checked(first)
    assert worker._CACHE.get() is None


def test_guard_still_runs_on_every_cached_logical_boundary(monkeypatch):
    monkeypatch.setenv('SSS_RSI_GITLEAKS_WORKER','/host/worker')
    monkeypatch.setenv('SSS_RSI_GITLEAKS_DEDUP','1')
    checked=[];scanned=[]
    def verify(_):
        checked.append(1)
        if len(checked)==3:raise worker.PrivacyToolError('privacy_scanner_changed')
        return Path('/host/worker'),{},('fixed-bytes',)
    monkeypatch.setattr(worker,'verified_worker',verify)
    monkeypatch.setattr(worker,'scan_with_worker',lambda payload,*_:scanned.append(payload))
    with worker.gitleaks_transaction():
        text._scan_gitleaks('exact original')
        text._scan_gitleaks('exact original')
        with pytest.raises(worker.PrivacyToolError):text._scan_gitleaks('exact original')
    assert len(checked)==3 and scanned==[b'exact original']


def test_credential_or_error_is_never_cached(monkeypatch):
    monkeypatch.setenv('SSS_RSI_GITLEAKS_WORKER','/host/worker')
    monkeypatch.setenv('SSS_RSI_GITLEAKS_DEDUP','1')
    monkeypatch.setattr(worker,'verified_worker',lambda _: (Path('/host/worker'),{},('fixed',)))
    calls=[]
    def reject(*_):
        calls.append(1)
        raise subprocess.CalledProcessError(1,['gitleaks'])
    monkeypatch.setattr(worker,'scan_with_worker',reject)
    with worker.gitleaks_transaction():
        for _ in range(2):
            with pytest.raises(subprocess.CalledProcessError):text._scan_gitleaks('credential')
    assert len(calls)==2


def test_forked_process_cannot_reuse_parent_transaction_result(monkeypatch):
    monkeypatch.setenv('SSS_RSI_GITLEAKS_DEDUP','1')
    monkeypatch.setattr(worker.os,'getpid',lambda:10)
    with worker.gitleaks_transaction():
        key=worker.scan_key(b'original',('fixed',));worker.remember_clear(key)
        monkeypatch.setattr(worker.os,'getpid',lambda:11)
        assert not worker.already_checked(worker.scan_key(b'original',('fixed',)))


def test_worker_asset_tampering_and_linked_path_fail_before_execution(monkeypatch,tmp_path):
    import json,platform
    binary=tmp_path/'worker';binary.write_bytes(b'pinned build')
    created=binary.stat()
    os.utime(binary,ns=(created.st_atime_ns,created.st_mtime_ns - 2_000_000_000))
    spec=tmp_path/'manifest.json';spec.write_text(json.dumps({'platforms':{platform.system()+'-x64':{
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}}}))
    monkeypatch.setattr(worker,'_MANIFEST',spec)
    worker.verified_worker(str(binary))
    binary.write_bytes(b'altered build')
    with pytest.raises(worker.PrivacyToolError):worker.verified_worker(str(binary))


def test_protocol_error_never_returns_a_clear_result():
    import io
    class Process:
        stdin=io.BytesIO()
        stdout=io.BytesIO(b'{"private":"unexpected response"}\n')
        def poll(self):return 0
    instance=object.__new__(worker.Worker)
    instance.owner=os.getpid();instance.identity=('test',);instance.ready=False
    instance.spec={'gitleaks':'8.30.0','rules_sha256':'fixed','regex_engine':'fixed'}
    instance.process=Process()
    with pytest.raises(subprocess.CalledProcessError) as error:instance.scan(b'original')
    assert error.value.returncode==2 and error.value.cmd==['gitleaks']


def test_timeout_kills_only_its_owned_transport(monkeypatch):
    class ImmediateTimeout:
        def wait(self,_):return False
        def set(self):pass
    class Thread:
        def __init__(self,**_):pass
        def start(self):pass
        def join(self,**_):pass
    monkeypatch.setattr(worker,'Event',ImmediateTimeout)
    monkeypatch.setattr(worker,'Thread',Thread)
    instance=object.__new__(worker.Worker);stopped=[]
    instance.stop=lambda:stopped.append(True)
    with pytest.raises(subprocess.TimeoutExpired):instance.scan(b'original')
    assert stopped==[True]


@pytest.mark.skipif(not os.environ.get('SSS_RSI_GITLEAKS_WORKER'),reason='requires pinned built local worker')
def test_actual_worker_keeps_no_finding_between_requests(monkeypatch):
    monkeypatch.setenv('SSS_RSI_GITLEAKS_DEDUP','0')
    token='ghp_'+'AbCdEf0123456789'*2+'AbCd'
    text._scan_gitleaks('Compute RMSE and n=128.')
    first=worker._WORKER.process.pid
    with pytest.raises(subprocess.CalledProcessError) as error:
        text._scan_gitleaks('token='+token)
    assert error.value.returncode==1
    text._scan_gitleaks('Compute RMSE and n=128.')
    assert worker._WORKER.process.pid==first
    worker.close_worker()
