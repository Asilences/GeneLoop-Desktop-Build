"""Run the unmodified official low-level evaluators after solver termination.

No score threshold or reference source is sent back to the solver or learner.
The official GPT-4 Vision stage remains explicit, never replaced by a different
judge or silently omitted from an overall quality claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


def evaluate(official, frozen, trial, output, image, delivery=None):
    official, frozen, trial, output = map(lambda p: Path(p).resolve(), (official, frozen, trial, output))
    effective = json.loads((trial / 'effective.json').read_text())
    task_id = effective['task_id']
    task = json.loads((frozen / 'manifest.json').read_text())['tasks'][task_id]
    reference = frozen / 'evaluation-only' / task_id / (task_id + '.py')
    if hashlib.sha256(reference.read_bytes()).hexdigest() != task['reference_code_sha256']:
        raise ValueError('chartmimic_reference_code_changed')
    audit = json.loads(Path(delivery).read_text()) if delivery else None
    if audit and audit['task_id'] != task_id:
        raise ValueError('chartmimic_delivery_task_mismatch')
    source = Path(audit['source']['path']) if audit else trial / 'workspace/code/plot.py'
    if not source.is_file() and effective.get('capability_library'):
        source = trial / 'workspace/outputs/code/rendered/geneloop_reused_program.py'
    if not source.is_file():
        raise ValueError('chartmimic_candidate_source_missing')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    # Scoring executes code and creates log files. Work only on new copies.
    shutil.copytree(official, output / 'official', ignore=shutil.ignore_patterns('.git'))
    shutil.copytree(trial / 'workspace/code', output / 'work')
    shutil.copytree(trial / 'workspace/inputs', output / 'work/inputs', dirs_exist_ok=True)
    shutil.copytree(trial / 'workspace/outputs/code', output / 'work/outputs', dirs_exist_ok=True)
    raw_source = source.read_bytes()
    if audit and hashlib.sha256(raw_source).hexdigest() != audit['source']['sha256']:
        raise ValueError('chartmimic_delivery_source_changed')
    (output / 'source-original.py').write_bytes(raw_source)
    entrypoint_binding = None
    if effective.get('program_layout', '').startswith('parameter-files-'):
        bindings = audit['inputs'] if audit else [{'virtual': '/work/plot-spec.json',
            'path': str(trial/'workspace/code/plot-spec.json')}]
        for item in bindings:
            path=Path(item['path'])
            if not path.is_file() or item.get('sha256',hashlib.sha256(path.read_bytes()).hexdigest()) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('chartmimic_current_parameters_missing_or_changed')
        # Bind only the solver's own current JSON. The official evaluators still
        # instrument/execute the resulting source unchanged; no reference data
        # or algorithm is injected. Each execution gets a fresh scratch output.
        indices = audit['input_argument_indices'] if audit else [0]
        output_index = audit['output_argument_index'] if audit else 1
        arguments = [''] * (max(indices+[output_index])+1)
        for index,item in zip(indices,bindings,strict=True):
            arguments[index]=item['virtual']
        arguments[output_index]='/work/outputs/evaluation-rendered'
        if any(not value for value in arguments):
            raise ValueError('chartmimic_incomplete_native_argv_binding')
        argv = ['/work/plot.py']+arguments
        prefix = ('import sys as chart_evaluation_sys\nimport shutil as chart_evaluation_shutil\n'
                  + 'import runpy as chart_evaluation_runpy\n'
                  + 'chart_evaluation_sys.argv=' + repr(argv) + '\n'
                  + "chart_evaluation_shutil.rmtree('/work/outputs/evaluation-rendered',ignore_errors=True)\n"
                  + "try:\n    chart_evaluation_runpy.run_path('/work/source-original.py',run_name='__main__')\n"
                  + 'except SystemExit as chart_evaluation_exit:\n'
                  + '    if chart_evaluation_exit.code not in (None,0):\n        raise\n')
        # A CLI module may contain __future__ imports or a successful SystemExit.
        # Launch it with normal Python module semantics, not string concatenation.
        (output / 'work/source-original.py').write_bytes(raw_source)
        (output / 'work/plot.py').write_text(prefix)
        entrypoint_binding = {'argv': argv, 'source_sha256': hashlib.sha256(raw_source).hexdigest(),
            'current_parameters': bindings,
            'driver': 'stdlib_runpy_preserving_original_module_bytes',
            'scope': 'host_current_file_and_argv_binding_only_no_oracle_data'}
    (output / 'gold').mkdir()
    shutil.copyfile(reference, output / 'gold' / reference.name)
    script = '''import json,sys,time,os
sys.path[:0]=['/official','/official/chart2code']
from utils.evaluator.text_evaluator import TextEvaluator
from utils.evaluator.chart_type_evaluator import ChartTypeEvaluator
from utils.evaluator.color_evaluator import ColorEvaluator
from utils.evaluator.layout_evaluator import LayoutEvaluator
results={}
for name,scorer in [('text',TextEvaluator(use_position=False,use_axs=False)),('chart_type',ChartTypeEvaluator()),('color',ColorEvaluator()),('layout',LayoutEvaluator())]:
    started=time.monotonic()
    try:
        scorer(generation_code_file='/work/plot.py',golden_code_file='/gold/TASK.py')
        results[name]={'status':'scored','metrics':scorer.metrics}
    except Exception as error:
        results[name]={'status':'failed','error':type(error).__name__+':'+str(error)}
    results[name]['elapsed_seconds']=time.monotonic()-started
with open('/scores/lowlevel.json','w') as f:json.dump(results,f,indent=2)
'''.replace('TASK', task_id)
    (output / 'score.py').write_text(script)
    started = time.monotonic()
    process = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--cpus', '2', '--memory', '4g',
        '-v', str(output / 'official') + ':/official', '-v', str(output / 'work') + ':/work',
        '-v', str(output / 'gold') + ':/gold', '-v', str(output) + ':/scores',
        '-e', 'PROJECT_PATH=/official', '-e', 'PYTHONPATH=/official:/official/chart2code',
        '-w', '/official', image, 'python3', '/scores/score.py'], capture_output=True, text=True, timeout=300)
    (output / 'stdout.log').write_text(process.stdout)
    (output / 'stderr.log').write_text(process.stderr)
    scores = json.loads((output / 'lowlevel.json').read_text()) if (output / 'lowlevel.json').is_file() else None
    result = {'format': 'chartmimic_evaluation_v1', 'task_id': task_id,
        'lowlevel': scores, 'returncode': process.returncode, 'elapsed_seconds': time.monotonic() - started,
        'highlevel': {'status': 'pending', 'judge': 'gpt-4-vision-preview',
            'official_prompt_sha256': hashlib.sha256((official / 'chart2code/prompts/GPT4EvaluationAgent/gpt-4-vision-preview.json').read_bytes()).hexdigest(),
            'reason': 'original_judge_not_configured_in_this_trial'},
        'overall_quality': 'unreviewed', 'official_evaluator_modified': False,
        'entrypoint_binding': entrypoint_binding,
        'scope': 'official_four_lowlevel_metrics_only; highlevel and complete quality remain pending'}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('official', 'frozen', 'trial', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--image', default='geneloop-chartmimic:20261109')
    parser.add_argument('--delivery', type=Path, help='Hash-checked final delivery audit and actual native argv slots.')
    args = parser.parse_args()
    print(json.dumps(evaluate(args.official, args.frozen, args.trial, args.output, args.image, args.delivery), indent=2))
