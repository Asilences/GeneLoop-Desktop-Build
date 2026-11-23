import copy
import json
from pathlib import Path
import subprocess
import os
import importlib.util

import pytest
from jsonschema import Draft202012Validator, ValidationError

from src.adapters.rsi_privacy_policy import POLICY, ROOT
from src.adapters import geneloop_privacy as privacy
from src.adapters import rsi_privacy_tools as tools


def test_policy_rejects_unknown_fields_and_preserves_the_declared_benchmark_scope():
    schema=json.loads((ROOT/'schemas/geneloop-privacy-policy.schema.json').read_text())
    validator=Draft202012Validator(schema)
    invalid=copy.deepcopy(POLICY);invalid['text']['bypass']='unapproved'
    with pytest.raises(ValidationError):validator.validate(invalid)
    frozen=json.loads((ROOT/'scripts/privacy-benchmark/policy-scope-v1.json').read_text())
    assert POLICY['text']['declared_categories']==frozen['protected_text_categories']
    assert POLICY['text']['conditional_categories']==frozen['conditional_on_identity_context']
    assert POLICY['text']['conditional_context_implemented'] is False


@pytest.mark.parametrize('failure,reason',[
    (subprocess.CalledProcessError(1,['not-printed']),'credential_detected'),
    (subprocess.CalledProcessError(2,['not-printed']),'scanner_error'),
    (subprocess.TimeoutExpired(['not-printed'],8),'scanner_timeout'),
    (tools.PrivacyToolError('privacy_scanner_unverified'),'tool_unverified'),
    (tools.PrivacyToolError('privacy_dependency_version_mismatch'),'dependency_unavailable'),
])
def test_private_reason_codes_separate_unavailable_tools_from_detection_without_changing_public_error(monkeypatch,failure,reason):
    def failed(_):raise failure
    monkeypatch.setattr(privacy,'_scan',failed)
    with pytest.raises(privacy.PrivacyRejected) as error:
        privacy.learning_view({'text':'synthetic plain input'})
    assert error.value.reason==reason
    assert str(error.value)=='geneloop_privacy_rejected'
    assert 'not-printed' not in str(error.value)


def test_explicit_secret_and_ambiguous_input_have_distinct_private_reasons(monkeypatch):
    monkeypatch.setattr(privacy,'_scan',lambda _:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value)
    for value,reason in [({'password':'diagnostic-only'},'credential_detected'),
                         ({'text':'{"password":"diagnostic-only","password":""}'},'ambiguous_json')]:
        with pytest.raises(privacy.PrivacyRejected) as error:privacy.learning_view(value)
        assert error.value.reason==reason and str(error.value)=='geneloop_privacy_rejected'


ACTUAL_TOOLS=bool(os.environ.get('SSS_RSI_GITLEAKS')) and importlib.util.find_spec('presidio_analyzer') is not None


@pytest.mark.skipif(not ACTUAL_TOOLS,reason='requires actual pinned local privacy tools')
@pytest.mark.parametrize('text',[
    '银行卡号：4111111111111112，保留 n=128 和 mean ± SD。',
    '登记银行卡4111111111111112用于核对，保留 24 fps。',
    'Credit card: 4111 1111 1111 1112; keep RMSE and 24 fps.',
])
def test_contextual_card_recognition_does_not_treat_invalid_checksum_as_safe(text):
    result=privacy.learning_view({'text':text})['text']
    assert '4111111111111112' not in result and '4111 1111 1111 1112' not in result
    for keep in ['n=128','mean ± SD','24 fps','RMSE']:
        if keep in text:assert keep in result


@pytest.mark.skipif(not ACTUAL_TOOLS,reason='requires actual pinned local privacy tools')
def test_unlabeled_long_metric_is_not_masked_by_weak_contextual_candidate():
    text='Set the trial seed to 4111111111111112; keep n=128 and RMSE.'
    assert privacy.learning_view({'text':text})['text']==text


@pytest.mark.skipif(not ACTUAL_TOOLS,reason='requires actual pinned local privacy tools')
def test_canonical_identity_labels_keep_structured_and_prose_aliases_consistent():
    address='南京市雨花台区测试路123号'
    result=privacy.learning_view({'银行卡号':'4111111111111112','home_address':address,
        'text':'银行卡号：4111111111111112；住址：'+address+'；保留 n=128。'})
    assert result['银行卡号'] in result['text']
    assert result['home_address'] in result['text']
    assert 'n=128' in result['text']
