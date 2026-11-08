"""Compile observed page-write runs, not a supplied presentation recipe.

Payloads remain external inputs. Contracts describe effects and parameter roles;
the writer, delivery operation and their order must occur in normal traces.
"""
from .ppt_program_learning import digest


def at(value, path):
    for key in path:
        value = value[key]
    return value


def page_runs(trace, contracts):
    records = trace['records']
    for start, first in enumerate(records):
        role = contracts.get(first['name'], {}).get('page_write')
        if not role:
            continue
        writes = []
        observations = []
        previous = None
        for position in range(start, min(start + 65, len(records))):
            row = records[position]
            if row.get('error') or previous and row.get('call_sequence', -1) <= previous.get('result_sequence', float('inf')):
                break
            if row['name'] == first['name']:
                args = row.get('arguments', {})
                if any(key not in args for key in (role['resource_argument'], role['identity_argument'])):
                    break
                choices = role.get('payload_choice_arguments', [])
                if choices and sum(key in args for key in choices) != 1:
                    break
                if writes and args[role['resource_argument']] != writes[0]['arguments'][role['resource_argument']]:
                    break
                # A returned page version witnesses a real installed write.
                try:
                    version = at(row['value'], role['version_output'])
                except (KeyError, TypeError, IndexError):
                    break
                if not isinstance(version, str) or len(version) != 64:
                    break
                writes.append(row)
                previous = row
                continue
            delivery = contracts.get(row['name'], {}).get('observed_completion')
            if not writes or not delivery:
                boundary=row.get('state_boundary',{})
                before,after=boundary.get('before',{}).get('files'),boundary.get('after',{}).get('files')
                if writes and (contracts.get(row['name'],{}).get('read_only') is True or
                               row['name']=='bash' and before is not None and after is not None):
                    observations.append(row)
                    continue
                break
            resource = writes[0]['arguments'][role['resource_argument']]
            resource_key = contracts[row['name']].get('resource_argument')
            if not resource_key or row['arguments'].get(resource_key) != resource:
                break
            try:
                value = row['value']
                pages = at(value, delivery['collection'])
                findings = at(value, delivery['empty_findings'])
                allowed = delivery.get('allowed_finding_severities', [])
                if (at(value, delivery['success']) != delivery['success_value'] or not isinstance(findings, list) or
                        any(not isinstance(item, dict) or item.get('severity') not in allowed for item in findings) or not isinstance(pages,list)):
                    break
            except (KeyError, TypeError, IndexError):
                break
            # The caller still sees every rendered page. Reading/judging is not
            # silently certified by a write; preview binding uses current output.
            modes = {'revision' if item['arguments'].get(role['revision_argument']) else 'new' for item in writes}
            if len(modes) != 1:
                break
            mode = next(iter(modes))
            if mode == 'revision' and any(len(item['arguments'][role['revision_argument']]) != 64 for item in writes):
                break
            if len({item['arguments'][role['identity_argument']] for item in writes})!=len(writes):
                break
            evidence=row.get('delivery_evidence',{})
            if observations:
                if evidence.get('project')!=resource or not evidence.get('files') or not evidence.get('pages'):
                    break
                prefix='code/'+resource.removeprefix('/work/')+'/'
                required=[prefix+item['path'] for item in evidence['files'] if item['path']!='delivery.json']
                if not required or any(not isinstance(name,str) or '..' in name.split('/') for name in required):
                    break
                covered=True
                for observation in observations:
                    if observation['name']=='bash':
                        files=observation['state_boundary']['before']['files']
                        after=observation['state_boundary']['after']['files']
                        if not all(name in files and files[name]==after.get(name) for name in required):covered=False
                for item in writes:
                    name=resource+'/svg_output/'+item['arguments'][role['identity_argument']]
                    proof=next((page for page in evidence['pages'] if page['source']==name),None)
                    if not proof or at(item['value'],role['version_output']) not in (proof.get('source_initial_sha256'),proof.get('source_sha256')):
                        covered=False
                if not covered:break
            schema = trace['schemas'].get(first['name'])
            export_schema = trace['schemas'].get(row['name'])
            if not schema or not export_schema:
                break
            argument_names=sorted(schema.get('properties') or set().union(*(item['arguments'] for item in writes)))
            required=sorted(set(schema.get('required', argument_names)) | {role['resource_argument'],role['identity_argument']} |
                            set(role.get('required_payload_arguments', [])) |
                            ({role['revision_argument']} if mode=='revision' else set()))
            if any(not set(required).issubset(item['arguments']) for item in writes):
                break
            # No scientific text, filenames, component id or geometry is copied
            # into the IR. Even values equal in all samples remain parameters.
            ir = {'version': 1, 'kind': 'observed_page_write_delivery', 'mode': mode,
                'writer': {'tool': first['name'], 'schema_sha256': digest(schema),
                    'argument_names': argument_names, 'required_arguments':required,'repeated_page_run':len(writes)>1, **role},
                'delivery': {'tool': row['name'], 'schema_sha256': digest(export_schema),
                    'resource_argument': resource_key, 'argument_names': sorted(export_schema.get('properties') or row['arguments']),
                    'required_arguments':sorted(set(export_schema.get('required', row['arguments'])) | {resource_key}), **delivery}}
            # Match actual image reads to a returned file collection. Visual
            # assessment stays in the parent; only file binding is compiled.
            preview = observed_preview(records[position + 1:], row, trace, contracts)
            if preview:
                ir['preview'] = preview
            if findings and not preview:
                break
            witness = {key: trace[key] for key in ('task_id', 'decision_id', 'source_signature', 'question_sha256', 'events_sha256')}
            witness['source_family']=trace.get('source_family',trace['source_signature'])
            witness.update(write_call_ids=[item['call_id'] for item in writes], delivery_call_id=row['call_id'],
                           observed_items=len(writes), mode=mode,
                           elided_observation_call_ids=[item['call_id'] for item in observations],
                           visual_observations_complete=bool(preview))
            yield ir, witness
            break



