import json

import pytest

from scenarios.agentic_vbench.plan_quality import evaluate
from scenarios.agentic_vbench.plan_evaluation import frame_worker, media_chains, qualify, HELPERS, CONSTANTS


def check(tmp_path, fault=None):
    cfg = {'clips': [{'source': '8'}, {'source': '3'}], 'output_options': {}}
    rows = [{'name': f'{i}.mp4', 'path': f'/workspace/materials/{i}.mp4',
             'video_duration_seconds': d, 'container_duration_seconds': d + .1,
             'streams': [{'codec_type': 'video', 'duration': str(d)}]}
            for i, d in ((3, 2.5), (8, 1.25))]
    manifest = {'segments': [{'source': '8', 'output': [0, 1.25], 'source_range': [0, 1.25]},
                             {'source': '3', 'output': [1.25, 3.75], 'source_range': [0, 2.5]}]}
    concat = "file '/workspace/materials/8.mp4'\nduration 1.25\nfile '/workspace/materials/3.mp4'\nduration 2.5\n"
    if fault == 'container_clock':
        concat = concat.replace('duration 1.25', 'duration 1.35')
    if fault == 'no_clock':
        concat = '\n'.join(line for line in concat.splitlines() if not line.startswith('duration'))
    if fault == 'order':
        concat = concat.replace('/8.mp4', '/3.mp4')
    if fault == 'copied_measurement':
        cfg['clips'][0]['duration'] = 1.25
    if fault == 'range':
        manifest['segments'][1]['source_range'][1] = 2.4
    paths = [tmp_path / name for name in ('config.json', 'solution.json', 'records.json', 'concat.txt')]
    for path, value in zip(paths, (cfg, manifest, rows, concat)):
        path.write_text(value if isinstance(value, str) else json.dumps(value))
    return evaluate(*paths)


def test_same_video_clock_even_when_container_has_padding(tmp_path):
    result = check(tmp_path)
    assert result['passed'] is True
    assert result['storyboard_quality'] == 'not_evaluated'


@pytest.mark.parametrize('fault', ['container_clock', 'no_clock', 'order', 'copied_measurement', 'range'])
def test_rejects_real_plan_failures(tmp_path, fault):
    assert check(tmp_path, fault)['passed'] is False


def test_frame_projection_never_executes_checker_or_expected_order(tmp_path):
    checker = tmp_path/'judge.py'
    checker.write_text("raise RuntimeError('top-level oracle must not execute')\nEXPECTED_ORDER=[99]\n"
                       + '\n'.join(f'{name}=3' for name in CONSTANTS)
                       + '\n' + '\n'.join(f'def {name}(*args):\n    return None' for name in HELPERS)
                       + "\ndef score():\n    return EXPECTED_ORDER\n")
    worker = frame_worker(checker, '/workspace/output')
    assert 'EXPECTED_ORDER' not in worker
    assert 'def score' not in worker
    assert 'top-level oracle' not in worker
    assert "Path('/workspace/output')" in worker


def test_consumption_audit_expands_only_literal_paths_without_executing_shell(tmp_path):
    command = "set -euo pipefail\nPLAN=/workspace/program/outputs/current\nffmpeg -i \"$PLAN/concat.txt\" /workspace/output/solution.mp4 && cp \"$PLAN/solution.json\" /workspace/output/solution.json\n"
    chains = list(media_chains(command))
    assert chains[-1][0][2] == '/workspace/program/outputs/current/concat.txt'
    assert chains[-1][1][1] == '/workspace/program/outputs/current/solution.json'
    assert list(media_chains('PLAN=$(touch /tmp/not-executed)\nffmpeg -i "$PLAN/concat.txt" x')) == []
    assert list(media_chains('ffmpeg -i "$UNKNOWN/concat.txt" x')) == []


@pytest.mark.parametrize('fault', ['different_materials', 'successor'])
def test_recovery_cannot_admit_other_materials_or_successor(tmp_path, fault):
    source, media, extraction = [tmp_path/name for name in ('source','media','extraction')]
    for path in (source, media, extraction):
        path.mkdir()
    effect = {'role':'certification', 'task_id':'canonical-held-task',
              'evaluation_scope':'configured_full_clip_plan_v1', 'inputs_sha256':{'1.mp4':'original'}}
    if fault == 'successor':
        effect['role'] = 'successor'
    (source/'effective.json').write_text(json.dumps(effect))
    (source/'result.json').write_text(json.dumps({'status':'completed'}))
    (extraction/'summary.json').write_text(json.dumps({'role':effect['role'],'task_id':effect['task_id']}))
    effect = {**effect, 'inputs_sha256':{'1.mp4':'different'}}
    (media/'effective.json').write_text(json.dumps(effect))
    (media/'result.json').write_text(json.dumps({'status':'completed'}))
    with pytest.raises(ValueError):
        qualify(source, extraction, tmp_path/'unused-judge.py', tmp_path/'must-not-qualify', media_trial=media)
    assert not (tmp_path/'must-not-qualify').exists()
