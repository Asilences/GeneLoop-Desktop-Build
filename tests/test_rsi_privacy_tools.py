"""Trust drift controls; actual upstream scanner execution stays in privacy E2E."""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from src.adapters import rsi_privacy_tools as tools
from src.adapters.rsi_text_privacy import _scan


@pytest.mark.parametrize('kind', ['credential', 'processing'])
def test_spacy_memory_zone_cleans_after_rejection_and_next_chinese_input(kind):
    spacy=pytest.importorskip('spacy')
    nlp=spacy.blank('zh')
    marker='synthetic_privacy_exception_cleanup_marker'
    assert marker not in nlp.vocab.strings
    error=(subprocess.CalledProcessError(1,['synthetic-privacy-refusal'])
           if kind=='credential' else ValueError('synthetic-processing-failure'))
    with pytest.raises(type(error)):
        with nlp.memory_zone():
            nlp.vocab.strings.add(marker)
            nlp('合成文本内存清理检查')
            raise error
    # spaCy3.8.7 skipped cleanup when an exception crossed the zone. The next
    # request could see dangling vocabulary entries, even after safe rejection.
    assert marker not in nlp.vocab.strings
    with nlp.memory_zone():
        assert nlp('继续处理下一条中文任务').text=='继续处理下一条中文任务'


def test_unverified_executable_is_rejected_before_it_can_run(tmp_path, monkeypatch):
    target=tmp_path/'scanner'
    target.write_bytes(b'unissued-test-executable')
    target.chmod(0o700)
    monkeypatch.delenv('SSS_RSI_GITLEAKS_WORKER', raising=False)
    monkeypatch.setenv('SSS_RSI_GITLEAKS',str(target))
    executed=[]
    monkeypatch.setattr('subprocess.run',lambda *args,**kwargs:executed.append(True))
    with pytest.raises(ValueError,match='privacy_scanner_unverified'):
        _scan('synthetic plain text')
    assert executed==[]


def test_binary_verification_detects_same_size_content_change(tmp_path, monkeypatch):
    target=tmp_path/'scanner';target.write_bytes(b'approved-fixture')
    created=target.stat()
    os.utime(target,ns=(created.st_atime_ns,created.st_mtime_ns - 2_000_000_000))
    expected=hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.setattr(tools,'gitleaks_asset',lambda:{'binary_sha256':expected})
    assert tools.verified_gitleaks(target)==target
    before=target.stat()
    target.write_bytes(b'changed--fixture')
    # Keep size/mtime to catch caches relying on portable file metadata alone.
    assert target.stat().st_size==before.st_size
    os.utime(target,ns=(before.st_atime_ns,before.st_mtime_ns))
    with pytest.raises(ValueError,match='privacy_scanner_unverified'):
        tools.verified_gitleaks(target)


def test_unverified_platform_and_dependency_drift_are_rejected(monkeypatch):
    monkeypatch.setattr(tools.platform,'machine',lambda:'unsupported-test-architecture')
    with pytest.raises(ValueError,match='privacy_tool_platform_unverified'):
        tools.gitleaks_asset()
    monkeypatch.setattr(tools.importlib.metadata,'version',lambda name:'unexpected-version')
    with pytest.raises(ValueError,match='privacy_dependency_version_mismatch'):
        tools.verify_nlp_versions()


@pytest.mark.parametrize('machine,arch', [('arm64','arm64'), ('aarch64','arm64'), ('x86_64','x64')])
def test_macos_scanner_pins_match_the_native_architecture(monkeypatch, machine, arch):
    monkeypatch.setattr(tools.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(tools.platform, 'machine', lambda: machine)
    asset = tools.gitleaks_asset()
    assert asset['asset'] == f'darwin_{arch}.tar.gz'
    assert asset['binary'] == 'gitleaks'
    other = 'x64' if arch == 'arm64' else 'arm64'
    assert asset['binary_sha256'] != tools.TOOLS['gitleaks']['platforms'][f'Darwin-{other}']['binary_sha256']

@pytest.mark.parametrize(('machine', 'asset'), [
    ('arm64', 'darwin_arm64.tar.gz'),
    ('x86_64', 'darwin_x64.tar.gz'),
])
def test_macos_scanner_uses_the_approved_asset_for_its_architecture(monkeypatch, machine, asset):
    monkeypatch.setattr(tools.platform, 'machine', lambda: machine)
    monkeypatch.setattr(tools.platform, 'system', lambda: 'Darwin')
    assert tools.gitleaks_asset()['asset'] == asset


def test_tool_configuration_matches_pinned_dependency_file():
    root=Path(__file__).resolve().parents[1]
    requirements=(root/'requirements-rsi-privacy.txt').read_text()
    for name,version in tools.TOOLS['packages'].items():
        assert f'{name}=={version}' in requirements or f'{name.replace("-","_")}-{version}-py3-none-any.whl#sha256=' in requirements


@pytest.mark.skipif(not os.environ.get('SSS_RSI_GITLEAKS'),reason='requires actual pinned local Gitleaks')
def test_actual_installed_scanner_matches_the_trusted_asset(monkeypatch):
    monkeypatch.delenv('SSS_RSI_GITLEAKS_WORKER', raising=False)
    target=tools.verified_gitleaks(os.environ['SSS_RSI_GITLEAKS'])
    assert target.is_file()
    _scan('Compute RMSE; keep 24 fps and mean ± SD.')
