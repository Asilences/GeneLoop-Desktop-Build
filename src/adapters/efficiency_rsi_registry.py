"""Host-owned, durable request ownership; never reconstruct from observations.

Register an owner before running it, bind each request before upstream I/O, then
export against the provider inventory. The journal is private trusted-runner
evidence, not authentication against an operator rewriting all study evidence.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

from .efficiency_rsi_measurement import _validate, digest, validate_study
from .file_lock import exclusive_lock


class StudyRequestRegistry:
    def __init__(self, plan, journal, *, create=False):
        self.plan = validate_study(plan)
        self.path = Path(journal).resolve()
        self.header = {'event': 'study_registered', 'format': 'efficiency_rsi_journal_v1',
                       'plan_sha256': digest(self.plan)}
        self.cells = {c['id']: c for c in self.plan['cells']}
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with exclusive_lock(self.path.with_suffix('.lock')):
                with self.path.open('x', encoding='utf-8') as stream:
                    os.chmod(self.path, 0o600)
                    self._write(stream, self.header)
        self._read()  # Missing/truncated evidence fails; never silently rebuild it.

    @staticmethod
    def _write(stream, row):
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        stream.flush()
        os.fsync(stream.fileno())

    def _apply(self, state, row):
        owners, bindings, closed = state
        event = row.get('event')
        if event == 'owner_registered':
            owner_id, path = row['owner_id'], row['path']
            if not isinstance(owner_id, str) or not 1 <= len(owner_id) <= 256:
                raise ValueError('efficiency_registry_invalid_owner_id')
            if owner_id in owners or any(o['path'] == path for o in owners.values()):
                raise ValueError('efficiency_registry_owner_already_registered')
            cell, category = row['cell_id'], row['category']
            if row['owner_type'] == 'attempt':
                if cell not in self.cells or category is not None or cell in closed:
                    raise ValueError('efficiency_registry_invalid_attempt_owner')
                count = sum(o['cell_id'] == cell for o in owners.values())
                limit = self.cells[cell]['max_attempts']
                if limit is not None and count >= limit:
                    raise ValueError('efficiency_registry_attempt_limit')
            elif row['owner_type'] == 'overhead':
                if cell is not None or category not in {r['category'] for r in self.plan['overhead_allocations']}:
                    raise ValueError('efficiency_registry_invalid_overhead_owner')
            else:
                raise ValueError('efficiency_registry_invalid_owner_type')
            owners[owner_id] = row
        elif event == 'request_booked':
            owner = owners.get(row['owner_id'])
            if owner is None or owner['cell_id'] in closed:
                raise ValueError('efficiency_registry_unavailable_owner')
            if any(not isinstance(row[k], str) or not 1 <= len(row[k]) <= 256 for k in ('ledger_ref', 'id')):
                raise ValueError('efficiency_registry_invalid_request_reference')
            key = row['ledger_ref'], row['id']
            if key in bindings:
                raise ValueError('efficiency_registry_request_already_bound')
            bindings[key] = {'ledger_ref': key[0], 'id': key[1],
                             **{k: owner[k] for k in ('owner_id', 'owner_type', 'cell_id', 'category')}}
        elif event == 'cell_closed':
            cell = row['cell_id']
            if cell not in self.cells or cell in closed:
                raise ValueError('efficiency_registry_invalid_cell_close')
            closed.add(cell)
        else:
            raise ValueError('efficiency_registry_unknown_event')

    def _read(self):
        raw = self.path.read_text(encoding='utf-8')
        if not raw.endswith('\n'):
            raise ValueError('efficiency_registry_incomplete_journal')
        rows = [json.loads(line) for line in raw.splitlines()]
        if not rows or rows[0] != self.header:
            raise ValueError('efficiency_registry_frozen_plan_changed')
        state = ({}, {}, set())
        for row in rows[1:]:
            self._apply(state, row)
        return state

    def _append(self, row):
        with exclusive_lock(self.path.with_suffix('.lock')):
            state = self._read()
            self._apply(state, row)
            with self.path.open('a', encoding='utf-8') as stream:
                self._write(stream, row)

    def register_owner(self, path, owner_id, *, cell_id=None, category=None):
        """Called by the host before execution; IDs are study-wide, not basenames."""
        # prepare_attempt creates its directory later with exist_ok=False.
        # Pin its canonical future path now; resolving it again at booking also
        # rejects a changed symlink target rather than moving the owner.
        path = Path(path).resolve()
        if path.exists() and not path.is_dir():
            raise ValueError('efficiency_registry_owner_directory_required')
        self._append({'event': 'owner_registered', 'owner_id': owner_id, 'path': str(path),
                      'owner_type': 'attempt' if cell_id is not None else 'overhead',
                      'cell_id': cell_id, 'category': category})

    def owner_for_path(self, path):
        owners, _, closed = self._read()
        path = str(Path(path).resolve(strict=True))
        matches = [o for o in owners.values() if o['path'] == path and o['cell_id'] not in closed]
        if len(matches) != 1:
            raise ValueError('efficiency_registry_unavailable_owner')
        return deepcopy(matches[0])

    def bind_request(self, path, ledger_ref, request_id):
        owner = self.owner_for_path(path)
        self._append({'event': 'request_booked', 'owner_id': owner['owner_id'],
                      'ledger_ref': ledger_ref, 'id': str(request_id)})

    def close_cell(self, cell_id):
        """The host closes only after all requests and quality review are collected."""
        self._append({'event': 'cell_closed', 'cell_id': cell_id})

    def export(self, provider_request_refs):
        """Compare complete study-scoped provider inventory, including pending IDs.

        This inventory must come from booking/ledger evidence, never summaries
        filtered to successful/settled requests. Original cumulative logs remain
        unchanged; requests from other studies are outside this study inventory.
        """
        owners, bindings, closed = self._read()
        keys = [(r['ledger_ref'], r['id']) for r in provider_request_refs]
        if len(keys) != len(set(keys)) or set(keys) != set(bindings):
            raise ValueError('efficiency_registry_provider_inventory_mismatch')
        return _validate({'format': 'efficiency_rsi_registry_v2', 'plan_sha256': self.header['plan_sha256'],
            'cells': [{'cell_id': cell, 'closed': cell in closed,
                       'attempt_ids': [o['owner_id'] for o in owners.values() if o['cell_id'] == cell]}
                      for cell in self.cells],
            'overhead_ids': [o['owner_id'] for o in owners.values() if o['owner_type'] == 'overhead'],
            'request_refs': [{'ledger_ref': k[0], 'id': k[1]} for k in bindings],
            'request_bindings': list(bindings.values())}, 'registry')
