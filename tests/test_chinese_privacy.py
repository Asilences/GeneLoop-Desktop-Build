"""Generic Chinese backend and bounded batching contract; no scene-specific rules."""
from contextlib import contextmanager
import json
import subprocess
from types import SimpleNamespace
import pytest

from src.adapters import rsi_text_privacy as text
from src.adapters.rsi_chinese_privacy import ChineseTools, _BATCH
from src.adapters.rsi_privacy_candidates import _transport_escape_only, candidate_context
from src.adapters.privacy_diagnostics import observe_privacy, privacy_stage


@pytest.mark.parametrize('settings', [None, [], {}, {'format':'geneloop.privacy-chinese/v1','skip':True}])
def test_chinese_configuration_cannot_relax_the_common_contract(settings):
    with pytest.raises(ValueError, match='invalid_configuration'):
        ChineseTools(settings)


def test_chinese_credential_review_keeps_gitleaks_first(monkeypatch):
    backend = object.__new__(ChineseTools)
    calls = []
    backend.credential_reviewer = SimpleNamespace(scan=lambda value: calls.append(('review', value)))
    monkeypatch.setattr(text, '_scan_gitleaks', lambda value: calls.append(('gitleaks', value)))
    with candidate_context(backend):
        text._scan('synthetic material')
    assert calls == [('gitleaks', 'synthetic material'), ('review', 'synthetic material')]

    def reject(_):
        raise subprocess.CalledProcessError(1, ['gitleaks'])

    monkeypatch.setattr(text, '_scan_gitleaks', reject)
    with candidate_context(backend), pytest.raises(subprocess.CalledProcessError):
        text._scan('other synthetic material')
    assert len(calls) == 2


def test_credential_review_sees_original_source_and_real_scalar_bindings(monkeypatch):
    from src.adapters.geneloop_privacy import check_material

    backend = object.__new__(ChineseTools)
    backend.review_source_material = True
    received = {}
    backend.credential_reviewer = SimpleNamespace(
        scan=lambda value, **scope: received.update(review=value, **scope))
    monkeypatch.setattr(text, '_scan_gitleaks', lambda value: received.update(gitleaks=value))
    source = '逐行保留\n配置字段说明'
    with candidate_context(backend):
        check_material({'text': source, 'database_password': 'fixture value'})
    assert received['review'] == received['gitleaks']
    assert source in received['source_text']
    assert '"database_password":"fixture value"' in received['source_text']
    assert '"text":"逐行保留\\n配置字段说明"' in received['gitleaks']
    assert '"text":"逐行保留\\n配置字段说明"' not in received['source_text']


def test_only_exact_wrapper_escape_findings_require_source_confirmation():
    raw = 'first fixture line\nsecond fixture line'
    encoded = json.dumps(raw)[1:-1]
    wrapper = json.dumps({'text': raw})
    start = wrapper.index(encoded)
    entry = SimpleNamespace(line=wrapper, value=encoded, value_start=start, value_end=start + len(encoded))
    finding = SimpleNamespace(line_data_list=[entry])
    assert _transport_escape_only(finding, raw, (wrapper,))
    assert not _transport_escape_only(finding, raw + '\n' + encoded, (wrapper,))
    assert not _transport_escape_only(finding, raw, ())
    assert not _transport_escape_only(finding, 'missing original', (wrapper,))
    entry.value_end -= 1
    assert not _transport_escape_only(finding, raw, (wrapper,))


def test_diagnostics_never_record_content_and_reset_after_failure():
    with observe_privacy() as rows:
        with pytest.raises(ValueError):
            with privacy_stage('candidate_ner'):
                raise ValueError('private content must not escape')
    assert rows[0]['error_type'] == 'ValueError'
    assert set(rows[0]) == {'stage', 'seconds', 'error_type'}
    with privacy_stage('outside'):
        pass
    assert len(rows) == 1


def test_chinese_backend_validates_spans_and_preserves_multiple_occurrences():
    backend = object.__new__(ChineseTools)
    from threading import RLock
    backend.lock = RLock()
    backend.pipeline = SimpleNamespace(bulk_process=lambda values: [SimpleNamespace(ents=[
        SimpleNamespace(type='PERSON', start_char=0, end_char=2, text='张三'),
        SimpleNamespace(type='PERSON', start_char=3, end_char=5, text='张三')]) for _ in values])
    assert [s['start'] for s in backend.findings('张三和张三')] == [0, 3]
    with pytest.raises(ValueError, match='invalid_span'):
        backend.findings('李四和张三')
    assert backend.findings('JSON HTTP 2.0') == []


def test_chinese_batch_does_not_retain_results_or_skip_unprefetched_tail():
    backend = object.__new__(ChineseTools)
    calls = []
    def predict(values):
        calls.append(values)
        return [[] for _ in values]
    backend._predict = predict
    with backend.batch_context(['正文甲', 'HTTP']):
        backend.findings('正文甲')
        backend.findings('正文乙')
    assert calls == [['正文甲'], ['正文乙']]
    assert _BATCH.get() is None
    backend.findings('正文甲')
    assert len(calls) == 3


def test_prefetch_capacity_never_truncates_scalar_detection(monkeypatch):
    @contextmanager
    def zone():
        yield
    seen = []
    class Engine:
        nlp = {'zh': SimpleNamespace(memory_zone=zone)}
        def process_batch(self, values, **kwargs):
            seen.append((kwargs['language'], list(values)))
            return [(v, object()) for v in values]
    analyzer = SimpleNamespace(nlp_engine=Engine())
    monkeypatch.setattr(text, '_presidio', lambda: (analyzer, None))
    class Backend:
        @contextmanager
        def batch_context(self, values):
            assert len(values) <= 32
            yield
    values = ['正文'+str(i) for i in range(40)]
    with candidate_context(Backend()):
        with text.text_batch_context(iter(values)):
            assert ('zh', values[0]) in text._BATCH_ARTIFACTS.get()
            assert ('zh', values[-1]) not in text._BATCH_ARTIFACTS.get()
    assert text._BATCH_ARTIFACTS.get() is None
    assert all(len(rows) == 32 for _, rows in seen)


def test_future_agent_uses_the_same_projection_without_scene_specific_rules(monkeypatch):
    from src.adapters import geneloop_privacy as privacy, geneloop_learning_trace as trace
    monkeypatch.setattr(privacy, '_scan', lambda _: None)
    monkeypatch.setattr(privacy, 'anonymize_text', lambda value, **_: value.replace('张三', '<PERSON_1>'))
    events = [{'type':'user/message','data':{'content':[{'type':'text','text':'张三需要分析数据'}]}},
        {'type':'tool/call','data':{'callId':'call-1','name':'future_agent.analyze',
                                 'arguments':'{"text":"张三需要分析数据"}'}}]
    packet = trace.project(events, 'future_agent', 'completed', ['future_agent.analyze'])
    assert packet['scene'] == 'generic' and packet['nodes'][0]['tool'] == 'tool-0'
    assert '张三' not in __import__('json').dumps(packet, ensure_ascii=False)
    assert events[0]['data']['content'][0]['text'].startswith('张三')
