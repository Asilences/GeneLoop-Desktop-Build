"""Local text de-identification for explicitly admitted RSI task intent."""

import os
import re
import subprocess
import unicodedata
from array import array
from functools import lru_cache
from tempfile import TemporaryDirectory
from contextlib import ExitStack
from threading import RLock

MAX_INTENT_CHARS = 2048
MODELS = {"en": "en_core_web_sm", "zh": "zh_core_web_sm"}
from .rsi_privacy_policy import POLICY

EXTRA_PATTERNS = POLICY['text']['supplemental_patterns']
NON_IDENTITY_ENTITIES = frozenset(POLICY['text']['excluded_generic_entities'])
STAT_ABBREVIATION = re.compile(r"\bmean\s*±\s*(SD|SEM|SE)\b", re.IGNORECASE)
STAT_SAMPLE_SIZE = re.compile(r'\bn\s*=\s*\d+\b', re.IGNORECASE)
PROTOCOL_WORDS = frozenset(POLICY['protected_prose']['protocol_words'])
_PROTOCOL_WORD = re.compile(r'(?<![\w@])(?:' + '|'.join(sorted(PROTOCOL_WORDS, key=len, reverse=True)) + r')(?![\w@])')
_NLP_LOCK=RLock()


def _normalized_view(text):
    """Map standard Unicode grapheme normalization back to original offsets.

    Recognition sees one canonical spelling; replacement preserves untouched
    code/equations byte for byte. Ambiguous normalization fails closed.
    """
    normalized = unicodedata.normalize('NFKC', text)
    if normalized == text:
        return text, None, None
    import regex  # Presidio's existing regex dependency implements Unicode \X.
    pieces, starts, ends = [], array('I'), array('I')
    for cluster in regex.finditer(r'\X', text):
        value = unicodedata.normalize('NFKC', cluster.group())
        pieces.append(value)
        starts.extend([cluster.start()] * len(value))
        ends.extend([cluster.end()] * len(value))
    if ''.join(pieces) != normalized:
        raise ValueError('unsupported_unicode_alignment')
    return normalized, starts, ends


@lru_cache(maxsize=1)
def _presidio():
    # The structural projector and its existing callers have no NLP dependency.
    from .rsi_privacy_tools import verify_nlp_versions
    verify_nlp_versions()
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer
    from presidio_anonymizer import AnonymizerEngine
    from spacy.util import is_package

    if not all(is_package(model) for model in MODELS.values()):
        raise ValueError("local_presidio_models_required")
    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": lang, "model_name": model} for lang, model in MODELS.items()],
    })
    engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=engine, supported_languages=list(MODELS))
    # Use Presidio's email pattern without its optional remote suffix-list lookup.
    analyzer.registry.remove_recognizer("EmailRecognizer")
    analyzer.registry.add_recognizer(PatternRecognizer(
        supported_entity="EMAIL_ADDRESS", patterns=EmailRecognizer.PATTERNS,
    ))
    analyzer.registry.add_recognizer(PhoneRecognizer(supported_language="zh", supported_regions=["CN"]))
    analyzer.registry.add_recognizer(PhoneRecognizer(supported_language="en", supported_regions=["CN"]))
    for entity, patterns in EXTRA_PATTERNS.items():
        analyzer.registry.add_recognizer(PatternRecognizer(
            supported_language="en", supported_entity=entity,
            patterns=[Pattern(f"{entity}-{i}", pattern, 0.9) for i, pattern in enumerate(patterns)],
        ))
    from .rsi_privacy_recognizers import add_contextual_recognizers
    add_contextual_recognizers(analyzer,POLICY)
    for language, entities in POLICY['text']['requested_entities_by_language'].items():
        if set(entities) - set(analyzer.get_supported_entities(language=language)):
            raise ValueError('privacy_recognizer_unavailable')
    return analyzer, AnonymizerEngine()


def _scan_gitleaks(text):
    from .rsi_privacy_tools import verified_gitleaks
    binary = verified_gitleaks(os.environ.get("SSS_RSI_GITLEAKS", ""))
    # Do not inherit rule overrides or print scanner findings, even on failure.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    with TemporaryDirectory(prefix="rsi-scan-") as directory:
        subprocess.run([str(binary), "stdin", "--no-banner", "--redact=100",
                        "--ignore-gitleaks-allow", "--max-decode-depth", "2"],
                       input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       cwd=directory, env=env, timeout=8, check=True)


def _scan(text):
    _scan_gitleaks(text)
    from .rsi_privacy_candidates import active_candidate
    candidate = active_candidate()
    if candidate is not None:
        candidate.scan(text)


