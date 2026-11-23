"""Read-only qualification of an actually used normal data plan.

Uses only generic frame-comparison helpers from the official checker. Expected
ordering, score(), main() and storyboard labels are never loaded or executed.
The generated worker runs in the existing task image, not in a new media backend.
"""
import argparse
import ast
import json
from pathlib import Path
import posixpath
import re
import shlex
import subprocess

try:
    from .plan_quality import evaluate, file_ref, SCOPE
except ImportError:
    from plan_quality import evaluate, file_ref, SCOPE

HELPERS = {'_downscale_max', '_ssim_gray', '_read_frames_around', '_max_ssim_pair', '_check_honesty'}
CONSTANTS = {'SSIM_THRESHOLD', 'N_SAMPLES', 'SSIM_MAX_SIDE'}


def frame_worker(checker, delivery):
    tree = ast.parse(Path(checker).read_text())
    selected = [node for node in tree.body if
                isinstance(node, ast.FunctionDef) and node.name in HELPERS or
                isinstance(node, ast.Assign) and len(node.targets) == 1 and
                isinstance(node.targets[0], ast.Name) and node.targets[0].id in CONSTANTS]
    names = {node.name if isinstance(node, ast.FunctionDef) else node.targets[0].id for node in selected}
    if names != HELPERS | CONSTANTS:
        raise ValueError('generic_frame_helper_contract_changed')
    for node in selected:
        if isinstance(node, ast.Assign) and type(ast.literal_eval(node.value)) not in (int, float):
            raise ValueError('generic_frame_constants_must_be_numeric')
    prefix = 'from pathlib import Path\nimport cv2\nimport numpy as np\nimport json\n'
    body = ast.unparse(ast.Module(body=selected, type_ignores=[]))
    suffix = '''
root = Path(DELIVERY)
segments = json.loads((root/'solution.json').read_text())['segments']
checks = []
for segment in segments:
    source = str(segment['source']).removesuffix('.mp4')
    ok, samples = _check_honesty(root/'solution.mp4', Path('/workspace/materials')/(source+'.mp4'), segment)
    checks.append({'source':source, 'passed':ok, 'samples':samples})
capture = cv2.VideoCapture(str(root/'solution.mp4'))
fps = capture.get(cv2.CAP_PROP_FPS)
advertised = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
decoded = 0
while True:
    ok, frame = capture.read()
    if not ok: break
    decoded += 1
capture.release()
duration = decoded / fps if fps > 0 else None
end = float(segments[-1]['output'][1])
clock_ok = duration is not None and abs(duration-end) <= 1/fps + 2e-6
print(json.dumps({'passed':bool(checks) and all(c['passed'] for c in checks) and decoded==advertised and clock_ok,
 'clips':checks, 'threshold':SSIM_THRESHOLD, 'samples_per_clip':N_SAMPLES,
 'decoded_frames':decoded, 'advertised_frames':advertised, 'fps':fps,
 'decoded_video_duration_seconds':duration, 'manifest_end_seconds':end, 'video_clock_passed':clock_ok,
 'scope':'configured_claimed_sources_and_decoded_video_clock_no_storyboard_or_audio_quality'}))
'''.replace('DELIVERY', repr(delivery))
    return prefix + body + '\n' + suffix


