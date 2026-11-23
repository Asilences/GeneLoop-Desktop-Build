import copy
import json

from scenarios.agentic_vbench.trial import media_array_view
from src.adapters.artifact_motif_compiler import file_contract


def test_media_view_preserves_current_measurements_and_actual_names():
    metadata = {name: {'path': '/workspace/materials/'+name,
        'video_duration_seconds': duration, 'streams': [{'codec_type': 'video', 'time_base': '1/12800'}]}
        for name, duration in [('10.mp4', 1.4), ('2.mp4', 3.2), ('1.mp4', 2.0)]}
    original = copy.deepcopy(metadata)
    rows = media_array_view(metadata)
    assert [row['name'] for row in rows] == ['1.mp4', '2.mp4', '10.mp4']
    assert {row['name']: {key: value for key, value in row.items() if key != 'name'}
        for row in rows} == original
    assert metadata == original


def test_array_view_avoids_binding_candidate_names_or_count_without_changing_original_contract(tmp_path):
    def contract(name, value):
        path = tmp_path/name
        path.write_text(json.dumps(value))
        return file_contract(path)
    first = {'1.mp4': {'path': '/workspace/materials/1.mp4', 'video_duration_seconds': 2.0},
        '2.mp4': {'path': '/workspace/materials/2.mp4', 'video_duration_seconds': 3.0}}
    changed = {'9.mp4': {'path': '/workspace/materials/9.mp4', 'video_duration_seconds': 4.0}}
    assert contract('map-first.json', first) != contract('map-changed.json', changed)
    assert contract('rows-first.json', media_array_view(first)) == contract('rows-changed.json', media_array_view(changed))
