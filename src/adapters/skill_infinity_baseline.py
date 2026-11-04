"""Skill∞论文复现适配，实际模型会话、评分器和账本由原宿主提供。

The agent steers each iteration through tools. This module owns the immutable
candidate archive and external evaluation boundary, not the agent's search
policy. Native discovery receives names/descriptions and package locations.
"""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import shutil

from .capability_feedback import file_ref, verify
from .capability_improvement import save


PAPER = 'https://arxiv.org/html/2610.35434v1'
REPRODUCTION = 'skill_infinity_paper_reproduction_v1'
SEED_INSTRUCTIONS = """# Skill optimization

Inspect the supplied optimization workspace and its archive. Diagnose the
parent from relevant training rollouts and earlier unsuccessful revisions.
Use the available rollout and archive tools to investigate concrete actions,
results, and recovery. Check the underlying evidence when a summary is unclear.
Use read_evidence with an evidence_id from the host's evidence_refs to inspect
original task trajectories, tool results and verifier diagnostics in pages.
Host evidence indexes can reveal further authorized records. Reference answers
and oracle solutions are unavailable in this shared comparison protocol.

Create one or two complete skill revisions in an iteration when a useful
change is supported by evidence. Describe the observation, the change, the
expected result, and an outcome that would contradict your hypothesis. Skills
may contain instructions, reference material, and reusable executable helpers.
Keep useful behavior and maintain valid package links and the skill identity.

Request external evaluation of each candidate and its independent review.
Inspect the results and decide which reviewed candidate or previous parent to
retain. Use the search history and evidence to choose the next direction,
including retaining a tied candidate when its actual rollout addresses the
diagnosed issue. Decide whether to continue or stop within the candidate budget.

For a task skill, investigate task requirements, actual execution, activation,
and verifier outcomes. For this optimizer skill, inspect the inner optimization
histories and their gains, then improve diagnosis, candidate construction,
review, or selection across the supplied tasks. Preserve these responsibilities
and independent external scoring. Consult references/workspace.md,
references/evaluation.md, and references/reviewer-policy.md as needed.
"""


def _text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(content)


def create_seed_task_skill(directory, name, description):
    """Create the generic task seed described by Appendix F, with no solver."""
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) or not description.strip():
        raise ValueError('skill_seed_identity_invalid')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    _text(directory / 'SKILL.md', '---\nname: ' + name + '\ndescription: '
          + json.dumps(description, ensure_ascii=False) + '\n---\n\n'
          '# Task execution\n\nInspect the instruction and supplied inputs. '
          'Execute the required work, check the outputs, and address observed '
          'failures before returning the requested artifacts.\n')
    return str(directory.resolve())


