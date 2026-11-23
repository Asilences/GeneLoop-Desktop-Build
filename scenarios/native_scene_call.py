"""One-shot business-tool invocation for the Harness native scene plugin.

The child exits after every call. It does not speak MCP or hold a service open.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from src.adapters.file_lock import exclusive_lock

def _read_state(path: Path, task_id: str):
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 4_000_000:
        raise ValueError('native_scene_state_changed')
    state = json.loads(path.read_text())
    if state.get('task_id') != task_id:
        return {}
    return state


def _write_state(path: Path, state: dict):
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.native-scene-', delete=False) as stream:
        temporary = Path(stream.name)
        os.chmod(temporary, 0o600)
        json.dump(state, stream, ensure_ascii=False)
    os.replace(temporary, path)


def _result(value):
    result = value.model_dump(mode='json', by_alias=True, exclude_none=True)
    if 'structuredContent' not in result:
        blocks = result.get('content', [])
        if blocks and blocks[0].get('type') == 'text':
            try:
                result['structuredContent'] = json.loads(blocks[0]['text'])
            except (ValueError, TypeError):
                pass
    return result


async def call(request: dict):
    scene = request['scene']
    workspace = Path(request['workspace']).resolve(strict=True)
    if workspace.name != 'work' or workspace.is_symlink():
        raise ValueError('native_scene_workspace_invalid')
    inputs = workspace / 'inputs'
    if scene == 'paper':
        from scenarios.paper_proofreading.server import create_server as paper_server
        grant = json.loads((workspace / 'paper-output-grant.json').read_text())
        task_id = grant['task_id']
        lock_path = workspace / '.native-paper-state.lock'
        with exclusive_lock(lock_path):
            path = workspace / '.native-paper-state.json'
            saved = _read_state(path, task_id)
            server = paper_server(inputs, request.get('renderer_root'))
            files, citation_state, citations = server._native_state
            files.handles = {key: tuple(value) for key, value in saved.get('file_handles', {}).items()}
            if saved.get('citation_handles'):
                evidence = citations()
                evidence.handles = {key: tuple(value) for key, value in saved['citation_handles'].items()}
                evidence.citation_batches = {key: (value[0], tuple(value[1]), value[2]) for key, value in saved.get('citation_batches', {}).items()}
                evidence.preprint_packets = saved.get('preprint_packets', {})
            result = await server.call_tool(request['tool'].removeprefix('mcp__paper_checks__'), request.get('arguments') or {})
            evidence = citation_state['service']
            state = {'task_id': task_id, 'file_handles': files.handles,
                     'citation_handles': evidence.handles if evidence and hasattr(evidence, 'handles') else {},
                     'citation_batches': evidence.citation_batches if evidence and hasattr(evidence, 'citation_batches') else {},
                     'preprint_packets': evidence.preprint_packets if evidence and hasattr(evidence, 'preprint_packets') else {}}
            _write_state(path, state)
            return _result(result)
    if scene == 'video':
        from scenarios.remotion_edit.web_server import create_server as video_server
        if request.get('private_root'):
            os.environ['HARLESS_PRIVATE_ROOT'] = request['private_root']
        if request.get('program_store'):
            os.environ['GENELOOP_VIDEO_MOTIF_STORE'] = request['program_store']
            os.environ['GENELOOP_VIDEO_MOTIF_OWNER'] = request['program_owner']
        else:
            os.environ['GENELOOP_VIDEO_MOTIF_STORE'] = ''
            os.environ['GENELOOP_VIDEO_MOTIF_OWNER'] = ''
        grant = json.loads((workspace / 'video-output-grant.json').read_text())
        task_id = grant['task_id']
        with exclusive_lock(workspace / '.native-video-state.lock'):
            path = workspace / '.native-video-state.json'
            saved = _read_state(path, task_id)
            server = video_server(inputs)
            server._native_scene.RECEIPT = saved.get('receipt')
            name = request['tool'].removeprefix('mcp__remotion__')
            if name.startswith('reuse_'):
                programs = server._video_programs
                if programs is None:
                    raise ValueError('video_program_unavailable')
                from src.adapters.source_program_mcp import learned_tool_name
                rows = [p for p in programs.catalog['programs'] if learned_tool_name(p, programs.naming) == name]
                if len(rows) != 1:
                    raise ValueError('video_program_unknown')
                value = server._video_execute(rows[0]['id'], request.get('arguments') or {})
                result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'structuredContent': value}
            else:
                result = _result(await server.call_tool(name, request.get('arguments') or {}))
            _write_state(path, {'task_id': task_id, 'receipt': server._native_scene.RECEIPT})
            return result
    raise ValueError('native_scene_unknown')


if __name__ == '__main__':
    value = asyncio.run(call(json.load(sys.stdin)))
    print(json.dumps(value, ensure_ascii=False))
