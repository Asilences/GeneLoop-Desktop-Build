"""Single source for the Kouri API address, model ID and credential."""
from __future__ import annotations

import os
from urllib.parse import urlsplit


MODEL_API_ROOT = 'https://api.kourichat.com'
MODEL_API_PREFIX = '/v1'
MODEL_API_KEY_ENV = 'KOURI_API_KEY'
MODEL_SDK_ID = 'deepseek-flash'
MODEL_WIRE_ID = 'deepseek-v4.1-flash'
MODEL_CATALOG_PATH = '/v1/models'
MODEL_CHAT_PATH = '/v1/chat/completions'


def model_api_root() -> str:
    root = MODEL_API_ROOT.rstrip('/')
    parsed = urlsplit(root)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('model API root must be an HTTPS origin without credentials or a path')
    return root


def model_api_url(path: str) -> str:
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
        raise ValueError('model API path must start with one slash')
    return model_api_root() + path


def model_api_base_url() -> str:
    return model_api_url(MODEL_API_PREFIX)


def model_api_key() -> str:
    key = os.environ.get(MODEL_API_KEY_ENV, '').strip()
    if not key:
        raise ValueError(f'{MODEL_API_KEY_ENV} is required for real model requests')
    return key


def model_api_key_configured() -> bool:
    return bool(os.environ.get(MODEL_API_KEY_ENV, '').strip())


def model_sdk_key() -> str:
    """Local DSH credential; the budget gate adds the Kouri key upstream."""
    model_api_key()
    return 'kouri-local-budget-gateway'


def model_upstream_headers(upstream: str, headers: dict[str, str]) -> dict[str, str]:
    if upstream.rstrip('/') != model_api_root():
        return headers
    return {**{name: value for name, value in headers.items()
               if name.lower() not in {'authorization', 'x-api-key'}},
            'Authorization': 'Bearer ' + model_api_key()}


def model_wire_id(model: str) -> str:
    return MODEL_WIRE_ID if model in {MODEL_SDK_ID, 'deepseek-v4-flash'} else model


def model_catalog_snapshot() -> dict:
    """Explicitly configured model; no unverified /models call to Kouri."""
    return {'data': [{'id': MODEL_SDK_ID}], 'source': model_api_base_url(),
            'model_requests': 0, 'catalog_mode': 'configured'}


def model_catalog_url() -> str:
    return model_api_url(MODEL_CATALOG_PATH)


def model_chat_path() -> str:
    return MODEL_CHAT_PATH


def model_chat_url() -> str:
    return model_api_url(model_chat_path())
