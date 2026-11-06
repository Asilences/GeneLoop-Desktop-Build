"""Transport/guard units and separately marked actual local-tool diagnostics."""
import json
import os
from pathlib import Path
import importlib.util

import pytest

from src.adapters import geneloop_privacy as privacy
from src.adapters import geneloop_learning_trace as trace


def test_recursive_keys_values_numeric_identity_and_local_relationships(monkeypatch):
    monkeypatch.setattr(privacy, '_scan', lambda value: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value.replace('owner@example.com', '<EMAIL>'))
    value = {'owner@example.com': [{'phone': 13800138000, 'task_id': 'private-task'},
                                  {'task_id': 'private-task', 'other': 'owner@example.com'}], 'count': 3}
    result = privacy.learning_view(value)
    assert result['<EMAIL>'][0]['phone'].startswith('<PHONE_NUMBER_')
    assert result['<EMAIL>'][0]['task_id'] == result['<EMAIL>'][1]['task_id']
    assert result['<EMAIL>'][1]['other'] == '<EMAIL>' and result['count'] == 3
    assert value['owner@example.com'][0]['phone'] == 13800138000
    with pytest.raises(privacy.PrivacyRejected):
        privacy.admit_publication(value)


@pytest.mark.parametrize('value', [{'nested': {'access_token': 'synthetic-private'}},
                                 {'x': float('nan')}, {'x': object()}])
def test_invalid_or_secret_material_is_never_a_partial_success(monkeypatch, value):
    monkeypatch.setattr(privacy, '_scan', lambda value: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    with pytest.raises(privacy.PrivacyRejected, match='^geneloop_privacy_rejected$'):
        privacy.learning_view(value)


def test_scanner_failure_and_anonymized_key_collision_fail_closed(monkeypatch):
    monkeypatch.setattr(privacy, '_scan', lambda value: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: '<PERSON>')
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'Alice': 1, 'Bob': 2})
    def failed(value):
        raise RuntimeError('/private/account synthetic-secret')
    monkeypatch.setattr(privacy, '_scan', failed)
    with pytest.raises(privacy.PrivacyRejected) as error:
        privacy.learning_view({'text': 'do not fall back'})
    assert str(error.value) == 'geneloop_privacy_rejected'


def events(prompt, arguments, response):
    return [
        {'type':'user/message','data':{'source':{'kind':'user'},'content':[{'type':'text','text':prompt}]}},
        {'type':'tool/call','data':{'callId':'private-source-call','name':'mcp__diagnostic__analyze',
                                  'arguments':json.dumps(arguments,ensure_ascii=False)}},
        {'type':'tool/result','data':{'message':{'source':{'kind':'tool','callId':'private-source-call'},
            'content':[{'type':'tool-result','toolCallId':'private-source-call','isError':False,
                        'content':[{'type':'text','text':json.dumps(response,ensure_ascii=False)}]}]}}},
        {'type':'assistant/message','data':{'message':{'content':[{'type':'text','text':response['text']}]}}},
    ]


TOOLS = ['mcp__diagnostic__analyze']
CASES = [
    ('paper-proofreading','核对 references 与 Equation (12)，联系邮箱 owner@example.com。','Equation (12)'),
    ('ppt','姓名：王小明。保留 16:9 与 slide master，联系邮箱 owner@example.com。','16:9'),
    ('research-data-analysis','Fit y = 2*x + 1, show mean ± SD; email owner@example.com.','y = 2*x + 1'),
    ('files','按修改时间排序，保留扩展名，联系邮箱 owner@example.com。','按修改时间排序'),
    ('video-editing','Keep 24 fps, duration 12 seconds; contact owner@example.com.','24 fps'),
    ('coding','Fix def weighted_mean(values, weights): return sum(values); contact owner@example.com.','weighted_mean'),
    ('chat','用中文解释 recursion，联系邮箱 owner@example.com。','recursion'),
    ('new-scene','Use a stacked chart with 3 groups. Email owner@example.com.','stacked chart'),
    ('future-custom-mcp','Compute RMSE and R2, preserve units; email owner@example.com.','RMSE'),
]
LOCAL_TOOLS = bool(os.environ.get('SSS_RSI_GITLEAKS')) and importlib.util.find_spec('presidio_analyzer') is not None


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual local Presidio/spaCy models and Gitleaks')
@pytest.mark.parametrize('scene,prompt,keep', CASES)
def test_all_registered_and_future_scenes_keep_task_semantics(scene, prompt, keep):
    original = events(prompt, {'nested':[{'email':'owner@example.com','phone':13800138000}], 'threshold':0.05},
                      {'text': keep+' — owner@example.com', 'path':'/home/private-owner/report.pdf'})
    result = trace.project(original, scene, 'completed', TOOLS)
    rendered = json.dumps(result, ensure_ascii=False)
    for private in ['owner@example.com','13800138000','private-source-call','/home/private-owner/report.pdf','王小明']:
        assert private not in rendered
    assert keep in rendered and '0.05' in rendered
    assert result['nodes'] == [{'tool':TOOLS[0], 'outcome':'observed_success'}]
    assert 'owner@example.com' in json.dumps(original)
    structural = trace.project(original,scene,'completed',TOOLS,semantic=False)
    assert 'content' not in trace.sharing_object(structural,TOOLS)['trace']
    with pytest.raises(privacy.PrivacyRejected):
        trace.sharing_object(result,TOOLS)


def test_unknown_fields_or_forged_catalog_cannot_enter_a_shared_object(monkeypatch):
    monkeypatch.setattr(trace, 'admit_publication', lambda value: value)
    sample=trace.project(events('task',{}, {'text':'result'}),'future-mcp','completed',TOOLS,semantic=False)
    for bad in [{**sample,'nested':{'password':'synthetic'}}, {**sample,'status':'failed'},
                {**sample,'nodes':[{'tool':'mcp__private__unregistered','outcome':'observed_success'}]},
                {**sample,'nodes':[{'tool':TOOLS[0],'outcome':'observed_success','path':'/private'}]}]:
        with pytest.raises(privacy.PrivacyRejected):
            trace.sharing_object(bad,TOOLS)
