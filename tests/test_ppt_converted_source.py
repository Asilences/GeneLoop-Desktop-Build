from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import asyncio
import pytest
from scenarios.ppt_master.server import SourceReader
from scenarios.ppt_master.converted_source import ConvertedSources


@pytest.fixture
def source(tmp_path, monkeypatch):
    import scenarios.ppt_master.converted_source as module
    inputs=tmp_path/'inputs';inputs.mkdir();(tmp_path/'code').mkdir()
    pdf=inputs/'paper.pdf';pdf.write_bytes(b'%PDF-test')
    version=hashlib.sha256(pdf.read_bytes()).hexdigest()
    (tmp_path/'approved-inputs.json').write_text(json.dumps({'files':{pdf.name:version}}))
    reader=SourceReader(inputs)
    monkeypatch.setattr(module,'read_verified',lambda *args:b'verified')
    def run(args,**kwargs):
        path=Path(args[-1]);assert path.read_bytes()==pdf.read_bytes()
        assert 'DEEPSEEK_API_KEY' not in kwargs['env']
        path.with_suffix('.md').write_text('Full text with figure ![](image.png)',encoding='utf-8')
        (path.parent/'image.png').write_bytes(b'figure')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess,'run',run)
    skill=SimpleNamespace(root=tmp_path/'skill',lock={'files':{'scripts/source_to_md.py':'hash'}})
    api=ConvertedSources(reader,skill)
    pin=reader.pin(pdf.name,version)
    return tmp_path,reader,api,pin,pdf


def test_conversion_receipt_preserves_source_and_returns_complete_text(source):
    root,reader,api,pin,pdf=source
    before=pdf.read_bytes();converted=api.convert(pin['source_id']);out=api.read(converted['converted_id'])
    assert pdf.read_bytes()==before and out['version_sha256']==pin['version_sha256']
    assert out['text']=='Full text with figure ![](image.png)' and out['truncated'] is False
    assert out['markdown_path'].startswith('/work/ppt-source-') and not out['visual_checked']
    with pytest.raises(ValueError,match='unknown_session'):
        ConvertedSources(reader,api.skill).read(converted['converted_id'])


@pytest.mark.parametrize('mutation',['source','permission','derivative','new_file'])
def test_changed_source_or_derivative_never_reused(source,mutation):
    root,reader,api,pin,pdf=source;converted=api.convert(pin['source_id']);receipt=converted['converted_id']
    directory=api.receipts[receipt][3]
    if mutation=='source':pdf.write_bytes(b'changed')
    elif mutation=='permission':(root/'approved-inputs.json').write_text('{"files":{}}')
    elif mutation=='derivative':(directory/'source.md').write_text('changed')
    else:(directory/'extra.md').write_text('injected')
    with pytest.raises(ValueError):api.read(receipt)


def test_converter_failure_returns_no_receipt(source,monkeypatch):
    import scenarios.ppt_master.converted_source as module
    root,reader,api,pin,pdf=source
    monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=2))
    with pytest.raises(ValueError,match='failed_exit_2'):api.convert(pin['source_id'])
    assert api.receipts=={}


def test_first_conversion_initializes_private_scratch_without_bash(source):
    root,reader,api,pin,pdf=source
    (root/'code').rmdir()
    converted=api.convert(pin['source_id'])
    assert (root/'code').is_dir()
    assert api.read(converted['converted_id'])['text'].startswith('Full text')


def test_conversion_refuses_symlink_scratch(source):
    import os
    root,reader,api,pin,pdf=source
    (root/'code').rmdir();outside=root/'outside';outside.mkdir()
    try:os.symlink(outside,root/'code',target_is_directory=True)
    except OSError:pytest.skip('symlink creation unavailable')
    with pytest.raises(ValueError,match='session_code_directory_required'):
        api.convert(pin['source_id'])
    assert not list(outside.iterdir())


def test_markdown_change_after_tree_check_is_not_returned(source,monkeypatch):
    root,reader,api,pin,pdf=source;converted=api.convert(pin['source_id'])
    checked=api._files
    def change_after_hash(directory):
        hashes=checked(directory)
        (directory/'source.md').write_text('changed after tree check',encoding='utf-8')
        return hashes
    monkeypatch.setattr(api,'_files',change_after_hash)
    with pytest.raises(ValueError,match='version_changed'):api.read(converted['converted_id'])


def test_new_derivative_hardlink_is_rejected(source):
    import os
    root,reader,api,pin,pdf=source;converted=api.convert(pin['source_id'])
    directory=api.receipts[converted['converted_id']][3]
    os.link(directory/'source.md',directory/'alias.md')
    with pytest.raises(ValueError,match='hardlink'):api.read(converted['converted_id'])


def test_mcp_read_keeps_long_unicode_text_and_bounded_structured_receipt(source, monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError
    from scenarios.ppt_master import server
    root, reader, api, pin, pdf = source
    converted = api.convert(pin['source_id'])
    receipt = converted['converted_id']
    source_id, version, name, directory, _ = api.receipts[receipt]
    text = ('科研原文 αβ — ![](image.png)\n' * 6000)
    (directory/'source.md').write_text(text, encoding='utf-8', newline='\n')
    api.receipts[receipt] = (source_id, version, name, directory, api._files(directory))
    monkeypatch.setattr(server, 'SkillReader', lambda: api.skill)
    monkeypatch.setattr(server, 'ConvertedSources', lambda *args: api)
    monkeypatch.setattr(server.sys, 'argv', ['ppt-master', str(root/'inputs')])
    app = server.create_server()
    result = asyncio.run(app.call_tool('read_converted_source', {'converted_id': receipt}))
    wire = result.model_dump(by_alias=True, exclude_none=True)
    displayed = json.loads(wire['content'][0]['text'])
    metadata = wire['structuredContent']
    assert displayed['text'] == text and displayed['truncated'] is False
    assert metadata['version_sha256'] == pin['version_sha256']
    assert metadata['markdown_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert metadata['markdown_bytes'] == len(text.encode())
    assert metadata['full_text_in_content'] is True and 'text' not in metadata
    assert len(json.dumps(metadata).encode()) < 4096
    tools = {t.name: t.model_dump(by_alias=True, exclude_none=True) for t in asyncio.run(app.list_tools())}
    assert 'outputSchema' not in tools['read_converted_source']
    (directory/'source.md').write_text('changed', encoding='utf-8')
    with pytest.raises(ToolError, match='converted_source_version_changed'):
        asyncio.run(app.call_tool('read_converted_source', {'converted_id': receipt}))
