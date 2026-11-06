"""Single source for the Kouri API address, model ID and credential."""
from __future__ import annotations

import math
import os
import re
from urllib.parse import urlsplit


MODEL_API_ROOT = 'https://api.kourichat.com'
MODEL_API_PREFIX = '/v1'
MODEL_API_KEY_ENV = 'KOURI_API_KEY'
MODEL_SDK_ID = 'deepseek-flash'
MODEL_WIRE_ID = 'deepseek-v4.1-flash'
MODEL_CATALOG_PATH = '/v1/models'
MODEL_CHAT_PATH = '/v1/chat/completions'

# Add Kouri models here. The first id is retained for existing Harness sessions;
# new ids may use their Kouri wire id directly. Prices are reservation estimates,
# not verified Kouri billing rates. Do not list a model without a deliberate rate.
KOURI_MODELS = (
    {'id': MODEL_SDK_ID, 'wire_id': MODEL_WIRE_ID,
     'label': 'DeepSeek V4.1 Flash',
     'context_window': 1_000_000, 'max_output_tokens': 393_216,
     'input_modalities': ('text', 'image'),
     'supported_reasoning_efforts': ('off', 'low', 'high', 'max'),
     'input_usd_per_million': 0.30, 'cache_hit_usd_per_million': 0.006,
     'output_usd_per_million': 1.20},
)


def model_routes() -> tuple[dict, ...]:
    ids = [row['id'] for row in KOURI_MODELS]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError('Kouri model ids must be unique and nonempty')
    for row in KOURI_MODELS:
        if (not re.fullmatch(r'[A-Za-z0-9._-]+', row['id']) or
                not re.fullmatch(r'[A-Za-z0-9._:/-]+', row['wire_id']) or
                not isinstance(row['label'], str) or not row['label'] or
                type(row['context_window']) is not int or row['context_window'] < 1 or
                type(row['max_output_tokens']) is not int or row['max_output_tokens'] < 1 or
                not row['input_modalities'] or
                set(row['input_modalities']) - {'text', 'image'} or
                len(row['input_modalities']) != len(set(row['input_modalities'])) or
                not row['supported_reasoning_efforts'] or
                'off' not in row['supported_reasoning_efforts'] or
                set(row['supported_reasoning_efforts']) - {'off', 'low', 'high', 'max'} or
                len(row['supported_reasoning_efforts']) != len(set(row['supported_reasoning_efforts'])) or
                any(type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0
                    for key in ('input_usd_per_million', 'cache_hit_usd_per_million', 'output_usd_per_million')) or
                row['input_usd_per_million'] == 0 or row['output_usd_per_million'] == 0 or
                row['cache_hit_usd_per_million'] > row['input_usd_per_million']):
            raise ValueError('invalid Kouri model route configuration')
    return KOURI_MODELS


def model_ids() -> set[str]:
    return {row['id'] for row in model_routes()}


def model_price_rates() -> tuple[dict[str, tuple[float, float]], dict[str, float]]:
    routes = model_routes()
    return ({row['id']: (row['input_usd_per_million'], row['output_usd_per_million']) for row in routes},
            {row['id']: row['cache_hit_usd_per_million'] for row in routes})


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
    if model == 'deepseek-v4-flash':
        return MODEL_WIRE_ID  # Historical SDK name in saved tasks.
    return next((row['wire_id'] for row in model_routes() if row['id'] == model), model)


def model_catalog_snapshot() -> dict:
    """Explicitly configured models; no unverified /models call to Kouri."""
    return {'data': [{'id': row['id'], 'name': row['label'],
                      'context_window': row['context_window'],
                      'max_output_tokens': row['max_output_tokens'],
                      'input_modalities': list(row['input_modalities']),
                      'supported_reasoning_efforts': list(row['supported_reasoning_efforts'])}
                     for row in model_routes()], 'source': model_api_base_url(),
            'model_requests': 0, 'catalog_mode': 'configured'}


def model_catalog_url() -> str:
    return model_api_url(MODEL_CATALOG_PATH)


def model_chat_path() -> str:
    return MODEL_CHAT_PATH


def model_chat_url() -> str:
    return model_api_url(model_chat_path())
