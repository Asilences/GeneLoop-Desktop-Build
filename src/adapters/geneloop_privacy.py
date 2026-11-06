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
from jsonschema import Draft202012Validator

from .rsi_text_privacy import _scan, anonymize_text

MAX_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 100_000
MAX_DEPTH = 48
SECRET_FIELDS = frozenset(("apikey", "authorization", "accesstoken", "refreshtoken",
                           "password", "passwd", "secret", "cookie", "setcookie",
                           "privatekey", "clientsecret", "token", "apitoken", "authtoken", "bearertoken", "credential", "credentials",
                           "密码", "口令", "密钥", "令牌"))
IDENTITY_FIELDS = {
    **dict.fromkeys(("email", "emailaddress", "邮箱", "联系邮箱"), "EMAIL_ADDRESS"),
    **dict.fromkeys(("phone", "phonenumber", "mobile", "telephone", "手机", "电话"), "PHONE_NUMBER"),
    **dict.fromkeys(("personname", "fullname", "username", "姓名", "联系人"), "PERSON"),
    **dict.fromkeys(("homeaddress", "mailingaddress", "住址", "邮寄地址"), "ADDRESS"),
    **dict.fromkeys(("streetaddress", "contactaddress", "address", "家庭地址"), "ADDRESS"),
    **dict.fromkeys(("bankaccount", "accountnumber", "iban", "银行卡号"), "FINANCIAL_ACCOUNT"),
    **dict.fromkeys(("passportnumber", "idnumber", "ssn", "证件号", "身份证号"), "IDENTITY_NUMBER"),
    **dict.fromkeys(("filename", "filepath", "attachmentname", "文件名", "附件名", "文件路径"), "PRIVATE_REFERENCE"),
    **dict.fromkeys(("accountid", "userid", "sessionid", "taskid"), "PRIVATE_ID"),
}
_FIELD = re.compile(r"[\s_-]+")
_PROTOCOL = frozenset(('string','number','integer','object','array','boolean','null'))
_OPAQUE = re.compile(r'(?:[a-f0-9]{64}|(?:task_|history_|evidence_)[a-f0-9]{24,64}|private-[a-f0-9-]{32,36})\Z')


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
                        parsed = json.loads(value)
                    except (ValueError,RecursionError):
                        parsed = None
                    if isinstance(parsed,(dict,list,str)):
                        clean = walk(parsed,1)
                        cache[value] = value if clean == parsed else _encoded(clean)
                        return cache[value]
                if any(unicodedata.category(char) in ('Cc','Cf') and char not in '\n\r\t' for char in value):
                    raise PrivacyRejected()
                cache[value] = anonymize_text(value, alias=alias)
                shadow = unicodedata.normalize("NFKC", value)
                if shadow != value and unicodedata.normalize("NFKC", cache[value]) != anonymize_text(shadow, alias=alias):
                    raise PrivacyRejected()
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
                    raise PrivacyRejected()
                safe_key = text(key)
                if safe_key in output:
                    raise PrivacyRejected()
                if field in ('base64','imagedata','audiodata','videodata','binary','blob','bytes') and isinstance(child,(str,list,dict)):
                    output[safe_key] = '<BINARY_OMITTED>'
                elif field in ('image','audio','video') and isinstance(child,str) and child.lower().startswith('data:'):
                    output[safe_key] = '<BINARY_OMITTED>'
                elif identity == 'ADDRESS' and (type(child) in (int,float) or isinstance(child,str) and re.fullmatch(r'0x[0-9a-fA-F]+',child)):
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
