"""Single source for the Kouri API address, model ID and credential."""
from __future__ import annotations

import math
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


MODEL_API_ROOT = 'https://api.kourichat.com'
MODEL_API_PREFIX = '/v1'
MODEL_API_KEY_ENV = 'KOURI_API_KEY'
MODEL_SDK_ID = 'deepseek-flash'
MODEL_WIRE_ID = 'deepseek-v4.1-flash'
MODEL_CATALOG_PATH = '/v1/models'
MODEL_CHAT_PATH = '/v1/chat/completions'
EXTRA_MODELS_ENV = 'KOURI_EXTRA_MODELS_JSON'
MODELS_FILE_ENV = 'KOURI_MODELS_FILE'
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _parse_model_routes(raw: str, source: str) -> tuple[dict, ...]:
    if len(raw) > 65_536:
        raise ValueError(f'{source} is too large')
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f'{source} must be a JSON array') from error
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError(f'{source} must contain 1 to 32 models')
    allowed = {'id', 'wire_id', 'label', 'context_window', 'max_output_tokens',
               'input_modalities', 'supported_reasoning_efforts',
               'input_usd_per_million', 'cache_hit_usd_per_million',
               'output_usd_per_million'}
    required = {'id', 'context_window', 'max_output_tokens',
                'input_usd_per_million', 'output_usd_per_million'}
    result = []
    for row in rows:
        if not isinstance(row, dict) or required - row.keys() or row.keys() - allowed:
            raise ValueError(f'invalid model entry in {source}')
        model = row['id']
        result.append({**row,
                       'wire_id': row.get('wire_id', model),
                       'label': row.get('label', model),
                       'input_modalities': row.get('input_modalities', ['text']),
                       'supported_reasoning_efforts': row.get('supported_reasoning_efforts', ['off']),
                       'cache_hit_usd_per_million': row.get('cache_hit_usd_per_million',
                                                            row['input_usd_per_million'])})
    return tuple(result)


def _file_model_routes(name: str) -> tuple[dict, ...]:
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        with path.open('r', encoding='utf-8') as source:
            raw = source.read(65_537)
    except (OSError, UnicodeError) as error:
        raise ValueError(f'cannot read {MODELS_FILE_ENV} model configuration') from error
    return _parse_model_routes(raw, MODELS_FILE_ENV)


# Shared default template; prices remain estimates, not verified Kouri rates.
KOURI_MODELS = _file_model_routes('config/kouri-models.json')


def model_routes() -> tuple[dict, ...]:
    filename = os.environ.get(MODELS_FILE_ENV, '').strip()
    extra = os.environ.get(EXTRA_MODELS_ENV, '').strip()
    base = _file_model_routes(filename) if filename else KOURI_MODELS
    routes = (*base, *(_parse_model_routes(extra, EXTRA_MODELS_ENV) if extra else ()))
    ids = [row['id'] for row in routes]
    if not ids or any(not isinstance(model, str) for model in ids) or len(ids) != len(set(ids)):
        raise ValueError('Kouri model ids must be unique and nonempty')
    for row in routes:
        if (not isinstance(row['id'], str) or
                not re.fullmatch(r'[A-Za-z0-9._-]+', row['id']) or
                not isinstance(row['wire_id'], str) or
                not re.fullmatch(r'[A-Za-z0-9._:/-]+', row['wire_id']) or
                not isinstance(row['label'], str) or not row['label'].strip() or
                type(row['context_window']) is not int or row['context_window'] < 1 or
                type(row['max_output_tokens']) is not int or row['max_output_tokens'] < 1 or
                row['max_output_tokens'] > row['context_window'] or
                not isinstance(row['input_modalities'], (list, tuple)) or
                not row['input_modalities'] or
                any(not isinstance(value, str) for value in row['input_modalities']) or
                set(row['input_modalities']) - {'text', 'image'} or
                len(row['input_modalities']) != len(set(row['input_modalities'])) or
                not isinstance(row['supported_reasoning_efforts'], (list, tuple)) or
                not row['supported_reasoning_efforts'] or
                any(not isinstance(value, str) for value in row['supported_reasoning_efforts']) or
                'off' not in row['supported_reasoning_efforts'] or
                set(row['supported_reasoning_efforts']) - {'off', 'low', 'high', 'max'} or
                len(row['supported_reasoning_efforts']) != len(set(row['supported_reasoning_efforts'])) or
                any(type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0
                    for key in ('input_usd_per_million', 'cache_hit_usd_per_million', 'output_usd_per_million')) or
                row['input_usd_per_million'] == 0 or row['output_usd_per_million'] == 0 or
                row['cache_hit_usd_per_million'] > row['input_usd_per_million']):
            raise ValueError('invalid Kouri model route configuration')
    return routes


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
