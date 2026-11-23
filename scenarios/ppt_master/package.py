"""Materialize and verify the presentation resources shipped by GeneLoop."""
from pathlib import PurePosixPath
from src.adapters.filesystem_paths import Path
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).with_name('third_party') / 'ppt-master-desktop'
MOUNT = Path('/opt/geneloop/ppt-master')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def installation():
    override = os.environ.get('GENELOOP_PPT_MASTER_ROOT')
    return MOUNT if override == str(MOUNT) and MOUNT.is_dir() else prepare_bundled_resources()


def provenance():
    metadata = json.loads((ASSETS / 'PROVENANCE.json').read_text(encoding='utf-8'))
    if metadata.get('schema_version') != 1 or any(
            not isinstance(metadata.get(key), str) or len(metadata[key]) != 64 or
            any(char not in '0123456789abcdef' for char in metadata[key])
            for key in ('archive_sha256', 'bundle_sha256')):
        raise ValueError('ppt_resource_provenance_invalid')
    return metadata


@lru_cache(maxsize=4)
def bundled_lock(root):
    metadata = provenance()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('ppt_resource_path_invalid')
    files = {}
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError('ppt_resource_path_invalid')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    digest = sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
    if len(files) != metadata['file_count'] or digest != metadata['bundle_sha256']:
        raise ValueError('ppt_resource_bytes_changed')
    return {'schema_version': 1, 'version': metadata['upstream_version_label'],
            'files': files, 'package_sha256': digest}


def bundled_root():
    return ROOT / '.local/ppt-resources' / provenance()['bundle_sha256']


def prepare_bundled_resources():
    target = bundled_root()
    if not target.exists():
        archive = ASSETS / 'ppt-master-presentation.zip'
        if sha(archive.read_bytes()) != provenance()['archive_sha256']:
            raise ValueError('ppt_resource_archive_changed')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.resolve() != target.parent:
            raise ValueError('ppt_resource_cache_redirected')
        with tempfile.TemporaryDirectory(prefix='prepare-', dir=target.parent) as temporary:
            staged = Path(temporary) / 'resources'
            staged.mkdir()
            with zipfile.ZipFile(archive) as package:
                for entry in package.infolist():
                    name = PurePosixPath(entry.filename)
                    if name.is_absolute() or '..' in name.parts or '\\' in entry.filename or ':' in entry.filename or entry.is_dir():
                        raise ValueError('ppt_resource_archive_path_invalid')
                    file = staged.joinpath(*name.parts)
                    file.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(entry) as source, file.open('xb') as output:
                        shutil.copyfileobj(source, output)
            bundled_lock(staged)
            try:
                staged.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
    bundled_lock(target)
    return target


def runtime_lock(root):
    return bundled_lock(Path(root).absolute())


def read_lock():
    return runtime_lock(installation())


def read_verified(root, name, lock=None):
    lock = lock or runtime_lock(root)
    root = Path(root).absolute()
    path = root / name
    if (root.resolve(strict=True) != root or root.is_symlink() or
            name not in lock['files'] or path.is_symlink() or path.resolve(strict=True) != path or
            not path.is_file()):
        raise ValueError('ppt_master_path_invalid')
    data = path.read_bytes()
    if sha(data) != lock['files'][name]:
        raise ValueError('ppt_master_file_changed: ' + name)
    return data


def verify_installation(root):
    lock = runtime_lock(root)
    for name in lock['files']:
        read_verified(root, name, lock)
    # Reject injected Python modules, executables, links, or secrets as well.
    actual = {p.relative_to(root).as_posix() for p in Path(root).rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(lock['files']):
        raise ValueError('ppt_master_unregistered_files')
    return lock
