import importlib.util
import json
import os

import pytest

from src.adapters import geneloop_privacy as privacy
from src.adapters.rsi_privacy_candidates import OfficialTools
from src.adapters.rsi_privacy_context import address_spans, resolve_overlaps


def test_contact_and_social_context_is_local_and_preserves_record_shape(monkeypatch):
    monkeypatch.setattr(privacy, '_scan', lambda _: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    source = {
        'contacts': [
            {'name': '样例人甲', 'phone': 19900000001, 'email': 'person@example.invalid',
             'shipping_address': {'city': '北京市', 'street': '示例路', 'building': 5, 'room': 702}},
            {'platform': '微信', 'handle': 'fictional-account-123'},
            {'platform': 'QQ', 'value': 123456789},
        ],
        'summary': {'name': 'RMSE', 'value': 0.12, 'room': 8},
    }
    snapshot = json.dumps(source, ensure_ascii=False)
    out = privacy.learning_view(source)
    assert out['contacts'][0] == {
        'name': '<PERSON_1>', 'phone': '<PHONE_NUMBER_1>', 'email': '<EMAIL_ADDRESS_1>',
        'shipping_address': {'city': '<LOCATION_1>', 'street': '<LOCATION_2>',
                             'building': '<LOCATION_3>', 'room': '<LOCATION_4>'},
    }
    assert out['contacts'][1:] == [
        {'platform': '微信', 'handle': '<PRIVATE_ID_1>'},
        {'platform': 'QQ', 'value': '<PRIVATE_ID_2>'},
    ]
    assert out['summary'] == source['summary']
    assert privacy.learning_view(out) == out
    assert json.dumps(source, ensure_ascii=False) == snapshot


def test_unknown_members_of_explicit_identity_records_keep_whole_field_protection(monkeypatch):
    monkeypatch.setattr(privacy, '_scan', lambda _: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    out = privacy.learning_view({
        'address': {'street': '样例路', 'other': {'details': '未识别的住址'}},
        '联系人': {'昵称': '样例昵称', 'unknown': '未识别的账号'},
        'report': {'name': 'RMSE', 'email': None},
    })
    assert out['address'] == '<LOCATION_1>'
    assert out['联系人'] == '<PERSON_1>'
    assert out['report'] == {'name': 'RMSE', 'email': None}


@pytest.mark.parametrize('address', [
    '北京市海淀区示例大街27号院3栋2单元502室',
    '上海市徐汇区样例路48号B座16层1601室',
    '成都市武侯区测试小区7幢4单元301室',
    '虚构花园C座12层1204室',
    '合肥市蜀山区金禾巷31号，青棠小区南区6栋2单元1204房',
    '长沙市开福区兰渡路9号，星白苑8-1-1703',
    '徐州市泉山区，清沅里6-2-1307',
    '宁波市江北区承云路29号、雾荷苑B座东门3单元508室',
])
def test_address_components_span_ends_before_next_instruction(address):
    text = '寄到' + address + '，保留帧率24 fps。'
    assert [text[a:b] for a, b in address_spans(text)] == [address]
    assert not address_spans('北京市按季度展示指标，图表编号3号。')


def test_address_does_not_absorb_an_unrelated_numbered_item():
    address = '宁波市海曙区临星路18号'
    text = f'请寄到{address}，清点表第2栋；保留图片尺寸。'
    assert [text[left:right] for left, right in address_spans(text)] == [address]


def test_category_resolution_does_not_use_unrelated_model_score():
    analyzer = pytest.importorskip('presidio_analyzer')
    match = analyzer.RecognizerResult
    rows = resolve_overlaps([
        match('PERSON', 3, 11, 1.0),
        match('LOCATION', 0, 17, 0.4, recognition_metadata={'recognizer_name':'GeneLoopDetailedAddress'}),
        match('PHONE_NUMBER', 18, 29, 0.4),
        match('PERSON', 23, 29, 1.0),
    ])
    assert [(x.entity_type, x.start, x.end) for x in rows] == [('LOCATION', 0, 17), ('PHONE_NUMBER', 18, 29)]


@pytest.mark.parametrize('decisions,reason', [
    ((0, 1), 'credential_review_required'),
    ((1, 1), 'credential_detected'),
])
def test_reviewer_blocks_weak_and_confirmed_candidates(decisions, reason, monkeypatch):
    backend = object.__new__(OfficialTools)
    backend.credential_decisions = lambda _: decisions
    monkeypatch.setattr(privacy, '_scan', backend.scan)
    with pytest.raises(privacy.PrivacyRejected) as exc:
        privacy.learning_view({'text': 'synthetic payload'})
    assert exc.value.reason == reason
    assert exc.value.detector == 'credsweeper'


ACTUAL = bool(os.environ.get('SSS_RSI_GITLEAKS')) and importlib.util.find_spec('presidio_analyzer') is not None


@pytest.mark.skipif(not ACTUAL, reason='requires pinned local Presidio and Gitleaks')
@pytest.mark.parametrize(('body', 'label'), [
    ('{{"client-secret": "{literal}", "format": "svg"}}', '"client-secret":'),
    ('export SERVICE_SECRET="{literal}"\nformat=svg', 'SERVICE_SECRET='),
    ("login_password='{literal}'\nformat=svg", 'login_password='),
    ("create user fixture identified by '{literal}'\nformat=svg", 'identified by'),
    ("settings.setPassword('{literal}')\nformat=svg", 'setPassword('),
])
def test_embedded_credential_value_is_masked_without_removing_its_field(body, label):
    from src.adapters.rsi_text_privacy import anonymize_text

    literal = 'synthetic-value-for-unit-test'
    text = '保留表格。\n' + body.format(literal=literal)
    result = anonymize_text(text)
    assert literal not in result
    assert label in result
    assert 'svg' in result


@pytest.mark.skipif(not ACTUAL, reason='requires pinned local Presidio and Gitleaks')
def test_contextual_name_preserves_temporal_and_organization_phrases():
    from src.adapters.rsi_text_privacy import anonymize_text

    result = anonymize_text('请确认是梁清序审阅了初稿。确认是正在审核的版本。确认由质检中心签收。')
    assert '梁清序' not in result
    assert '正在审核' in result
    assert '质检中心' in result


@pytest.mark.skipif(not ACTUAL, reason='requires pinned local Presidio and Gitleaks')
def test_inline_basic_identifiers_and_complete_address_keep_task_text():
    values = ['19900000001', 'person@example.invalid', '00000020000101234X',
              'fictionalQQid', '123456789', '北京市海淀区示例大街27号院3栋2单元502室']
    text = (f'手机号：{values[0]}，邮箱：{values[1]}，身份证号：{values[2]}，'
            f'微信号：{values[3]}，QQ号：{values[4]}。寄到{values[5]}，保留 24 fps。')
    result = privacy.learning_view({'text': text})['text']
    assert all(value not in result for value in values)
    assert '<LOCATION_1>，保留 24 fps。' in result
    assert '502室' not in result
