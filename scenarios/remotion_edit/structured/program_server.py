"""Same render tools in both arms; learned programs supply source, not old output."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import time
import asyncio
import sys
from uuid import uuid4
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT))
spec = importlib.util.spec_from_file_location('remotion_structured', HERE/'server.py')
scene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scene)
LIBRARY = os.environ.get('REMOTION_SOURCE_LIBRARY')
BINDING = os.environ.get('REMOTION_PARAMETER_BINDING','full')
SHOW_SOURCE = os.environ.get('REMOTION_PROGRAM_EVIDENCE','interface')=='source'
SCOPE = os.environ.get('REMOTION_LIBRARY_SCOPE','all')
INTENT = os.environ.get('REMOTION_PROGRAM_INTENT','')
from src.adapters.source_program_bridge import FrozenSourceLibrary
TASK_LIBRARY = FrozenSourceLibrary(LIBRARY,
    expected_sha256=os.environ.get('REMOTION_SOURCE_LIBRARY_SHA256'),
    expected_digest=os.environ.get('REMOTION_SOURCE_LIBRARY_DIGEST'),
    scope=SCOPE, intent=INTENT, include_source=SHOW_SOURCE) if LIBRARY else None


def program_request(value):
    if TASK_LIBRARY is None:
        raise ToolError('no learned program is installed for this task; use render_source')
    if value['operation'] == 'catalog':
        return TASK_LIBRARY.catalog()
    return TASK_LIBRARY.materialize(value['program_id'], value['parameters'], BINDING)


def list_programs() -> dict:
    """List the frozen learned source programs and their current parameter interfaces; may be empty."""
    return program_request({'operation': 'catalog','include_source':SHOW_SOURCE}) if LIBRARY else {'programs': []}


def render_source(text: str) -> dict:
    """Write the current model-authored TSX and render it in one ordinary operation. Available in both arms."""
    with scene.LOCK:
        version = scene.write_source(text)['source_version']
        return scene.render_composition(version)


def render_program(program_id: str, parameters: dict) -> dict:
    """Select a learned program with explicit CURRENT task parameters, instantiate and actually render it.

    This writes task source/output. It reuses computation, never a historical video
    or old semantic decision. Review the returned video with inspect_render.
    """
    with scene.LOCK:
        audit = scene.WORK.parent/'source-program-audit.jsonl'
        record = {'call_id': uuid4().hex, 'time': time.time(), 'program_id': program_id}
        def append(value):
            with audit.open('a') as stream:
                stream.write(json.dumps(value, ensure_ascii=False)+'\n')
            audit.chmod(0o600)
        try:
            materialized = program_request({'operation': 'materialize', 'program_id': program_id, 'parameters': parameters})
            record.update({key: materialized[key] for key in ('program_id','parameters_sha256','source_sha256','library_digest','source_program_version')})
            record.update(supplied_parameters=parameters, parameters=materialized['parameters'],
                          parameter_binding=materialized['parameter_binding'])
            append({**record, 'kind': 'source_program_selected', 'phase': 'materialized'})
            version = scene.write_source(materialized['source'])['source_version']
            if version != materialized['source_sha256']:
                raise ToolError('source_program_written_source_changed')
            result = scene.render_composition(version)
            current = scene.current_source_version() == version
            if not current or result.get('source_version') != version:
                raise ToolError('source_program_render_source_changed')
            receipt = {'format': 'source_program_render_receipt_v1', 'call_id': record['call_id'],
                       'status': 'succeeded', 'phase': 'rendered',
                       'source_program_version': materialized['source_program_version'],
                       'source_sha256': version, 'video_sha256': result['video_sha256'],
                       'video_path': result['video_path']}
            append({**record, 'kind': 'source_program_rendered', 'render': result,
                    'source_current': current, 'native_receipt': receipt})
            return {**result, 'program_id': program_id, 'library_digest': materialized['library_digest'],
                    'source_program_version': materialized['source_program_version'], 'native_receipt': receipt}
        except Exception:
            # Preserve the failed invocation, but never echo private source or
            # supplied parameters through an exception sent to the model.
            append({'kind': 'source_program_failed', 'call_id': record['call_id'],
                    'time': time.time(), 'program_id': program_id, 'reason': 'source_program_render_failed'})
            raise ToolError('source_program_render_failed') from None



if __name__ == '__main__':
    server = MCPServer('Remotion learned program experiment')
    readers = [scene.list_assets, scene.probe_asset, scene.read_source, scene.inspect_render, list_programs]
    for fn in readers + [scene.write_source, scene.render_composition, scene.write_notes, render_source, render_program]:
        if fn in (list_programs,render_program) and (not LIBRARY or os.environ.get('REMOTION_PROGRAM_INTERFACE')=='typed_tools'):
            continue
        server.tool(annotations=ToolAnnotations(readOnlyHint=fn in readers, destructiveHint=False))(fn)
    if os.environ.get('REMOTION_PROGRAM_INTERFACE')=='typed_tools':
        from src.adapters.source_program_mcp import serve_source_tools
        programs=list_programs()['programs']
        asyncio.run(serve_source_tools(server,programs,render_program,os.environ.get('REMOTION_PROGRAM_TOOL_NAMING','opaque'),BINDING))
    else:
        server.run(transport='stdio')
