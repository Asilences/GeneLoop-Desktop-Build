"""Provider counters and configured-price evidence; never an invoice or a cap bypass."""
import math
import json
import re
from decimal import Decimal
from urllib.parse import urlsplit

FIELDS = ('prompt_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens', 'total_tokens')


def _identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9._:/-]{1,256}', value) else None


def _number(value):
    if type(value) in (int, float):
        return abs(value) < 1e100 and math.isfinite(value)
    return isinstance(value, str) and re.fullmatch(r'-?\d{1,40}(?:\.\d{1,40})?(?:[eE][+-]?\d{1,3})?', value) is not None and Decimal(value).is_finite() and abs(Decimal(value)) < Decimal('1e100')


def _raw_usage(value):
    """Keep original numeric fields, not response content or arbitrary strings."""
    omitted = 0
    remaining = 128

    def project(node, depth=0):
        nonlocal omitted, remaining
        result = {}
        for key, item in node.items():
            if (remaining <= 0 or not isinstance(key, str) or
                    re.fullmatch(r'[a-z][a-z0-9_]{0,63}', key) is None or
                    (depth == 0 and key not in {'cost', 'total_cost', 'cost_details', 'currency', 'cost_currency', 'unit', 'cost_unit'}
                     and not key.endswith(('_tokens', '_tokens_details')))):
                omitted += 1
                continue
            remaining -= 1
            if _number(item):
                result[key] = item
            elif key in {'currency', 'cost_currency'} and isinstance(item, str) and re.fullmatch(r'[A-Z]{3}', item):
                result[key] = item
            elif key in {'unit', 'cost_unit'} and item in ('currency', 'credits', 'points', 'micro_currency', 'milli_currency'):
                result[key] = item
            elif isinstance(item, dict) and depth < 3:
                result[key] = project(item, depth + 1)
            else:
                omitted += 1
        return result

    raw = project(value)
    return raw, 'filtered' if omitted else 'complete', omitted


def upstream_cost(raw):
    """A supplier-reported amount never becomes USD or an invoice by inference."""
    value = raw.get('cost')
    container = value if isinstance(value, dict) else raw
    amount = container.get('amount') if isinstance(value, dict) else value
    currency = container.get('currency', container.get('cost_currency', raw.get('currency', raw.get('cost_currency', 'unknown'))))
    unit = container.get('unit', container.get('cost_unit', raw.get('unit', raw.get('cost_unit', 'unknown'))))
    currency = currency if isinstance(currency, str) and re.fullmatch(r'[A-Z]{3}', currency) else 'unknown'
    unit = unit if unit in ('currency', 'credits', 'points', 'micro_currency', 'milli_currency') else 'unknown'
    valid = _number(amount)
    return {'amount': amount if valid else None, 'currency': currency, 'unit': unit,
            'status': ('reported' if currency != 'unknown' and unit != 'unknown' else 'reported_unit_unknown') if valid else 'unavailable',
            'source': 'usage.cost', 'basis': 'upstream_report_not_invoice', 'invoice_usd': None}


class UpstreamEvidence:
    """Per-request bounded metadata projection; never stores message/choice text."""
    def __init__(self, body, target):
        request = json.loads(body) if body else {}
        route = urlsplit(target)
        self.value = {'schema_version': 1, 'requested_model': _identifier(request.get('model')),
                      'route': {'scheme': route.scheme, 'host': route.hostname, 'port': route.port, 'path': route.path},
                      'response_model': None, 'response_id': None, 'system_fingerprint': None,
                      'request_ids': {}, 'http_status': None, 'outcome': 'not_sent',
                      'response_complete': False, 'raw_usage': None, 'raw_usage_status': 'missing',
                      'omitted_usage_fields': 0, 'reported_cost': upstream_cost({})}

    def headers(self, status, headers):
        self.value.update(http_status=status, outcome='http_response')
        for key in ('x-request-id', 'request-id', 'x-correlation-id', 'x-amzn-requestid', 'x-amz-request-id', 'cf-ray'):
            value = _identifier(headers.get(key))
            if value is not None:
                self.value['request_ids'][key] = value

    def packet(self, packet):
        if not isinstance(packet, dict):
            return
        for source, destination in (('model', 'response_model'), ('id', 'response_id'), ('system_fingerprint', 'system_fingerprint')):
            value = _identifier(packet.get(source))
            if value is not None:
                self.value[destination] = value
        if isinstance(packet.get('usage'), dict):
            raw, status, omitted = _raw_usage(packet['usage'])
            self.value.update(raw_usage=raw, raw_usage_status=status, omitted_usage_fields=omitted,
                              reported_cost=upstream_cost(raw))

    def body(self, content_type, answer):
        if 'json' in content_type:
            try:
                self.packet(json.loads(answer))
            except (ValueError, TypeError):
                pass

    def transport_error(self, error, content_type):
        partial = getattr(error, 'partial', None)
        if isinstance(partial, bytes):
            self.body(content_type, partial)
        self.value.update(outcome='transport_error', transport_error_type=type(error).__name__)


