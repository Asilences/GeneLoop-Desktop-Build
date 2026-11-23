"""Counter/proxy diagnostics, no paid calls or fabricated billing settlement."""
import json
import pytest
from src.adapters import deepseek_cost_gate
from src.adapters.model_usage import normalize_usage, cost_evidence, summarize_receipts, recorded_task_usage


def reported():
    # The observed SDK split was 1124 new + 22400 cached; total also had +59.
    return {'prompt_tokens': 23524, 'completion_tokens': 96, 'total_tokens': 23679,
            'prompt_tokens_details': {'cached_tokens': 22400}}


def test_standard_cache_is_shared_by_web_and_file_without_rewriting_total():
    usage = deepseek_cost_gate.response_usage('application/json', json.dumps({'usage': reported()}).encode())
    assert usage['prompt_cache_hit_tokens'] == 22400
    assert usage['prompt_cache_miss_tokens'] == 1124
    assert usage['total_tokens'] == 23679
    with pytest.raises(ValueError, match='inconsistent'):
        deepseek_cost_gate.observed_peak_cost('deepseek-flash', usage)
    evidence = cost_evidence('deepseek-flash', usage, {'deepseek-flash': (.30, 1.20)}, {'deepseek-flash': .006})
    assert evidence['status'] == 'unclassified_tokens' and evidence['unclassified_tokens'] == 59
    assert evidence['reported_component_proxy_usd'] == pytest.approx(.0005868)
    assert evidence['conditional_proxy_upper_usd'] == pytest.approx(.0006576)
    assert evidence['invoice_usd'] is None


@pytest.mark.parametrize('cache', [-1, 23525, True, 1.5])
def test_invalid_standard_cache_is_not_forged_into_valid_usage(cache):
    value = reported(); value['prompt_tokens_details']['cached_tokens'] = cache
    assert normalize_usage(value) == {}


def test_conflicting_cache_dialects_fail_and_partial_legacy_split_is_derived():
    value = reported(); value['prompt_cache_hit_tokens'] = 7
    assert normalize_usage(value) == {}
    value = reported(); value['prompt_cache_miss_tokens'] = 1125
    assert normalize_usage(value) == {}
    value = reported(); del value['prompt_tokens_details']; value['prompt_cache_miss_tokens'] = 1124
    assert normalize_usage(value)['prompt_cache_hit_tokens'] == 22400


def test_summary_keeps_unknown_response_and_anomalous_counter_distinct():
    usage = normalize_usage(reported())
    summary = summarize_receipts([{'model': 'flash', 'response_status': 200, 'response_usage': usage},
                                  {'model': 'flash', 'response_status': 502, 'response_usage': {}}],
                                 {'flash': (.30, 1.20)}, {'flash': .006})
    assert summary['reported_usage']['prompt_tokens'] == 23524
    assert summary['usage_anomaly_requests'] == 1 and summary['unusable_usage_requests'] == 1
    assert summary['reported_component_proxy_usd'] == pytest.approx(.0005868)
    assert summary['conditional_proxy_upper_usd'] is None


def test_complete_standard_cache_settles_at_configured_cache_price(tmp_path):
    usage = reported(); usage['total_tokens'] -= 59
    usage = deepseek_cost_gate.response_usage('text/event-stream', b'data: '+json.dumps({'usage': usage}).encode()+b'\n\ndata: [DONE]\n\n')
    state = deepseek_cost_gate.State(cap_usd=None, output_cap=100, record=tmp_path/'ledger.jsonl')
    book = state.book(b'{"model":"deepseek-flash","max_tokens":100,"messages":[]}')
    actual, released = state.settle(book[0], book[1], 200, usage)
    assert actual == pytest.approx(.0005868) and released > 0


def test_recorded_rate_snapshot_survives_price_changes_and_ignores_free_file_calls(tmp_path):
    usage = normalize_usage(reported())
    evidence = cost_evidence('flash', usage, {'flash': (.30, 1.20)}, {'flash': .006})
    record = tmp_path/'ledger.jsonl'
    rows = [{'task_id': 'owned', 'request_id': 1, 'model': 'flash', 'response_status': 200,
             'response_usage': usage, 'cost_evidence': evidence},
            {'task_id': 'owned', 'kind': 'files_api', 'response_status': 200},
            {'task_id': 'other', 'request_id': 2, 'model': 'flash', 'response_status': 500}]
    record.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
    summary = recorded_task_usage(record, 'owned', {'flash': (30, 120)}, {'flash': .6})
    assert summary['reported_component_proxy_usd'] == pytest.approx(.0005868)
    assert summary['current_rate_fallback_requests'] == summary['unusable_usage_requests'] == 0
    assert summary['reported_usage_requests'] == 1


def test_legacy_receipt_price_fallback_is_explicit_not_a_historical_settlement():
    summary = summarize_receipts([{'model': 'flash', 'response_status': 200, 'response_usage': normalize_usage(reported())}],
                                 {'flash': (.30, 1.20)}, {'flash': .006})
    assert summary['current_rate_fallback_requests'] == 1 and summary['invoice_usd'] is None
