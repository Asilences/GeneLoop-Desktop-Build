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
    source={'filename':'private-person.ipynb','relative_path':'private-person.ipynb','image':'data:image/png;base64,U2FtcGxl',
            'bytes':[1,2,3], 'address':'0xdeadbeef','nested':{'bank_account':'synthetic-account'}}
    result=privacy.learning_view(source)
    assert result['filename'].endswith('.ipynb') and 'private-person' not in result['filename']
    assert result['relative_path'] == result['filename']
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
           'record_evidence_id':'evidence_'+'c'*64,
           'id':'a'*64,'task_id':'task_'+'b'*24}
    assert privacy.learning_view(value)==value
    value['input_schema']['properties']['email']['default']='owner@example.com'
    assert privacy.learning_view(value)['input_schema']['properties']['email']['default'].startswith('<EMAIL_ADDRESS_')
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'parameters':{'type':'object','properties':{'password':{'type':'string','default':'synthetic'}}}})
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'parameters':{'type':'object','properties':{'password':{
            'type':'array','items':{'type':'string','default':'synthetic'}}}}})


def test_fixed_pending_reason_keeps_meaning_without_bypassing_packet_scan(monkeypatch):
    reason='new_material_requires_next_generation_snapshot'
    scanned=[]
    monkeypatch.setattr(privacy,'_scan',scanned.append)
    monkeypatch.setattr(privacy,'anonymize_text',
        lambda value,**_: '<LOCATION>' if value in (reason,'Jane Smith') else value)
    assert privacy.learning_view({'reason':reason,'note':'Jane Smith'}) == {
        'reason':reason,'note':'<LOCATION>'}
    assert len(scanned)==2 and all(reason in value for value in scanned)
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'reason':reason,'nested':{'access_token':'synthetic-private'}})


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


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual local Presidio and Gitleaks')
def test_english_task_text_covers_chinese_phone_without_a_chinese_label():
    result=privacy.learning_view({'text':'Please call 13800138000. Keep RMSE and 24 fps.'})
    assert '13800138000' not in result['text']
    assert 'RMSE' in result['text'] and '24 fps' in result['text']


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


@pytest.mark.parametrize('wrappers', [0, 1, 2])
def test_scanner_sees_decoded_multiline_strings_in_every_json_wrapper(monkeypatch, wrappers):
    raw = 'key = "synthetic-value"\nsecond line'
    source = raw
    for _ in range(wrappers):
        source = json.dumps({'stdout': source}, ensure_ascii=True)
    seen = []
    def scan(value):
        seen.append(value)
        if raw in value:
            raise ValueError('synthetic scanner hit')
    monkeypatch.setattr(privacy, '_scan', scan)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'text': source})
    assert raw in seen[0]


def test_decoded_key_and_normalized_source_are_scanned_before_and_after(monkeypatch):
    seen = []
    monkeypatch.setattr(privacy, '_scan', seen.append)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    source = {'ｋｅｙ': 'row\n"quoted"'}
    assert privacy.learning_view(source) == source
    assert len(seen) == 2
    assert all('row\n"quoted"' in value and 'key' in value.split('\n\n') for value in seen)


def test_text_normalization_maps_graphemes_without_rewriting_task_code():
    from src.adapters.rsi_text_privacy import _normalized_view
    source = 'Ａ\u030a，保持 x² 与 ﬃ'
    canonical, starts, ends = _normalized_view(source)
    assert canonical == 'Å,保持 x2 与 ffi'
    assert source[starts[0]:ends[0]] == 'Ａ\u030a'
    i = canonical.index('ffi')
    assert source[starts[i]:ends[i+2]] == 'ﬃ'


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual local Presidio and Gitleaks')
def test_inline_identity_and_protocol_words_are_sanitized_without_unicode_rejection():
    source = {'text': 'Keep record_evidence_id and new_material_requires_next_generation_snapshot. '
                       '联系人：张三；邮箱 owner@example.com；手机 13800138000。保留 mean ± SD，三次重复，n=128。'}
    result = privacy.learning_view(source)['text']
    assert all(value not in result for value in ['张三', 'owner@example.com', '13800138000'])
    assert all(value in result for value in ['record_evidence_id', 'new_material_requires_next_generation_snapshot', 'mean ± SD', 'n=128'])
    assert '联系人：' in result


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual local Presidio and Gitleaks')
def test_unicode_identity_values_share_alias_while_original_unicode_math_is_kept():
    source = {'text':'姓名：张三，保留 x²、µ 和 ﬃ。', 'full_name':'张三'}
    result = privacy.learning_view(source)
    assert result['full_name'] in result['text']
    assert 'x²、µ 和 ﬃ' in result['text'] and source['full_name'] == '张三'


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual local Gitleaks')
@pytest.mark.parametrize('fullwidth', [False, True])
def test_actual_scanner_hit_cannot_be_hidden_by_quoted_nested_json(fullwidth):
    import random
    import string
    import subprocess
    from src.adapters.rsi_text_privacy import _scan
    # Deterministic synthetic entropy, never an issued or verified credential.
    value = ''.join(random.Random(814).choices(string.ascii_letters + string.digits, k=40))
    raw = 'api_key = "' + value + '"\nKeep 24 fps.'
    with pytest.raises(subprocess.CalledProcessError) as hit:
        _scan(raw)
    assert hit.value.returncode == 1
    if fullwidth:
        raw = raw.replace('api_key', 'ａｐｉ＿ｋｅｙ')
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'stdout': json.dumps({'nested': raw})})


