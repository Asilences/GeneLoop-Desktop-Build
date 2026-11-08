"""Opt-in local official detectors; frozen R4 remains the unconfigured default.

This module provides adapters, not another NER or secret detection algorithm.
Only trusted host configuration can activate it; input JSON cannot select tools.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
from threading import RLock

_ACTIVE = ContextVar('geneloop_privacy_candidate', default=None)
_ADMISSION = ContextVar('geneloop_privacy_candidate_admission', default=False)
_MANIFEST = Path(__file__).resolve().parents[2] / 'config/rsi-privacy-candidate-tools.json'


def active_candidate():
    return _ACTIVE.get()


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _verify_distribution(name, spec):
    distribution = importlib.metadata.distribution(name)
    if distribution.version != spec['version']:
        raise ValueError('candidate_package_version_mismatch')
    for name, digest in spec['files'].items():
        path = Path(distribution.locate_file(name))
        if not path.is_file() or _sha(path) != digest:
            raise ValueError('candidate_package_bytes_mismatch')


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('candidate_ambiguous_configuration')
        result[key] = value
    return result


class OfficialTools:
    def __init__(self, settings):
        required = {'format','text_mode','credential_mode','checkpoint','tokenizer_cache','threads'}
        if (not isinstance(settings, dict) or set(settings) != required
                or settings['format'] != 'geneloop.privacy-candidate/v1'
                or settings['text_mode'] not in ('r4', 'r4+opf')
                or settings['credential_mode'] not in ('gitleaks', 'gitleaks+credsweeper')
                or type(settings['threads']) is not int or not 1 <= settings['threads'] <= 4):
            raise ValueError('candidate_invalid_configuration')
        self.text_mode = settings['text_mode']
        self.credential_mode = settings['credential_mode']
        self.spec = json.loads(_MANIFEST.read_text(encoding='utf-8'), object_pairs_hook=_strict_object)
        self.lock = RLock()
        self.detector = None
        self.scanner = None
        if self.text_mode == 'r4+opf':
            self._load_opf(settings)
        if self.credential_mode == 'gitleaks+credsweeper':
            self._load_credsweeper(settings)

    def _load_opf(self, settings):
        spec = self.spec['opf']
        _verify_distribution('opf', spec)
        for name in ('torch', 'tiktoken'):
            if importlib.metadata.version(name) != spec[name]:
                raise ValueError('candidate_dependency_version_mismatch')
        checkpoint = Path(settings['checkpoint'])
        cache = Path(settings['tokenizer_cache'])
        if not checkpoint.is_absolute() or not cache.is_absolute():
            raise ValueError('candidate_absolute_model_paths_required')
        for name, expected in spec['model_files'].items():
            path = checkpoint / name
            if not path.is_file() or path.stat().st_size != expected['bytes']:
                raise ValueError('candidate_model_bytes_mismatch')
            if 'sha256' in expected:
                valid = _sha(path) == expected['sha256']
            else:
                data = path.read_bytes()
                valid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == expected['git_blob']
            if not valid:
                raise ValueError('candidate_model_bytes_mismatch')
        for name, digest in spec['tokenizer_cache'].items():
            if not (cache / name).is_file() or _sha(cache / name) != digest:
                raise ValueError('candidate_tokenizer_cache_required')
        if os.environ.get('OPF_EXPERTS_PER_TOKEN') or any(
                os.environ.get(key, '0').lower() not in ('0', 'false', '') for key in
                ('OPF_TORCH_COMPILE', 'OPF_MOE_TRITON', 'OPF_ATTN_LOW_PRECISION', 'OPF_ALLOW_TF32')):
            raise ValueError('candidate_runtime_override_not_allowed')
        os.environ['TIKTOKEN_CACHE_DIR'] = str(cache)
        from opf import OPF
        import torch
        torch.set_num_threads(settings['threads'])
        self.detector = OPF(model=checkpoint, device='cpu', context_window_length=4096,
                            decode_mode='viterbi', trim_whitespace=True,
                            discard_overlapping_predicted_spans=False)
        self.detector.get_runtime()

    def _load_credsweeper(self, settings):
        spec = self.spec['credsweeper']
        _verify_distribution('credsweeper', spec)
        if importlib.metadata.version('onnxruntime') != spec['onnxruntime']:
            raise ValueError('candidate_dependency_version_mismatch')
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from credsweeper import CredSweeper
        self.scanner = CredSweeper(pool_count=1, stdout=False, color=False, hashed=True,
                                  ml_threads_limit=1, ml_providers='CPUExecutionProvider', log_level='CRITICAL')

    def native_findings(self, text):
        """Return official model character spans, including policy-excluded labels."""
        if self.detector is None:
            return []
        with self.lock:
            result = self.detector.redact(text)
            if result.warning or result.text != text:
                raise ValueError('candidate_tokenizer_roundtrip_mismatch')
            findings = []
            for span in result.detected_spans:
                if (type(span.start) is not int or type(span.end) is not int
                        or not 0 <= span.start < span.end <= len(text)
                        or text[span.start:span.end] != span.text
                        or span.label not in set(self.spec['opf']['label_map']) | set(self.spec['opf']['excluded_labels'])):
                    raise ValueError('candidate_invalid_output_span')
                findings.append({'start': span.start, 'end': span.end, 'label': span.label})
            return findings

    def findings(self, text):
        mapping = self.spec['opf']['label_map']
        spans = self.native_findings(text)
        if _ADMISSION.get() and any(span['label'] == 'secret' for span in spans):
            # Native text masking can be measured separately. Learning admission
            # keeps the existing policy: a detected credential rejects the packet.
            raise subprocess.CalledProcessError(1, ['opf-secret'])
        return [dict(span, label=mapping[span['label']]) for span in spans if span['label'] in mapping]

    def credential_count(self, text):
        if self.scanner is None:
            return 0
        from credsweeper.file_handler.string_content_provider import StringContentProvider
        with self.lock:
            provider = StringContentProvider(lines=text.splitlines(), file_path='memory.txt', file_type='.txt')
            self.scanner.credential_manager.clear_credentials()
            try:
                self.scanner.scan([provider], None)
                self.scanner.post_processing(None)
                return self.scanner.credential_manager.len_credentials()
            finally:
                self.scanner.credential_manager.clear_credentials()
                provider.free()

    def scan(self, text):
        if self.credential_count(text):
            raise subprocess.CalledProcessError(1, ['credsweeper'])


@lru_cache(maxsize=1)
def _configured(path, expected_digest):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError('candidate_configuration_digest_mismatch')
    return OfficialTools(json.loads(raw, object_pairs_hook=_strict_object))


@contextmanager
def candidate_context(backend=None, *, from_environment=False, admission=None):
    """Host-owned scope, reset even on rejection; no request controls configuration."""
    if from_environment and active_candidate() is not None:
        backend = active_candidate()
    elif from_environment:
        path = os.environ.get('SSS_RSI_PRIVACY_CANDIDATE_CONFIG')
        digest = os.environ.get('SSS_RSI_PRIVACY_CANDIDATE_SHA256')
        if bool(path) != bool(digest):
            raise ValueError('candidate_configuration_pair_required')
        backend = _configured(path, digest) if path else None
    token = _ACTIVE.set(backend)
    admission_token = _ADMISSION.set(_ADMISSION.get() if admission is None else admission)
    try:
        yield backend
    finally:
        _ADMISSION.reset(admission_token)
        _ACTIVE.reset(token)
