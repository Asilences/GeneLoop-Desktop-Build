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
import subprocess
import sys
import unicodedata
from jsonschema import Draft202012Validator

from .rsi_text_privacy import _scan, anonymize_text, PROTOCOL_WORDS
from .rsi_privacy_tools import PrivacyToolError

MAX_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 100_000
MAX_DEPTH = 48
from .rsi_privacy_policy import POLICY

SECRET_FIELDS = frozenset(POLICY['structured']['secret_fields'])
IDENTITY_FIELDS = POLICY['structured']['identity_fields']
_FIELD = re.compile(r"[\s_-]+")
_PROTOCOL = PROTOCOL_WORDS
_SCHEMA_KEYS=frozenset(Draft202012Validator.VALIDATORS)|frozenset(('$schema','$defs','$ref','$comment','title','description','default','examples','deprecated','readOnly','writeOnly'))
_OPAQUE = re.compile(r'(?:[a-f0-9]{64}|(?:task_|history_|evidence_)[a-f0-9]{24,64}|private-[a-f0-9-]{32,36})\Z')


class PrivacyRejected(ValueError):
    REASONS = frozenset(('policy_rejected','ambiguous_json','input_limit','invalid_input',
                         'credential_detected','scanner_error','scanner_timeout',
                         'tool_unverified','dependency_unavailable','processing_failed'))

    def __init__(self, reason='policy_rejected'):
        self.reason = reason if reason in self.REASONS else 'processing_failed'
        super().__init__("geneloop_privacy_rejected")


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PrivacyRejected('ambiguous_json')
        result[key] = value
    return result


def decode_material_json(value):
    # A last-key-wins parse cannot certify the original nested text: discarded
    # fields could still contain an explicit credential. Reuse stdlib decoding,
    # rejecting ambiguity and resource failures instead of treating them as prose.
    try:
        return json.loads(value, object_pairs_hook=_json_object)
    except RecursionError:
        raise PrivacyRejected('input_limit') from None


# Retain the compatibility name for existing callers and frozen evaluators.
_decoded = decode_material_json


def _scan_material(value):
    """Feed Gitleaks both the JSON envelope and its decoded text, in memory.

    JSON escaping changes regex context. Keep complete strings (including
    multiline source and nested JSON strings) intact; never send only their
    serialized representation. This adapts input, not Gitleaks rules.
    """
    encoded = _encoded(value)
    if len(encoded.encode()) > MAX_BYTES:
        raise PrivacyRejected()
    pending = [(value, 0)]
    normalized = unicodedata.normalize('NFKC', encoded)
    parts = list(dict.fromkeys((encoded, normalized)))
    seen, remaining, size = set(), MAX_ITEMS * 2, 0
    while pending:
        item, depth = pending.pop()
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise PrivacyRejected()
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and item not in seen:
            seen.add(item)
            for text in dict.fromkeys((item, unicodedata.normalize('NFKC', item))):
                size += len(text.encode()) + 2
                if size > MAX_BYTES * 2:
                    raise PrivacyRejected()
                parts.append(text)
            if item.lstrip().startswith(('{', '[', '"')):
                try:
                    parsed = _decoded(item)
                except PrivacyRejected:
                    raise
                except ValueError:
                    continue
                if isinstance(parsed, (dict, list, str)):
                    pending.append((parsed, depth + 1))
    _scan('\n\n'.join(parts))


def learning_view(value):
    """Apply the public contract, optionally using host-configured local tools."""
    from .rsi_privacy_candidates import candidate_context
    try:
        with candidate_context(from_environment=True, admission=True):
            return _learning_view(value)
    except PrivacyRejected:
        raise
    except Exception:
        raise PrivacyRejected('processing_failed') from None