def summarize_upstream_costs(rows):
    reported = missing = unknown = incomplete = 0
    totals = {}
    for row in rows:
        upstream = row.get('upstream_response') or {}
        cost = upstream.get('reported_cost') or {}
        if not _number(cost.get('amount')):
            missing += 1
            continue
        reported += 1
        complete = upstream.get('response_complete') and upstream.get('usage_parse_valid', True)
        if not complete:
            incomplete += 1
        if cost.get('currency', 'unknown') == 'unknown' or cost.get('unit', 'unknown') == 'unknown':
            unknown += 1
        elif complete:
            key = (cost['currency'], cost['unit'])
            total, count = totals.get(key, (Decimal(0), 0))
            totals[key] = total + Decimal(str(cost['amount'])), count + 1
    return {'reported_cost_requests': reported, 'missing_cost_requests': missing,
            'unit_unknown_requests': unknown, 'incomplete_response_cost_requests': incomplete,
            'totals_by_currency_and_unit': [{'currency': currency, 'unit': unit, 'amount': str(total), 'requests': count}
                                          for (currency, unit), (total, count) in sorted(totals.items())],
            'aggregation_scope': 'complete_responses_with_explicit_currency_and_unit_only',
            'basis': 'upstream_report_not_invoice', 'invoice_usd': None}


def accounting_breakdown(reserved_usd, summary):
    return {'budget_reservation': {'amount': reserved_usd, 'currency': 'USD', 'basis': 'conservative_budget_accounting_not_spend'},
            'configured_estimate': {'amount': summary['reported_component_proxy_usd'], 'currency': 'USD',
                                    'basis': 'configured_rates_not_provider_bill', 'unusable_usage_requests': summary['unusable_usage_requests'],
                                    'usage_anomaly_requests': summary['usage_anomaly_requests'], 'unclassified_tokens': summary['unclassified_tokens']},
            'upstream_reported': summary['upstream_reported_costs'], 'invoice_usd': None}


def count(value):
    return type(value) is int and value >= 0