def media_chains(command):
    """Read literal paths in successful trace lines; never execute shell text.

    This is only a consumption audit. It neither extracts programs nor grants
    candidates to the original learner. Unknown expansions remain unsupported.
    """
    variables = {}
    for line in command.splitlines():
        assignment = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)=(/[^\s$`;&|]+)', line.strip())
        if assignment:
            variables[assignment[1]] = assignment[2]
            continue
        expanded = re.sub(r'\$([A-Za-z_][A-Za-z0-9_]*)',
                          lambda match: variables.get(match[1], match[0]), line)
        if any(token in expanded for token in (';', '||', '$', '`')):
            continue
        yield [shlex.split(piece) for piece in expanded.split('&&')]


def qualify(trial, extraction, checker, output, delivery_relative='.', media_trial=None,
            frozen_frame_worker=None):
    trial, extraction, checker, output = map(lambda p: Path(p).resolve(), (trial, extraction, checker, output))
    effective = json.loads((trial/'effective.json').read_text())
    result = json.loads((trial/'result.json').read_text())
    summary = json.loads((extraction/'summary.json').read_text())
    if (effective['role'] not in ('development', 'certification') or
            effective.get('evaluation_scope') != SCOPE or result['status'] != 'completed' or
            summary['task_id'] != effective['task_id'] or summary['role'] != effective['role']):
        raise ValueError('finished_normal_plan_source_or_certification_required')
    media_trial = Path(media_trial).resolve() if media_trial else trial
    media_effective = json.loads((media_trial/'effective.json').read_text())
    media_result = json.loads((media_trial/'result.json').read_text())
    same = ('task_id','task_sha256','role','evaluation_scope','inputs_sha256','media_metadata_sha256',
            'media_array_metadata_sha256','image_id','model')
    if (any(media_effective.get(key) != effective.get(key) for key in same)
            or media_result['status'] != 'completed'):
        raise ValueError('same_finished_project_inputs_required_for_media_recovery')
    if media_trial != trial and (effective['role'] != 'certification' or not frozen_frame_worker):
        raise ValueError('same_certification_recovery_requires_frozen_frame_worker')
    delivery = media_trial/'media-workspace/output'/delivery_relative
    if not delivery.resolve().is_relative_to((media_trial/'media-workspace/output').resolve()):
        raise ValueError('delivery_must_be_inside_actual_output_tree')
    output.mkdir(parents=True, exist_ok=False)
    proof = {'scope': SCOPE, 'passed': False, 'task_id': effective['task_id'], 'role': effective['role'],
             'evaluator_sha256': file_ref(__file__)['sha256'],
             'plan_evaluator_sha256': file_ref(Path(__file__).with_name('plan_quality.py'))['sha256'],
             'quality_scope': 'configured_project_delivery_not_official_storyboard_success',
             'source': [file_ref(trial/name) for name in ('effective.json','result.json','events.jsonl','native-tools.jsonl')],
             'extraction': file_ref(extraction/'artifact.json'), 'delivery_relative': delivery_relative}
    rows = [row for row in map(json.loads, (trial/'native-tools.jsonl').read_text().splitlines())
            if row['phase'] == 'finished' and row['name'] == 'execute']
    media_rows = [row for row in map(json.loads, (media_trial/'native-tools.jsonl').read_text().splitlines())
                  if row['phase'] == 'finished' and row['name'] == 'execute']
    if media_trial != trial:
        proof['source'] += [file_ref(media_trial/name) for name in ('effective.json','result.json','events.jsonl','native-tools.jsonl')]
        proof['recovery'] = {'producer_trial': str(trial), 'media_trial': str(media_trial),
                             'scope': 'same_project_recovery_not_another_independent_example',
                             'same_effective_input_fields': list(same)}
    candidates = [candidate for row in json.loads((extraction/'artifact.json').read_text())
                  for candidate in row['candidates']]
    reports = []
    for candidate in candidates:
        witness = candidate['witness']
        if (witness.get('source_task_mode') != 'normal_execution' or
                witness['task_id'] != effective['task_id'] or len(witness['input_paths']) != 2):
            continue
        producer = next(row for row in rows if row['call_id'] == witness['call_id'])
        before = json.loads(Path(producer['boundary']['path']).read_text())
        after = json.loads(Path(producer['after_boundary']['path']).read_text())
        config = Path(witness['input_paths']['0'])
        metadata = Path(witness['input_paths']['1'])
        if file_ref(metadata)['sha256'] != effective['media_array_metadata_sha256']:
            continue
        options = json.loads(config.read_text()).get('output_options', {})
        generated = Path(witness['original_output'])
        manifest = generated/options.get('manifest_name', 'solution.json')
        concat = generated/options.get('concat_name', 'concat.txt')
        report = evaluate(config, manifest, metadata, concat)
        report.update(program_id=candidate['id'], source_sha256=candidate['source_sha256'])
        reports.append(report)
        if not report['passed']:
            continue
        # Bind the final project delivery to the exact generated bytes.
        if file_ref(delivery/'solution.json')['sha256'] != file_ref(manifest)['sha256']:
            report.update(passed=False, reason='delivered_manifest_not_actual_program_output')
            continue
        movie_virtual = posixpath.normpath('/workspace/output/'+delivery_relative+'/solution.mp4')
        json_virtual = posixpath.normpath('/workspace/output/'+delivery_relative+'/solution.json')
        consumption = None
        for row in (media_rows if media_trial != trial else rows[rows.index(producer)+1:]):
            if row['result']['returncode'] != 0:
                continue
            capture = json.loads(Path(row['boundary']['path']).read_text())
            if capture['before']['complete'] is not True:
                continue
            for pieces in media_chains(row['arguments']['command']):
                render = next((p for p in pieces if p and p[0] == 'ffmpeg' and '-i' in p
                               and p[-1] == movie_virtual), None)
                if not render:
                    continue
                concat_virtual = render[render.index('-i')+1]
                if not concat_virtual.startswith('/workspace/program/outputs/'):
                    continue
                manifest_virtual = posixpath.join(posixpath.dirname(concat_virtual), manifest.name)
                copy = next((p for p in pieces if p == ['cp', manifest_virtual, json_virtual]), None)
                key = 'outputs/code/'+concat_virtual.removeprefix('/workspace/program/outputs/')
                manifest_key = posixpath.join(posixpath.dirname(key), manifest.name)
                files = capture['before']['files']
                # Recovery may use a new fresh directory, but must consume the
                # identical plans from identical current inputs and source.
                if (copy and pieces.index(render) < pieces.index(copy)
                        and files.get(key, {}).get('sha256') == file_ref(concat)['sha256']
                        and files.get(manifest_key, {}).get('sha256') == file_ref(manifest)['sha256']
                        and files.get('code/instance.json', {}).get('sha256') == file_ref(config)['sha256']
                        and files.get('inputs/media-records.json', {}).get('sha256') == file_ref(metadata)['sha256']
                        and any(value.get('sha256') == candidate['source_sha256']
                                for name,value in files.items() if name.startswith('code/') and name.endswith('.py'))):
                    for name in (key, manifest_key, 'code/instance.json', 'inputs/media-records.json'):
                        if file_ref(files[name]['path']) != files[name]:
                            raise ValueError('consumed_plan_boundary_bytes_changed')
                    consumption = row
                    break
            if consumption:
                break
        if consumption is None:
            report.update(passed=False, reason='actual_generated_plan_media_consumption_not_witnessed')
            continue
        worker = output/'generic-frame-check.py'
        worker.write_text(frame_worker(checker, str(Path('/workspace/output')/delivery_relative)))
        if frozen_frame_worker:
            if worker.read_bytes() != Path(frozen_frame_worker).read_bytes():
                raise ValueError('frozen_frame_quality_worker_changed')
            proof['frozen_frame_worker'] = file_ref(frozen_frame_worker)
        command = ['docker','run','--rm','--network','none','--cpus','2','--memory','4g',
                   '-v',str(media_trial/'media-workspace')+':/workspace:ro',
                   '-v',str(worker)+':/check.py:ro',effective['image_id'],'python3','/check.py']
        frames = subprocess.run(command, text=True, capture_output=True)
        (output/'frame-worker.stderr').write_text(frames.stderr)
        frames.check_returncode()
        frame_result = json.loads(frames.stdout)
        frame_path = output/'frame-quality.json';frame_path.write_text(json.dumps(frame_result, indent=2)+'\n')
        proof.update(program_id=candidate['id'], source_sha256=candidate['source_sha256'],
                     producer_call_id=producer['call_id'], media_call_id=consumption['call_id'],
                     plan_inputs=report['inputs'], frame_quality=frame_result,
                     frame_evidence=file_ref(frame_path), generic_worker=file_ref(worker),
                     generic_checker_source=file_ref(checker),
                     delivered={name:file_ref(delivery/name) for name in ('solution.json','solution.mp4')},
                     input_sha256=witness['input_sha256'],
                     boundary_evidence=[producer['boundary'],producer['after_boundary'],consumption['boundary'],consumption['after_boundary']],
                     passed=frame_result['passed'])
        break
    proof['plans'] = reports
    (output/'qualification.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('trial','extraction','checker','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--delivery-relative', default='.')
    parser.add_argument('--media-trial', type=Path)
    parser.add_argument('--frozen-frame-worker', type=Path)
    args = parser.parse_args()
    print(json.dumps(qualify(args.trial, args.extraction, args.checker, args.output, args.delivery_relative, args.media_trial, args.frozen_frame_worker), indent=2))