def _learning_view(value):
    """Sanitize arbitrary JSON keys AND values, with no scene switch or bypass.

    Presidio owns text recognition/anonymization; Gitleaks scans the whole
    material at both boundaries. Explicit identity fields also cover numeric
    phone numbers and account identifiers which NLP cannot reliably infer.
    """
    try:
        _scan_material(value)
        remaining, cache, identities = MAX_ITEMS, {}, {}

        def alias(entity, original):
            if entity == 'BINARY_PAYLOAD':
                return '<BINARY_OMITTED>'
            identity = (entity, unicodedata.normalize("NFKC", str(original)).casefold())
            if identity not in identities:
                index = 1 + sum(key[0] == entity for key in identities)
                suffix = ""
                if entity == 'PRIVATE_REFERENCE':
                    extension = re.search(r'\.([A-Za-z0-9]{1,8})(?:[?#].*)?$',str(original).strip('\'"'))
                    if extension and extension[1].lower() in ('pdf','ppt','pptx','doc','docx','csv','xlsx','tex','bib',
                                                            'py','js','ts','mjs','md','json','yaml','yml','ipynb','txt',
                                                            'png','jpg','jpeg','svg','webp','mp4','mov','wav','mp3','zip','parquet'):
                        suffix = '.'+extension[1].lower()
                identities[identity] = "<" + entity + "_" + str(index) + ">" + suffix
            return identities[identity]

        def text(value):
            if value not in cache:
                # JSON types and host digest handles are protocol vocabulary,
                # not prose. NLP must not turn `integer` into a person's name
                # or corrupt a version/evidence digest. The whole packet still
                # passes both credential scans and explicit identity fields.
                if value in _PROTOCOL or _OPAQUE.fullmatch(value):
                    return value
                # Tool stdout and nested packet fields often contain JSON
                # encoded as text. Parse data only; never evaluate source code.
                if value.lstrip().startswith(('{','[','"')):
                    try:
                        parsed = _decoded(value)
                    except PrivacyRejected:
                        raise
                    except ValueError:
                        parsed = None
                    if isinstance(parsed,(dict,list,str)):
                        clean = walk(parsed,1)
                        cache[value] = value if clean == parsed else _encoded(clean)
                        return cache[value]
                if any(unicodedata.category(char) in ('Cc','Cf') and char not in '\n\r\t' for char in value):
                    raise PrivacyRejected()
                cache[value] = anonymize_text(value, alias=alias)
            return cache[value]

        def walk(item, depth=0, schema=False, property_name=None):
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
                return [walk(child, depth + 1, schema=schema, property_name=property_name) for child in item]
            if type(item) is not dict:
                raise PrivacyRejected()
            output = {}
            for key, child in item.items():
                if type(key) is not str:
                    raise PrivacyRejected()
                # Schema properties declare fields, not identity instances.
                # Reuse jsonschema's validation before treating them as such;
                # descriptions and actual defaults/const/enum still sanitize.
                if schema and key=='properties' and isinstance(child,dict):
                    properties={}
                    for name,definition in child.items():
                        safe_name=text(name)
                        if safe_name in properties:
                            raise PrivacyRejected()
                        properties[safe_name]=walk(definition,depth+2,schema=True,property_name=name)
                    output[key]=properties
                    continue
                if schema and key in ('default','const','enum') and property_name:
                    output[key]=next(iter(walk({property_name:child},depth+1).values()))
                    continue
                if key in ('parameters','input_schema','output_schema') and isinstance(child,dict) and any(
                        name in child for name in ('type','properties','oneOf','anyOf','allOf','$ref')):
                    Draft202012Validator.check_schema(child)
                    output[key]=walk(child,depth+1,schema=True)
                    continue
                field = _FIELD.sub("", unicodedata.normalize("NFKC", key)).casefold()
                variants = [field,*([field[:-1]] if field.endswith('s') else []),
                            *([field[:-2]] if field.endswith('es') else [])]
                secret = next((name for name in sorted(SECRET_FIELDS,key=len,reverse=True)
                               if any(value.endswith(name) for value in variants)),None)
                identity = next((entity for name,entity in IDENTITY_FIELDS.items()
                                 if any(value.endswith(name) for value in variants)),None)
                if secret and child is not None and child != '' and type(child) is not bool and not (
                        secret == 'token' and field.endswith('tokens') and type(child) in (int,float)):
                    raise PrivacyRejected('credential_detected')
                safe_key = key if schema and key in _SCHEMA_KEYS else text(key)
                if safe_key in output:
                    raise PrivacyRejected()
                if field in ('base64','imagedata','audiodata','videodata','binary','blob','bytes') and isinstance(child,(str,list,dict)):
                    output[safe_key] = '<BINARY_OMITTED>'
                elif field in ('image','audio','video') and isinstance(child,str) and child.lower().startswith('data:'):
                    output[safe_key] = '<BINARY_OMITTED>'
                elif identity in ('ADDRESS','LOCATION') and (type(child) in (int,float) or isinstance(child,str) and re.fullmatch(r'0x[0-9a-fA-F]+',child)):
                    output[safe_key] = child
                elif identity and child is not None:
                    entity = identity
                    def reference(value):
                        # Investigation already replaces native task IDs with
                        # one-way task_<digest> handles before the boundary.
                        if entity=='PRIVATE_ID' and isinstance(value,str) and re.fullmatch(r'task_[a-f0-9]{24}',value):
                            return value
                        return value if isinstance(value,str) and re.fullmatch(
                            r"<"+entity+r"_[1-9][0-9]{0,6}>(?:\.[a-z0-9]{1,8})?",value) else alias(entity, value)
                    output[safe_key] = [reference(value) for value in child] if isinstance(child,list) else reference(child)
                else:
                    output[safe_key] = walk(child, depth + 1, schema=schema, property_name=property_name)
            return output

        result = walk(value)
        _scan_material(result)
        return result
    except PrivacyRejected:
        raise
    except PrivacyToolError as error:
        reason='dependency_unavailable' if error.reason.startswith('privacy_dependency') else 'tool_unverified'
        raise PrivacyRejected(reason) from None
    except subprocess.TimeoutExpired:
        raise PrivacyRejected('scanner_timeout') from None
    except subprocess.CalledProcessError as error:
        raise PrivacyRejected('credential_detected' if error.returncode==1 else 'scanner_error') from None
    except Exception:
        raise PrivacyRejected('processing_failed') from None


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
        value = _decoded(raw)
        result = admit_publication(value) if args.publication else learning_view(value)
        print(_encoded(result))
    except Exception:
        parser.exit(1, "geneloop_privacy_rejected\n")


if __name__ == "__main__":
    main()
