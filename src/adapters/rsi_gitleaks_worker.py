"""Pinned official Gitleaks library transport and transaction-local scan reuse."""
import atexit
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
from threading import Event, RLock, Thread
from time import monotonic

from .privacy_diagnostics import privacy_stage
from .rsi_privacy_tools import PrivacyToolError, _fingerprint, _verify_binary, gitleaks_asset

_MANIFEST = Path(__file__).resolve().parents[2]/'config/rsi-gitleaks-worker-tools.json'
_CACHE = ContextVar('gitleaks_transaction', default=None)
_LOCK = RLock()
_WORKER = None
MAX_INPUT = 512*1024*1024


@contextmanager
def gitleaks_transaction():
    mode = os.environ.get('SSS_RSI_GITLEAKS_DEDUP', '0')
    if mode not in ('0', '1'):
        raise PrivacyToolError('privacy_scanner_configuration_invalid')
    if mode == '0' or _CACHE.get() is not None:
        yield
        return
    token = _CACHE.set(set())
    try:
        yield
    finally:
        _CACHE.reset(token)


def scan_key(payload, fingerprint):
    return os.getpid(), fingerprint, hashlib.sha256(payload).digest()


def already_checked(key):
    cache = _CACHE.get()
    if cache is not None and key in cache:
        with privacy_stage('gitleaks_exact_reuse'):
            pass
        return True
    return False


def remember_clear(key):
    cache = _CACHE.get()
    if cache is not None and len(cache) < 64:
        cache.add(key)


def verified_worker(path):
    import platform
    spec = json.loads(_MANIFEST.read_text(encoding='utf-8'))
    # Uses the same architecture/platform admission as the existing CLI guard.
    gitleaks_asset()
    expected = spec['platforms'].get(platform.system()+'-x64')
    if not expected:
        raise PrivacyToolError('privacy_tool_platform_unverified')
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.absolute() != candidate.resolve():
        raise PrivacyToolError('local_gitleaks_worker_required')
    path_info = candidate.lstat()
    before = _fingerprint(path_info)
    _verify_binary(candidate, expected['binary_sha256'], path_info)
    if before != _fingerprint(candidate.lstat()):
        raise PrivacyToolError('privacy_scanner_changed')
    return candidate, spec, (str(candidate), expected['binary_sha256'], before)


class Worker:
    def __init__(self, path, spec, identity):
        self.owner = os.getpid()
        self.identity = identity
        self.spec = spec
        env = {k:os.environ[k] for k in ('SYSTEMROOT','WINDIR') if k in os.environ}
        self.process = subprocess.Popen([str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0, env=env, close_fds=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.ready = False

    def stop(self):
        process = self.process
        if self.owner == os.getpid() and process.poll() is None:
            process.kill()
            try:process.wait(timeout=1)
            except subprocess.TimeoutExpired:pass
        for stream in (process.stdin, process.stdout):
            try:stream.close()
            except OSError:pass

    def scan(self, payload, timeout=8):
        if len(payload) > MAX_INPUT:
            raise PrivacyToolError('privacy_scanner_input_limit')
        done, result = Event(), {}
        def exchange():
            try:
                if not self.ready:
                    header = bytearray()
                    while len(header) <= 4096:
                        char = self.process.stdout.read(1)
                        if not char:raise ValueError()
                        header.extend(char)
                        if char == b'\n':break
                    hello = json.loads(header)
                    expected = {key:self.spec[key] for key in ('gitleaks','rules_sha256','regex_engine')}
                    expected['format'] = 'geneloop.gitleaks-worker/v1'
                    if hello != expected:raise ValueError()
                    self.ready = True
                for part in (struct.pack('!Q',len(payload)), payload):
                    view = memoryview(part)
                    while view:
                        size = self.process.stdin.write(view)
                        if not size:raise OSError()
                        view = view[size:]
                status = self.process.stdout.read(1)
                if status not in (b'\0', b'\1'):raise ValueError()
                result['status'] = status
            except Exception:
                result['failed'] = True
            finally:
                done.set()
        thread = Thread(target=exchange, daemon=True, name='gitleaks-local-transport')
        thread.start()
        if not done.wait(timeout):
            self.stop();thread.join(timeout=1)
            raise subprocess.TimeoutExpired('gitleaks', 8)
        if result.get('failed'):
            self.stop()
            raise subprocess.CalledProcessError(2, ['gitleaks'])
        if result['status'] == b'\1':
            raise subprocess.CalledProcessError(1, ['gitleaks'])


def scan_with_worker(payload, path, spec, identity):
    global _WORKER
    started = monotonic()
    if not _LOCK.acquire(timeout=8):
        raise subprocess.TimeoutExpired('gitleaks',8)
    try:
        remaining = 8-(monotonic()-started)
        if remaining <= 0:
            raise subprocess.TimeoutExpired('gitleaks',8)
        if _WORKER is not None and (_WORKER.owner != os.getpid() or _WORKER.identity != identity or _WORKER.process.poll() is not None):
            _WORKER.stop();_WORKER = None
        if _WORKER is None:
            _WORKER = Worker(path, spec, identity)
        with privacy_stage('gitleaks_library'):
            _WORKER.scan(payload,timeout=remaining)
    finally:
        _LOCK.release()


def close_worker():
    global _WORKER
    with _LOCK:
        if _WORKER is not None:
            _WORKER.stop();_WORKER = None


atexit.register(close_worker)
