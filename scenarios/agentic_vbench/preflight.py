"""Zero-model inspection of official tasks and witnessed native tool calls.

This is a scene preflight, not a learner or benchmark runner. Admission delegates
to the original Script/Artifact compilers; a static pass grants no certificate.
Task answers and oracle files are never opened by this module.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.artifact_motif_compiler import validate_source
from src.motif_core.offline.compilation.script_motif_compiler import compile_script, extract


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_task(task):
    """Read only the public prompt, container recipe, and scheduling metadata."""
    task = Path(task)
    config = tomllib.loads((task/'task.toml').read_text())
    steps = config.get('steps', [])
    if len(steps) != 1 or steps[0].get('name') != 'solve':
        raise ValueError('agentic_vbench_single_solve_step_required')
    prompt = task/'steps/solve/instruction.md'
    recipe = task/'environment/Dockerfile'
    text = prompt.read_text()
    family = task.parent.name.removeprefix('agentic_vbench_')
    if family not in ('assembly', 'sequencing'):
        raise ValueError('agentic_vbench_family_outside_experiment')
    candidates = re.search(r'You are given \*\*(\d+) candidate video clips', text)
    segments = re.search(r'Exactly \*\*(\d+) entries\*\*', text)
    return {
        'task_id': task.name, 'family': family,
        'prompt_sha256': sha(prompt), 'dockerfile_sha256': sha(recipe),
        'config_sha256': sha(task/'task.toml'),
        'candidate_count': int(candidates[1]) if candidates else None,
        'required_segments': int(segments[1]) if segments else None,
        'storyboard_slots': len(re.findall(r'^### Slot \d+\s*$', text, re.M)) if family == 'assembly' else None,
        'deliverables': sorted(set(re.findall(r'/workspace/output/solution\.(?:mp4|json)', text))),
        'agent': steps[0].get('agent', {}), 'verifier': steps[0].get('verifier', {}),
        'base_tools': ['execute', 'read_image'],
        'toolchain': 'ffmpeg/ffprobe' if 'ffmpeg' in recipe.read_text() else 'unknown',
        'host_layout': 'steps/solve; BenchmarkHost SkillsBenchTrial expects root instruction/tests',
        'materials_setup': 'copy /baked/materials into isolated /workspace/materials before agent',
    }


def _check(function, *args):
    try:
        function(*args)
        return {'status': 'static_pass_only'}
    except (ValueError, SyntaxError, KeyError, TypeError, OSError, UnicodeError) as error:
        return {'status': 'rejected', 'reason': str(error)[:240]}


def audit_native_trace(trace):
    """Pass exact successful command bytes to the old compiler, without replay.

    Missing pre-call snapshots remain missing. A post-task source file is never
    substituted for execution-boundary evidence, and no candidate is invented.
    """
    trace = Path(trace)
    rows = [json.loads(line) for line in trace.read_text().splitlines() if line]
    calls = [row for row in rows if row.get('phase') == 'finished']
    programs = []
    for row in calls:
        if row.get('name') != 'execute':
            continue
        command = row.get('arguments', {}).get('command', '')
        result = row.get('result', {})
        item = {'call_id': row.get('call_id'),
                'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
                'returncode': result.get('returncode')}
        if result.get('returncode') != 0:
            item['status'] = 'original_execution_failed'
            programs.append(item)
            continue
        try:
            source = extract(command)[1]
        except (ValueError, SyntaxError, OSError) as error:
            item.update(status='not_extracted', reason=str(error)[:240])
        else:
            tree = ast.parse(source)
            imports = sorted({name for node in ast.walk(tree)
                              for name in ([node.module] if isinstance(node, ast.ImportFrom)
                                           else [a.name for a in node.names] if isinstance(node, ast.Import) else [])})
            item.update(status='extracted', source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                        source_bytes=len(source.encode()), imports=imports,
                        script=_check(compile_script, source, {}), artifact=_check(validate_source, source))
        programs.append(item)
    return {'trace_sha256': sha(trace), 'finished_tool_calls': len(calls),
            'tools': dict(Counter(row.get('name') for row in calls)),
            'programs': programs, 'certified_capabilities': None,
            'scope': 'static admission diagnostic; not learning, certification, adoption, or savings',
            'boundary_evidence': 'not inferred from final workspace'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--official-root', type=Path)
    parser.add_argument('--trace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'model_requests': 0, 'compilers': {str(p.relative_to(ROOT)): sha(p) for p in (
        ROOT/'src/motif_core/offline/compilation/script_motif_compiler.py', ROOT/'src/adapters/artifact_motif_compiler.py')}}
    if args.official_root:
        report['tasks'] = [inspect_task(task) for family in ('assembly', 'sequencing')
                           for task in sorted((args.official_root/'tasks'/('agentic_vbench_'+family)).iterdir())
                           if task.is_dir()]
    if args.trace:
        report['trace'] = audit_native_trace(args.trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite another run's diagnostic evidence.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(args.output)


if __name__ == '__main__':
    main()
