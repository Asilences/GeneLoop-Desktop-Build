"""One native Source render in its own workspace/container; no model calls."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def cleanup_owned_container(name, nonce):
    """Inspect ownership, then remove the immutable ID, never a task-wide label."""
    if not re.fullmatch(r'geneloop-cap-[a-f0-9]{32}', name) or not re.fullmatch(r'[a-f0-9]{32}', nonce):
        raise ValueError('source_container_identity_invalid')
    result = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True, timeout=15)
    if result.returncode:
        if 'No such object' in result.stderr or 'No such container' in result.stderr:
            return {'status': 'absent', 'name': name}
        raise RuntimeError('source_container_inspection_failed')
    values = json.loads(result.stdout)
    if len(values) != 1 or values[0].get('Config', {}).get('Labels', {}).get('geneloop.capability_nonce') != nonce:
        raise RuntimeError('source_container_owner_mismatch')
    identity = values[0]['Id']
    removed = subprocess.run(['docker', 'rm', '-f', identity], capture_output=True, text=True, timeout=30)
    if removed.returncode:
        raise RuntimeError('source_container_cleanup_failed')
    return {'status': 'removed', 'name': name, 'container_id': identity}


def run(request):
    call_id, nonce = request['call_id'], request['nonce']
    if not re.fullmatch(r'[a-f0-9-]{36}', call_id) or not re.fullmatch(r'[a-f0-9]{32}', nonce):
        raise ValueError('source_worker_identity_invalid')
    work = Path(request['work']).resolve()
    work.mkdir(mode=0o700)
    for directory in ('src', 'out', 'public'):
        (work/directory).mkdir(mode=0o700)
    (work/'node_modules').symlink_to('/runtime/node_modules')
    assets = {}
    for item in request['inputs']:
        name = item['name']
        if not name or Path(name).name != name or name in assets:
            raise ValueError('source_worker_asset_invalid')
        raw = Path(item['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('source_worker_asset_changed')
        (work/'public'/name).write_bytes(raw)
        assets[name] = item['sha256']
    raw = base64.b64decode(request['library_base64'], validate=True)
    if hashlib.sha256(raw).hexdigest() != request['library_sha256']:
        raise ValueError('source_worker_library_changed')
    library = work.parent/'source-library.json'
    with library.open('xb') as stream:
        stream.write(raw)
    library.chmod(0o600)
    os.environ.update(REMOTION_WORK=str(work), REMOTION_RUNTIME=request['runtime_directory'],
                      REMOTION_IMAGE=request['image'], REMOTION_TASK_ASSETS=json.dumps(assets),
                      REMOTION_TASK_NONCE=nonce, REMOTION_SOURCE_LIBRARY=str(library),
                      REMOTION_SOURCE_LIBRARY_SHA256=request['library_sha256'],
                      REMOTION_SOURCE_LIBRARY_DIGEST=request['library_digest'],
                      REMOTION_CONTAINER_NAME='geneloop-cap-'+nonce, REMOTION_CONTAINER_NONCE=nonce,
                      REMOTION_PARAMETER_BINDING='full', REMOTION_LIBRARY_SCOPE='all')
    if request.get('media_tools_directory'):
        os.environ['REMOTION_MEDIA_TOOLS'] = request['media_tools_directory']
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location('source_capability_program_server', HERE/'program_server.py')
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    rendered = server.render_program(request['program_id'], request['arguments'])
    native = rendered['native_receipt']
    if native['phase'] != 'rendered' or native['status'] != 'succeeded':
        raise RuntimeError('source_worker_render_incomplete')
    video = (work/rendered['video_path']).resolve()
    if not video.is_relative_to(work) or not video.is_file() or hashlib.sha256(video.read_bytes()).hexdigest() != rendered['video_sha256']:
        raise RuntimeError('source_worker_video_changed')
    native = {**native, 'scene_call_id': native['call_id'], 'call_id': call_id,
              'parent_call_id': request['parent_call_id'], 'task_id': request['task_id'],
              'container_nonce': nonce, 'video_path': str(video)}
    value = {'source_version': rendered['source_version'], 'video_sha256': rendered['video_sha256'],
             'video_path': str(video), 'duration_seconds': rendered['duration_seconds'], 'call_id': call_id}
    return {'status': 'succeeded', 'value': value, 'native_receipt': native}


def main():
    request = json.load(sys.stdin)
    def cancelled(*_):
        raise InterruptedError('source_worker_cancelled')
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    parent = request['parent_pid']
    if not isinstance(parent, int) or parent <= 1 or os.getppid() != parent:
        raise ValueError('source_worker_parent_changed')
    done = threading.Event()
    def watch_parent():
        # A hard-killed CLI cannot deliver AbortSignal. Stop this detached worker
        # if it loses that exact parent, rather than leaving a renderer running.
        while not done.wait(.25):
            if os.getppid() != parent:
                os.kill(os.getpid(), signal.SIGTERM)
                return
    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        result = run(request)
    except BaseException as error:
        reason = str(error)
        result = {'status': 'failed', 'reason': reason if re.fullmatch(r'source_[a-z_]+', reason) else 'source_worker_failed'}
    try:
        # The child owns only this nonce. Even a failed docker launch may have
        # created a container before returning its ID; use the preassigned name.
        result['cleanup'] = cleanup_owned_container('geneloop-cap-'+request['nonce'], request['nonce'])
    except BaseException:
        result = {'status': 'failed', 'reason': 'source_worker_cleanup_unconfirmed'}
    done.set()
    print(json.dumps(result, allow_nan=False), flush=True)
    return 0 if result['status'] == 'succeeded' else 1


if __name__ == '__main__':
    raise SystemExit(main())
