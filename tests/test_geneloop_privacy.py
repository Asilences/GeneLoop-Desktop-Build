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
                                 {'nested':{'token':'synthetic-private'}}, {'password':0},
                                 {'nested':{'x_api_key':'synthetic-private'}},
                                 {'token':123456},
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
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'input_schema':{'type':'object','properties':{'Alice':{},'Bob':{}}}})
    def failed(value):
        raise RuntimeError('/private/account synthetic-secret')
    monkeypatch.setattr(privacy, '_scan', failed)
    with pytest.raises(privacy.PrivacyRejected) as error:
        privacy.learning_view({'text': 'do not fall back'})
    assert str(error.value) == 'geneloop_privacy_rejected'


def test_media_bytes_are_omitted_and_technical_file_types_remain(monkeypatch):
    monkeypatch.setattr(privacy,'_scan',lambda value:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value)
    source={'filename':'private-person.ipynb','image':'data:image/png;base64,U2FtcGxl',
            'bytes':[1,2,3], 'address':'0xdeadbeef','nested':{'bank_account':'synthetic-account'}}
    result=privacy.learning_view(source)
    assert result['filename'].endswith('.ipynb') and 'private-person' not in result['filename']
    assert result['image']==result['bytes']=='<BINARY_OMITTED>'
    assert result['address']=='0xdeadbeef' and result['nested']['bank_account'].startswith('<FINANCIAL_ACCOUNT_')
    assert privacy.learning_view(result)==result
    assert privacy.learning_view({'prompt_tokens':512,'has_token':True})=={'prompt_tokens':512,'has_token':True}


def test_json_inside_stdout_cannot_bypass_the_same_recursive_rule(monkeypatch):
    monkeypatch.setattr(privacy,'_scan',lambda value:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value)
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'stdout':json.dumps({'headers':{'X-API-Key':'synthetic-private'}})})
    source={'stdout':json.dumps({'email':'owner@example.com','count':2})}
    result=json.loads(privacy.learning_view(source)['stdout'])
    assert result['email'].startswith('<EMAIL_ADDRESS_') and result['count']==2


def test_schema_declarations_and_digest_handles_keep_protocol_meaning(monkeypatch):
    monkeypatch.setattr(privacy,'_scan',lambda value:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_: '<PERSON>' if value=='integer' else value)
    value={'input_schema':{'type':'object','properties':{'email':{'type':'string'},'offset':{'type':'integer'}}},
           'id':'a'*64,'task_id':'task_'+'b'*24}
    assert privacy.learning_view(value)==value
    value['input_schema']['properties']['email']['default']='owner@example.com'
    assert privacy.learning_view(value)['input_schema']['properties']['email']['default'].startswith('<EMAIL_ADDRESS_')
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'parameters':{'type':'object','properties':{'password':{'type':'string','default':'synthetic'}}}})
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'parameters':{'type':'object','properties':{'password':{
            'type':'array','items':{'type':'string','default':'synthetic'}}}}})


def test_quoted_json_source_remains_valid_after_path_redaction(monkeypatch):
    monkeypatch.setattr(privacy,'_scan',lambda value:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value.replace('/private/input','<PRIVATE_REFERENCE>'))
    source=json.dumps('literal = "/private/input"')
    assert json.loads(privacy.learning_view({'content':source})['content'])=='literal = "<PRIVATE_REFERENCE>"'


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


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual local Presidio and Gitleaks')
def test_code_comment_literal_is_kept_while_private_file_path_is_removed():
    source={'code':'literal = "// header"','file_path':'/home/private-owner/main.py'}
    result=privacy.learning_view(source)
    assert result['code']==source['code']
    assert '/home/private-owner' not in result['file_path']


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
    assert privacy.learning_view(result['content']) == result['content']
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


def test_registered_tool_metadata_cannot_bypass_credential_admission(monkeypatch):
    name='synthetic-credential-tool'
    def scan(value):
        if name in value:raise ValueError('synthetic scanner rejection')
    monkeypatch.setattr(privacy,'_scan',scan)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value)
    source=events('task',{}, {'text':'result'})
    source[1]['data']['name']=name
    with pytest.raises(privacy.PrivacyRejected):
        trace.project(source,'future-mcp','completed',[name])
