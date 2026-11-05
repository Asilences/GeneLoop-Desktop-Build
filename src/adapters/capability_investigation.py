"""Paged investigation tools over existing Capability and experience evidence.

The host chooses the evidence scope and inspector. This module has no model
loop, registry, evaluator, or publication authority. Tool calls retain their
original references and never turn observed repetition into a benefit claim.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .capability_authoring import aliases, authoring_context
from .capability_contract import capability_digest, validate_capability_snapshot
from .capability_evolution_agent import inspect_graph
from .capability_feedback import file_ref, verify
from .capability_improvement import save
from .negative_field_compiler import MISSING, _at


def _page(values, offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('investigation_page_invalid')
    end = min(offset + limit, len(values))
    return {'items': copy.deepcopy(values[offset:end]), 'total': len(values),
            'offset': offset, 'next_offset': end if end < len(values) else None}


def _amount(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('investigation_cost_invalid')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError('investigation_cost_invalid') from error
    if not result.is_finite() or result < 0:
        raise ValueError('investigation_cost_invalid')
    return result


class Investigation:
    """One host-scoped view. Even a single unknown-quality source is queryable."""

    def __init__(self, snapshot, entries, scope, directory, *, inspector=inspect_graph,
                 history=(), objective='Improve future execution and construction.', catalog=None,
                 sealed_evidence=(), development_evidence=()):
        self.snapshot = validate_capability_snapshot(snapshot)
        if not isinstance(scope, str) or not scope.strip() or not isinstance(objective, str) or not objective.strip():
            raise ValueError('investigation_scope_or_objective_required')
        self.scope = scope
        self.objective = objective
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.observations = {}
        self.history = {}
        self.evidence = {}
        self.notes = []
        self.sealed_evidence = list(sealed_evidence)
        self._sealed_hashes = {ref['sha256'] for ref in self.sealed_evidence}
        self._sealed_paths = {str(Path(ref['path']).resolve()) for ref in self.sealed_evidence}
        self.development_evidence = list(development_evidence)
        self._unexposed_development = {ref['sha256'] for ref in self.development_evidence}
        self.sequence = 0
        self._inspector = inspector
        self._entries = {}
        history = list(history)
        for entry in entries:
            if (set(entry) != {'split', 'scope', 'evidence'} or entry['split'] != 'training'
                    or entry['scope'] != scope):
                raise ValueError('investigation_split_or_scope_changed')
            self._check_discovery_reference(entry['evidence'])
            row = copy.deepcopy(inspector(entry['evidence'], self.snapshot['owner']))
            if row.get('evaluation_role') == 'evaluation':
                raise ValueError('investigation_evaluation_source_excluded')
            if (not row.get('source_identity') or not row.get('task_id') or not row.get('relation')
                    or row.get('stage') not in ('execution', 'construction', 'capability')
                    or row.get('status') not in ('passed', 'failed', 'unknown')):
                raise ValueError('investigation_observation_invalid')
            if any(ref not in self.snapshot['roots'] for ref in row.get('capabilities', [])):
                raise ValueError('investigation_capability_not_visible')
            _amount(row.get('observed_cost_usd'))
            row['id'] = capability_digest(row)
            self.observations[row['id']] = row
            self._entries[row['id']] = copy.deepcopy(entry)
            self._index_evidence([entry['evidence'], *row['evidence']])
        for reference in history:
            value = json.loads(verify(reference))
            if not isinstance(value, dict) or value.get('owner', self.snapshot['owner']) != self.snapshot['owner']:
                raise ValueError('investigation_history_owner_changed')
            identifier = 'history_' + reference['sha256']
            self.history[identifier] = {'id': identifier, 'value': value, 'reference': copy.deepcopy(reference)}
            self._index_evidence([reference])
            if value.get('format') == 'gene_benchmark_construction_feedback_v1':
                if value.get('scope') != self.scope or value.get('origin') != 'trusted_benchmark_host':
                    raise ValueError('investigation_construction_history_scope_changed')
                self._index_history_sources(value.get('sources', {}))
        table = aliases(self.snapshot)
        self.capabilities = {cap['id']: cap for cap in self.snapshot['capabilities']}
        descriptions = authoring_context({}, self.snapshot, catalog or {})['capabilities']
        self.capability_cards = {}
        for item in descriptions:
            reference = table[item['alias']]
            cap = self.capabilities[reference['id']]
            self.capability_cards[reference['id']] = {
                'id': reference['id'], 'capability': reference, 'alias': item['alias'],
                'description': item.get('description'), 'kind': item['kind'],
                'input_fields': list(cap['contract']['input_schema'].get('properties', {})),
                'output_fields': list(cap['contract']['output_schema'].get('properties', {})),
                'certification': cap['certification'], 'lifecycle': cap['lifecycle']}
        save(self.directory / 'index.json', {'format': 'capability_investigation_index_v1',
             'owner': self.snapshot['owner'], 'scope': scope, 'snapshot_sha256': self.snapshot['digest'],
             'entries': list(self._entries.values()), 'history': list(history)})

    def _index_evidence(self, references):
        for reference in references:
            self._check_discovery_reference(reference)
            self.evidence['evidence_' + reference['sha256']] = copy.deepcopy(reference)

    def _check_discovery_reference(self, reference):
        if (reference['sha256'] in self._sealed_hashes or
                str(Path(reference['path']).resolve()) in self._sealed_paths or
                reference['sha256'] in self._unexposed_development):
            raise ValueError('investigation_sealed_evidence_excluded')
        verify(reference)

    def expose_development(self):
        """Trusted evaluator marks its frozen development feedback exposed."""
        self._unexposed_development.clear()
        exposed = []
        for reference in self.development_evidence:
            if (reference['sha256'] in self._sealed_hashes or
                    str(Path(reference['path']).resolve()) in self._sealed_paths):
                continue
            self._index_evidence([reference])
            exposed.append(reference)
        save(self.directory / 'development-exposure.json', {
            'role': 'development', 'exposed': exposed,
            'sealed_unchanged': self.sealed_evidence})

    def _index_history_sources(self, value):
        # Only explicit sources in the host manifest grant access. Never parse
        # model proposals, source text or referenced file contents for paths.
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'}:
                self._index_evidence([value])
            else:
                for child in value.values():
                    self._index_history_sources(child)
        elif isinstance(value, list):
            for child in value:
                self._index_history_sources(child)

    def _row(self, identifier):
        if identifier not in self.observations:
            raise ValueError('investigation_observation_unavailable')
        row = self.observations[identifier]
        verify(self._entries[identifier]['evidence'])
        for reference in row['evidence']:
            verify(reference)
        return row

    def _experience_card(self, row):
        decision = row.get('decision_context', {})
        return {'id': row['id'], 'task_id': self._task_alias(row), 'source_identity': row['source_identity'],
                'stage': row['stage'], 'status': row['status'], 'quality': row.get('quality', 'unreviewed'),
                'objective': decision.get('objective'), 'outcome': decision.get('outcome'),
                'relation': row['relation'], 'capabilities': copy.deepcopy(row.get('capabilities', [])),
                'observed_cost_usd': row.get('observed_cost_usd'),
                'cost_attribution': row.get('cost_attribution', 'unknown'),
                'counterexample': row.get('counterexample', False),
                'model_decision_count': row.get('model_decision_count'),
                'observed_actions': len(row.get('action_overview', [])),
                'observed_steps': len(row.get('steps', []))}

    @staticmethod
    def _history_card(item):
        value = item['value']
        return {'id': item['id'], 'format': value.get('format'), 'status': value.get('status'),
                'kind': value.get('kind', value.get('target')),
                'entry_counts': {key: len(child) for key, child in value.items()
                                 if isinstance(child, (dict, list))},
                'evidence_id': 'evidence_' + item['reference']['sha256'],
                'reference': copy.deepcopy(item['reference'])}

    @staticmethod
    def _task_alias(row):
        return 'task_' + capability_digest(row['task_id'])[:24]

    def overview(self):
        rows = list(self.observations.values())
        for row in rows:
            self._row(row['id'])
        costs = [_amount(row.get('observed_cost_usd')) for row in rows]
        known = [value for value in costs if value is not None]
        latest = self.notes[-1] if self.notes else None
        return {'format': 'capability_investigation_overview_v1', 'objective': self.objective,
                'scope': self.scope, 'snapshot_sha256': self.snapshot['digest'],
                'capabilities': {'selectable': len(self.capability_cards), 'closure': len(self.capabilities)},
                'experiences': {'observations': len(rows),
                    'independent_sources': len({row['source_identity'] for row in rows}),
                    'stages': dict(Counter(row['stage'] for row in rows)),
                    'statuses': dict(Counter(row['status'] for row in rows)),
                    'qualities': dict(Counter(row.get('quality', 'unreviewed') for row in rows))},
                'costs': {'known_observations': len(known),
                          'minimum_known_observation_usd': str(min(known)) if known else None,
                          'maximum_known_observation_usd': str(max(known)) if known else None,
                          'unknown_observations': sum(value is None for value in costs),
                          'scope': 'Per-observation costs can overlap; inspect attribution before aggregating.'},
                'history_entries': len(self.history), 'latest_note':
                    {'id': 'evidence_' + latest['reference']['sha256'],
                     'hypothesis_preview': latest['hypothesis'][:300]}
                    if latest else None,
                'tools': [tool['name'] for tool in self.tools()]}

    def search(self, kind, query='', *, offset=0, limit=10, stage=None, status=None, capability=None, quality=None):
        if not isinstance(query, str):
            raise ValueError('investigation_query_invalid')
        if kind == 'experience':
            rows = [self._experience_card(self._row(key)) for key in sorted(self.observations)]
            if stage is not None:
                rows = [row for row in rows if row['stage'] == stage]
            if status is not None:
                rows = [row for row in rows if row['status'] == status]
            if quality is not None:
                rows = [row for row in rows if row['quality'] == quality]
            if capability is not None:
                rows = [row for row in rows if any(ref['id'] == capability for ref in row['capabilities'])]
            searchable = {row['id']: json.dumps(self.observations[row['id']], ensure_ascii=False).casefold()
                          for row in rows}
        elif kind == 'capability':
            rows = [copy.deepcopy(self.capability_cards[key]) for key in sorted(self.capability_cards)]
            searchable = {row['id']: json.dumps(row, ensure_ascii=False).casefold() for row in rows}
        elif kind == 'history':
            for item in self.history.values():
                verify(item['reference'])
            rows = [self._history_card(item) for key, item in sorted(self.history.items())]
            searchable = {key: json.dumps(item['value'], ensure_ascii=False).casefold()
                          for key, item in self.history.items()}
        else:
            raise ValueError('investigation_search_kind_invalid')
        terms = query.casefold().split()
        scores = {row['id']: sum(term in searchable[row['id']] for term in terms) for row in rows}
        if terms:
            rows = [row for row in rows if scores[row['id']] > 0]
        rows.sort(key=lambda row: (-scores[row['id']], row['id']))
        return {'kind': kind, 'query': query, **_page(rows, offset, limit)}

    def read(self, kind, id, section='summary', offset=0, limit=10, json_path=None):
        if json_path is not None:
            if (kind not in ('history', 'evidence') or section != 'content'
                    or not isinstance(json_path, list)
                    or any(type(field) not in (str, int) or type(field) is int and field < 0
                           for field in json_path)):
                raise ValueError('investigation_json_path_invalid')
        if kind == 'experience':
            row = self._row(id)
            if section == 'summary':
                return self._experience_card(row)
            if section == 'context':
                return {'id': id, 'decision_context': copy.deepcopy(row.get('decision_context')),
                        'observation_level': row.get('observation_level', 'host_observation'),
                        'strategy_usage': copy.deepcopy(row.get('strategy_usage')),
                        'cost_attribution': row.get('cost_attribution', 'unknown')}
            if section == 'steps':
                return {'id': id, **_page(row.get('steps', []), offset, limit)}
            if section == 'diagnostics':
                return {'id': id, **_page(row.get('construction_outcomes', []), offset, limit)}
            if section == 'quality':
                findings = [{**copy.deepcopy(check), 'evidence': [
                    {'id': 'evidence_' + ref['sha256'], 'sha256': ref['sha256']}
                    for ref in check['evidence']]} for check in row.get('quality_findings', [])]
                return {'id': id, 'quality': row.get('quality', 'unreviewed'),
                        'review': copy.deepcopy(row.get('quality_review')),
                        **_page(findings, offset, limit)}
            if section == 'actions':
                return {'id': id, 'scope': row.get('action_scope'),
                        **_page(row.get('action_overview', []), offset, limit)}
            if section == 'evidence':
                refs = [{'id': 'evidence_' + ref['sha256'], 'sha256': ref['sha256'],
                         'name': Path(ref['path']).name, 'suffix': Path(ref['path']).suffix}
                        for ref in [self._entries[id]['evidence'], *row['evidence']]]
                return {'id': id, **_page(list({ref['id']: ref for ref in refs}.values()), offset, limit)}
        elif kind == 'capability' and id in self.capabilities:
            cap = self.capabilities[id]
            if section == 'summary' and id in self.capability_cards:
                return copy.deepcopy(self.capability_cards[id])
            if section == 'interface':
                return {'id': id, 'contract': copy.deepcopy(cap['contract']),
                        'dependencies': copy.deepcopy(cap['dependencies'])}
            if section == 'implementation':
                return {'id': id, 'implementation': copy.deepcopy(cap['implementation'])}
        elif kind == 'history' and id in self.history:
            item = self.history[id]
            verify(item['reference'])
            if section == 'summary':
                return self._history_card(item)
            if section == 'content':
                evidence_id = 'evidence_' + item['reference']['sha256']
                return {**self.read('evidence', evidence_id, 'content', offset, limit, json_path),
                        'id': id, 'evidence_id': evidence_id}
        elif kind == 'evidence' and id in self.evidence and section in ('summary', 'content'):
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError('investigation_page_invalid')
            raw = verify(self.evidence[id]).decode('utf-8')
            selection = {}
            if json_path is not None:
                try:
                    value = json.loads(raw)
                except ValueError as error:
                    raise ValueError('investigation_json_content_required') from error
                selected = _at(value, json_path)
                if selected is MISSING:
                    raise ValueError('investigation_json_path_missing')
                raw = json.dumps(selected, ensure_ascii=False, allow_nan=False)
                selection = {'json_path': copy.deepcopy(json_path), 'content_encoding': 'json'}
            # Each page unit is 512 Unicode characters, including single-line JSON.
            start = offset * 512
            end = min(start + limit * 512, len(raw))
            return {'id': id, 'content': raw[start:end], 'offset': offset,
                    'total_characters': len(raw), 'page_unit_characters': 512,
                    'next_offset': offset + limit if end < len(raw) else None, **selection}
        raise ValueError('investigation_read_unavailable')

    def note(self, hypothesis, evidence_ids, next_questions):
        if (not isinstance(hypothesis, str) or not hypothesis.strip()
                or not isinstance(evidence_ids, list) or not isinstance(next_questions, list)
                or any(not isinstance(item, str) or not item.strip() for item in next_questions)):
            raise ValueError('investigation_note_invalid')
        for identifier in evidence_ids:
            self._row(identifier)
        value = {'format': 'capability_investigation_note_v1', 'authorship': 'model_interpretation',
                 'hypothesis': hypothesis, 'evidence_ids': list(evidence_ids),
                 'next_questions': list(next_questions)}
        path = self.directory / ('note-' + str(len(self.notes)) + '.json')
        save(path, value)
        reference = file_ref(path)
        self._index_evidence([reference])
        self.notes.append({'reference': reference, **value})
        return copy.deepcopy(value)

    def context(self, observation_ids):
        """Build a host context for the original candidate validator/handlers."""
        if (not isinstance(observation_ids, list) or not observation_ids
                or any(not isinstance(item, str) for item in observation_ids)
                or len(set(observation_ids)) != len(observation_ids)):
            raise ValueError('investigation_selection_invalid')
        rows = [copy.deepcopy(self._row(identifier)) for identifier in observation_ids]
        referenced = {ref['id'] for row in rows for ref in row.get('capabilities', [])}
        return {'format': 'capability_evolution_packet_v1', 'owner': self.snapshot['owner'],
                'scope': self.scope, 'snapshot_sha256': self.snapshot['digest'],
                'stage': rows[0]['stage'] if len({row['stage'] for row in rows}) == 1 else 'mixed',
                'independent_sources': len({row['source_identity'] for row in rows}),
                'inventory': {'observations': len(rows), 'failed': sum(row['status'] == 'failed' for row in rows),
                    'counterexamples': sum(row.get('counterexample', False) for row in rows),
                    'unknown_cost': sum(row.get('observed_cost_usd') is None for row in rows)},
                'observations': rows, 'capabilities': [
                    {'capability': self.capability_cards[key]['capability'],
                     'contract': copy.deepcopy(self.capabilities[key]['contract']),
                     'certification': self.capabilities[key]['certification'],
                     'lifecycle': self.capabilities[key]['lifecycle']}
                    for key in sorted(referenced)],
                'max_candidates': 2, 'omitted_observations': len(self.observations) - len(rows),
                'cost_claim': 'Observed costs retain their scopes; net benefit requires independent evaluation.'}

    def reference_map(self, observation_ids):
        return {self._task_alias(row): {'task': row['task_id'],
                    'calls': {step['call_id']: step['call_id'] for step in row.get('steps', [])}}
                for row in (self._row(identifier) for identifier in observation_ids)}

    def tools(self):
        text = {'type': 'string'}
        page = {'type': 'integer', 'minimum': 0}
        size = {'type': 'integer', 'minimum': 1, 'maximum': 100}
        definitions = [
            ('evolution_overview', 'Read compact counts, cost coverage and investigation status.', {}, []),
            ('evolution_search', 'Search paged capability, experience or prior-improvement cards.',
             {'kind': {'enum': ['capability', 'experience', 'history']}, 'query': text,
              'stage': {'enum': ['execution', 'construction', 'capability']},
              'status': {'enum': ['passed', 'failed', 'unknown']}, 'capability': text,
              'quality': {'type': 'string', 'description': 'Filter quality separately from execution status, e.g. failed or unreviewed.'},
              'offset': page, 'limit': size}, ['kind']),
            ('evolution_read', 'Read a selected interface, trace or evidence. History summary returns a compact card. '
             'History/evidence content uses 512-character page units with offset/limit and next_offset. '
             'For JSON content, select a local subtree with json_path, for example ["tool_calls",0,"result"], '
             'then follow its next_offset. Omit json_path to read original text.',
             {'kind': {'enum': ['capability', 'experience', 'history', 'evidence']}, 'id': text,
              'section': {'enum': ['summary', 'context', 'steps', 'diagnostics', 'quality', 'actions', 'evidence',
                                   'interface', 'implementation', 'content']},
              'offset': page, 'limit': size,
              'json_path': {'type': 'array', 'items': {'oneOf': [text, page]},
                            'description': 'Optional JSON object fields/array indices for history/evidence content only.'}},
             ['kind', 'id']),
            ('evolution_note', 'Save your hypothesis, supporting observation IDs and remaining questions.',
             {'hypothesis': text, 'evidence_ids': {'type': 'array', 'items': text},
              'next_questions': {'type': 'array', 'items': text}},
             ['hypothesis', 'evidence_ids', 'next_questions'])]
        return [{'name': name, 'description': description,
                 'parameters': {'type': 'object', 'properties': properties,
                                'required': required, 'additionalProperties': False}}
                for name, description, properties, required in definitions]

    def dispatch(self, name, arguments):
        methods = {'evolution_overview': self.overview, 'evolution_search': self.search,
                   'evolution_read': self.read, 'evolution_note': self.note}
        if name not in methods or not isinstance(arguments, dict):
            raise ValueError('investigation_tool_invalid')
        record = {'name': name, 'arguments': arguments}
        try:
            result = methods[name](**arguments)
            record.update(status='succeeded', result=result)
            return result
        except Exception as error:
            record.update(status='failed', error=type(error).__name__ + ':' + str(error))
            raise
        finally:
            save(self.directory / ('tool-' + str(self.sequence) + '.json'), record)
            self.sequence += 1
