"""Independent data-plan checks. No program generation or storyboard answers.

This scope requires an explicit video clock in both generated artifacts. It
does not certify an arbitrary ffmpeg command, audio fidelity or clip selection.
"""
import hashlib
import json
import math
from pathlib import Path
import shlex

SCOPE = 'configured_full_clip_plan_v1'


def file_ref(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def evaluate(configuration, manifest, records, concat):
    result = {'scope': SCOPE, 'passed': False, 'storyboard_quality': 'not_evaluated',
              'evaluator_sha256': file_ref(__file__)['sha256']}

    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    def number(value):
        require(type(value) in (int, float) and math.isfinite(value), 'finite_number_required')
        return value

    try:
        paths = list(map(Path, (configuration, manifest, records, concat)))
        require(all(p.is_file() and not p.is_symlink() for p in paths), 'regular_files_required')
        result['inputs'] = dict(zip(('configuration', 'manifest', 'media_records', 'concat'),
                                    map(file_ref, paths)))
        cfg, output, measured = [json.loads(p.read_text()) for p in paths[:3]]
        require(set(cfg) <= {'clips', 'output_options'}, 'choices_and_output_options_only')
        require(isinstance(measured, list), 'measured_record_array_required')
        by_id = {Path(r['name']).stem: r for r in measured}
        require(len(by_id) == len(measured), 'unique_measured_sources_required')
        choices, segments = cfg['clips'], output['segments']
        require(isinstance(choices, list) and len(choices) > 0, 'nonempty_choices_required')
        require(len(segments) == len(choices), 'one_segment_per_choice_required')
        lines = [shlex.split(line, comments=True) for line in paths[3].read_text().splitlines()]
        lines = [line for line in lines if line]
        if lines and lines[0] == ['ffconcat', 'version', '1.0']:
            lines = lines[1:]
        require(len(lines) == 2 * len(choices), 'file_and_video_duration_per_clip_required')
        cursor, durations = 0.0, []
        for index, (choice, segment) in enumerate(zip(choices, segments)):
            require(set(choice) == {'source'}, 'current_choices_must_not_copy_measurements')
            source = str(choice['source']).removesuffix('.mp4')
            media = by_id[source]
            duration = number(media['video_duration_seconds'])
            require(duration > 0, 'positive_video_duration_required')
            stream = next(s for s in media['streams'] if s['codec_type'] == 'video')
            require(abs(float(stream['duration']) - duration) <= 1e-6, 'video_measurement_disagrees')
            require(str(segment['source']).removesuffix('.mp4') == source, 'current_order_mismatch')
            out, src = segment['output'], segment['source_range']
            require(len(out) == len(src) == 2, 'two_endpoint_ranges_required')
            start, end, begin, finish = map(number, (*out, *src))
            require(end > start and abs(start - cursor) <= 2e-6, 'output_gap_or_overlap')
            require(abs(begin) <= 1e-6 and abs(finish - duration) <= 2e-6, 'full_source_range_required')
            require(abs(end - start - duration) <= 2e-6, 'output_duration_mismatch')
            require(lines[2 * index] == ['file', media['path']], 'concat_source_order_or_path_mismatch')
            timing = lines[2 * index + 1]
            require(len(timing) == 2 and timing[0] == 'duration', 'explicit_concat_video_clock_required')
            value = float(timing[1])
            require(math.isfinite(value) and abs(value - duration) <= 1e-6, 'concat_video_duration_mismatch')
            cursor = end
            durations.append(duration)
        require(abs(cursor - math.fsum(durations)) <= 2e-6, 'total_video_duration_mismatch')
        result.update(passed=True, segment_count=len(choices), total_duration_seconds=cursor,
                      checks=['current_choices_only', 'measured_video_clock', 'complete_source_ranges',
                              'contiguous_manifest', 'same_concat_order_paths_and_video_clock'])
    except (ValueError, TypeError, KeyError, IndexError, StopIteration, OSError) as error:
        result['reason'] = str(error) or type(error).__name__
    return result
