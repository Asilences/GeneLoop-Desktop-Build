"""Append-only native material admissions; never rewrite the frozen seed.

Only trusted scene learners call register after native certification. Consumers
recheck the original evidence and rebuild contracts through the native mapper.
This is not a certificate authority or permission to replay a user task.
"""
import hashlib
import json
from pathlib import Path
from src.adapters.capability_contract import capability_digest
from src.adapters.capability_improvement import evidence, read, save
from src.adapters.file_lock import exclusive_lock


class CapabilityMaterials:
    def __init__(self, directory, owner):
        self.owner = owner
        self.directory = Path(directory)/hashlib.sha256(owner.encode()).hexdigest()

    def records(self):
        rows = []
        for path in sorted(self.directory.glob('*.json')):
            row = read(path)
            if row.get('format') != 'capability_material_v1' or row.get('owner') != self.owner:
                raise ValueError('material_owner_or_format_changed')
            if path.stem != capability_digest(row):
                raise ValueError('material_record_changed')
            if row['backend'] not in ('source_program', 'artifact_motif', 'script_motif'):
                raise ValueError('material_backend_unsupported')
            for ref in [row['library'], *row['evidence']]:
                evidence(ref)
            rows.append(row)
        return rows

    def register(self, *, backend, library, refs, acquisition_key, opportunity):
        if backend not in ('source_program', 'artifact_motif', 'script_motif') or not refs:
            raise ValueError('material_native_evidence_required')
        row = dict(format='capability_material_v1', owner=self.owner, backend=backend,
                   library=library, evidence=refs, acquisition_key=acquisition_key,
                   opportunity=opportunity)
        for ref in [library, *refs]: evidence(ref)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with exclusive_lock(self.directory/'.lock'):
            self.records()
            path = self.directory/(capability_digest(row)+'.json')
            if not path.exists(): save(path, row)
        return row

    def export(self):
        return {'owner':self.owner, 'materials':self.records()}
