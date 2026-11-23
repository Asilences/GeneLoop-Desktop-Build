"""Skill-guided search hints, never executable recipes or admission evidence.

Tool order, repetition and bindings must still come from owned normal traces.
Only hashes and registered tool names leave the local Skill snapshot.
"""
import re

from src.adapters.ppt.learning.ppt_program_learning import digest


def skill_corpus(root, contracts):
    """Read only reviewed local adaptations. Raw third-party instructions stay data."""
    from src.adapters.filesystem_paths import Path
    from src.adapters.ppt.learning.ppt_program_learning import read, sha
    root = Path(root).resolve()
    primary = root / 'scenarios/ppt_master/SKILL.md'
    registry = root / 'scenarios/ppt_master/skill-sources.json'
    documents = [{'id': 'geneloop-ppt', 'path': 'scenarios/ppt_master/SKILL.md',
                  'text': primary.read_text(encoding='utf-8'), 'source_sha256': sha(primary)}]
    if registry.is_file():
        manifest = read(registry)
        if manifest.get('version') != 1 or manifest.get('kind') != 'reviewed_ppt_skill_sources':
            raise ValueError('ppt_skill_corpus_version_invalid')
        seen = {'geneloop-ppt'}
        for source in manifest['sources']:
            name = source['adapted_path']
            if (source['id'] in seen or not re.fullmatch(r'[a-z0-9-]{1,80}', source['id']) or
                    source.get('license') not in ('MIT', 'Apache-2.0') or
                    not re.fullmatch(r'[a-f0-9]{40}', source.get('commit', '')) or
                    not re.fullmatch(r'[a-f0-9]{64}', source.get('upstream_sha256', '')) or
                    not name.startswith('scenarios/ppt_master/skill_sources/') or
                    '\\' in name or '..' in name.split('/')):
                raise ValueError('ppt_skill_corpus_source_invalid')
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError('ppt_skill_corpus_path_invalid')
            seen.add(source['id'])
            documents.append({'id': source['id'], 'path': name, 'source_sha256': sha(path),
                              'upstream_commit': source['commit'], 'text': path.read_text(encoding='utf-8')})
    opportunities = []
    for document in documents:
        hints = skill_opportunities(document['text'], contracts)
        for hint in hints['opportunities']:
            body = {**hint, 'source_id': document['id'], 'source_sha256': document['source_sha256']}
            if document.get('upstream_commit'):
                body['upstream_commit'] = document['upstream_commit']
            opportunities.append({**body, 'id': 'ppt_opportunity_' + digest(body)[:24]})
    sources = [{key: value for key, value in row.items() if key != 'text'} for row in documents]
    return {'version': 1, 'kind': 'skill_guided_trace_search', 'sources': sources,
            'skill_sha256': digest({'sources': sources, 'registry': sha(registry) if registry.is_file() else None}),
            'opportunities': opportunities, 'new_model_requests': 0}


def skill_opportunities(text, contracts):
    paragraphs = re.split(r'\n\s*\n', text.replace('\r\n', '\n'))
    sections, mentioned = [], set()
    for index, paragraph in enumerate(paragraphs):
        tools = sorted(name for name in contracts
                       if re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', paragraph))
        if tools:
            mentioned.update(tools)
            sections.append({'paragraph': index, 'text_sha256': digest(paragraph), 'tools': tools})
    skill_sha256 = digest(text)
    scopes = [{'scope': 'paragraph', **section} for section in sections]
    if mentioned:
        scopes.append({'scope': 'skill', 'tools': sorted(mentioned)})
    opportunities = []
    for scope in scopes:
        body = {'skill_sha256': skill_sha256, **scope}
        opportunities.append({'id': 'ppt_opportunity_' + digest(body)[:24], **body,
                              'executable': False})
    return {'version': 1, 'kind': 'skill_guided_trace_search',
            'skill_sha256': skill_sha256, 'opportunities': opportunities,
            'new_model_requests': 0}


def program_tools(program):
    ir = program['ir']
    if ir['kind'] == 'observed_page_write_delivery':
        tools = {ir['writer']['tool'], ir['delivery']['tool']}
        if ir.get('preview'):
            tools.add(ir['preview']['tool'])
        return tools
    if ir['kind'] == 'observed_anchor_read_map':
        return {ir['anchor']['tool'], ir['step']['tool']}
    return {ir['anchor']['tool'], *(step['tool'] for step in ir['steps'])}


def guide_candidates(programs, opportunities):
    """Annotate and rank actual mined candidates; Skill-only hints cannot enter."""
    guided = []
    for program in programs:
        tools = program_tools(program)
        matches = [row for row in opportunities['opportunities'] if tools <= set(row['tools'])]
        if not matches:
            guided.append(program)  # Preserve discovery beyond the Skill's wording.
            continue
        hint = min(matches, key=lambda row: (len(row['tools']), row['scope'] != 'paragraph', row['id']))
        # Do not put authored order, text, task facts or scientific conclusions in the IR.
        guided.append({**program, 'learning_opportunity': {
            'id': hint['id'], 'skill_sha256': opportunities['skill_sha256'],
            'matched_source_ids': sorted({row['source_id'] for row in matches if 'source_id' in row}),
            'origin': 'skill_hint_and_observed_trace', 'recipe_source': 'normal_execution_traces',
            'observed_support': len(program['provenance']),
            'production_savings_proven': False}})
    return sorted(guided, key=lambda row: (
        'learning_opportunity' not in row,
        row['ir']['kind'] != 'observed_page_write_delivery',
        not row['ir'].get('writer', {}).get('repeated_page_run', False),
        -len(row['provenance']), row['id']))


def failure_observations(info, contracts):
    """Keep negative experience as non-executable counterexamples, including failed tasks."""
    request = info['request']
    if request.get('learning_eligible') is False or request.get('role') in ('holdout', 'evaluate', 'benchmark'):
        return []
    from src.adapters.filesystem_paths import Path
    from src.adapters.ppt.learning.ppt_program_learning import sha
    import json
    path = Path(info['task_dir']) / 'events.jsonl'
    calls, failures = {}, []
    lines = path.read_text(encoding='utf-8').splitlines()
    start = info.get('effective', {}).get('trace_start_index', 0)
    if type(start) is not int or not 0 <= start <= len(lines):
        return []
    for line in lines[start:]:
        event = json.loads(line)
        data = event.get('data', {})
        if event.get('type') == 'tool/call' and data.get('name') in contracts:
            calls[data['callId']] = data['name']
        if event.get('type') == 'tool/result':
            for block in data.get('message', {}).get('content', []):
                tool = calls.pop(block.get('toolCallId'), None)
                if tool and block.get('type') == 'tool-result' and block.get('isError'):
                    failures.append({'task_id': info['task_id'], 'tool': tool,
                        'call_id': block['toolCallId'], 'response_sha256': digest(block.get('content', [])),
                        'events_sha256': sha(path),
                        'use': 'counterexample_only', 'executable': False})
    return failures
