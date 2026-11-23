"""Native paper/video calls preserve task state without a resident MCP server."""
import hashlib
import asyncio
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def invoke(work, scene, tool, arguments=None):
    request = {'scene': scene, 'workspace': str(work), 'tool': tool, 'arguments': arguments or {}}
    completed = subprocess.run([sys.executable, '-m', 'scenarios.native_scene_call'],
                               input=json.dumps(request), text=True, capture_output=True,
                               cwd=ROOT, timeout=30)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)['structuredContent']


def workspace(tmp_path, filename, data, grant):
    work = tmp_path / 'work'
    inputs = work / 'inputs'
    inputs.mkdir(parents=True)
    (inputs / filename).write_bytes(data)
    version = hashlib.sha256(data).hexdigest()
    (work / 'approved-inputs.json').write_text(json.dumps({'files': {filename: version}}))
    (work / grant).write_text(json.dumps({'schema_version': 1, 'task_id': 'a' * 32,
                                         'allow_output': False}))
    return work, version


def test_paper_handle_survives_one_shot_processes(tmp_path):
    work, version = workspace(tmp_path, 'paper.txt', b'Original sentence.', 'paper-output-grant.json')
    assert invoke(work, 'paper', 'mcp__paper_checks__list_inputs')['files'][0]['sha256'] == version
    pinned = invoke(work, 'paper', 'mcp__paper_checks__pin_document',
                    {'name': 'paper.txt', 'sha256': version})
    read = invoke(work, 'paper', 'mcp__paper_checks__read_pinned_document',
                  {'source_id': pinned['source_id']})
    assert read['text'] == 'Original sentence.'
    assert read['version_sha256'] == version
    (work / 'paper-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'b' * 32, 'allow_output': False}))
    old = subprocess.run([sys.executable, '-m', 'scenarios.native_scene_call'],
                         input=json.dumps({'scene': 'paper', 'workspace': str(work),
                                           'tool': 'mcp__paper_checks__read_pinned_document',
                                           'arguments': {'source_id': pinned['source_id']}}),
                         text=True, capture_output=True, cwd=ROOT, timeout=30)
    assert old.returncode != 0


def test_video_asset_uses_task_bound_handle_without_service(tmp_path):
    work, version = workspace(tmp_path, 'still.png', b'image bytes', 'video-output-grant.json')
    listed = invoke(work, 'video', 'mcp__remotion__list_assets')
    pinned = invoke(work, 'video', 'mcp__remotion__pin_asset', {'name': 'still.png'})
    assert listed['assets'][0]['sha256'] == version
    assert pinned['source_version'] == version
    assert pinned['source_id'].startswith('source-')
    source = 'import React from "react"; export const Main=()=> <div>Hello</div>;'
    written = invoke(work, 'video', 'mcp__remotion__write_source', {'text': source})
    read = invoke(work, 'video', 'mcp__remotion__read_source')
    assert read['text'] == source
    assert read['source_version'] == written['source_version']


def test_video_render_receipt_restores_only_for_owning_task(tmp_path):
    work, _ = workspace(tmp_path, 'still.png', b'image bytes', 'video-output-grant.json')
    source_version = invoke(work, 'video', 'mcp__remotion__read_source')['source_version']
    video = work / 'remotion/out/video.mp4'
    video.write_bytes(b'changed render')
    (work / '.native-video-state.json').write_text(json.dumps({
        'task_id': 'a' * 32,
        'receipt': {'source_version': source_version, 'video_sha256': '0' * 64},
    }))
    request = {'scene': 'video', 'workspace': str(work),
               'tool': 'mcp__remotion__inspect_render', 'arguments': {'seconds': [0]}}
    restored = subprocess.run([sys.executable, '-m', 'scenarios.native_scene_call'],
                              input=json.dumps(request), text=True, capture_output=True,
                              cwd=ROOT, timeout=30)
    assert 'render output version changed' in restored.stdout + restored.stderr
    (work / 'video-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'b' * 32, 'allow_output': False}))
    changed_task = subprocess.run([sys.executable, '-m', 'scenarios.native_scene_call'],
                                  input=json.dumps(request), text=True, capture_output=True,
                                  cwd=ROOT, timeout=30)
    assert 'render the current source before inspecting' in changed_task.stdout + changed_task.stderr


def test_native_published_schema_matches_current_business_functions(tmp_path):
    from scenarios.paper_proofreading.server import create_server as paper_server
    from scenarios.remotion_edit.web_server import create_server as video_server

    work, _ = workspace(tmp_path / 'paper', 'paper.txt', b'paper', 'paper-output-grant.json')
    video_work, _ = workspace(tmp_path / 'video', 'still.png', b'image', 'video-output-grant.json')
    for server, path, prefix in (
        (paper_server(work / 'inputs'), ROOT / 'scenarios/paper_proofreading/native-tool-schemas.json', 'mcp__paper_checks__'),
        (video_server(video_work / 'inputs'), ROOT / 'scenarios/remotion_edit/web-tool-schemas.json', 'mcp__remotion__'),
    ):
        actual = {prefix + tool.name: tool for tool in asyncio.run(server.list_tools())}
        expected = json.loads(path.read_text())
        assert set(actual) == {row['name'] for row in expected if row['name'].startswith(prefix)}
        for row in expected:
            if not row['name'].startswith(prefix):
                continue
            tool = actual[row['name']]
            assert row['description'] == tool.description
            assert row['parameters'] == tool.input_schema
