"""Local text de-identification for explicitly admitted RSI task intent."""

import os
import re
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

MAX_INTENT_CHARS = 2048
MODELS = {"en": "en_core_web_sm", "zh": "zh_core_web_sm"}
EXTRA_PATTERNS = {
    "BINARY_PAYLOAD": [r"(?i)data:(?:image|audio|video|application/octet-stream)/?[^\s,]*;base64,[A-Za-z0-9+/=_-]+"],
    "PRIVATE_REFERENCE": [
        r"(?i)(?:https?|s3|file|ssh|ftp|smb)://[^\s<>\"',;，。；！？、）\])]+",
        r"""["'](?:[A-Za-z]:[\\/]|\\\\|~/|/(?!/\s))[^"'\n]+["']""",
        r"(?<![\w/:])(?:[A-Za-z]:[\\/]|\\\\|~/|/)[\w.~-]+(?:[\\/][\w.~-]+)+",
        r"(?i)(?<![\w.-])[\w.-]+\.(?:pdf|pptx?|docx?|xlsx?|csv|tex|bib)(?![\w-]|\.[\w-])",
        r"(?i)(?<![\w])\.local[\\/][^\s<>\"',;，。；！？]+",
    ],
    "CREDENTIAL": [
        r"""(?i)\b(?:authorization|cookie|set-cookie)["']?\s*[:=：][^\n]+""",
        r"""(?i)\b(?:api[_ -]?key|access[_ -]?token|password|passwd|secret|token)["']?\s*[:=：]\s*(?:"[^"\n]*"|'[^'\n]*'|[^\s,;，；]+)""",
        r"""(?:密码|口令|令牌|密钥)\s*[:=：]\s*(?:"[^"\n]*"|'[^'\n]*'|[^\s,;，；]+)""",
    ],
    "PERSON": [r"(?:联系人|姓名)\s*[:=：]\s*[\p{Han}·]{2,8}(?=\s|[,;，；。]|$)"],
    "ADDRESS": [r"(?i)(?:通讯地址|邮寄地址|住址|\b(?:home|mailing|street) address)\s*[:=：]\s*[^\n;,，；。]+"],
    "CN_ID_NUMBER": [r"(?<!\d)[1-9]\d{16}[\dXx](?!\d)"],
}
ENTITIES = ["PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "IP_ADDRESS",
            "CREDIT_CARD", "IBAN_CODE", "US_SSN", *[key for key in EXTRA_PATTERNS if key != "PERSON"]]
STAT_ABBREVIATION = re.compile(r"\bmean\s*±\s*(SD|SEM|SE)\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _presidio():
    # The structural projector and its existing callers have no NLP dependency.
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
    for entity, patterns in EXTRA_PATTERNS.items():
        analyzer.registry.add_recognizer(PatternRecognizer(
            supported_language="en", supported_entity=entity,
            patterns=[Pattern(f"{entity}-{i}", pattern, 0.9) for i, pattern in enumerate(patterns)],
        ))
    return analyzer, AnonymizerEngine()


def _scan(text):
    binary = Path(os.environ.get("SSS_RSI_GITLEAKS", ""))
    if not binary.is_absolute() or not binary.is_file():
        raise ValueError("local_gitleaks_required")
    # Do not inherit rule overrides or print scanner findings, even on failure.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    with TemporaryDirectory(prefix="rsi-scan-") as directory:
        subprocess.run([str(binary), "stdin", "--no-banner", "--redact=100",
                        "--ignore-gitleaks-allow", "--max-decode-depth", "2"],
                       input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       cwd=directory, env=env, timeout=8, check=True)


def _has_han(text):
    return any("\u3400" <= char <= "\u9fff" for char in text)


def anonymize_text(text, *, alias=None):
    """Shared Presidio operation, independent of scenes and JSON transport.

    Callers scan the complete material before and after this operation. Keep
    Unicode and whitespace unchanged for code, equations and structured text.
    """
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError("invalid_privacy_text")
    if not text:
        return text
    analyzer, anonymizer = _presidio()
    statistical_spans = {match.span(1) for match in STAT_ABBREVIATION.finditer(text)}
    findings = []
    for language, entities in (("en", ENTITIES), ("zh", ["PERSON", "LOCATION", "PHONE_NUMBER"])):
        if language == "zh" and not _has_han(text):
            continue
        for finding in analyzer.analyze(text=text, language=language, entities=entities, score_threshold=0.4):
            # Limit model labels to their script and protect statistical notation.
            # Pattern recognizers and the credential scan still cover every span.
            if finding.recognition_metadata.get("recognizer_name") == "SpacyRecognizer":
                start, end = finding.start, finding.end
                if (start, end) in statistical_spans or _has_han(text[start:end]) != (language == "zh"):
                    continue
            findings.append(finding)
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