def test_protected_prose_vocabulary_does_not_bypass_explicit_identity_fields(monkeypatch):
    monkeypatch.setattr(privacy, '_scan', lambda value: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    result = privacy.learning_view({'full_name':'record_evidence_id', 'phone':'n=128'})
    assert result['full_name'].startswith('<PERSON_')
    assert result['phone'].startswith('<PHONE_NUMBER_')


@pytest.mark.parametrize('raw', ['{"password":"a","password":null}',
                               r'{"email":"first","\u0065mail":"second"}'])
def test_standard_json_decoder_rejects_duplicate_and_escaped_duplicate_keys(raw):
    with pytest.raises(privacy.PrivacyRejected):
        privacy._decoded(raw)


@pytest.mark.parametrize('wrappers', [0, 1, 2])
def test_duplicate_json_fields_never_preserve_the_ambiguous_original(monkeypatch, wrappers):
    monkeypatch.setattr(privacy, '_scan', lambda value: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    raw = '{"password":"a","password":null}'
    for _ in range(wrappers):
        raw = json.dumps({'nested': raw})
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'stdout': raw})


def test_json_decoder_depth_failure_is_not_reinterpreted_as_safe_prose(monkeypatch):
    import sys
    monkeypatch.setattr(privacy, '_scan', lambda value: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value)
    depth = sys.getrecursionlimit() + 50
    with pytest.raises(privacy.PrivacyRejected):
        privacy.learning_view({'stdout': '[' * depth + '0' + ']' * depth})


@pytest.mark.parametrize('source',['user','model','tool','arguments'])
def test_projector_rejects_ambiguous_json_before_any_value_is_discarded(monkeypatch,source):
    monkeypatch.setattr(privacy,'_scan',lambda value:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value)
    raw='{"password":"diagnostic-only","password":""}'
    original=events('Keep RMSE.',{}, {'text':'Keep 24 fps.'})
    if source=='arguments':original[1]['data']['arguments']=raw
    elif source=='tool':original[2]['data']['message']['content'][0]['content'][0]['text']=raw
    elif source=='model':original[3]['data']['message']['content'][0]['text']=raw
    else:original[0]['data']['content'][0]['text']=raw
    before=json.dumps(original,ensure_ascii=False)
    with pytest.raises(privacy.PrivacyRejected):
        trace.project(original,'future-custom-mcp','completed',TOOLS)
    assert json.dumps(original,ensure_ascii=False)==before


def test_offline_jsonl_rejects_duplicate_event_fields_in_first_parse(tmp_path,monkeypatch):
    monkeypatch.setattr(privacy,'_scan',lambda value:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value)
    path=tmp_path/'events.jsonl'
    raw='{"type":"user/message","data":{"password":"diagnostic-only"},"data":{}}\n'
    path.write_text(raw,encoding='utf-8')
    with pytest.raises(privacy.PrivacyRejected):
        trace.import_trace(path,'chat','completed',0,[])
    assert path.read_text()==raw