def create_seed_meta_skill(directory):
    """Materialize an authored paraphrase of the published seed responsibilities."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    _text(directory / 'SKILL.md', '---\nname: skill-self-evolver\n'
          'description: Optimize task skills or this optimization skill using '
          'execution evidence, candidate evaluation, independent review, and '
          'parent selection.\n---\n\n' + SEED_INSTRUCTIONS)
    _text(directory / 'references/workspace.md',
          '# Workspace\n\nEach archive node holds a complete skill package. '
          'Creating a revision consumes one candidate unit, including drafts '
          'that later fail. Inspect the archive and prior decisions. Create '
          'revisions from an existing eligible parent and record your hypothesis. '
          'Use select_parent to retain a seed or accepted node and decide '
          'whether to continue.\n')
    _text(directory / 'references/evaluation.md',
          '# Evaluation\n\nrollout runs training trials. evaluate_candidate '
          'uses the fixed validation set. Task scores are macro-averaged trial '
          'rewards. Meta scores are mean improvements of the task skills produced '
          'by inner optimizations over their initial validation scores. Original '
          'verifier outcomes, activation evidence, failures, and costs remain '
          'available through read_evidence using the sha256 evidence_id in '
          'host-provided evidence_refs. Read long records in pages. Only trusted '
          'host evidence indexes authorize additional records. Oracle and '
          'reference solutions are unavailable.\n')
    _text(directory / 'references/reviewer-policy.md',
          '# Independent review\n\nReview the parent, candidate, proposal, '
          'evaluation, and supporting rollout without optimizer deliberations. '
          'Reject unchanged or unusable revisions and revisions that were never '
          'activated according to the full rollout and native loading evidence. '
          'The evaluation activation summary is true when all evaluated executions '
          'confirm loading, false when any execution lacks loading, and null when '
          'unknown. A false summary can include partial activation. Assess partial '
          'or unknown loading from all available rollout and validation evidence, '
          'and retain uncertainty without claiming actual use. Meta revisions '
          'must retain evidence-based diagnosis, candidate construction, '
          'external evaluation, independent review, and parent selection. '
          'Give the verdict and its supporting evidence.\n')
    return str(directory.resolve())


def _card(directory):
    directory = Path(directory).resolve()
    content = (directory / 'SKILL.md').read_text(encoding='utf-8')
    match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)', content, re.S)
    if match is None:
        raise ValueError('skill_frontmatter_missing')
    fields = {}
    for key in ('name', 'description'):
        line = re.search(r'^' + key + r':[ \t]*(.*)$', match[1], re.M)
        if line is None:
            raise ValueError('skill_' + key + '_missing')
        value = line[1].strip()
        if value in ('|', '|-', '|+', '>', '>-', '>+'):
            following = match[1][line.end():].splitlines()
            block = []
            for part in following:
                if part and not part[0].isspace():
                    break
                if part.strip():
                    block.append(part.strip())
            value = (' ' if value.startswith('>') else '\n').join(block)
        elif value.startswith('"'):
            value = json.loads(value)
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        if not isinstance(value, str) or not value.strip():
            raise ValueError('skill_' + key + '_invalid')
        fields[key] = value
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', fields['name']):
        raise ValueError('skill_name_invalid')
    return {**fields, 'path': str(directory)}


def _package(directory):
    directory = Path(directory).resolve()
    files = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('skill_package_symlink')
        if path.is_file():
            files.append((path.relative_to(directory).as_posix(),
                          hashlib.sha256(path.read_bytes()).hexdigest()))
    card = _card(directory)
    digest = hashlib.sha256(json.dumps(files, ensure_ascii=False).encode()).hexdigest()
    return {'card': card, 'digest': digest, 'files': [name for name, _ in files]}


def _score(result):
    value = result.get('score')
    if isinstance(value, bool) or value is None:
        raise ValueError('skill_evaluation_score_invalid')
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError('skill_evaluation_score_invalid') from error
    if not amount.is_finite():
        raise ValueError('skill_evaluation_score_invalid')
    return amount


def _tool(name, description, properties=None, required=()):
    return {'name': name, 'description': description, 'parameters': {
        'type': 'object', 'properties': properties or {}, 'required': list(required),
        'additionalProperties': False}}


class SkillInfinityRun:
    """One task/meta optimization archive controlled by a tool-using agent."""

    def __init__(self, seed_skill, workspace, *, optimization_target, context,
                 call_agent, evaluate, review, candidate_budget=4, meta_skill=None):
        if optimization_target not in ('task_skill', 'meta_skill'):
            raise ValueError('skill_optimization_target_invalid')
        if type(candidate_budget) is not int or candidate_budget < 0:
            raise ValueError('skill_candidate_budget_invalid')
        self.directory = Path(workspace).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.target = optimization_target
        self.context = copy.deepcopy(context)
        self.call_agent = call_agent
        self.evaluate = evaluate
        self.review = review
        self.budget = candidate_budget
        self.meta_skill = Path(meta_skill).resolve() if meta_skill else None
        self.nodes = {}
        self.decisions = []
        self.iteration = 0
        self.created = 0
        self.tool_calls = 0
        self.parent = 'seed'
        self.active_decision = None
        self.iteration_created = 0
        self.controller_reads = []
        self.controller_observations = []
        self.evidence_refs = {}
        self.evidence_indexes = set()
        self._install('seed', seed_skill, None)
        save(self.directory / 'context.json', {'format': REPRODUCTION,
             'paper': PAPER, 'optimization_target': self.target,
             'candidate_budget': self.budget, 'context': self.context,
             'cost_accounting': 'original_caller_ledger'})

    def _install(self, node_id, package, parent):
        package = _package(package)
        destination = self.directory / node_id / 'skill' / package['card']['name']
        shutil.copytree(package['card']['path'], destination)
        node = {'node_id': node_id, 'parent_id': parent, 'status': 'seed' if parent is None else 'proposed',
                'skill_directory': str(destination), 'name': package['card']['name']}
        save(self.directory / node_id / 'node.json', node)
        self.nodes[node_id] = node
        return node

    def _node(self, node_id):
        node = self.nodes[node_id]
        package = _package(node['skill_directory'])
        if node.get('evaluated_digest') and node['evaluated_digest'] != package['digest']:
            raise ValueError('skill_evaluated_package_changed')
        return node

    def tools(self):
        identity = {'type': 'string'}
        return [
            _tool('inspect_archive', 'Read optimization history, scores and remaining candidates.'),
            _tool('read_skill', 'Read a skill resource. controller reads the installed meta-skill.',
                  {'node_id': identity, 'resource': identity}, ('node_id', 'resource')),
            _tool('read_evidence', 'Read a page of original host-authorized evidence by sha256. '
                  'Trusted evidence indexes reveal further authorized references. No arbitrary paths.',
                  {'evidence_id': identity, 'offset': {'type': 'integer', 'minimum': 0},
                   'limit': {'type': 'integer', 'minimum': 1, 'maximum': 24000}}, ('evidence_id',)),
            _tool('rollout', 'Execute training trials and obtain their original evidence.',
                  {'node_id': identity}, ('node_id',)),
            _tool('create_candidate', 'Copy an eligible skill parent and apply complete resource replacements.',
                  {'parent_id': identity, 'files': {'type': 'object', 'additionalProperties': {'type': ['string', 'null']}},
                   'proposal': {'type': 'object', 'properties': {key: identity for key in
                       ('observation', 'change', 'predicted_effect', 'falsifying_outcome')},
                       'required': ['observation', 'change', 'predicted_effect', 'falsifying_outcome'],
                       'additionalProperties': False}}, ('parent_id', 'files', 'proposal')),
            _tool('evaluate_candidate', 'Run the fixed external validation on a candidate.',
                  {'node_id': identity}, ('node_id',)),
            _tool('review_candidate', 'Request an independent fresh-context review of an evaluated candidate.',
                  {'node_id': identity}, ('node_id',)),
            _tool('select_parent', 'Choose a seed/accepted node and continue or stop this optimization.',
                  {'selected_node_id': identity, 'action': {'type': 'string', 'enum': ['continue', 'stop']},
                   'reason': identity}, ('selected_node_id', 'action', 'reason'))]

    def archive(self):
        return {'optimization_target': self.target, 'context': self.context,
                'parent': self.parent, 'iteration': self.iteration,
                'remaining_candidates': self.budget - self.created,
                'nodes': copy.deepcopy(list(self.nodes.values())),
                'decisions': copy.deepcopy(self.decisions),
                'evidence_refs': copy.deepcopy(list(self.evidence_refs.values()))}

    def _register_evidence(self, result):
        # Only explicit host fields authorize reads. Raw trajectories may contain
        # model-authored path/hash pairs and never extend this allowlist.
        for field in ('evidence_refs', 'evidence_indexes'):
            for reference in result.get(field, []):
                if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
                    raise ValueError('skill_host_evidence_reference_invalid')
                verify(reference)
                self.evidence_refs[reference['sha256']] = copy.deepcopy(reference)
                if field == 'evidence_indexes':
                    self.evidence_indexes.add(reference['sha256'])

    def _read_evidence(self, evidence_id, offset=0, limit=12000):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
            raise ValueError('skill_evidence_page_invalid')
        if evidence_id not in self.evidence_refs:
            raise ValueError('skill_evidence_not_authorized')
        reference = self.evidence_refs[evidence_id]
        content = verify(reference).decode('utf-8')
        discovered = []
        if evidence_id in self.evidence_indexes:
            index = json.loads(content)
            if not isinstance(index, dict):
                raise ValueError('skill_host_evidence_index_invalid')
            self._register_evidence(index)
            discovered = [copy.deepcopy(reference) for field in ('evidence_refs', 'evidence_indexes')
                          for reference in index.get(field, [])]
        end = min(len(content), offset + limit)
        return {'evidence': copy.deepcopy(reference), 'content': content[offset:end],
                'offset': offset, 'total_characters': len(content),
                'next_offset': end if end < len(content) else None,
                'discovered_evidence_refs': discovered}

    def _read_skill(self, node_id, resource):
        if node_id == 'controller':
            directory = self._controller()
        else:
            directory = Path(self._node(node_id)['skill_directory'])
        path = (directory / resource).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise ValueError('skill_resource_invalid')
        if node_id == 'controller' and resource == 'SKILL.md':
            self.controller_reads.append(file_ref(path))
        return {'resource': resource, 'content': path.read_text(encoding='utf-8'),
                'evidence': file_ref(path)}

    def _evaluate(self, node_id, split):
        node = self._node(node_id)
        field = 'rollout' if split == 'training' else 'evaluation'
        if field in node:
            return copy.deepcopy(node[field])
        directory = self.directory / node_id / field
        directory.mkdir()
        request = {'optimization_target': self.target, 'skill_directory': node['skill_directory'],
                   'node_id': node_id, 'split': split, 'context': self.context,
                   'output_directory': str(directory), 'discovery': 'native_name_description'}
        save(directory / 'request.json', request)
        before = _package(node['skill_directory'])['digest']
        try:
            result = self.evaluate(request)
            save(directory / 'result.json', result)
            if before != _package(node['skill_directory'])['digest']:
                raise ValueError('skill_evaluation_modified_package')
            _score(result)
            self._register_evidence(result)
            node[field] = result
            node['evaluated_digest'] = before
            if split == 'validation':
                node['validation_score'] = str(_score(result))
            return copy.deepcopy(result)
        except Exception as error:
            node['status'] = 'evaluation_failed'
            save(directory / 'failure.json', {'error': type(error).__name__ + ':' + str(error)})
            raise

    def _create(self, parent_id, files, proposal):
        if self.created >= self.budget or self.iteration_created >= 2:
            raise ValueError('skill_candidate_budget_exhausted')
        parent = self._node(parent_id)
        if parent['status'] not in ('seed', 'accepted'):
            raise ValueError('skill_candidate_parent_ineligible')
        node_id = 'i' + str(self.iteration).zfill(3) + '-c' + str(self.iteration_created + 1)
        self.created += 1
        self.iteration_created += 1
        node = self._install(node_id, parent['skill_directory'], parent_id)
        try:
            expected = {'observation', 'change', 'predicted_effect', 'falsifying_outcome'}
            if set(proposal) != expected or any(not isinstance(v, str) or not v.strip() for v in proposal.values()):
                raise ValueError('skill_candidate_proposal_invalid')
            if not isinstance(files, dict):
                raise ValueError('skill_candidate_files_invalid')
            directory = Path(node['skill_directory'])
            for resource, content in files.items():
                path = (directory / resource).resolve()
                if not path.is_relative_to(directory) or path == directory:
                    raise ValueError('skill_candidate_resource_invalid')
                if content is None:
                    path.unlink()
                else:
                    if not isinstance(content, str):
                        raise ValueError('skill_candidate_resource_invalid')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding='utf-8')
            if _card(directory)['name'] != parent['name']:
                raise ValueError('skill_candidate_identity_changed')
            node['proposal'] = copy.deepcopy(proposal)
            save(self.directory / node_id / 'proposal.json', proposal)
            return copy.deepcopy(node)
        except Exception as error:
            node['status'] = 'draft_failed'
            save(self.directory / node_id / 'failure.json', {'error': type(error).__name__ + ':' + str(error)})
            raise

    def _review(self, node_id):
        node = self._node(node_id)
        if node_id == 'seed' or 'evaluation' not in node:
            raise ValueError('skill_review_requires_candidate_evaluation')
        if 'review' in node:
            return copy.deepcopy(node['review'])
        parent = self._node(node['parent_id'])
        request = {'mode': 'review', 'fresh_context': True, 'optimization_target': self.target,
                   'parent_skill_directory': parent['skill_directory'],
                   'candidate_skill_directory': node['skill_directory'],
                   'proposal': node['proposal'], 'evaluation': node['evaluation'],
                   'parent_rollout': parent.get('rollout'),
                   'candidate_rollout': node.get('rollout'),
                   'reviewer_policy': str(self._controller() / 'references/reviewer-policy.md')}
        save(self.directory / node_id / 'review-request.json', request)
        result = self.review(request)
        if not isinstance(result.get('accepted'), bool) or not isinstance(result.get('reason'), str):
            raise ValueError('skill_review_result_invalid')
        self._node(node_id)
        unchanged = _package(node['skill_directory'])['digest'] == _package(parent['skill_directory'])['digest']
        result = {**result, 'skill_activated': node['evaluation'].get('skill_activated'),
                  'activation_basis': 'original_evaluation_summary; independent_review_of_available_evidence'}
        if unchanged:
            result = {**result, 'accepted': False, 'host_rejection': 'unchanged_package'}
        node['review'] = result
        node['status'] = 'accepted' if result['accepted'] else 'rejected'
        save(self.directory / node_id / 'review.json', result)
        return copy.deepcopy(result)

    def _select(self, selected_node_id, action, reason):
        node = self._node(selected_node_id)
        if node['status'] not in ('seed', 'accepted') or action not in ('continue', 'stop'):
            raise ValueError('skill_selection_invalid')
        if not isinstance(reason, str) or not reason.strip() or self.active_decision is not None:
            raise ValueError('skill_selection_reason_or_duplicate')
        pending_reviews = [row['node_id'] for row in self.nodes.values()
                           if row['parent_id'] is not None and 'evaluation' in row and 'review' not in row]
        if pending_reviews:
            raise ValueError('skill_selection_reviews_pending')
        decision = {'selected_node_id': selected_node_id, 'action': action, 'reason': reason}
        save(self.directory / ('decision-' + str(self.iteration).zfill(3) + '.json'), decision)
        self.active_decision = decision
        return decision

    def dispatch(self, name, arguments):
        """Expose host tools to the original model session; retain errors too."""
        operations = {'inspect_archive': self.archive, 'read_skill': self._read_skill,
                      'read_evidence': self._read_evidence,
                      'rollout': lambda node_id: self._evaluate(node_id, 'training'),
                      'create_candidate': self._create,
                      'evaluate_candidate': lambda node_id: self._evaluate(node_id, 'validation'),
                      'review_candidate': self._review, 'select_parent': self._select}
        receipt = {'tool': name, 'arguments': copy.deepcopy(arguments)}
        try:
            if self.active_decision is not None:
                raise ValueError('skill_iteration_already_decided')
            result = operations[name](**arguments)
            receipt.update(status='succeeded', result=result)
        except Exception as error:
            result = {'status': 'error', 'error': type(error).__name__ + ':' + str(error)}
            receipt.update(status='failed', result=result)
        self.tool_calls += 1
        (self.directory / 'tool-calls').mkdir(exist_ok=True)
        save(self.directory / 'tool-calls' / (str(self.tool_calls).zfill(5) + '.json'), receipt)
        return result

    def _controller(self):
        if self.target == 'meta_skill':
            return Path(self._node(self.parent)['skill_directory'])
        if self.meta_skill is None:
            raise ValueError('skill_meta_controller_required')
        return self.meta_skill

    def run(self):
        result = {'format': REPRODUCTION, 'status': 'failed', 'production_enabled': False,
                  'optimization_target': self.target, 'observed_model_usd_decimal': None,
                  'cost_accounting': 'original_caller_ledger'}
        try:
            self._evaluate('seed', 'validation')
            while self.created < self.budget:
                self.iteration_created = 0
                self.active_decision = None
                self.controller_reads = []
                request = {'mode': 'meta_iteration' if self.target == 'meta_skill' else 'iteration',
                           'prompt': 'Optimize the skill in this workspace. Complete iteration '
                                     + str(self.iteration) + ', record your decision, then return.',
                           'workspace': str(self.directory), 'parent': self.parent,
                           'optimization_target': self.target,
                           'available_skill_cards': [_card(self._controller())], 'tools': self.tools()}
                save(self.directory / ('request-' + str(self.iteration).zfill(3) + '.json'), request)
                response = self.call_agent(request, self.dispatch)
                save(self.directory / ('response-' + str(self.iteration).zfill(3) + '.json'), response)
                activation = True if self.controller_reads else response.get('controller_activated')
                if activation is not None and type(activation) is not bool:
                    raise ValueError('skill_controller_activation_invalid')
                self.controller_observations.append({'iteration': self.iteration,
                    'controller': request['available_skill_cards'][0],
                    'activated': activation, 'read_evidence': self.controller_reads,
                    'host_evidence': response.get('controller_activation_evidence')})
                if self.active_decision is None:
                    raise ValueError('skill_agent_decision_missing')
                self.decisions.append(self.active_decision)
                self.parent = self.active_decision['selected_node_id']
                if self.active_decision['action'] == 'stop':
                    break
                if self.iteration_created == 0:
                    raise ValueError('skill_iteration_without_candidate')
                self.iteration += 1
            selected = self._node(self.parent)
            result.update(status='completed', selected_node=self.parent,
                          selected_skill=selected['skill_directory'], score=selected['validation_score'],
                          candidate_count=self.created, tool_calls=self.tool_calls,
                          controller_activation_observations=self.controller_observations,
                          archive=self.archive())
        except Exception as error:
            result.update(error=type(error).__name__ + ':' + str(error), archive=self.archive())
        if self.target == 'meta_skill':
            result['self_improvement'] = ('failed' if result['status'] != 'completed' else
                                          'completed' if self.decisions else 'seed_only')
            result['meta_refinement_outcome'] = 'changed' if self.parent != 'seed' else 'retained_seed'
        save(self.directory / 'result.json', result)
        return result


def optimize_task_skill(seed_skill, workspace, *, call_agent, evaluate, review,
                        task_context=None, meta_skill=None, candidate_budget=4):
    """Optimize one task skill with an installed meta-skill and original trials."""
    if meta_skill is None:
        meta_skill = create_seed_meta_skill(Path(workspace).parent / (Path(workspace).name + '-meta-seed'))
    return SkillInfinityRun(seed_skill, workspace, optimization_target='task_skill',
                            context=task_context or {}, call_agent=call_agent, evaluate=evaluate,
                            review=review, candidate_budget=candidate_budget, meta_skill=meta_skill).run()


def refine_meta_skill(seed_meta_skill, optimization_tasks, workspace, *, call_agent,
                      evaluate, review, outer_candidate_budget=4, inner_candidate_budget=2):
    """Use the same agent-led optimizer at both levels and score mean inner gain.

    Each task has id, seed_skill, and context. The caller supplies fixed trial
    sets through context and external evaluate. Final heldout task execution
    remains with the benchmark host.
    """
    if not optimization_tasks or len({task['id'] for task in optimization_tasks}) != len(optimization_tasks):
        raise ValueError('skill_meta_tasks_invalid')

    def evaluate_meta(request):
        rows = []
        evidence_refs = []
        evidence_indexes = []
        for index, task in enumerate(optimization_tasks):
            output = Path(request['output_directory']) / ('inner-' + str(index))
            inner = optimize_task_skill(task['seed_skill'], output, call_agent=call_agent,
                evaluate=evaluate, review=review, task_context=task.get('context', {}),
                meta_skill=request['skill_directory'], candidate_budget=inner_candidate_budget)
            if inner['status'] != 'completed':
                raise ValueError('skill_meta_inner_optimization_failed:' + task['id'])
            evidence_refs.append(file_ref(output / 'result.json'))
            for pattern in ('tool-calls/*.json', 'request-*.json', 'response-*.json'):
                evidence_refs.extend(file_ref(path) for path in sorted(output.glob(pattern)))
            for node in inner['archive']['nodes']:
                for field in ('rollout', 'evaluation'):
                    evidence_refs.extend(node.get(field, {}).get('evidence_refs', []))
                    evidence_indexes.extend(node.get(field, {}).get('evidence_indexes', []))
            initial = _score(inner['archive']['nodes'][0]['evaluation'])
            gain = Decimal(inner['score']) - initial
            rows.append({'task_id': task['id'], 'initial_score': str(initial),
                         'final_score': inner['score'], 'gain': str(gain),
                         'inner_result': file_ref(output / 'result.json')})
        activations = []
        for row in rows:
            inner = json.loads(Path(row['inner_result']['path']).read_text(encoding='utf-8'))
            activations.extend(observation['activated'] for observation in
                               inner['controller_activation_observations'])
        activated = None
        if activations and all(value is True for value in activations):
            activated = True
        elif any(value is False for value in activations):
            activated = False
        return {'score': str(sum((Decimal(row['gain']) for row in rows), Decimal(0)) / len(rows)),
                'skill_activated': activated, 'optimization_results': rows,
                'evidence_refs': evidence_refs, 'evidence_indexes': evidence_indexes,
                'activation_basis': 'inner_controller_observations',
                'observed_model_usd_decimal': None, 'cost_accounting': 'original_caller_ledger'}

    result = SkillInfinityRun(seed_meta_skill, workspace, optimization_target='meta_skill',
        context={'optimization_task_ids': [task['id'] for task in optimization_tasks],
                 'inner_candidate_budget': inner_candidate_budget}, call_agent=call_agent,
        evaluate=evaluate_meta, review=review, candidate_budget=outer_candidate_budget).run()
    return result
