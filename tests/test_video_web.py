import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]

def adapter():
    spec=importlib.util.spec_from_file_location('video_web_under_test',ROOT/'scenarios/remotion_edit/web_server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def workspace(tmp_path):
    work=tmp_path/'session-11111111-1111-4111-8111-111111111111/work'
    inputs=work/'inputs';inputs.mkdir(parents=True)
    raw=b'owned media fixture';(inputs/'clip.mp4').write_bytes(raw)
    (work/'approved-inputs.json').write_text(json.dumps({'files':{'clip.mp4':hashlib.sha256(raw).hexdigest()}}))
    (work/'video-output-grant.json').write_text(json.dumps({'schema_version':1,'task_id':'a'*32,'allow_output':False}))
    return work,inputs

def test_video_tools_use_source_hashes_and_reload_task_grants(tmp_path):
    asyncio.run(check_tools(tmp_path))

async def check_tools(tmp_path):
    work,inputs=workspace(tmp_path);server=adapter().create_server(inputs)
    tools=await server.list_tools();names={row.name for row in tools}
    assert names=={'list_assets','pin_asset','probe_media','probe_asset','read_source','inspect_render','write_source','render_composition','write_notes','render_source','run_command'}
    assert next(row for row in tools if row.name=='inspect_render').input_schema['properties']['seconds']['type']=='array'
    result=await server.call_tool('list_assets',{})
    assert 'clip.mp4' in str(result)
    with pytest.raises(Exception,match='outside the frozen task input'):
        await server.call_tool('pin_asset',{'name':'../private.mp4'})
    with pytest.raises(Exception,match='output permission'):
        await server.call_tool('render_composition',{'source_version':'0'*64})
    with pytest.raises(Exception,match='timeout'):
        await server.call_tool('run_command',{'command':'true','timeout_seconds':0})
    before=(work/'remotion/public/clip.mp4').read_bytes()
    (inputs/'clip.mp4').write_bytes(b'changed')
    with pytest.raises(Exception):
        await server.call_tool('list_assets',{})
    assert (work/'remotion/public/clip.mp4').read_bytes()==before

