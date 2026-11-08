"""Candidate boundary controls; real inference is a separate server receipt."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from src.adapters import geneloop_privacy as privacy
from src.adapters import rsi_privacy_candidates as candidates
from src.adapters import rsi_text_privacy as text_privacy


def test_unconfigured_default_does_not_load_candidate_dependencies(monkeypatch):
    monkeypatch.delenv('SSS_RSI_PRIVACY_CANDIDATE_CONFIG', raising=False)
    monkeypatch.delenv('SSS_RSI_PRIVACY_CANDIDATE_SHA256', raising=False)
    monkeypatch.setattr(candidates, 'OfficialTools', lambda *a: pytest.fail('default loaded a candidate'))
    monkeypatch.setattr(privacy, '_scan', lambda text: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda text, **kwargs: text)
    source = {'text': 'Compare linear regression with random forests.'}
    assert privacy.learning_view(source) == source


def test_task_payload_cannot_select_a_candidate_backend(monkeypatch):
    monkeypatch.delenv('SSS_RSI_PRIVACY_CANDIDATE_CONFIG', raising=False)
    monkeypatch.delenv('SSS_RSI_PRIVACY_CANDIDATE_SHA256', raising=False)
    monkeypatch.setattr(candidates,'OfficialTools',lambda *a:pytest.fail('payload selected a candidate'))
    monkeypatch.setattr(privacy,'_scan',lambda text:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda text,**kwargs:text)
    privacy.learning_view({'text':'Explain regression','SSS_RSI_PRIVACY_CANDIDATE_CONFIG':'synthetic-value'})
    assert candidates.active_candidate() is None


def test_worker_forwards_candidate_configuration_without_model_credentials(monkeypatch):
    from src.adapters.rsi_privacy_tools import privacy_worker_environment
    monkeypatch.setenv('SSS_RSI_PRIVACY_CANDIDATE_CONFIG','/private/config.json')
    monkeypatch.setenv('SSS_RSI_PRIVACY_CANDIDATE_SHA256','a'*64)
    monkeypatch.setenv('KOURI_API_KEY','synthetic-not-a-real-credential')
    env=privacy_worker_environment()
    assert env['SSS_RSI_PRIVACY_CANDIDATE_CONFIG']=='/private/config.json'
    assert env['SSS_RSI_PRIVACY_CANDIDATE_SHA256']=='a'*64
    assert 'KOURI_API_KEY' not in env


@pytest.mark.parametrize('name', ['SSS_RSI_PRIVACY_CANDIDATE_CONFIG', 'SSS_RSI_PRIVACY_CANDIDATE_SHA256'])
def test_partial_host_configuration_fails_closed(monkeypatch, name):
    for key in ('SSS_RSI_PRIVACY_CANDIDATE_CONFIG', 'SSS_RSI_PRIVACY_CANDIDATE_SHA256'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(name, 'untrusted-private-path-or-digest')
    with pytest.raises(privacy.PrivacyRejected, match='^geneloop_privacy_rejected$'):
        privacy.learning_view({'text': 'original private material'})
    assert candidates.active_candidate() is None


def test_configuration_digest_and_duplicate_keys_are_checked_before_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, 'OfficialTools', lambda *a: pytest.fail('unverified configuration loaded'))
    path = tmp_path / 'candidate.json'
    path.write_text('{"text_mode":"r4","text_mode":"r4+opf"}')
    with pytest.raises(ValueError, match='digest_mismatch'):
        candidates._configured(str(path), '0' * 64)
    with pytest.raises(ValueError, match='ambiguous_configuration'):
        candidates._configured(str(path), hashlib.sha256(path.read_bytes()).hexdigest())


def test_same_version_modified_package_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / 'opf/_api.py'
    source.parent.mkdir()
    source.write_text('modified source')
    monkeypatch.setattr(candidates.importlib.metadata, 'distribution',
                        lambda name: SimpleNamespace(version='0.1.0', locate_file=lambda name: tmp_path / name))
    with pytest.raises(ValueError, match='package_bytes_mismatch'):
        candidates._verify_distribution('opf', {'version':'0.1.0', 'files':{'opf/_api.py':'0' * 64}})


def test_scope_resets_on_failure_and_does_not_cross_threads():
    a, b = object(), object()
    def run(backend):
        assert candidates.active_candidate() is None
        with candidates.candidate_context(backend):
            with candidates.candidate_context(from_environment=True):
                assert candidates.active_candidate() is backend
        assert candidates.active_candidate() is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, (a, b)))
    with pytest.raises(RuntimeError):
        with candidates.candidate_context(a):
            raise RuntimeError('synthetic failure')
    assert candidates.active_candidate() is None


def test_official_spans_require_original_unicode_coordinates():
    backend = object.__new__(candidates.OfficialTools)
    backend.lock = candidates.RLock()
    backend.spec = {'opf': {'label_map': {'private_person':'PERSON'}, 'excluded_labels': {}}}
    backend.detector = SimpleNamespace(redact=lambda text: SimpleNamespace(
        warning=None, text=text, detected_spans=[SimpleNamespace(start=0, end=2, text='changed', label='private_person')]))
    with pytest.raises(ValueError, match='invalid_output_span'):
        backend.native_findings('张三')
    backend.detector.redact = lambda text: SimpleNamespace(warning='roundtrip mismatch', text=text, detected_spans=[])
    with pytest.raises(ValueError, match='roundtrip_mismatch'):
        backend.native_findings('张三')


def test_policy_does_not_silently_enable_private_dates():
    backend = object.__new__(candidates.OfficialTools)
    backend.spec = json.loads(candidates._MANIFEST.read_text(encoding='utf-8'))
    backend.native_findings = lambda text: [{'start':0,'end':2,'label':'private_person'},
                                          {'start':3,'end':13,'label':'private_date'}]
    assert backend.findings('张三 2000-01-01') == [{'start':0,'end':2,'label':'PERSON'}]


def test_model_secret_rejects_admission_without_changing_native_span_measurement():
    backend=object.__new__(candidates.OfficialTools)
    backend.spec=json.loads(candidates._MANIFEST.read_text(encoding='utf-8'))
    backend.native_findings=lambda text:[{'start':0,'end':4,'label':'secret'}]
    assert backend.findings('demo')==[{'start':0,'end':4,'label':'CREDENTIAL'}]
    with candidates.candidate_context(backend,admission=True):
        with pytest.raises(subprocess.CalledProcessError):
            backend.findings('demo')
    assert backend.findings('demo')==[{'start':0,'end':4,'label':'CREDENTIAL'}]


def test_additional_scanner_rejection_uses_the_public_contract(monkeypatch):
    monkeypatch.setattr(text_privacy, '_scan_gitleaks', lambda text: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda text, **kwargs: text)
    class Backend:
        def scan(self, text):
            raise subprocess.CalledProcessError(1, ['credsweeper'])
    with candidates.candidate_context(Backend()):
        with pytest.raises(privacy.PrivacyRejected) as error:
            privacy.learning_view({'text': 'synthetic credential content'})
    assert error.value.reason == 'credential_detected'


def test_candidate_failure_never_returns_an_unsanitized_success(monkeypatch):
    monkeypatch.setattr(text_privacy, '_scan_gitleaks', lambda text: None)
    class Backend:
        def scan(self, text):
            raise RuntimeError('/private/raw-detail')
    with candidates.candidate_context(Backend()):
        with pytest.raises(privacy.PrivacyRejected) as error:
            privacy.learning_view({'text': 'original content'})
    assert str(error.value) == 'geneloop_privacy_rejected'
    assert '/private' not in str(error.value)
