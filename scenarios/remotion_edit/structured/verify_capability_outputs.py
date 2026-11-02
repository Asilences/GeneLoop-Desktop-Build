"""Independent, frozen mechanical checks for the Source capability pilot.

No candidate code is imported. Read-only containers probe/decode actual outputs;
selected pixels are compared to the frozen original media. This is not human
review of typography, editing aesthetics, or general semantic quality.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from fractions import Fraction
from PIL import Image, ImageChops, ImageStat


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def selected_videos(result, specification):
    expected = specification['outputs']
    if not any('result_path' in spec for spec in expected):
        return (result or {}).get('videos', [])
    videos = []
    for index, spec in enumerate(expected):
        path = spec.get('result_path', ['videos', index])
        if not isinstance(path, list) or not path:
            raise ValueError('validator_result_path_invalid')
        value = result
        for key in path:
            if isinstance(key, str) and key not in ('__proto__', 'prototype', 'constructor') and isinstance(value, dict):
                value = value.get(key)
            elif type(key) is int and key >= 0 and isinstance(value, list):
                value = value[key] if key < len(value) else None
            else:
                raise ValueError('validator_result_path_invalid')
        if not isinstance(value, dict) or 'video_path' not in value:
            raise ValueError('validator_video_result_missing')
        videos.append(value)
    return videos


def verify(manifest, trace, specification, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    workspace = Path(manifest['workspace']).resolve(strict=True)
    runtime = Path(manifest['runtime_directory']).resolve(strict=True)
    media = Path(manifest['media_tools_directory']).resolve(strict=True)
    ffmpeg = media/'node_modules/@ffmpeg-installer/linux-x64/ffmpeg'
    inputs = {item['name']: item for item in manifest['inputs']}
    checks = []
    def check(name, condition, observation):
        checks.append({'id': name, 'status': 'passed' if condition else 'failed',
                       'observation': str(observation)})
    check('execution', trace.get('status') == 'succeeded', trace.get('status'))
    videos = selected_videos(trace.get('result'), specification)
    expected = specification['outputs']
    check('output_count', len(videos) == len(expected) and len(expected) > 0, len(videos))
    seen = set()
    for index, (video, spec) in enumerate(zip(videos, expected)):
        prefix = f'video_{index}'
        path = Path(video['video_path']).resolve(strict=True)
        if not path.is_relative_to(workspace) or path in seen:
            raise ValueError('validator_output_scope_or_duplicate')
        seen.add(path)
        check(prefix+'_sha', sha(path) == video['video_sha256'], sha(path))
        relative = '/work/' + str(path.relative_to(workspace))
        def container(program, args):
            executable = '/runtime/node_modules/@remotion/compositor-linux-x64-gnu/ffprobe' if program == 'ffprobe' else '/tools/node_modules/@ffmpeg-installer/linux-x64/ffmpeg'
            return subprocess.run(['docker','run','--rm','--user',f'{os.getuid()}:{os.getgid()}',
                '--network','none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
                '--memory=2g','--cpus=2','--tmpfs','/tmp','--entrypoint',executable,
                '-v',f'{runtime}:/runtime:ro','-v',f'{media}:/tools:ro','-v',f'{workspace}:/work:ro',
                manifest['image'],*args],capture_output=True,text=True,timeout=180)
        probe = container('ffprobe',['-v','error','-count_frames','-show_streams','-show_format','-of','json',relative])
        if probe.returncode:
            raise ValueError('validator_probe_failed')
        metadata = json.loads(probe.stdout)
        stream = next(item for item in metadata['streams'] if item['codec_type'] == 'video')
        for key in ('width','height'):
            check(prefix+'_'+key, stream[key] == spec[key], stream[key])
        check(prefix+'_fps', Fraction(stream['r_frame_rate']) == spec['fps'], stream['r_frame_rate'])
        check(prefix+'_frames', int(stream.get('nb_read_frames',0)) == spec['frames'], stream.get('nb_read_frames'))
        decoded = container('ffmpeg',['-v','error','-xerror','-i',relative,'-map','0:v:0','-c:v','libx264','-preset','ultrafast','-f','null','-'])
        check(prefix+'_decode', decoded.returncode == 0, decoded.returncode)
        def frame(source, seconds, target, fit=False, size=None):
            args = [str(ffmpeg),'-v','error','-y','-ss',str(seconds),'-i',str(source)]
            if fit:
                width,height=size or (spec['width'],spec['height'])
                args += ['-vf',f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"]
            args += ['-frames:v','1',str(target)]
            result = subprocess.run(args,capture_output=True,timeout=60)
            if result.returncode or not target.is_file():
                raise ValueError('validator_frame_failed')
            return Image.open(target).convert('RGB')
        samples = spec['source_samples']
        check(prefix+'_samples_present', bool(samples), len(samples))
        for j, sample in enumerate(samples):
            source = inputs[sample['source']]
            source_path = Path(source['path']).resolve(strict=True)
            if sha(source_path) != source['sha256']:
                raise ValueError('validator_input_changed')
            actual = frame(path,sample['output_seconds'],output/f'{index}-{j}-actual.png')
            if 'box' in sample:
                x0,y0,x1,y1=sample['box']
                if not (0 <= x0 < x1 <= spec['width'] and 0 <= y0 < y1 <= spec['height']):raise ValueError('validator_box_invalid')
                actual=actual.crop((x0,y0,x1,y1))
            reference = frame(source_path,sample['source_seconds'],output/f'{index}-{j}-expected.png',True,actual.size)
            box = tuple(round(v * actual.size[n%2]) for n,v in enumerate(sample['roi']))
            mae = sum(ImageStat.Stat(ImageChops.difference(actual.crop(box),reference.crop(box))).mean)/3
            check(prefix+f'_source_{j}',mae <= spec['pixel_mae_max'],f'pixel_mae={mae:.6f}')
        check(prefix+'_sha_after',sha(path) == video['video_sha256'],sha(path))
    result = {'passed':bool(checks) and all(c['status']=='passed' for c in checks),'checks':checks,
              'scope':'dimensions_fps_frames_full_decode_and_selected_source_pixels',
              'limitations':['No human or typography review','Not an efficiency comparison']}
    (output/'verification.json').write_text(json.dumps(result,indent=2))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    for name in ('manifest','trace','specification','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    paths={'manifest':args.manifest,'trace':args.trace,'specification':args.specification}
    frozen={name:path.read_bytes() for name,path in paths.items()}
    result=verify(*(json.loads(frozen[name]) for name in ('manifest','trace','specification')),args.output)
    if any(path.read_bytes()!=frozen[name] for name,path in paths.items()):raise ValueError('validator_evidence_changed')
    result['evidence_binding']={name+'_sha256':hashlib.sha256(raw).hexdigest() for name,raw in frozen.items()}
    (args.output/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 2)
