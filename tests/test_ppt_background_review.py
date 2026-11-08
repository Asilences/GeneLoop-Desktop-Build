"""Review contract and accounting separation diagnostics, without model requests."""
import json
import io
import pytest
from src.adapters import ppt_background_review as reviews
from src.adapters.ppt_background_review import validate_review, review_request, DIMENSIONS


def answer():
    value = {key: {'status': 'passed', 'score': 8, 'reason': 'Evidence on the inspected page.', 'pages': [1]} for key in DIMENSIONS}
    return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'review_presentation', 'arguments': json.dumps(value)}}]}}]}


def test_missing_source_figure_coverage_remains_unknown_even_when_model_reports_passed():
    result = validate_review(answer(), 2, True)
    assert result['scientific']['status'] == 'unknown'
    assert result['scientific']['score'] is None
    assert result['scientific']['model_original_score'] == 8
    assert result['visual']['status'] == 'passed'


def test_review_rejects_invented_pages_and_nonfinite_scores():
    for field, value in [('pages', [3]), ('score', 11), ('score', float('nan'))]:
        result = answer()
        data = json.loads(result['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        data['visual'][field] = value
        result['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = json.dumps(data)
        with pytest.raises(ValueError):
            validate_review(result, 2, False)


def test_review_uses_actual_slide_images_and_separate_typed_response():
    payload = review_request({'user_request': 'Show our plan', 'sources': []}, [{'page': 1, 'png': b'actual-render-probe'}])
    assert payload['max_tokens'] == 393216
    assert payload['tool_choice']['function']['name'] == 'review_presentation'
    assert payload['messages'][1]['content'][-1]['type'] == 'image_url'


def test_pending_review_retries_after_environment_recovers_without_blocking_queue(tmp_path, monkeypatch):
    store = tmp_path / 'learning'
    store.mkdir()
    monkeypatch.setenv('GENELOOP_PPT_REVIEW_POLICY', 'private-policy')
    monkeypatch.setattr(reviews.time, 'time', lambda: 1000)
    infos = {'one': {'task_id': 'one', 'state': {'status': 'completed'}}}
    turns = {'turn': {'lanes': {'baseline': {'task_id': 'one', 'output_sha256': 'version'}}}}
    calls = []

    def review(*args):
        calls.append(True)
        if len(calls) == 1:
            raise OSError('temporary source storage unavailable')
        result = store / 'result.json'
        reviews.save(result, {'binding': {'version': 'fixed'}})
        return reviews.read(result), result

    monkeypatch.setattr(reviews, 'perform_review', review)
    reviews.advance_reviews(tmp_path, store, infos, turns, delivery=lambda *args: None)
    reviews.advance_reviews(tmp_path, store, infos, turns, delivery=lambda *args: None)
    assert len(calls) == 1
    monkeypatch.setattr(reviews.time, 'time', lambda: 1301)
    reviews.advance_reviews(tmp_path, store, infos, turns, delivery=lambda *args: None)
    assert len(calls) == 2
    assert reviews.read(store / 'background-review-index.json')['one:version']['status'] == 'reviewed'


def test_uncertain_original_model_request_requires_reconciliation(tmp_path, monkeypatch):
    monkeypatch.setenv('GENELOOP_PPT_REVIEW_POLICY', 'private-policy')
    infos = {'one': {'task_id': 'one', 'state': {'status': 'completed'}}}
    turns = {'turn': {'lanes': {'baseline': {'task_id': 'one', 'output_sha256': 'version'}}}}
    calls = []

    def uncertain(*args):
        calls.append(True)
        raise ValueError('background_review_original_request_requires_reconciliation')

    monkeypatch.setattr(reviews, 'perform_review', uncertain)
    reviews.advance_reviews(tmp_path, tmp_path, infos, turns, delivery=lambda *args: None)
    reviews.advance_reviews(tmp_path, tmp_path, infos, turns, delivery=lambda *args: None)
    assert len(calls) == 1
    assert reviews.read(tmp_path / 'background-review-index.json')['one:version']['status'] == 'reconciliation_required'


def test_review_creates_a_fresh_budget_attempt_and_reuses_the_bound_result(tmp_path, monkeypatch):
    original_gate = reviews.PptCapabilityBudget
    requests = []

    class Budget:
        register_attempt = original_gate.register_attempt

        def __init__(self, policy, folder):
            self.policy = {'endpoint': 'http://127.0.0.1:1'}

        def session_id(self, folder, **kwargs):
            assert folder.is_dir()
            assert kwargs['phase'] == 'ppt_background_review'
            return 'diagnostic-review-session'

        def costs(self, folder):
            return {'diagnostic': True}

    def response(*args, **kwargs):
        requests.append(True)
        return io.BytesIO(json.dumps(answer()).encode())

    monkeypatch.setattr(reviews, 'PptCapabilityBudget', Budget)
    monkeypatch.setattr(reviews.urllib.request, 'urlopen', response)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic-not-a-real-credential')
    binding = {'task_id': 'owned-task', 'artifact_sha256': 'version'}
    context = {'user_request': 'A plan', 'sources': [], 'unreviewed_sources': [], 'source_figure_coverage': 'user_request_only'}
    monkeypatch.setattr(reviews, 'review_material', lambda *args: (binding, context, [{'page': 1, 'png': b'diagnostic'}]))
    for _ in range(2):
        result, path = reviews.perform_review(tmp_path, tmp_path, {}, 'baseline', {'task_id': 'owned-task'}, 'policy')
        assert result['included_in_B_O_execution'] is False
        assert result['automatic_revision_requested'] is False
    assert len(requests) == 1
    assert path.is_file()


def test_review_queue_requests_another_wakeup_until_all_immutable_decks_are_reviewed(tmp_path, monkeypatch):
    monkeypatch.setenv('GENELOOP_PPT_REVIEW_POLICY', 'private-policy')
    infos = {name: {'task_id': name, 'state': {'status': 'completed'}} for name in ('one', 'two')}
    turns = {name: {'lanes': {'baseline': {'task_id': name, 'output_sha256': 'version'}}} for name in infos}
    calls = []

    def review(output, store, turn, lane, info, policy):
        calls.append(info['task_id'])
        path = store / (info['task_id'] + '.json')
        reviews.save(path, {'binding': {'task_id': info['task_id']}})
        return reviews.read(path), path

    monkeypatch.setattr(reviews, 'perform_review', review)
    reviews.advance_reviews(tmp_path, tmp_path, infos, turns, delivery=lambda *args: None)
    assert reviews.read(tmp_path / 'background-review-queue.json')['pending_count'] == 1
    reviews.advance_reviews(tmp_path, tmp_path, infos, turns, delivery=lambda *args: None)
    assert set(calls) == set(infos)
    assert reviews.read(tmp_path / 'background-review-queue.json')['pending_count'] == 0


def test_source_page_images_are_sent_separately_from_slide_numbering(tmp_path):
    import fitz
    import zipfile
    folder = tmp_path / 'comparison-artifacts/turn/baseline/0'
    folder.mkdir(parents=True)
    pdf = fitz.open()
    pdf.new_page().insert_text((60, 80), 'Source supported text')
    data = pdf.tobytes()
    (folder / 'png').write_bytes(pdf[0].get_pixmap(alpha=False).tobytes('png'))
    pdf.close()
    (folder / 'pdf').write_bytes(data)
    with zipfile.ZipFile(folder / 'pptx', 'w') as archive:
        archive.writestr('ppt/slides/slide1.xml', '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:sp><a:t>Actual native text</a:t></p:sp></p:sld>')
        archive.writestr('ppt/notesSlides/notesSlide1.xml', '<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Actual speaker note</a:t></p:notes>')
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    (inputs / 'paper.pdf').write_bytes(data)
    artifacts = [{'id': name, 'name': 'deck.' + name, 'sha256': reviews.sha(folder / name), 'attempt': 0} for name in ('pdf', 'pptx', 'png')]
    turn = {'id': 'turn', 'lanes': {'baseline': {'task_id': 'one', 'output_sha256': 'version', 'artifacts': artifacts}}}
    info = {'task_id': 'one', 'request': {'content': [{'type': 'text', 'text': 'Explain the paper'}]},
            'effective': {'workspace': str(tmp_path), 'scene_inputs': [{'file': 'paper.pdf', 'version_sha256': reviews.sha(inputs / 'paper.pdf')}]}}
    binding, context, images = reviews.review_material(tmp_path, turn, 'baseline', info)
    assert context['source_figure_coverage'] == 'full_pdf_page_images'
    assert context['sources'][0]['figure_images_provided'] is True
    assert len(images) == 2 and images[1]['kind'] == 'source'
    payload = reviews.review_request(context, images)
    assert sum(part['type'] == 'image_url' for part in payload['messages'][1]['content']) == 2
    facts = context['verified_artifact_evidence']
    assert set(facts['artifact_formats']) == {'.pptx', '.pdf', '.png'}
    assert facts['native_slide_content'][0]['native_text'] == ['Actual native text']
    assert facts['native_slide_content'][0]['native_shapes'] == 1
    assert facts['speaker_notes'][0]['text'] == ['Actual speaker note']
    assert binding['rubric_version'].endswith('v4')


@pytest.mark.parametrize('valid_retry', [True, False])
def test_known_invalid_response_gets_one_metered_retry_and_preserves_original(tmp_path, monkeypatch, valid_retry):
    binding = {'task_id': 'owned-task', 'artifact_sha256': 'version'}
    context = {'source_figure_coverage': 'user_request_only'}
    monkeypatch.setattr(reviews, 'review_material', lambda *args: (binding, context, [{'page': 1, 'png': b'diagnostic'}]))
    folder = tmp_path / 'background-reviews' / reviews.digest(binding)
    folder.mkdir(parents=True)
    bad = answer()
    bad['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = '{"scientific" invalid}'
    reviews.save(folder / 'response.json', bad)
    original_sha = reviews.sha(folder / 'response.json')
    calls = []

    class Budget:
        register_attempt = reviews.PptCapabilityBudget.register_attempt

        def __init__(self, policy, root):
            self.policy = {'endpoint': 'http://127.0.0.1:1'}

        def session_id(self, root, **kwargs):
            assert root.name == 'format-retry-1'
            return 'diagnostic-format-retry'

        def costs(self, root):
            return {'provider_requests': 1, 'observed_model_usd': 0.01, 'diagnostic': True}

    def response(*args, **kwargs):
        calls.append(True)
        return io.BytesIO(json.dumps(answer() if valid_retry else bad).encode())

    monkeypatch.setattr(reviews, 'PptCapabilityBudget', Budget)
    monkeypatch.setattr(reviews.urllib.request, 'urlopen', response)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic-not-a-real-credential')
    for _ in range(2):
        if valid_retry:
            result, path = reviews.perform_review(tmp_path, tmp_path, {}, 'baseline', {'task_id': 'owned-task'}, 'policy')
            assert result['format_retry'] == 1
            assert result['included_in_B_O_execution'] is False
        else:
            with pytest.raises(ValueError, match='invalid_response_exhausted'):
                reviews.perform_review(tmp_path, tmp_path, {}, 'baseline', {'task_id': 'owned-task'}, 'policy')
    assert len(calls) == 1
    assert reviews.sha(folder / 'response.json') == original_sha
    assert (folder / 'invalid-response.json').is_file()
    assert reviews.read(folder / 'format-retry-1/model-costs.json')['provider_requests'] == 1


def test_exhausted_format_retry_is_terminal_for_the_automatic_queue(tmp_path, monkeypatch):
    monkeypatch.setenv('GENELOOP_PPT_REVIEW_POLICY', 'private-policy')
    infos = {'one': {'task_id': 'one', 'state': {'status': 'completed'}}}
    turns = {'turn': {'lanes': {'baseline': {'task_id': 'one', 'output_sha256': 'version'}}}}
    calls = []

    def exhausted(*args):
        calls.append(True)
        raise ValueError('background_review_invalid_response_exhausted')

    monkeypatch.setattr(reviews, 'perform_review', exhausted)
    for _ in range(2):
        reviews.advance_reviews(tmp_path, tmp_path, infos, turns, delivery=lambda *args: None)
    assert len(calls) == 1
    assert reviews.read(tmp_path / 'background-review-index.json')['one:version']['status'] == 'review_failed'
    assert reviews.read(tmp_path / 'background-review-queue.json')['pending_count'] == 0


def test_uncertain_format_retry_is_never_sent_again(tmp_path, monkeypatch):
    binding = {'task_id': 'owned-task', 'artifact_sha256': 'version'}
    monkeypatch.setattr(reviews, 'review_material', lambda *args: (binding, {'source_figure_coverage': 'user_request_only'}, [{'page': 1}]))
    folder = tmp_path / 'background-reviews' / reviews.digest(binding)
    retry = folder / 'format-retry-1'
    retry.mkdir(parents=True)
    bad = answer()
    bad['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = 'invalid JSON'
    reviews.save(folder / 'response.json', bad)
    reviews.save(retry / 'request.json', {'diagnostic': True})
    with pytest.raises(ValueError, match='original_request_requires_reconciliation'):
        reviews.perform_review(tmp_path, tmp_path, {}, 'baseline', {'task_id': 'owned-task'}, 'policy')
