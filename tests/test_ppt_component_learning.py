"""Deterministic component admission and SVG rendering regression checks."""
import json
import io
from pathlib import Path

import pytest

from src.adapters.ppt_component_learning import validate_proposal, proposal_request, decode_component_proposal, native_svg_proofs, propose_component
from src.adapters.artifact_motif_compiler import digest, sha
from src.adapters.ppt_component_render import render_component_page


def test_component_proposal_requires_explicit_current_json_and_complete_schema():
    proposal = {'description': 'Current title page', 'source': 'import sys,json\nprint(json.load(open(sys.argv[1])))',
                'parameters_schema': {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title'], 'additionalProperties': False},
                'default_parameters': {'title': 'Current title'}}
    assert validate_proposal(proposal) == proposal
    assert validate_proposal({**proposal, 'description': 'Detailed layout documentation. ' * 35})['source'] == proposal['source']
    with pytest.raises(ValueError, match='program_current_arguments_required'):
        validate_proposal({**proposal, 'source': 'print("fixed answer")'})
    with pytest.raises(Exception):
        validate_proposal({**proposal, 'default_parameters': {}})
    assert proposal_request({'source': '<svg/>'})['max_tokens'] == 393216
    request = proposal_request({'source': '<svg/>'})
    assert request['response_format'] == {'type': 'json_object'}
    assert 'tools' not in request and 'tool_choice' not in request
    assert 'exactly description, source, parameters_schema, default_parameters.' in request['messages'][0]['content']
    answer = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
        {'function': {'name': 'propose_ppt_component', 'arguments': json.dumps(proposal)}}]}}]}
    assert decode_component_proposal(answer) == proposal
    with pytest.raises(ValueError, match='complete_typed'):
        decode_component_proposal({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal)}}]})


def test_json_mode_component_requires_complete_independent_parameters():
    proposal = {'description': 'Current title page', 'source': 'import sys,json\nprint(json.load(open(sys.argv[1])))',
                'parameters_schema': {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title'], 'additionalProperties': False},
                'default_parameters': {'title': 'Training'}, 'heldout_parameters': {'title': 'Independent'}}
    request = proposal_request({'source': '<svg/>'}, independent={'source': '<svg/>'})
    assert 'default_parameters, heldout_parameters.' in request['messages'][0]['content']
    assert 'PATH of a UTF-8 JSON file, not JSON text' in request['messages'][0]['content']
    assert 'Use ONLY training.source' in request['messages'][0]['content']
    answer = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal)}}]}
    assert decode_component_proposal(answer, independent=True, allow_json_object=True) == proposal
    for text in (json.dumps(proposal)[:-1], json.dumps({key: value for key, value in proposal.items() if key != 'heldout_parameters'})):
        answer['choices'][0]['message']['content'] = text
        with pytest.raises((ValueError, KeyError)):
            decode_component_proposal(answer, independent=True, allow_json_object=True)
    answer['choices'][0]['message']['content'] = json.dumps({**proposal, 'heldout_parameters': {}})
    with pytest.raises(Exception):
        decode_component_proposal(answer, independent=True, allow_json_object=True)
    answer['choices'][0]['finish_reason'] = 'length'
    with pytest.raises(ValueError, match='complete_typed'):
        decode_component_proposal(answer, independent=True, allow_json_object=True)


@pytest.mark.parametrize('schema,parameters', [
    ({'type': 'object', 'properties': {'y': {'type': 'number'}}}, {'y': 0}),
    ({'type': 'object', 'properties': {'lines': {'type': 'array', 'items': {'type': 'object', 'properties': {'y': {'type': 'integer'}}}}}}, {'lines': [{'y': 0}]}),
])
def test_new_content_only_page_contract_rejects_geometry_parameters_without_changing_legacy_decoder(schema, parameters):
    proposal = {'description': 'Diagnostic layout', 'source': 'import sys,json\nprint(json.load(open(sys.argv[1])))',
                'parameters_schema': schema, 'default_parameters': parameters}
    answer = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal)}}]}
    assert decode_component_proposal(answer, allow_json_object=True) == proposal
    with pytest.raises(ValueError, match='requires_constant_geometry'):
        decode_component_proposal(answer, allow_json_object=True, text_content_only=True)
    request = proposal_request({'parameter_policy': 'text_content_only_v1'})
    assert 'Never ask callers to supply x, y' in request['messages'][0]['content']


