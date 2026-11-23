from argparse import Namespace
import json

import pytest
from scenarios.agentic_vbench.learning import parameterize


@pytest.mark.parametrize('role,scope',[('successor','configured_full_clip_manifest_v1'),
    ('development','official_video_task')])
def test_parameter_learning_rejects_successor_or_unqualified_video_before_loading_runtime(tmp_path,role,scope):
    source=tmp_path/'extracted';source.mkdir()
    trial=tmp_path/'trial';trial.mkdir()
    (source/'summary.json').write_text(json.dumps({'role':role,'component_learning_eligible':True,'task_id':'actual-task'}))
    (trial/'effective.json').write_text(json.dumps({'role':role,'evaluation_scope':scope,'task_id':'actual-task'}))
    (trial/'result.json').write_text(json.dumps({'status':'completed','component_evaluation':{'passed':True}}))
    args=Namespace(source=source,trial=trial,runtime=tmp_path/'missing-runtime')
    with pytest.raises(ValueError,match='qualified_normal_component_source_required_not_successor'):
        parameterize(args)
