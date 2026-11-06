"""GeneLoop's scene-independent boundary for learning material and publication.

Native execution, immutable evidence and version guards keep their private
originals. Only a separate derived view can be exposed as learning content.
No identity map, raw exception or rejected material is persisted here.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
import unicodedata

from .rsi_text_privacy import _scan, anonymize_text

MAX_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 100_000
MAX_DEPTH = 48
SECRET_FIELDS = frozenset(("apikey", "authorization", "accesstoken", "refreshtoken",
                           "password", "passwd", "secret", "cookie", "setcookie",
                           "privatekey", "clientsecret", "密码", "口令", "密钥", "令牌"))
IDENTITY_FIELDS = {
    **dict.fromkeys(("email", "emailaddress", "邮箱", "联系邮箱"), "EMAIL_ADDRESS"),
    **dict.fromkeys(("phone", "phonenumber", "mobile", "telephone", "手机", "电话"), "PHONE_NUMBER"),
    **dict.fromkeys(("personname", "fullname", "username", "姓名", "联系人"), "PERSON"),
    **dict.fromkeys(("homeaddress", "mailingaddress", "住址", "邮寄地址"), "ADDRESS"),
    **dict.fromkeys(("accountid", "userid", "sessionid", "taskid"), "PRIVATE_ID"),
}
_FIELD = re.compile(r"[\s_-]+")


class PrivacyRejected(ValueError):
    def __init__(self):
        super().__init__("geneloop_privacy_rejected")


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def learning_view(value):
    """Sanitize arbitrary JSON keys AND values, with no scene switch or bypass.

    Presidio owns text recognition/anonymization; Gitleaks scans the whole
    material at both boundaries. Explicit identity fields also cover numeric
    phone numbers and account identifiers which NLP cannot reliably infer.
    """
    try:
        original = _encoded(value)
        if len(original.encode()) > MAX_BYTES:
            raise PrivacyRejected()
        _scan(original)
        normalized = unicodedata.normalize("NFKC", original)
        if normalized != original:
            _scan(normalized)
        remaining, cache, identities = MAX_ITEMS, {}, {}

        def alias(entity, original):
            identity = (entity, unicodedata.normalize("NFKC", str(original)).casefold())
            if identity not in identities:
                index = 1 + sum(key[0] == entity for key in identities)
                identities[identity] = "<" + entity + "_" + str(index) + ">"
            return identities[identity]

        def text(value):
            if value not in cache:
                if any(unicodedata.category(char) in ('Cc','Cf') and char not in '\n\r\t' for char in value):
                    raise PrivacyRejected()
                cache[value] = anonymize_text(value, alias=alias)
                shadow = unicodedata.normalize("NFKC", value)
                if shadow != value and unicodedata.normalize("NFKC", cache[value]) != anonymize_text(shadow, alias=alias):
                    raise PrivacyRejected()
            return cache[value]

        def walk(item, depth=0):
            nonlocal remaining
            remaining -= 1
            if remaining < 0 or depth > MAX_DEPTH:
                raise PrivacyRejected()
            if item is None or type(item) is bool:
                return item
            if type(item) in (int, float):
                if type(item) is float and not math.isfinite(item):
                    raise PrivacyRejected()
                return item
            if type(item) is str:
                return text(item)
            if type(item) is list:
                return [walk(child, depth + 1) for child in item]
            if type(item) is not dict:
                raise PrivacyRejected()
            output = {}
            for key, child in item.items():
                if type(key) is not str:
                    raise PrivacyRejected()
                field = _FIELD.sub("", unicodedata.normalize("NFKC", key)).casefold()
                if field in SECRET_FIELDS and child not in (None, "", False):
                    raise PrivacyRejected()
                safe_key = text(key)
                if safe_key in output:
                    raise PrivacyRejected()
                if field in IDENTITY_FIELDS and child is not None:
                    entity = IDENTITY_FIELDS[field]
                    output[safe_key] = alias(entity, child)
                else:
                    output[safe_key] = walk(child, depth + 1)
            return output

        result = walk(value)
        _scan(_encoded(result))
        return result
    except Exception:
        raise PrivacyRejected() from None


def admit_publication(value):
    """Keep certified artifact bytes valid: reject, never silently re-sign.

    This is an export gate, not an instruction to publish. Authorization and
    the destination's strict object contract remain the caller's responsibility.
    """
    if learning_view(value) != value:
        raise PrivacyRejected()
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", action="store_true")
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise PrivacyRejected()
        value = json.loads(raw)
        result = admit_publication(value) if args.publication else learning_view(value)
        print(_encoded(result))
    except Exception:
        parser.exit(1, "geneloop_privacy_rejected\n")


if __name__ == "__main__":
    main()
