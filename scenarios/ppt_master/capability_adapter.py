"""PPT normal-task observations on the shared offline Capability controller."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

from src.adapters.capability_scene import CapabilityImprovementAdapter, ROOT, reference, run_child
from src.adapters.capability_improvement import evidence, read, save
from src.adapters.capability_discovery import read_context
from src.adapters.capability_contract import capability_digest


class PptCapabilityAdapter(CapabilityImprovementAdapter):
    withdrawal_reasons = CapabilityImprovementAdapter.withdrawal_reasons | {'artifact_capability_leaf_changed'}

    def __init__(self, plan):
        super().__init__(plan)
        policy = os.environ.get('GENELOOP_PPT_COMPONENT_LEARNING_POLICY') or os.environ.get('SSS_WEB_POLICY')
        if policy:
            from src.adapters.ppt_capability_budget import PptCapabilityBudget
            self.gate = PptCapabilityBudget(policy, plan['ledger_root'])

    def inspect_run(self, entry, owner):
        if entry.get('kind') != 'ppt_normal_task' or entry.get('role') not in ('training', 'validation'):
            raise ValueError('ppt_capability_observation_scope_invalid')
        context = read_context(entry['context'], owner)
        record = read(Path(entry['run']) / 'observation.json')
        if (record.get('format') != 'ppt_capability_observation_v1' or record.get('owner') != owner or
                record.get('scope') != context['scope'] or record.get('status') != 'passed'):
            raise ValueError('ppt_capability_owned_delivery_required')
        for ref in record['evidence']:
            evidence(ref)
        return {'kind': 'ppt_normal_task', 'task_id': record['task_id'],
                'task_fingerprint': record['task_fingerprint'], 'status': record['status'],
                'context': context, 'scope': context['scope'], 'evidence': [reference(Path(entry['run']) / 'observation.json'),
                    *record['evidence']], 'trace': record['trace'], 'role': entry['role']}

    def freeze_publication_inputs(self, job):
        plan = json.loads(evidence(job['publication_plan']))
        if plan.get('format') != 'ppt_capability_publication_inputs_v1' or plan.get('owner') != self.plan['owner']:
            raise ValueError('ppt_capability_publication_owner_invalid')
        for ref in plan['libraries']:
            evidence(ref)
        identities = []
        for label in ('validation', 'followup'):
            task = plan[label]
            if task.get('role') != label:
                raise ValueError('ppt_capability_partition_invalid')
            input_value = json.loads(evidence(task['input']))
            if input_value != task['arguments']:
                raise ValueError('ppt_capability_input_binding_changed')
            for ref in task.get('sources', []):
                evidence(ref)
            for name in ('reference_svg', 'reference_png'):
                evidence(task[name])
            identities.append((task['id'], task['input']['sha256']))
        if identities[0][0] == identities[1][0] or identities[0][1] == identities[1][1]:
            raise ValueError('ppt_capability_followup_must_be_independent')
        return plan

    def publish(self, job, candidate, attempt, expected_latest):
        source = copy.deepcopy(self.templates[job['id']])
        libraries = source['libraries'] + [row['library'] for row in self.materials.records() if row['backend'] == 'artifact_motif']
        libraries = list({ref['sha256']: ref for ref in libraries}.values())
        for ref in libraries:
            evidence(ref)
        plan = {'owner': self.plan['owner'], 'store': self.plan['store'], 'candidate': str(attempt / 'candidate.json'),
                'expected_latest': expected_latest, 'output': str(attempt / 'publication'), 'libraries': libraries,
                'resources': source.get('resources', {})}
        for label in ('validation', 'followup'):
            task = source[label]
            workspace = attempt / (label + '-workspace')
            for name in ('inputs', 'code', 'outputs/code', 'command-tmp'):
                (workspace / name).mkdir(parents=True, mode=0o700)
            raw = evidence(task['input'])
            target = workspace / 'inputs/parameters.json'
            target.write_bytes(raw)
            target.chmod(0o400)
            plan[label] = {**task, 'id': task['id'] + '-' + job['id'] + '-' + attempt.name,
                           'workspace': str(workspace.resolve()), 'input': task['arguments'],
                           'input_versions': [{'path': '/work/inputs/parameters.json', 'sha256': hashlib.sha256(raw).hexdigest()}]}
        save(attempt / 'publication-plan.json', plan)
        with (attempt / 'publication-stdout.log').open('w') as out, (attempt / 'publication-stderr.log').open('w') as err:
            code = run_child(['node', '--experimental-strip-types', str(Path(__file__).with_name('publish_capability.mjs')),
                              str(attempt / 'publication-plan.json')], cwd=ROOT,
                             env={**os.environ, 'SSS_PYTHON': sys.executable}, stdout=out, stderr=err)
        output = Path(plan['output'])
        result_file = output / 'result.json'
        result = read(result_file) if result_file.exists() else {'error': 'ppt_capability_publication_process_failed'}
        proof = reference(result_file if result_file.exists() else attempt / 'publication-stderr.log')
        if code == 0 and result.get('status') == 'completed':
            return {'status': 'published', 'publication_sha256': result['publication_sha256'], 'evidence_ref': proof}
        return {'status': 'failed', 'error': result.get('error', 'ppt_capability_publication_failed'),
                'committed': (output / 'publication.json').exists(), 'evidence_ref': proof,
                'repairable': result.get('error') in ('capability_store_validation_failed', 'cycle_followup_validation_failed')}


def create_adapter(plan):
    return PptCapabilityAdapter(plan)
