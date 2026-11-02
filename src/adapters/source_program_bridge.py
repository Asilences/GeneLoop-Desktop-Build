"""Task-local Source Program byte pin; delegates validation to the native TS path.

This bridge only materializes source. The existing scene owns execution, guards,
artifact validation and completion. It never evaluates candidate code itself.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


class FrozenSourceLibrary:
    def __init__(self, path, *, expected_sha256=None, expected_digest=None,
                 scope='all', intent='', include_source=False):
        self._raw = Path(path).read_bytes()
        if len(self._raw) > 4_000_000:
            raise ValueError('source_library_too_large')
        self.sha256 = hashlib.sha256(self._raw).hexdigest()
        if expected_sha256 is not None and self.sha256 != expected_sha256:
            raise ValueError('source_library_bytes_changed')
        self._request = {'library_base64': base64.b64encode(self._raw).decode('ascii'),
                         'expected_library_sha256': self.sha256, 'library_scope': scope, 'intent': intent}
        if expected_digest is not None:
            self._request['expected_library_digest'] = expected_digest
        self._catalog = self._call({'operation': 'catalog', 'include_source': include_source})
        self.digest = self._catalog['digest']
        self._request['expected_library_digest'] = self.digest
        self._versions = {row['program_id']: row for row in self._catalog['program_versions']}

    def _call(self, value):
        try:
            result = subprocess.run(['node', '--experimental-strip-types', str(ROOT/'scripts/materialize-source-program.mjs')],
                input=json.dumps({**self._request, **value}), capture_output=True, text=True, timeout=15, cwd=ROOT)
            if result.returncode:
                code = re.search(r'(?m)^(source_[a-z_]+)', result.stderr)
                raise ValueError(code.group(1) if code else 'source_program_bridge_rejected')
            return json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            raise ValueError('source_program_bridge_failed') from error

    def catalog(self):
        return copy.deepcopy(self._catalog)

    def save_bytes(self, path):
        """Persist exactly the captured bytes for a later task process, never overwrite."""
        target = Path(path)
        if target.exists():
            if target.read_bytes() != self._raw:
                raise ValueError('source_library_task_copy_changed')
            return
        with target.open('xb') as stream:
            stream.write(self._raw)
        target.chmod(0o600)

    def materialize(self, program_id, parameters, binding='full'):
        if program_id not in self._versions:
            raise ValueError('source_program_unknown')
        return self._call({'operation': 'materialize', 'program_id': program_id, 'parameters': parameters,
                           'parameter_binding': binding,
                           'expected_program_version': self._versions[program_id]})
