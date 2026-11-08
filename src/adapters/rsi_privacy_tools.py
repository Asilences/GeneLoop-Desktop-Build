"""Pinned local tool provenance; no downloads or caller-supplied trust roots."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import stat
import os

TOOLS = json.loads((Path(__file__).resolve().parents[2] / 'config/rsi-privacy-tools.json').read_text(encoding='utf-8'))


class PrivacyToolError(ValueError):
    """Fixed local reason, without a path, finding or upstream exception."""

    def __init__(self,reason):
        self.reason=reason
        super().__init__(reason)


def privacy_worker_environment():
    return {**{name:os.environ[name] for name in TOOLS['worker_environment'] if name in os.environ},'PYTHONUTF8':'1'}


def gitleaks_asset():
    machine = platform.machine().lower()
    if machine not in ('x86_64', 'amd64'):
        raise PrivacyToolError('privacy_tool_platform_unverified')
    try:
        return TOOLS['gitleaks']['platforms'][platform.system() + '-x64']
    except KeyError:
        raise PrivacyToolError('privacy_tool_platform_unverified') from None


def verify_nlp_versions():
    for package, expected in TOOLS['packages'].items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            raise PrivacyToolError('privacy_dependency_unavailable') from None
        if actual != expected:
            raise PrivacyToolError('privacy_dependency_version_mismatch')


def _fingerprint(info):
    # Windows path stat infers executable bits from .exe; fd stat does not.
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _verify_binary(path, expected, fingerprint):
    with Path(path).open('rb') as stream:
        before = os.fstat(stream.fileno())
        if _fingerprint(before) != fingerprint or not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 64 * 1024 * 1024:
            raise PrivacyToolError('privacy_scanner_changed')
        digest = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
        if _fingerprint(os.fstat(stream.fileno())) != fingerprint or digest.hexdigest() != expected:
            raise PrivacyToolError('privacy_scanner_unverified')


def verified_gitleaks(path):
    """Check actual asset bytes before every scanner invocation.

    This detects configuration drift/replacement, not a hostile host controlling
    both the trusted repository and its interpreter. File timestamps alone are
    not a portable integrity cache key. Never execute to discover whether an
    unverified binary claims the expected version.
    """
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.absolute() != candidate.resolve():
        raise PrivacyToolError('local_gitleaks_required')
    try:
        info = candidate.lstat()
    except OSError:
        raise PrivacyToolError('local_gitleaks_required') from None
    if not stat.S_ISREG(info.st_mode):
        raise PrivacyToolError('local_gitleaks_required')
    _verify_binary(str(candidate), gitleaks_asset()['binary_sha256'], _fingerprint(info))
    if _fingerprint(candidate.lstat()) != _fingerprint(info):
        raise PrivacyToolError('privacy_scanner_changed')
    return candidate
