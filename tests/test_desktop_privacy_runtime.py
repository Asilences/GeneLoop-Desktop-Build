"""Desktop path compatibility does not replace the shared privacy policy."""
import os
import pathlib
import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows extended-path resource semantics')
def test_native_privacy_resource_path_normalizes_parent_before_io(tmp_path):
    from src.adapters.filesystem_paths import Path
    folder = Path(tmp_path) / ('long-install-' + 'a' * 90) / ('privacy-site-' + 'b' * 90)
    (folder / 'presidio_analyzer' / 'conf').mkdir(parents=True)
    (folder / 'presidio_analyzer' / 'nlp_engine').mkdir()
    expected = folder / 'presidio_analyzer' / 'conf' / 'default.yaml'
    expected.write_text('recognizers: []', encoding='utf-8')
    extended = os.fspath(folder / 'presidio_analyzer' / 'nlp_engine')
    resource = Path(extended, '../conf', 'default.yaml')
    assert len(str(resource)) > 260
    assert '..' not in os.fspath(resource).split('\\')
    assert resource.read_text() == 'recognizers: []'
    assert pathlib.Path is not Path


@pytest.mark.skipif(os.name != 'nt', reason='Windows extended-path PPT resources')
def test_packaged_ppt_resources_keep_long_paths_and_digest_checks(tmp_path):
    import hashlib
    import json
    from src.adapters.filesystem_paths import Path
    from src.adapters.desktop.desktop_skill_runtime import verify_desktop_skill
    root = Path(tmp_path) / ('install-' + 'a' * 90) / ('resources-' + 'b' * 90) / 'ppt-master'
    name = 'templates/layouts/presentation_core/templates/17_two_picture_caption.svg'
    target = root / name
    target.parent.mkdir(parents=True)
    target.write_bytes(b'<svg/>')
    files = {name: hashlib.sha256(b'<svg/>').hexdigest()}
    lock = {'schema_version': 1, 'files': files,
            'package_sha256': hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}
    (root.parent / 'ppt-master-desktop-lock.json').write_text(json.dumps(lock), encoding='utf8')
    assert len(str(target)) > 260
    assert verify_desktop_skill(pathlib.Path(str(root))) == lock
    target.write_bytes(b'changed')
    with pytest.raises(ValueError, match='file_changed'):
        verify_desktop_skill(root)
