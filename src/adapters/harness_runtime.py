"""Single portability boundary for the pinned DSH Python SDK and Node runtime."""
from pathlib import Path
import os
import shutil
import functools
import json
from uuid import uuid4


def launch_args(root: Path, patches: tuple[str, ...]) -> tuple[str, ...]:
    cli = root / "node_modules/@deepseek-ai/dsh/lib/bin.js"
    if not cli.is_file():
        raise FileNotFoundError("Install the pinned runtime with npm ci first")
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("Node.js is required")
    return (node, str(cli), "--profile", "sdk",
            *(argument for patch in patches for argument in ("--patch", str(Path(patch).resolve()))))


def create_harness(*, root: Path, patches: tuple[str, ...], env=None, **kwargs):
    from deepseek_harness import DeepSeekHarness
    # SDK 0.1.5rc1's private launch seam is intentionally confined here. Launching
    # Node directly avoids Unix .bin scripts and Windows .cmd executable handling.
    child_env = {"DSH_HOME": str(root / ".local/dsh"),
                 "SSS_PURE_CODE_PYTHON": os.sys.executable, **(env or {})}
    harness = DeepSeekHarness(_launch_args=launch_args(root, patches),
                             env=child_env, reasoning_effort="off", **kwargs)
    original = harness.run
    original_close = harness.close
    harness.privacy_views = []
    pending, pending_bytes = [], 0
    try:
        privacy_root = Path(kwargs.get('runtime_cwd') or kwargs.get('cwd') or child_env['DSH_HOME']).resolve()/'.local/privacy-runs'
    except Exception:
        privacy_root = None

    @functools.wraps(original)
    def run(input, *, session_id=None, on_notification=None):
        nonlocal pending_bytes
        events, size, rejected = {}, 0, False
        def observe(notification):
            nonlocal size, rejected
            if getattr(notification,'method',None) == 'session.event' and not rejected:
                try:
                    sid = notification.payload.get('sessionId')
                    event = notification.payload.get('event')
                    if isinstance(sid,str) and isinstance(event,dict) and (session_id is None or sid==session_id):
                        raw = json.dumps(event,ensure_ascii=False,allow_nan=False)
                        size += len(raw.encode())
                        if pending_bytes+size > 32*1024*1024 or sum(map(len,events.values())) >= 20000:
                            rejected = True;events.clear()
                        else:
                            events.setdefault(sid,[]).append(json.loads(raw))
                except Exception:
                    rejected = True;events.clear()
            if on_notification is not None:
                return on_notification(notification)
        result = None
        try:
            result = original(input,session_id=session_id,on_notification=observe)
            return result
        finally:
            sid = session_id or getattr(result,'session_id',None) or next(iter(events),None)
            status = 'completed' if getattr(result,'finish_reason',None)=='completed' else 'failed'
            pending.append((sid,status,events,rejected))
            if not rejected:pending_bytes += size

    @functools.wraps(original_close)
    def close():
        nonlocal pending, pending_bytes
        # Stop the SDK first. A completion/cancellation observer may deliberately
        # raise to prevent another model request: privacy work cannot delay it.
        result = original_close()
        batch, pending = pending, []
        pending_bytes = 0
        for sid,status,events,rejected in batch:
            try:
                if privacy_root is None or privacy_root.resolve()!=privacy_root.absolute():
                    raise ValueError('geneloop_privacy_rejected')
                destination = privacy_root/uuid4().hex
                from .geneloop_learning_trace import capture_native_events
                if rejected or sid is None:
                    destination.mkdir(parents=True,mode=0o700)
                    (destination/'privacy-learning-rejected').touch(mode=0o600)
                else:
                    capture_native_events(destination,events[sid],session_id=sid,status=status)
                harness.privacy_views.append(destination)
            except Exception:
                # Privacy admission must not replace the original task result.
                pass
        return result
    harness.run = run
    harness.close = close
    return harness