def test_sdk_capture_never_persists_a_view_from_duplicate_arguments(tmp_path,monkeypatch):
    monkeypatch.setattr(privacy,'_scan',lambda value:None)
    monkeypatch.setattr(privacy,'anonymize_text',lambda value,**_:value)
    original=events('Keep RMSE.',{}, {'text':'Keep 24 fps.'})
    original[1]['data']['arguments']='{"password":"diagnostic-only","password":""}'
    destination=tmp_path/'sdk-admission'
    assert trace.capture_native_events(destination,original,session_id='synthetic-session',status='completed') is False
    assert (destination/'privacy-learning-rejected').is_file()
    assert not (destination/'privacy-learning.json').exists()


@pytest.mark.skipif(not LOCAL_TOOLS,reason='requires actual local Presidio/Gitleaks')
@pytest.mark.parametrize('source',['user','model','tool'])
def test_numeric_text_is_redacted_without_coercion_or_metric_loss(source):
    import copy
    original=events('Keep RMSE and n=128.',{'count':3,'threshold':0.05},{'text':'Keep 24 fps.'})
    phone='13800138000'
    if source=='user':original[0]['data']['content'][0]['text']=phone
    elif source=='model':original[3]['data']['message']['content'][0]['text']=phone
    else:original[2]['data']['message']['content'][0]['content'][0]['text']=phone
    before=copy.deepcopy(original)
    result=trace.project(original,'future-custom-mcp','completed',TOOLS)
    assert phone not in json.dumps(result,ensure_ascii=False)
    assert original==before
    args=next(row['value'] for row in result['content'] if row['type']=='tool/call')
    assert args=={'count':3,'threshold':0.05}


@pytest.mark.skipif(not LOCAL_TOOLS,reason='requires actual pinned local spaCy pipelines')
def test_persistent_model_reuse_does_not_retain_request_vocabulary():
    from uuid import uuid4
    from src.adapters.rsi_text_privacy import _presidio,anonymize_text
    analyzer,_=_presidio()
    token='privateword'+uuid4().hex
    nlp=analyzer.nlp_engine.nlp['en']
    assert token not in nlp.vocab.strings
    assert isinstance(anonymize_text('Compute RMSE. '+token),str)
    assert token not in nlp.vocab.strings


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual Presidio Anonymizer')
def test_original_person_view_adds_to_canonical_hits_and_preserves_aliases(monkeypatch):
    from src.adapters import rsi_text_privacy as text_privacy
    from presidio_analyzer import RecognizerResult
    from presidio_anonymizer import AnonymizerEngine
    source='甲，乙；保留 x²。'
    calls=[]
    class Analyzer:
        def get_supported_entities(self, **kwargs):return ['PERSON']
        def analyze(self, *, text, language, entities, **kwargs):
            calls.append((text,language))
            if language!='zh':return []
            value='甲' if text==source else '乙'
            start=text.index(value)
            return [RecognizerResult('PERSON',start,start+1,.85,
                recognition_metadata={'recognizer_name':'SpacyRecognizer'})]
    monkeypatch.setattr(text_privacy,'_presidio',lambda:(Analyzer(),AnonymizerEngine()))
    aliases={}
    def alias(entity,value):return aliases.setdefault(value,'<'+entity+'_'+str(len(aliases)+1)+'>')
    result=text_privacy.anonymize_text(source,alias=alias)
    assert '甲' not in result and '乙' not in result and '保留 x²。' in result
    assert set(aliases)=={'甲','乙'} and source=='甲，乙；保留 x²。'
    assert (source,'zh') in calls


@pytest.mark.skipif(not LOCAL_TOOLS, reason='requires actual Presidio Anonymizer')
@pytest.mark.parametrize('label',['record_evidence_id','n=128'])
def test_original_person_view_cannot_remove_protected_prose(monkeypatch,label):
    from src.adapters import rsi_text_privacy as text_privacy
    from presidio_analyzer import RecognizerResult
    from presidio_anonymizer import AnonymizerEngine
    source=label+'；保留 x²。'
    class Analyzer:
        def get_supported_entities(self, **kwargs):return ['PERSON']
        def analyze(self, *, text, language, **kwargs):
            return [RecognizerResult('PERSON',0,len(label),.85,
                recognition_metadata={'recognizer_name':'SpacyRecognizer'})] if text==source and language=='en' else []
    monkeypatch.setattr(text_privacy,'_presidio',lambda:(Analyzer(),AnonymizerEngine()))
    assert text_privacy.anonymize_text(source)==source
