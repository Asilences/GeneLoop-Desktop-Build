"""Real filesystem checks for the Windows learning path boundary, without models."""
import json
import os
from pathlib import Path as NativePath

import pytest

from src.adapters.filesystem_paths import Path, windows_io_path, windows_logical_path
from src.adapters.ppt.learning.ppt_program_learning import save, checked


def test_windows_drive_and_unc_io_names_do_not_change_logical_evidence_paths():
    for logical in (r'C:\Users\researcher\学习资料\record.json', r'\\server\share\学习资料\record.json'):
        io = windows_io_path(logical)
        assert io.startswith('\\\\?\\')
        assert windows_logical_path(io) == logical
        assert windows_io_path(io) == io
    assert windows_logical_path(r'\\?\unc\server\share\record.json') == r'\\server\share\record.json'


def deep_directory(root):
    directory = Path(root)
    while len(str(directory)) < 310:
        directory /= 'research-learning-' + 'x' * 25
    directory.mkdir(parents=True)
    return directory


def test_deep_atomic_learning_records_keep_normal_paths_and_exact_bytes(tmp_path):
    directory = deep_directory(tmp_path)
    path = directory / '学习证据.json'
    value = {'path': str(path), 'source_sha256': 'a' * 64, 'phase': 'probation'}
    save(path, value)
    assert path.resolve(strict=True) == path.absolute()
    assert str(NativePath(path)) == str(path)
    assert not str(path).startswith('\\\\?\\')
    assert json.loads(path.read_text(encoding='utf-8')) == value
    assert list(directory.glob('*.json')) == [path]
    save(path, {**value, 'phase': 'active'})
    assert json.loads(path.read_bytes())['phase'] == 'active'
    renamed = path.rename(directory / 'renamed.json')
    restored = renamed.replace(path)
    assert restored == path and path.is_file()
    if os.name == 'nt':
        assert os.fspath(path).startswith('\\\\?\\')
        assert str(Path(os.fspath(path))) == str(path)
    else:
        assert Path is NativePath


def test_deep_evidence_still_rejects_escape_mutation_and_hardlinks(tmp_path):
    output = Path(tmp_path)
    directory = deep_directory(output / 'owned')
    file = directory / 'evidence.txt'; file.write_text('original', encoding='utf-8')
    import hashlib
    version = hashlib.sha256(file.read_bytes()).hexdigest()
    assert checked(output, file.relative_to(output), version) == file
    file.write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence changed'):
        checked(output, file.relative_to(output), version)
    outside = output.parent / (output.name + '-outside.txt'); outside.write_text('outside', encoding='utf-8')
    with pytest.raises(ValueError, match='outside account'):
        checked(output, Path('..') / outside.name)
    alias = directory / 'alias.txt'; alias.hardlink_to(file)
    with pytest.raises(ValueError, match='outside account'):
        checked(output, alias.relative_to(output))
