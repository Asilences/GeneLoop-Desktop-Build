"""One repository-owned privacy policy for runtime and evaluation."""
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT/'config/geneloop-privacy-policy-v1.json').read_text(encoding='utf-8'))
_schema = json.loads((ROOT/'schemas/geneloop-privacy-policy.schema.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(_schema)
Draft202012Validator(_schema).validate(POLICY)
POLICY_SHA256 = hashlib.sha256(json.dumps(POLICY,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