def normalize_usage(usage):
    if not isinstance(usage, dict):
        return {}
    if 'input_tokens' in usage and 'output_tokens' in usage:
        values = [usage.get(key, 0) for key in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens')]
        if not all(count(value) for value in values):
            return {}
        fresh, created, cached, output = values
        return dict(zip(FIELDS, (fresh + created + cached, cached, fresh + created, output, fresh + created + cached + output)))
    values = {field: usage.get(field) for field in FIELDS}
    if not all(count(values[key]) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')):
        return {}
    details = usage.get('prompt_tokens_details')
    standard = details.get('cached_tokens') if isinstance(details, dict) else None
    hit, miss = values['prompt_cache_hit_tokens'], values['prompt_cache_miss_tokens']
    if any(value is not None and not count(value) for value in (hit, miss)):
        return {}
    if standard is not None:
        if not count(standard) or standard > values['prompt_tokens'] or hit is not None and hit != standard:
            return {}
        hit = standard
    if hit is None and miss is None:
        hit = 0
    if hit is None:
        if not count(miss):
            return {}
        hit = values['prompt_tokens'] - miss
    if miss is None:
        miss = values['prompt_tokens'] - hit if count(hit) else None
    values.update(prompt_cache_hit_tokens=hit, prompt_cache_miss_tokens=miss)
    if not all(count(value) for value in values.values()) or hit + miss != values['prompt_tokens']:
        return {}
    # Preserve even an inconsistent reported total. Do not invent output tokens.
    return values


def cost_evidence(model, usage, rates, cache_rates):
    empty = {'status': 'unusable', 'invoice_usd': None, 'basis': 'configured_rates_not_provider_bill'}
    if model not in rates or not isinstance(usage, dict) or not all(count(usage.get(key)) for key in FIELDS):
        return empty
    if usage['prompt_cache_hit_tokens'] + usage['prompt_cache_miss_tokens'] != usage['prompt_tokens']:
        return empty
    delta = usage['total_tokens'] - usage['prompt_tokens'] - usage['completion_tokens']
    if delta < 0:
        return {**empty, 'reason': 'reported_total_below_components', 'unclassified_tokens': delta}
    input_rate, output_rate = rates[model]
    cache_rate = cache_rates.get(model, input_rate)
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in (input_rate, output_rate, cache_rate)):
        return empty
    known = (usage['prompt_cache_miss_tokens'] * input_rate + usage['prompt_cache_hit_tokens'] * cache_rate + usage['completion_tokens'] * output_rate) / 1_000_000
    extra = delta * max(input_rate, output_rate, cache_rate) / 1_000_000
    return {**empty, 'status': 'complete' if not delta else 'unclassified_tokens', 'reported_tokens': dict(usage),
            'rates_usd_per_million': {'input': input_rate, 'cached_input': cache_rate, 'output': output_rate},
            'unclassified_tokens': delta, 'reported_component_proxy_usd': known,
            'unclassified_token_upper_usd': extra, 'conditional_proxy_upper_usd': known + extra}


def summarize_receipts(rows, rates, cache_rates):
    totals = {key: 0 for key in FIELDS}
    known = extra = 0.0
    usable = anomalous = unusable = delta = legacy = 0
    for row in rows:
        model = row.get('model')
        snapshot = row.get('cost_evidence', {}).get('rates_usd_per_million')
        if isinstance(snapshot, dict) and set(snapshot) == {'input', 'cached_input', 'output'}:
            row_rates, row_cache = {model: (snapshot['input'], snapshot['output'])}, {model: snapshot['cached_input']}
        else:
            row_rates, row_cache = rates, cache_rates
            legacy += 1
        evidence = cost_evidence(model, row.get('response_usage'), row_rates, row_cache) if row.get('response_status') == 200 else {'status': 'unusable'}
        if evidence['status'] == 'unusable':
            unusable += 1
            continue
        usable += 1
        anomalous += evidence['status'] != 'complete'
        delta += evidence['unclassified_tokens']
        known += evidence['reported_component_proxy_usd']
        extra += evidence['unclassified_token_upper_usd']
        for key in FIELDS:
            totals[key] += evidence['reported_tokens'][key]
    return {'reported_usage': totals, 'reported_usage_requests': usable, 'unusable_usage_requests': unusable,
            'usage_anomaly_requests': anomalous, 'unclassified_tokens': delta,
            'reported_component_proxy_usd': known, 'unclassified_token_upper_usd': extra,
            'conditional_proxy_upper_usd': known + extra if not unusable else None,
            'current_rate_fallback_requests': legacy, 'scope': 'received_model_responses',
            'basis': 'recorded_rates_with_explicit_current_rate_fallback_not_provider_bill', 'invoice_usd': None,
            'upstream_reported_costs': summarize_upstream_costs(rows)}


def recorded_task_usage(record, task_id, rates, cache_rates):
    rows = [json.loads(line) for line in record.read_text(encoding='utf-8').splitlines() if line.strip()] if record.exists() else []
    return summarize_receipts([row for row in rows if row.get('task_id') == task_id and type(row.get('request_id')) is int and 'response_status' in row], rates, cache_rates)