def observed_preview(records, delivered, trace, contracts):
    value = delivered.get('value') or {}
    images = []
    for record in records:
        if contracts.get(record['name'], {}).get('observed_completion') or contracts.get(record['name'], {}).get('page_write'):
            break
        if record.get('error') or not contracts.get(record['name'], {}).get('image_output_required'):
            continue
        for field, argument in record['arguments'].items():
            for collection, items in value.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if argument == item.get('path') and any(block.get('type') == 'image' and
                            block.get('attachment', {}).get('attachmentId') == 'sha256:' + item.get('sha256', '')
                            for block in record.get('content', [])):
                        images.append((collection, record['name'], field, argument))
    for collection in dict.fromkeys(item[0] for item in images):
        items = value[collection]
        selected = [item for item in items if isinstance(item, dict) and str(item.get('path', '')).endswith('.png')]
        reads = [row for row in images if row[0] == collection]
        shapes = {(name, field) for _, name, field, _ in reads}
        if selected and len(shapes) == 1 and {p['path'] for p in selected} <= {row[3] for row in reads}:
            tool, field = next(iter(shapes))
            if tool not in trace['schemas']:
                continue
            return {'tool': tool, 'schema_sha256': digest(trace['schemas'][tool]), 'bindings': {field: 'path'},
                    'collection': [collection], 'path_suffix': '.png'}
    return None


def discover_write_programs(training, heldout, contracts):
    candidates = {}
    for trace in training:
        for ir, witness in page_runs(trace, contracts):
            candidate = candidates.setdefault(digest(ir), {'ir': ir, 'witnesses': {}})
            family=trace.get('source_family',trace['source_signature'])
            old = candidate['witnesses'].get(family)
            if not old or old['observed_items'] < witness['observed_items']:
                candidate['witnesses'][family] = witness
    programs = []
    for key, candidate in sorted(candidates.items()):
        witnesses = list({row['decision_id']:row for row in candidate['witnesses'].values()}.values())
        if len(witnesses) < 2 or any(len({row[field] for row in witnesses}) < 2 for field in ('source_signature', 'question_sha256')):
            continue
        replay = []
        for trace in heldout:
            if trace.get('source_family',trace['source_signature']) in {row['source_family'] for row in witnesses}:
                continue
            if any(trace[field] == row[field] for field in ('decision_id', 'source_signature', 'question_sha256') for row in witnesses):
                continue
            replay.extend(witness for ir, witness in page_runs(trace, contracts) if digest(ir) == key)
        programs.append({'id': 'ppt_write_' + key[:24], 'ir': candidate['ir'],
            'status': 'certified' if replay else 'candidate', 'provenance': witnesses,
            'certification': {'status': 'passed' if replay else 'pending',
                'scope': 'independent_observed_write_binding_replay', 'training_decisions': len(witnesses),
                'independent_replay_decisions': len({row['decision_id'] for row in replay}), 'replay': replay,
                'new_model_requests': 0, 'quality_judgment_skipped': False,
                'runtime_followup_required': True}})
    # A witnessed multi-page run subsumes its one-page suffix. Do not flood
    # the model with both or claim a loop was observed from a single write.
    repeated={digest({**p['ir'],'writer':{**p['ir']['writer'],'repeated_page_run':False}})
              for p in programs if p['ir']['writer']['repeated_page_run'] and p['status']=='certified'}
    return [p for p in programs if p['ir']['writer']['repeated_page_run'] or digest(p['ir']) not in repeated]
