"""Project genuine scene events into the original offline learner unchanged."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys


def extract(runtime, trial, output, *, next_generation=None, retirement_evidence=None):
    trial, output = Path(trial), Path(output)
    result = json.loads((trial / 'result.json').read_text())
    effective = json.loads((trial / 'effective.json').read_text())
    source_use = None
    if effective['role'] not in ('learning', 'certification'):
        if not next_generation or retirement_evidence is None:
            raise ValueError('non_successor_task_required')
        if __package__:
            from .source_use import retired_source
        else:
            from source_use import retired_source
        source_use = retired_source(trial, next_generation, retirement_evidence)
    sys.path.insert(0, str(Path(runtime).resolve()))
    from src.adapters.execution_learning_bridge import collect_shell_call
    from src.rsi.feedback.capability_feedback import verify, file_ref
    if result['status'] != 'completed':
        output.mkdir(parents=True, exist_ok=False)
        summary = {'task_id': effective['task_id'], 'source': file_ref(trial / 'result.json'),
            'status': 'skipped_unqualified_source', 'reason': 'source_task_not_completed',
            'original_status': result['status'], 'original_finish_reason': result.get('finish_reason'),
            'script_candidates': 0, 'artifact_candidates': 0, 'certification': 'not_attempted',
            'quality': result['quality'], 'scope': 'failed_experience_retained_not_admitted_to_learning'}
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        return summary
    events = (trial / 'events.jsonl').read_bytes()
    goal = (trial / 'prompt.txt').read_text()
    rows = [json.loads(line) for line in (trial / 'native-tools.jsonl').read_text().splitlines()]
    candidates, artifact_candidates, rejected, source_diagnostics = [], [], [], []
    for row in rows:
        if row['name'] != 'execute' or row['phase'] != 'finished':
            continue
        boundary = json.loads(verify(row['boundary']))
        after = json.loads(verify(row['after_boundary']))
        converted = collect_shell_call(task_id=effective['task_id'], call_id=row['call_id'], goal=goal,
            command=row['arguments']['command'], description=goal, stdout=row['result']['stdout'],
            workspace=boundary['workspace'], boundary=boundary, workdir='/work', after_boundary=after,
            events_sha256=hashlib.sha256(events).hexdigest(), succeeded=row['result']['returncode'] == 0)
        candidates.extend(converted['candidates'])
        artifact_candidates.extend(converted.get('artifact_candidates', []))
        rejected.extend({'call_id': row['call_id'], **reason} for reason in converted['rejected'])
        # A shell-envelope rejection must not hide the next real blocker. Ask
        # the original file binder about exact emitted source bytes, solely as
        # a diagnostic. This path never certifies or registers a candidate.
        for relative, reference in after['after']['files'].items():
            if not relative.endswith('.py'):
                continue
            source_raw = verify(reference)
            source = source_raw.decode('utf-8')
            if source not in row['arguments']['command']:
                continue
            from src.adapters.artifact_path_binding import bind_observed_files
            from src.adapters.artifact_motif_compiler import validate_source
            diagnostic = {'call_id': row['call_id'], 'source': reference,
                'scope': 'exact_emitted_source_diagnostic_only_not_a_candidate'}
            try:
                bound = bind_observed_files(source, '/work', boundary['workspace'], boundary, after,
                    task_id=effective['task_id'], call_id=row['call_id'], description=goal,
                    events_sha256=hashlib.sha256(events).hexdigest())
                diagnostic['original_file_binder'] = 'candidate' if bound is not None else 'no_witnessed_file_input_output_interface'
            except Exception as error:
                diagnostic['original_file_binder'] = str(error)
            try:
                validate_source(source)
                diagnostic['unchanged_artifact_source_admission'] = 'passed'
            except (ValueError, SyntaxError) as error:
                diagnostic['unchanged_artifact_source_admission'] = str(error)
            tree = ast.parse(source)
            diagnostic['savefig_calls'] = sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'savefig' for n in ast.walk(tree))
            diagnostic['literal_array_assignments'] = sum(isinstance(n, ast.Assign)
                and isinstance(n.value, (ast.List, ast.Tuple)) for n in ast.walk(tree))
            source_diagnostics.append(diagnostic)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('script.json', candidates), ('artifact.json', artifact_candidates), ('rejected.json', rejected)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    summary = {'task_id': effective['task_id'], 'source': file_ref(trial / 'result.json'),
        'script_candidates': len(candidates), 'artifact_candidates': len(artifact_candidates),
        'rejected': rejected, 'source_diagnostics': source_diagnostics,
        'certification': 'not_attempted', 'quality': result['quality'],
        'scope': 'offline_extraction_only_no_registration_or_quality_claim'}
    if source_use:
        summary['source_use'] = source_use
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--next-generation')
    parser.add_argument('--retirement-evidence', type=Path)
    args = parser.parse_args()
    print(json.dumps(extract(args.runtime, args.trial, args.output,
        next_generation=args.next_generation, retirement_evidence=args.retirement_evidence)))
