"""Private wire-shape diagnostics. No prompts, URLs, paths, keys or pixels."""
from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


class RequestFingerprints:
    """Compare exact message prefixes per caller; never change model requests.

    These hashes diagnose local drift only. A common prefix cannot prove a
    provider cache hit, its routing, image tokenization or billed price.
    """
    def __init__(self, capacity=512):
        self.capacity = capacity
        self._previous = OrderedDict()
        self._lock = threading.Lock()

    def observe(self, body: bytes, scope: str):
        request = json.loads(body)
        messages = request.get('messages', [])
        if not isinstance(messages, list):
            messages = []
        hashes = [_digest(message) for message in messages]
        image_hashes, inline_bytes, text_bytes, files = [], 0, 0, 0

        def walk(value):
            nonlocal inline_bytes, text_bytes, files
            if isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, dict):
                kind = value.get('type')
                if kind == 'image_url':
                    image = value.get('image_url')
                    url = image.get('url', '') if isinstance(image, dict) else ''
                    if isinstance(url, str) and url:
                        image_hashes.append(hashlib.sha256(url.encode()).hexdigest())
                        if url.startswith('data:'):
                            inline_bytes += len(url.encode())
                elif kind == 'file':
                    files += 1
                for key, item in value.items():
                    if key in ('text', 'content') and isinstance(item, str):
                        text_bytes += len(item.encode())
                    elif isinstance(item, (dict, list)):
                        walk(item)

        walk(messages)
        envelope = _digest({key: value for key, value in request.items() if key != 'messages'})
        with self._lock:
            previous = self._previous.pop(scope, None) if scope else None
            if scope:
                self._previous[scope] = (hashes, envelope)
                while len(self._previous) > self.capacity:
                    self._previous.popitem(last=False)
        shared = 0
        if previous:
            for before, after in zip(previous[0], hashes):
                if before != after:
                    break
                shared += 1
        return {'schema_version': 1, 'body_sha256': hashlib.sha256(body).hexdigest(),
                'body_bytes': len(body), 'envelope_sha256': envelope,
                'message_sha256': hashes, 'message_count': len(hashes),
                'previous_message_count': len(previous[0]) if previous else None,
                'shared_prefix_messages': shared if previous else None,
                'envelope_unchanged': envelope == previous[1] if previous else None,
                'text_bytes': text_bytes, 'image_occurrences': len(image_hashes),
                'unique_image_payloads': len(set(image_hashes)), 'inline_image_bytes': inline_bytes,
                'file_occurrences': files, 'semantics': 'local_wire_shape_not_provider_cache_evidence'}
