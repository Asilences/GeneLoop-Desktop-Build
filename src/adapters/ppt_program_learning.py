"""Account-local PPT program learning using the existing Artifact certifier.

Native program collection is deterministic. Optional page parameterization uses
a separately metered model call. Future paired cost/quality gates are separate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import base64
import http.client
import socket
from uuid import uuid4
from .ppt_learning_evidence import verify_state_binding
from .ppt_component_learning import queue_component_sources
from .ppt_delivery_learning import learn_delivery_fonts

ROOT = Path(__file__).resolve().parents[2]
LAYOUT_ONLY_SCOPE = 'verified_layout_only_current_text_untrusted'


def page_material_scope(proof):
    if proof.get('status') != 'failed' and not proof.get('model_failed_pages'):
        return 'delivered_page_parameters_scientific_quality_not_certified'
    if proof.get('layout_status') == 'passed':
        return LAYOUT_ONLY_SCOPE
    return None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def program_implementation_signature():
    return digest({name: sha(ROOT / name) for name in (
        'src/adapters/ppt_program_learning.py', 'src/adapters/ppt_program_learning.ts',
        'src/adapters/ppt_program_evaluation.py', 'src/adapters/ppt_design.ts',
        'src/adapters/ppt_background_review.py', 'src/adapters/ppt_delivery_quality.py',
        'src/adapters/ppt_execution.ts', 'src/adapters/ppt_workflow_runtime.ts',
        'src/adapters/ppt_workflow_host.ts', 'src/adapters/ppt_workflow_learning.py',
        'src/adapters/ppt_write_learning.py', 'src/adapters/ppt_write_runtime.ts', 'src/adapters/ppt_write_tool.ts',
        'src/adapters/ppt_workflow_certification.py', 'scripts/certify-ppt-workflow.mjs',
        'scenarios/ppt_master/workflow-contracts.json',
        'scenarios/ppt_master/themes.json', 'scenarios/ppt_master/SKILL.md',
        'src/adapters/ppt_page_renderer.py', 'scenarios/ppt_master/page-layouts.json',
        'scenarios/ppt_master/design-conventions.md',
        'src/adapters/ppt_component_learning.py', 'src/adapters/ppt_page_learning.py',
        'src/adapters/ppt_component_literals.py',
        'src/adapters/ppt_component_tool.ts', 'src/adapters/ppt_component_schema.ts',
        'src/adapters/ppt_component_render.py', 'src/adapters/ppt_component_equivalence.py',
        'src/adapters/ppt_component_cache.ts', 'src/adapters/artifact_motif_transport.ts',
        'src/adapters/ppt_delivery_pipeline.ts', 'src/adapters/ppt_delivery_runner.py',
        'src/adapters/ppt_design_preflight.py', 'scenarios/ppt_master/runtime-policy.md',
        'src/adapters/artifact_motif_runtime.ts', 'src/adapters/artifact_motif_compiler.py',
        'src/adapters/ppt_capability_learning.py', 'src/adapters/ppt_capability_online.ts',
        'src/adapters/artifact_capability_runtime.ts', 'scenarios/ppt_master/capability_adapter.py',
        'src/adapters/ppt_capability_budget.py', 'src/adapters/capability_proposal.py',
        'scenarios/ppt_master/publish_capability.mjs',
        'scripts/certify-artifact-motifs.mjs')})


def checked(output, relative, version=None):
    path = output / relative
    if not path.is_file() or path.is_symlink() or path.resolve() != path.absolute() or not path.is_relative_to(output) or path.stat().st_nlink != 1:
        raise ValueError('PPT program evidence outside account output')
    if version is not None and sha(path) != version:
        raise ValueError('PPT program evidence changed')
    verify_state_binding(output,path)
    return path


def certify_programs(candidates, folder, resources, *, workflow=False):
    """The member socket runs the same certifier outside its user namespace."""
    endpoint=os.environ.get('GENELOOP_COMMAND_SOCKET')
    if not endpoint:
        return subprocess.run(['node','--experimental-strip-types',str(ROOT/('scripts/certify-ppt-workflow.mjs' if workflow else 'scripts/certify-artifact-motifs.mjs')),
            str(candidates),str(folder)],cwd=ROOT,capture_output=True,text=True,timeout=600 if workflow else 90,
            env={**os.environ,'GENELOOP_ARTIFACT_RESOURCES':json.dumps(resources)})
    connection=http.client.HTTPConnection('localhost',timeout=600 if workflow else 90)
    stream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);stream.settimeout(600 if workflow else 90);stream.connect(endpoint)
    connection.sock=stream
    try:
        connection.request('POST','/artifact',json.dumps({'operation':'workflow-certify' if workflow else 'certify','file':str(candidates)}),{'Content-Type':'application/json'})
        response=connection.getresponse()
        if response.status!=200:raise ValueError('PPT program certification broker refused the owning job')
        stdout,stderr=[],[];code=None
        for line in response:
            row=json.loads(line)
            if row.get('stdout'):stdout.append(base64.b64decode(row['stdout']).decode('utf-8'))
            if row.get('stderr'):stderr.append(base64.b64decode(row['stderr']).decode('utf-8'))
            if type(row.get('exit')) is int:code=row['exit']
        if code is None:raise ValueError('PPT program certification has no terminal receipt')
        return subprocess.CompletedProcess(['existing-command-broker','/artifact'],code,''.join(stdout),''.join(stderr))
    finally:connection.close()


def advance_programs(output, store, request, infos, turns, reviewed, *, delivery, positive, costs):
    """Called under the owning PPT learning lock after usage reconciliation."""
    font_infos, font_deliveries = {}, {}
    for turn in turns.values():
        lane = turn.get('learning_lane', 'baseline')
        info = infos.get(turn.get('lanes', {}).get(lane, {}).get('task_id'))
        if not info or not positive(reviewed.get((turn['id'], lane)), turn, lane):
            continue
        if info['request'].get('role') in ('holdout', 'evaluate', 'benchmark') or info['request'].get('learning_eligible') is False:
            continue
        try:
            proof = delivery(output, turn, lane, info['locks'], store=store, info=info, review=reviewed.get((turn['id'], lane)))
            if proof.get('status') == 'failed' or proof.get('model_failed_pages'):
                continue
            font_infos[info['task_id']] = info
            font_deliveries[info['task_id']] = {item['sha256'] for item in turn['lanes'][lane].get('artifacts', [])}
            if info['effective'].get('workspace'):
                queue_component_sources(output, store, info)
        except (ValueError, KeyError, OSError, TypeError):
            continue
    learn_delivery_fonts(output, store, font_infos, font_deliveries)
    selected_path = store / 'program-selected.json'
    status_path = store / 'program-status.json'
    pointer = read(selected_path) if selected_path.exists() else None
    feedback = store / 'feedback-version.json'
    feedback_version = sha(feedback) if feedback.exists() else None
    implementation = program_implementation_signature()
    retired_path = store / 'program-retired.json'
    retired = read(retired_path) if retired_path.exists() else []
    if pointer and pointer.get('phase') == 'disabled':
        retired.append({'implementation': pointer.get('implementation_signature'), 'program_ids': pointer.get('added_program_ids', []), 'generation': pointer})
        save(retired_path, retired)
        pointer = None
    def status(value):
        save(status_path, {'compilation_model_requests': 0, 'extra_provider_requests': 0,
                           'cpu_cost_usd': None, 'actual_paid_usd': None, **value})
    if pointer:
        try:
            from .ppt_program_evaluation import evaluate_generation
            pointer = evaluate_generation(output, store, request, pointer, infos, turns, reviewed,
                                          delivery=delivery, positive=positive, costs=costs)
            status({'status': pointer['phase'], 'library_digest': pointer['library_digest'],
                    'blocked': pointer.get('blocked', []),
                    'groups': [{key: group.get(key) for key in ('id', 'phase', 'pending')} for group in pointer.get('groups', [])]})
        except (ValueError, KeyError, OSError, TypeError) as error:
            save(selected_path, {**pointer, 'phase': 'disabled', 'reason': str(error)[:200]})
            status({'status': 'disabled', 'reason': str(error)[:200]})
            return
        if pointer['phase'] == 'disabled':
            return
    spec = importlib.util.spec_from_file_location('ppt_native_programs', ROOT / 'scripts/learn-artifact-motifs.py')
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    rows, eligible, page_eligible, excluded = [], [], [], []
    known = {p['id'] for p in read(store / pointer['library'])['programs']} if pointer else set()
    known.update(program for row in retired if row['implementation']==implementation for program in row['program_ids'])
    for turn in turns.values():
        lane=turn.get('learning_lane','baseline')
        info = infos.get(turn.get('lanes', {}).get(lane, {}).get('task_id'))
        allowed=('baseline','execute') if turn.get('evidence_kind')=='single_task' else ('baseline',)
        if not info or info['state'].get('status') != 'completed' or info['state'].get('failure') or info['effective'].get('mode') not in allowed or not positive(reviewed.get((turn['id'], lane)), turn, lane):
            continue
        if info['request'].get('role') in ('holdout','evaluate','benchmark') or info['request'].get('learning_eligible') is False:
            continue
        try:
            proof = delivery(output, turn, lane, info['locks'], store=store, info=info, review=reviewed.get((turn['id'], lane)))
            scope = page_material_scope(proof)
            if scope and info['effective'].get('workspace'):
                queue_component_sources(output, store, info)
                page_eligible.append((turn, {**info, 'page_learning_scope': scope, 'page_quality': proof}))
            if proof.get('status') == 'failed' or proof.get('model_failed_pages'):
                continue
            row = collector.collect(Path(info['task_dir']))
            row['candidates'] = [p for p in row['candidates'] if p['id'] not in known]
            rows.append(row);eligible.append((turn, info))
        except (ValueError, KeyError, OSError, TypeError) as error:
            excluded.append({'task_id': info['task_id'], 'reason': str(error)[:160]})
    chosen = None
    for i in reversed(range(len(rows))):
        if not rows[i]['candidates']:
            continue
        for j in reversed(range(len(rows))):
            if i != j and eligible[i][1]['compatibility'] == eligible[j][1]['compatibility'] and all(
                eligible[i][1][key] != eligible[j][1][key] for key in ('decision_id', 'source_signature', 'question_sha256')):
                chosen = (i, j)
                break
        if chosen:
            break
    if not chosen:
        from .ppt_page_learning import advance_page_components
        if advance_page_components(output, store, request, page_eligible):
            page_status = read(store / 'page-learning-status.json')
            attempted = int(page_status.get('model_request_attempted', False))
            status({'status': 'probation', 'origin': 'automatic_normal_page_parameterization_v1', 'compilation_model_requests': attempted,
                    'extra_provider_requests': attempted, 'page_learning': page_status})
            return
        page_status = read(store / 'page-learning-status.json') if (store / 'page-learning-status.json').exists() else None
        status({'status': 'waiting_for_independent_program_evidence' if not pointer else pointer['phase'], 'eligible_tasks': len(rows), 'excluded': excluded,
                'page_learning': page_status, 'compilation_model_requests': int(bool(page_status and page_status.get('model_request_attempted'))),
                'extra_provider_requests': int(bool(page_status and page_status.get('model_request_attempted')))})
        return
    i, j = chosen
    frozen = [{**rows[j], 'candidates': []}, {**rows[i], 'candidates': rows[i]['candidates'][:1]}]
    signature = digest({'rows': frozen, 'sources': {name: sha(ROOT / name) for name in (
        'src/adapters/ppt_program_learning.py', 'src/adapters/artifact_motif_compiler.py', 'src/adapters/artifact_motif_runtime.ts', 'scripts/certify-artifact-motifs.mjs')}})
    attempts_path = store / 'program-attempted.json'
    attempted = read(attempts_path) if attempts_path.exists() else []
    if signature in attempted:
        status({'status': 'unchanged_program_evidence', 'excluded': excluded})
        return
    save(attempts_path, [*attempted, signature])
    folder = store / ('program-' + signature[:24]);folder.mkdir(mode=0o700)
    save(folder / 'candidates.json', frozen)
    result = certify_programs(folder/'candidates.json',folder,request.get('command_resources') or {})
    save(folder / 'certification-run.json', {'exit_code': result.returncode, 'stdout': result.stdout[-8000:], 'stderr': result.stderr[-8000:]})
    if result.returncode or not (folder / 'library.json').is_file() or not read(folder / 'library.json')['programs']:
        status({'status': 'program_certification_rejected', 'evidence_signature': signature, 'excluded': excluded})
        return
    library = read(folder / 'library.json')
    locks = {name: version for k in (i, j) for name, version in eligible[k][1]['locks'].items()}
    for k in (i, j):
        boundary = Path(eligible[k][1]['task_dir']) / 'reuse-boundaries.jsonl'
        locks[boundary.relative_to(output).as_posix()] = sha(boundary)
    from .ppt_program_evaluation import publish_generation
    published = publish_generation(output, store, request, folder, library, locks,
        [eligible[k][0]['id'] for k in (i, j)],
        {key: [eligible[k][1][key] for k in (i, j)] for key in ('decision_id', 'source_signature', 'question_sha256')},
        'normal_program_learning')
    status({'status': 'probation' if published else 'certified_candidate_retained',
            'library_digest': read(selected_path)['library_digest'] if selected_path.exists() else None,
            'independent_pairs': 0, 'excluded': excluded})
