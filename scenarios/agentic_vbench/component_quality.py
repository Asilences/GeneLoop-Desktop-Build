"""Independent configured-manifest checks; no storyboard labels or program code."""
import hashlib
import json
import math
from pathlib import Path

SCOPE='configured_full_clip_manifest_v1'


def evaluate(config_path, manifest_path, metadata_path):
    paths=[Path(p) for p in (config_path,manifest_path,metadata_path)]
    def ref(p):
        return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    result={'scope':SCOPE,'passed':False,'storyboard_quality':'not_evaluated',
            'evaluator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def require(value,reason):
        if not value:raise ValueError(reason)
    def number(x):
        require(type(x) in (int,float) and math.isfinite(x),'finite_numbers_required')
        return x
    def source(x):
        return str(x).removesuffix('.mp4')
    try:
        require(all(p.is_file() and not p.is_symlink() for p in paths),'regular_current_files_required')
        result['inputs']={k:ref(p) for k,p in zip(('configuration','manifest','media_metadata'),paths)}
        cfg,manifest,metadata=[json.loads(p.read_text()) for p in paths]
        clips,segments=cfg['clips'],manifest['segments']
        require(isinstance(clips,list) and len(clips)>0,'nonempty_current_clip_plan_required')
        require(isinstance(segments,list) and len(segments)==len(clips),'one_segment_per_current_clip')
        previous=0.0;durations=[]
        for clip,segment in zip(clips,segments):
            name=source(clip['source']);media=metadata[name+'.mp4']
            duration=number(clip['duration']);require(duration>0,'positive_duration_required')
            stream=next(s for s in media['streams'] if s['codec_type']=='video')
            actual=float(stream.get('duration',media['duration_seconds']))
            require(abs(duration-actual)<=1e-5,'current_duration_differs_from_actual_video')
            require(source(segment['source'])==name,'current_clip_order_mismatch')
            out,src=segment['output'],segment['source_range']
            require(isinstance(out,list) and len(out)==2 and isinstance(src,list) and len(src)==2,'two_endpoint_intervals_required')
            start,end=map(number,out);begin,finish=map(number,src)
            require(end>start and abs(start-previous)<=2e-6,'output_gap_overlap_or_nonpositive_interval')
            require(abs(begin)<=1e-6 and abs(finish-duration)<=2e-6,'full_current_source_range_required')
            require(abs((end-start)-duration)<=2e-6,'output_duration_mismatch')
            previous=end;durations.append(duration)
        require(abs(previous-math.fsum(durations))<=2e-6,'total_duration_mismatch')
        result.update(passed=True,segment_count=len(segments),total_duration_seconds=previous,
            checks=['current_sources_and_order','measured_full_clip_durations','contiguous_positive_intervals','complete_source_ranges','total_duration'])
    except (ValueError,TypeError,KeyError,StopIteration,OSError) as error:
        result['reason']=str(error) or type(error).__name__
    return result