def _has_han(text):
    return any("\u3400" <= char <= "\u9fff" for char in text)


def _protected_spans(text):
    return ([match.span(1) for match in STAT_ABBREVIATION.finditer(text)]
            + [match.span() for match in STAT_SAMPLE_SIZE.finditer(text)]
            + [match.span() for match in _PROTOCOL_WORD.finditer(text)])


def anonymize_text(text, *, alias=None):
    """Shared Presidio operation, independent of scenes and JSON transport.

    Callers scan the complete material before and after this operation. Keep
    Unicode and whitespace unchanged for code, equations and structured text.
    """
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError("invalid_privacy_text")
    if not text:
        return text
    with _NLP_LOCK:
        analyzer,anonymizer=_presidio()
        with ExitStack() as stack:
            # Reuse model weights without retaining request vocabulary in a
            # persistent spaCy worker. Only plain spans/strings leave this zone.
            pipelines=getattr(getattr(analyzer,'nlp_engine',None),'nlp',{})
            for nlp in pipelines.values():stack.enter_context(nlp.memory_zone())
            return _anonymize_with_engine(text,analyzer,anonymizer,alias)


def _anonymize_with_engine(text,analyzer,anonymizer,alias):
    canonical, starts, ends = _normalized_view(text)
    protected = _protected_spans(canonical)
    findings = []
    for language in ('en', 'zh'):
        if language == "zh" and not _has_han(canonical):
            continue
        entities = POLICY['text']['requested_entities_by_language'][language]
        for finding in analyzer.analyze(text=canonical, language=language, entities=entities, score_threshold=POLICY['text']['score_threshold']):
            # Limit model labels to their script and protect statistical notation.
            # Pattern recognizers and the credential scan still cover every span.
            if finding.recognition_metadata.get("recognizer_name") == "SpacyRecognizer":
                start, end = finding.start, finding.end
                if any(a <= start and end <= b for a, b in protected) or _has_han(canonical[start:end]) != (language == "zh"):
                    continue
            if starts is not None:
                finding.start, finding.end = starts[finding.start], ends[finding.end - 1]
            findings.append(finding)
    if canonical != text:
        # Compatibility normalization can change the NER model's tokenization,
        # especially around Chinese punctuation. Keep the canonical detections
        # and add original-view PERSON results; never discard an existing hit.
        # The same script/prose protections apply in original coordinates.
        original_protected = _protected_spans(text)
        for language in ('en', 'zh'):
            if language == 'zh' and not _has_han(text):
                continue
            entities = POLICY['text']['requested_entities_by_language'][language]
            for finding in analyzer.analyze(text=text, language=language, entities=entities, score_threshold=POLICY['text']['score_threshold']):
                if finding.entity_type != 'PERSON' or finding.recognition_metadata.get('recognizer_name') != 'SpacyRecognizer':
                    continue
                start, end = finding.start, finding.end
                if (any(a <= start and end <= b for a, b in original_protected)
                        or _has_han(text[start:end]) != (language == 'zh')):
                    continue
                findings.append(finding)
    if POLICY['text'].get('canonicalize_labels',False):
        mapping=POLICY['text']['entity_category_map']
        for finding in findings:
            finding.entity_type=mapping.get(finding.entity_type,finding.entity_type)
    from .rsi_privacy_candidates import active_candidate
    candidate = active_candidate()
    if candidate is not None:
        from presidio_analyzer import RecognizerResult
        original_protected = _protected_spans(text)
        for span in candidate.findings(text):
            start, end = span['start'], span['end']
            if not 0 <= start < end <= len(text):
                raise ValueError('candidate_invalid_output_span')
            if any(a <= start and end <= b for a, b in original_protected):
                continue
            # Official model emits spans without calibrated confidence. Keep the
            # same fixed rendering score used by the frozen candidate scorer.
            findings.append(RecognizerResult(entity_type=span['label'], start=start, end=end, score=0.9))
    operators = None
    if alias is not None:
        from presidio_anonymizer.entities import OperatorConfig
        operators = {entity: OperatorConfig("custom", {"lambda": lambda value, entity=entity: alias(entity, value)})
                     for entity in {finding.entity_type for finding in findings}}
    return anonymizer.anonymize(text=text, analyzer_results=findings, operators=operators).text


def redact_task_intent(text):
    if not 0 < len(text) <= MAX_INTENT_CHARS:
        raise ValueError("invalid_task_intent_size")
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(char for char in text
                   if char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cf"})
    if not text.strip() or len(text) > MAX_INTENT_CHARS:
        raise ValueError("invalid_task_intent_size")
    _scan(text)
    redacted = anonymize_text(text)
    _scan(redacted)
    return redacted
