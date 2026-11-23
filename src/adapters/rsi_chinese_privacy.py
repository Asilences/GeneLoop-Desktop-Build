"""Opt-in Chinese NER using frozen official Stanza assets, for every scene."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import importlib.metadata
import json
from pathlib import Path
from threading import RLock

_BATCH = ContextVar('privacy_chinese_batch', default=None)
_MANIFEST = Path(__file__).resolve().parents[2] / 'config/rsi-privacy-chinese-tools.json'


class ChineseTools:
    def __init__(self, settings):
        required = {'format', 'model_dir', 'device', 'threads', 'batch_size', 'replace_zh_ner'}
        optional = {'credential_mode'}
        if (not isinstance(settings, dict) or not required <= settings.keys()
                or settings.keys() - required - optional
                or settings['format'] != 'geneloop.privacy-chinese/v1'
                or settings.get('credential_mode', 'gitleaks') not in ('gitleaks', 'gitleaks+credsweeper-review')
                or settings['device'] not in ('cpu', 'cuda:0')
                or type(settings['threads']) is not int or not 1 <= settings['threads'] <= 4
                or type(settings['batch_size']) is not int or not 1 <= settings['batch_size'] <= 32
                or type(settings['replace_zh_ner']) is not bool):
            raise ValueError('chinese_candidate_invalid_configuration')
        spec = json.loads(_MANIFEST.read_text(encoding='utf-8'))
        if importlib.metadata.version('stanza') != spec['version']:
            raise ValueError('chinese_candidate_dependency_mismatch')
        # A pinned CUDA distribution also implements explicit CPU execution.
        # No device fallback or unpinned version is admitted.
        allowed_torch = set(spec['torch'].values()) if settings['device'] == 'cpu' else {spec['torch']['cuda']}
        if importlib.metadata.version('torch') not in allowed_torch:
            raise ValueError('chinese_candidate_dependency_mismatch')
        distribution = importlib.metadata.distribution('stanza')
        root = Path(settings['model_dir'])
        if not root.is_absolute() or root.absolute() != root.resolve():
            raise ValueError('chinese_candidate_model_path_required')
        for base, files in [(root, spec['files']), (Path(distribution.locate_file('')), spec['code_files'])]:
            for name, digest in files.items():
                path = base / name
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('chinese_candidate_asset_mismatch')
        import torch
        import stanza
        torch.set_num_threads(settings['threads'])
        if settings['device'] != 'cpu' and not torch.cuda.is_available():
            raise ValueError('chinese_candidate_device_unavailable')
        self.lock = RLock()
        self.replace_zh_ner = settings['replace_zh_ner']
        self.batch_size = settings['batch_size']
        self.pipeline = stanza.Pipeline('zh-hans', dir=str(root), package=None,
            processors={'tokenize': 'gsdsimp', 'ner': spec['ner_package']},
            download_method=None, device=settings['device'], use_gpu=settings['device'] != 'cpu',
            ner_batch_size=self.batch_size, verbose=False)
        self.credential_reviewer = None
        self.review_source_material = settings.get('credential_mode') == 'gitleaks+credsweeper-review'
        if self.review_source_material:
            from .rsi_privacy_candidates import OfficialTools
            self.credential_reviewer = OfficialTools({
                'format': 'geneloop.privacy-candidate/v1',
                'text_mode': 'r4',
                'credential_mode': 'gitleaks+credsweeper-review',
                'checkpoint': '',
                'tokenizer_cache': '',
                'threads': 1,
            })

    def scan(self, text, **scope):
        # The common boundary runs Gitleaks before this optional review.
        if self.credential_reviewer is not None:
            self.credential_reviewer.scan(text, **scope)

    def _predict(self, texts):
        with self.lock:
            docs = self.pipeline.bulk_process(texts)
        if len(docs) != len(texts):
            raise ValueError('chinese_candidate_invalid_output')
        output = []
        for text, doc in zip(texts, docs):
            spans = []
            for entity in doc.ents:
                label = {'PERSON': 'PERSON', 'LOC': 'LOCATION', 'GPE': 'LOCATION', 'FAC': 'LOCATION'}.get(entity.type)
                if label is None:
                    continue
                start, end = entity.start_char, entity.end_char
                if not 0 <= start < end <= len(text) or text[start:end] != entity.text:
                    raise ValueError('chinese_candidate_invalid_span')
                spans.append({'start': start, 'end': end, 'label': label})
            output.append(spans)
        return output

    @contextmanager
    def batch_context(self, texts):
        from .rsi_text_privacy import _has_han
        from .privacy_diagnostics import privacy_stage
        texts = [text for text in texts if _has_han(text)]
        with privacy_stage('chinese_batch_ner'):
            spans = self._predict(texts) if texts else []
        token = _BATCH.set((self, dict(zip(texts, spans))))
        try:
            yield
        finally:
            _BATCH.reset(token)

    def findings(self, text):
        from .rsi_text_privacy import _has_han
        if not _has_han(text):
            return []
        batch = _BATCH.get()
        spans = batch[1].get(text) if batch is not None and batch[0] is self else None
        return [dict(span) for span in (spans if spans is not None else self._predict([text])[0])]