def test_component_renderer_creates_actual_png_and_requires_fresh_destination(tmp_path):
    pytest.importorskip('cairosvg')
    (tmp_path / 'page.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 72"><rect width="128" height="72" fill="white"/><text x="8" y="30">Current page</text></svg>')
    assert render_component_page(tmp_path)['width'] == 128
    assert (tmp_path / 'page.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    with pytest.raises(ValueError, match='fresh_render'):
        render_component_page(tmp_path)


@pytest.mark.parametrize('content', ['<image href="file:///etc/passwd"/>', '<script>1</script>', '<rect fill="url(https://example.com/x)"/>'])
def test_component_renderer_rejects_unbound_resources(tmp_path, content):
    pytest.importorskip('cairosvg')
    (tmp_path / 'page.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 72">' + content + '</svg>')
    with pytest.raises(ValueError):
        render_component_page(tmp_path)
    assert not (tmp_path / 'page.png').exists()


def test_native_bash_poststate_proves_generated_svg_without_a_python_cli(tmp_path):
    arguments = {'command': "python3 - <<'PY'\n# generated page\nPY"}
    events = [{'type': 'tool/call', 'data': {'callId': 'actual-native-call', 'name': 'bash', 'arguments': arguments}},
              {'type': 'tool/result', 'data': {'message': {'content': [{'type': 'tool-result', 'toolCallId': 'actual-native-call', 'isError': False}]}}}]
    path = tmp_path / 'events.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in events))
    boundary = {'call_id': 'actual-native-call', 'arguments_sha256': digest(arguments), 'is_error': False,
                'before': {'files': {}}, 'after': {'complete': True, 'files': {'code/project/page.svg': {'sha256': sha('<svg/>')}}}}
    file = tmp_path / 'reuse-boundaries.jsonl'
    file.write_text(json.dumps(boundary) + '\n')
    proof = native_svg_proofs(path)[0]
    assert proof['mode'] == 'native_bash_poststate' and proof['native_path'] == '/work/project/page.svg'
    boundary['arguments_sha256'] = '0' * 64
    file.write_text(json.dumps(boundary) + '\n')
    assert native_svg_proofs(path) == []


@pytest.mark.parametrize('tool,mode', [('create_ppt_page', 'native_component_install'), ('finalize_ppt', 'native_managed_delivery_source')])
def test_host_installed_component_page_can_enter_normal_learning_materials(tmp_path, tool, mode):
    arguments = {'project': '/work/projects/deck'} if tool == 'finalize_ppt' else {'id': 'p', 'parameters': {'title': 'Current'}, 'project': '/work/projects/deck', 'page': 'slide_01.svg'}
    events = [{'type': 'tool/call', 'data': {'callId': 'host', 'name': tool, 'arguments': arguments}},
              {'type': 'tool/result', 'data': {'message': {'content': [{'type': 'tool-result', 'toolCallId': 'host', 'isError': False}]}}}]
    path = tmp_path / 'events.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in events))
    receipt = {'call_id': 'host', 'arguments_sha256': digest(arguments), 'native_path': '/work/projects/deck/svg_output/slide_01.svg',
               'sha256': sha('<svg/>'), 'mode': mode}
    witness = tmp_path / 'ppt-native-pages.jsonl'
    witness.write_text(json.dumps(receipt) + '\n')
    assert native_svg_proofs(path)[0]['mode'] == mode
    receipt['arguments_sha256'] = '0' * 64
    witness.write_text(json.dumps(receipt) + '\n')
    assert native_svg_proofs(path) == []


@pytest.mark.parametrize('cap', [None, 0, .1])
def test_page_compiler_uses_owning_account_budget_identity_and_keeps_the_cap(tmp_path, monkeypatch, cap):
    """Protocol-only diagnostic with intercepted HTTP, no model request."""
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'endpoint': 'http://127.0.0.1:1/v1', 'control_endpoint': 'http://127.0.0.1:1',
                                  'control_token': 'diagnostic', 'budget_task_prefix': '12345678', 'budget_usd': cap}))
    proposal = {'description': 'Current title', 'source': 'import sys,json\nprint(json.load(open(sys.argv[1])))',
                'parameters_schema': {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title']},
                'default_parameters': {'title': 'Current'}}
    calls = []
    def http(request, **kwargs):
        calls.append((request.full_url, json.loads(request.data)))
        response = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': 'propose_ppt_component', 'arguments': json.dumps(proposal)}}]}}]} if request.full_url.endswith('/chat/completions') else {}
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic')
    monkeypatch.setattr('urllib.request.urlopen', http)
    propose_component({'source_sha256': 'source'}, policy, tmp_path / 'proposal')
    registered = calls[0][1]
    assert registered['task_id'].startswith('12345678') and len(registered['task_id']) == 32
    assert registered['session_id'] == 'turn-' + registered['task_id']
    assert registered['budget_usd'] == cap
    assert calls[-2][0].endswith('/tasks/cancel') and calls[-2][1]['session_id'] == registered['session_id']
    assert calls[-1][0].endswith('/unbind') and calls[-1][1]['budget_session_id'] == registered['session_id']
    assert calls[2][0].endswith('/bind') and calls[2][1]['session_id'].startswith('session-')
    assert calls[-1][1] == calls[2][1]
    assert json.loads((tmp_path / 'proposal/attribution.json').read_text())['included_in_B_O_execution'] is False
